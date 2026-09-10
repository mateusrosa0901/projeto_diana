"""
Carregamento e preparação das bases do app.

De onde vem cada coisa:
  - referencia/municipios.csv e referencia/estados.csv -> dados PÚBLICOS do IBGE,
    ficam no repositório.
  - alunos, polos e localidades prioritárias -> lidos direto das planilhas do
    Google Sheets mantidas pelo setor (via conta de serviço). Nada disso vai
    para o GitHub.

As planilhas têm o nome da cidade "do jeito que foi digitado". Aqui a gente
casa esse nome com o município oficial do IBGE (sem acento, sem maiúscula,
tolerando pequenos erros de digitação) para obter latitude/longitude.

Se o st.secrets não tiver a seção [fontes], o app cai no modo LOCAL e lê os
CSVs da pasta data/ (que está no .gitignore) — útil para desenvolver offline.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).parent
REF_DIR = BASE_DIR / "referencia"
DATA_DIR = BASE_DIR / "data"  # só para modo local / desenvolvimento

# Somente leitura: o app nunca escreve nas planilhas.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Configuração usada no modo LOCAL (CSVs antigos da pasta data/).
# No modo Google Sheets, isso vem de [fontes.*] no secrets.toml.
FONTES_LOCAIS = {
    "alunos": {"arquivo": "alunos.csv", "col_cidade": "municipio_ibge", "col_uf": "uf"},
    "polos": {
        "arquivo": "polos.csv",
        "col_cidade": "cidade_original",
        "col_uf": "uf_original",
        "col_status": "status",
        "col_bairro": "bairro",
    },
    "localidades": {
        "arquivo": "localidades_prioritarias.csv",
        "col_cidade": "municipio_ibge",
        "col_uf": "uf",
    },
}

STOPWORDS = {"de", "da", "do", "das", "dos", "d", "e"}


# ---------------------------------------------------------------------------
# Normalização de texto
# ---------------------------------------------------------------------------
def normalizar(txt) -> str:
    """'Santa Bárbara d'Oeste ' -> 'santa barbara d oeste'."""
    if txt is None or (isinstance(txt, float) and pd.isna(txt)):
        return ""
    s = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return s.strip()


def sem_stopwords(chave: str) -> str:
    return " ".join(p for p in chave.split() if p not in STOPWORDS)


# ---------------------------------------------------------------------------
# Bases de referência (públicas, IBGE)
# ---------------------------------------------------------------------------
def carregar_referencias():
    municipios = pd.read_csv(REF_DIR / "municipios.csv")
    estados = pd.read_csv(REF_DIR / "estados.csv")
    municipios = municipios.merge(estados[["codigo_uf", "uf"]], on="codigo_uf", how="left")

    aliases_path = REF_DIR / "aliases.csv"
    aliases = (
        pd.read_csv(aliases_path, dtype=str).fillna("")
        if aliases_path.exists()
        else pd.DataFrame(columns=["cidade_digitada", "uf", "municipio_ibge"])
    )
    return municipios, estados, aliases


class Geocodificador:
    """Casa (cidade digitada, UF digitada) -> município oficial do IBGE."""

    def __init__(self, municipios: pd.DataFrame, estados: pd.DataFrame, aliases: pd.DataFrame,
                 corte_fuzzy: float = 0.85):
        self.mun = municipios.set_index(["nome", "uf"])
        self.corte = corte_fuzzy

        # UF por sigla ou por nome por extenso ("minas gerais" -> "MG")
        self.uf_por_nome = {normalizar(n): u for n, u in zip(estados["nome"], estados["uf"])}
        self.ufs = set(estados["uf"])

        self.exato: dict[tuple[str, str], str] = {}
        self.sem_sw: dict[tuple[str, str], list[str]] = {}
        self.por_uf: dict[str, dict[str, str]] = {}
        self.nacional: dict[str, list[tuple[str, str]]] = {}
        for nome, uf in zip(municipios["nome"], municipios["uf"]):
            k = normalizar(nome)
            self.exato[(k, uf)] = nome
            self.sem_sw.setdefault((sem_stopwords(k), uf), []).append(nome)
            self.por_uf.setdefault(uf, {})[k] = nome
            self.nacional.setdefault(k, []).append((nome, uf))

        self.alias = {
            (normalizar(a.cidade_digitada), a.uf.strip().upper()): a.municipio_ibge
            for a in aliases.itertuples()
        }

    def uf(self, valor) -> str | None:
        s = normalizar(valor)
        if len(s) == 2 and s.upper() in self.ufs:
            return s.upper()
        return self.uf_por_nome.get(s)

    def separar_cidade_uf(self, cidade) -> tuple[str, str | None]:
        """'Contagem - MG', 'Contagem/MG', 'Contagem (MG)' -> ('Contagem', 'MG')."""
        m = re.match(r"^\s*(.*?)\s*[-/,(]\s*([A-Za-z]{2})\s*\)?\s*$", str(cidade or ""))
        if m and m.group(2).upper() in self.ufs:
            return m.group(1), m.group(2).upper()
        return str(cidade or ""), None

    def _variantes(self, texto: str) -> list[str]:
        """'Betim (Filadélfia) - Mg' -> ['Betim']; 'Campo Grande -Tabaí' -> [..., 'Campo Grande']."""
        t = re.sub(r"\([^)]*\)?", " ", texto)  # tira "(bairro)", inclusive sem fechar
        t = re.sub(r"\s+", " ", t).strip()
        out = [t]
        for sep in (" - ", "-", "/", ","):
            if sep in t:
                out.append(t.split(sep)[0].strip())
        return [v for i, v in enumerate(out) if v and v not in out[:i]]

    def _tentar(self, k: str, uf: str):
        if (k, uf) in self.alias:
            return self.alias[(k, uf)], "apelido"
        if (k, uf) in self.exato:
            return self.exato[(k, uf)], "exato"
        cands = self.sem_sw.get((sem_stopwords(k), uf), [])
        if len(cands) == 1:
            return cands[0], "exato"
        return None

    def resolver(self, cidade, uf_bruta) -> tuple[str, str, str] | None:
        """Retorna (municipio_ibge, uf, metodo) ou None.
        metodo: exato | apelido | aproximado | prefixo."""
        texto = str(cidade or "").strip()
        uf = self.uf(uf_bruta)
        if not normalizar(texto):
            return None

        # apelido cadastrado para o texto completo (ex.: 'Taguatinga Sul' / DF)
        if uf and (normalizar(texto), uf) in self.alias:
            return self.alias[(normalizar(texto), uf)], uf, "apelido"

        base, uf_no_texto = self.separar_cidade_uf(texto)          # 'Contagem (MG)'
        base = re.sub(r"\([^)]*\)?", " ", base)                   # tira '(bairro)'
        if not uf_no_texto:
            base, uf_no_texto = self.separar_cidade_uf(base)       # 'Boa Vista/Rr (...)'
        uf = uf or uf_no_texto
        variantes = self._variantes(base)

        if uf is None:
            # sem UF: só aceita se o nome for único no Brasil
            for v in variantes:
                cands = self.nacional.get(normalizar(v), [])
                if len(cands) == 1:
                    return cands[0][0], cands[0][1], "exato"
            return None

        if uf == "DF":  # o DF tem um único município
            return "Brasília", "DF", "exato"

        for v in variantes:
            r = self._tentar(normalizar(v), uf)
            if r:
                return r[0], uf, r[1]

        # erro de digitação: nome mais parecido DENTRO da mesma UF
        nomes_uf = self.por_uf.get(uf, {})
        for v in variantes:
            parecido = difflib.get_close_matches(normalizar(v), list(nomes_uf), n=1,
                                                 cutoff=self.corte)
            if parecido:
                return nomes_uf[parecido[0]], uf, "aproximado"

        # 'Ipatinga Transitório' -> 'Ipatinga' (maior início que seja um município)
        for v in variantes:
            palavras = normalizar(v).split()
            for n in range(len(palavras) - 1, 0, -1):
                r = self._tentar(" ".join(palavras[:n]), uf)
                if r:
                    return r[0], uf, "prefixo"
        return None

    def aplicar(self, df: pd.DataFrame, col_cidade: str, col_uf: str | None):
        """Adiciona municipio_ibge/uf/latitude/longitude.
        Retorna (linhas_ok, tabela_para_conferir)."""
        df = df.copy()
        df["_cidade"] = df[col_cidade].fillna("").astype(str).str.strip()
        df["_uf"] = df[col_uf].fillna("").astype(str).str.strip() if col_uf else ""

        pares = df[["_cidade", "_uf"]].drop_duplicates()
        resolvidos = {
            (c, u): self.resolver(c, u) for c, u in zip(pares["_cidade"], pares["_uf"])
        }
        res = [resolvidos[(c, u)] for c, u in zip(df["_cidade"], df["_uf"])]
        df["municipio_ibge"] = [r[0] if r else None for r in res]
        df["uf"] = [r[1] if r else None for r in res]
        df["_metodo"] = [r[2] if r else None for r in res]

        ok = df[df["municipio_ibge"].notna()].drop(
            columns=["latitude", "longitude"], errors="ignore"
        )
        coords = self.mun[["latitude", "longitude"]]
        ok = ok.join(coords, on=["municipio_ibge", "uf"])

        # relatório para o setor corrigir a planilha: o que não casou e o que
        # casou "no chute" (aproximado/prefixo), para conferência
        df["_resultado"] = df["municipio_ibge"].fillna("❌ não encontrado")
        conferir = (
            df[df["_metodo"].isna() | df["_metodo"].isin(["aproximado", "prefixo"])]
            .assign(_cidade=lambda d: d["_cidade"].replace("", "(em branco)"))
            .groupby(["_cidade", "_uf", "_resultado"], dropna=False).size()
            .reset_index(name="linhas")
            .rename(columns={"_cidade": "Na planilha", "_uf": "UF na planilha",
                             "_resultado": "Entendido como"})
            .sort_values(["Entendido como", "linhas"], ascending=[True, False])
        )
        return ok.drop(columns=["_cidade", "_uf", "_metodo"]), conferir


# ---------------------------------------------------------------------------
# Busca de município para o campo com autocomplete (app.py)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def indice_municipios() -> list[tuple[str, tuple[str, ...], str, str]]:
    """Lista (nome_normalizado, palavras, nome_oficial, uf) de todos os municípios."""
    municipios, _, _ = carregar_referencias()
    indice = []
    for nome, uf in zip(municipios["nome"], municipios["uf"]):
        chave = normalizar(nome)
        indice.append((chave, tuple(chave.split()), nome, uf))
    return indice


def _palavras_batem(termos: list[str], palavras: tuple[str, ...]) -> bool:
    """Cada termo digitado precisa ser o início de alguma palavra do nome.
    Ex.: 'jose campos' bate com 'sao jose dos campos'."""
    return all(any(p.startswith(t) for p in palavras) for t in termos)


def buscar_municipios(termo: str, limite: int = 15) -> list[tuple[str, tuple[str, str]]]:
    """Sugestões para o autocomplete: [('Nova Viçosa - BA', ('Nova Viçosa', 'BA')), ...].

    - ignora acentos e maiúsculas ('sao mateus' acha 'São Mateus');
    - aceita pedaços de palavras em qualquer ordem ('jose campos');
    - aceita a UF no fim ('bom jesus pi', 'contagem - mg');
    - quem começa com o texto digitado aparece primeiro.
    """
    alvo = normalizar(termo)
    if len(alvo) < 2:
        return []
    termos = alvo.split()
    indice = indice_municipios()
    ufs = {uf for *_, uf in indice}

    # último pedaço com 2 letras pode ser UF ('pa') ou início de palavra ('pa' de
    # 'Paulo'): aceitamos as duas leituras
    uf_digitada = termos[-1].upper() if len(termos) > 1 and termos[-1].upper() in ufs else None
    alvo_sem_uf = " ".join(termos[:-1]) if uf_digitada else alvo

    achados = []
    for chave, palavras, nome, uf in indice:
        if _palavras_batem(termos, palavras):
            base = alvo
        elif uf_digitada == uf and _palavras_batem(termos[:-1], palavras):
            base = alvo_sem_uf
        else:
            continue
        if chave == base:
            ordem = 0  # nome exato
        elif chave.startswith(base):
            ordem = 1  # começa com o que foi digitado
        else:
            ordem = 2  # bate só por pedaços de palavras
        achados.append((ordem, chave, uf, nome))

    achados.sort()
    return [(f"{nome} - {uf}", (nome, uf)) for _, _, uf, nome in achados[:limite]]


# ---------------------------------------------------------------------------
# Leitura das fontes (Google Sheets ou CSV local)
# ---------------------------------------------------------------------------
def usando_google_sheets() -> bool:
    try:
        return "fontes" in st.secrets and "google_service_account" in st.secrets
    except Exception:  # sem secrets.toml nenhum
        return False


@st.cache_resource(show_spinner=False)
def _cliente_gspread():
    import gspread

    info = dict(st.secrets["google_service_account"])
    return gspread.service_account_from_dict(info, scopes=SCOPES)


def _cabecalhos_unicos(cab: list[str]) -> list[str]:
    vistos: dict[str, int] = {}
    saida = []
    for i, c in enumerate(cab):
        c = str(c).strip() or f"coluna_{i + 1}"
        if c in vistos:
            vistos[c] += 1
            c = f"{c}_{vistos[c]}"
        else:
            vistos[c] = 0
        saida.append(c)
    return saida


def _ler_planilha(cfg) -> pd.DataFrame:
    gc = _cliente_gspread()
    if cfg.get("sheet_id"):
        planilha = gc.open_by_key(cfg["sheet_id"])
    else:
        pasta = st.secrets.get("google_drive", {}).get("FOLDER_ID")
        planilha = gc.open(cfg["titulo"], folder_id=pasta)

    aba = planilha.worksheet(cfg["aba"]) if cfg.get("aba") else planilha.get_worksheet(0)
    valores = aba.get_all_values()
    linha_cab = int(cfg.get("linha_cabecalho", 1))
    if len(valores) < linha_cab:
        return pd.DataFrame()
    cab = _cabecalhos_unicos(valores[linha_cab - 1])
    return pd.DataFrame(valores[linha_cab:], columns=cab)


def _coluna(df: pd.DataFrame, nome: str | None, base: str, obrigatoria=True) -> str | None:
    """Acha a coluna ignorando acento/maiúscula/espaço. Erro claro se não achar."""
    if not nome:
        return None
    alvo = normalizar(nome)
    for c in df.columns:
        if normalizar(c) == alvo:
            return c
    if obrigatoria:
        raise KeyError(
            f"Coluna '{nome}' não encontrada na base '{base}'. "
            f"Colunas disponíveis: {', '.join(map(str, df.columns))}"
        )
    return None


def _ler_fonte(nome_base: str):
    if usando_google_sheets():
        cfg = dict(st.secrets["fontes"][nome_base])
        bruto = _ler_planilha(cfg)
    else:
        cfg = FONTES_LOCAIS[nome_base]
        bruto = pd.read_csv(DATA_DIR / cfg["arquivo"], dtype=str)

    col_cidade = _coluna(bruto, cfg["col_cidade"], nome_base)
    col_uf = _coluna(bruto, cfg.get("col_uf"), nome_base)
    extras = {
        k: _coluna(bruto, cfg.get(k), nome_base, obrigatoria=False)
        for k in ("col_status", "col_bairro")
    }
    # Mantém SÓ as colunas necessárias (nome de aluno etc. é descartado aqui)
    manter = [c for c in [col_cidade, col_uf, *extras.values()] if c]
    return bruto[manter].copy(), col_cidade, col_uf, extras


# ---------------------------------------------------------------------------
# Função principal, com cache
# ---------------------------------------------------------------------------
def _ttl_segundos() -> int:
    try:
        return int(st.secrets["fontes"].get("ttl_minutos", 10)) * 60
    except Exception:
        return 10 * 60


@st.cache_data(ttl=_ttl_segundos(), show_spinner="Carregando dados das planilhas...")
def carregar_bases() -> dict:
    municipios, estados, aliases = carregar_referencias()
    geo = Geocodificador(municipios, estados, aliases)
    falhas = {}

    # --- Alunos: agregamos por cidade na hora; nenhum dado pessoal fica em memória
    bruto, c_cid, c_uf, _ = _ler_fonte("alunos")
    total_alunos_planilha = len(bruto)
    alunos_ok, falhas["Alunos"] = geo.aplicar(bruto, c_cid, c_uf)
    alunos_por_cidade = (
        alunos_ok.groupby(["municipio_ibge", "uf", "latitude", "longitude"])
        .size()
        .reset_index(name="qtd_alunos")
    )

    # --- Polos
    bruto, c_cid, c_uf, extras = _ler_fonte("polos")
    polos, falhas["Polos"] = geo.aplicar(bruto, c_cid, c_uf)
    polos["cidade_original"] = polos[c_cid]
    polos["bairro"] = polos[extras["col_bairro"]] if extras["col_bairro"] else ""
    polos["status"] = polos[extras["col_status"]] if extras["col_status"] else "Sem status"
    polos["bairro"] = polos["bairro"].fillna("").replace({"nan": ""})
    polos["status"] = (
        polos["status"].fillna("").astype(str).str.strip().replace({"": "Sem status", "nan": "Sem status"})
    )
    polos = polos[["cidade_original", "bairro", "status", "municipio_ibge", "uf",
                   "latitude", "longitude"]].reset_index(drop=True)

    # --- Localidades prioritárias
    bruto, c_cid, c_uf, _ = _ler_fonte("localidades")
    loc, falhas["Localidades prioritárias"] = geo.aplicar(bruto, c_cid, c_uf)
    localidades = loc[["municipio_ibge", "uf"]].drop_duplicates().reset_index(drop=True)

    return {
        "municipios": municipios,
        "alunos_por_cidade": alunos_por_cidade,
        "total_alunos_planilha": total_alunos_planilha,
        "polos": polos,
        "localidades": localidades,
        "falhas": falhas,
        "origem": "Google Sheets" if usando_google_sheets() else "CSV local (data/)",
        "atualizado_em": datetime.now(ZoneInfo("America/Sao_Paulo")),
    }