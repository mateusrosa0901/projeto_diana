"""
Mapa de Polos x Alunos
-----------------------
App para analisar, a partir de uma cidade de referência, quais cidades estão
num raio de 100km, cruzando com:
  - polos cadastrados, com status
  - localidades prioritárias para abertura
  - alunos cadastrados (apenas a contagem por cidade)

As três bases vêm das planilhas do Google Sheets mantidas pelo setor
(ver dados.py e .streamlit/secrets.toml.example). Os dados são recarregados
automaticamente a cada `ttl_minutos` (padrão: 10 min).

Para rodar:
    pip install -r requirements.txt
    streamlit run app.py
"""

import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

import dados

st.set_page_config(page_title="Mapa de Polos x Alunos", layout="wide")

# Cores/ícones por status do polo (cobre variações comuns de grafia)
STATUS_STYLE = {
    "inserido": {"color": "green", "icon": "building", "label": "Ativo (Inserido)"},
    "inativo": {"color": "lightgray", "icon": "building", "label": "Inativo"},
    "distrato": {"color": "red", "icon": "ban", "label": "Distrato"},
    "não realizado": {"color": "gray", "icon": "question", "label": "Não realizado"},
    "sem status": {"color": "gray", "icon": "question", "label": "Sem status"},
}
STATUS_PADRAO = {"color": "gray", "icon": "question", "label": "Sem status"}


def status_style(status):
    return STATUS_STYLE.get(str(status).strip().lower(), STATUS_PADRAO)


def haversine(lat1, lon1, lat2, lon2):
    """Distância em km entre dois pontos (graus decimais)."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------------------
# Carregamento (cacheado; recarrega sozinho a cada ttl_minutos)
# ---------------------------------------------------------------------------
try:
    bases = dados.carregar_bases()
except Exception as erro:  # permissão, planilha/aba/coluna não encontrada etc.
    st.error("Não foi possível carregar as bases de dados.")
    st.exception(erro)
    st.info(
        "Confira no secrets.toml: o ID de cada planilha, o nome da aba e das "
        "colunas, e se cada planilha foi compartilhada (como Leitor) com o "
        "e-mail da conta de serviço (campo `client_email`)."
    )
    st.stop()

municipios = bases["municipios"].copy()
alunos_por_cidade = bases["alunos_por_cidade"]
polos = bases["polos"].copy()
localidades = bases["localidades"]

# ---------------------------------------------------------------------------
# Filtro por status do polo (aplica tanto no mapa quanto nas tabelas)
# ---------------------------------------------------------------------------
st.sidebar.header("⚙️ Filtros")
status_disponiveis = sorted(polos["status"].unique())
st.sidebar.markdown("**🏷️ Status dos polos a exibir**")
status_selecionados = st.sidebar.multiselect(
    "Status", options=status_disponiveis, default=status_disponiveis
)
polos = polos[polos["status"].isin(status_selecionados)].copy()
st.sidebar.caption(f"{len(polos)} polo(s) cadastrado(s) (após filtro de status).")

st.sidebar.divider()
st.sidebar.markdown("**🔄 Dados**")
st.sidebar.caption(
    f"Fonte: {bases['origem']}  \n"
    f"Carregados às {bases['atualizado_em']:%H:%M} de {bases['atualizado_em']:%d/%m/%Y}"
)
if st.sidebar.button("Recarregar agora"):
    dados.carregar_bases.clear()
    st.rerun()

conferir = {k: v for k, v in bases["falhas"].items() if not v.empty}
if conferir:
    with st.sidebar.expander("⚠️ Cidades para conferir nas planilhas"):
        st.caption(
            "Nomes que não foram reconhecidos (❌ ficam fora da análise) ou que "
            "foram reconhecidos por aproximação. Corrija na planilha ou "
            "cadastre um apelido em referencia/aliases.csv."
        )
        for nome_base, tabela in conferir.items():
            st.markdown(f"**{nome_base}**")
            st.dataframe(tabela, hide_index=True)

# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
st.title("📍 Mapa de Polos x Alunos")
st.caption(
    "Informe uma cidade de referência e o app calcula as cidades num raio de "
    "100km, verifica polos cadastrados (com status), cidades prioritárias "
    "para abertura e quantos alunos existem na região."
)

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    cidade_input = st.text_input("Cidade de referência", placeholder="Ex: Nova Viçosa")
with col2:
    ufs_disponiveis = sorted(municipios["uf"].dropna().unique())
    uf_input = st.selectbox("UF", options=[""] + ufs_disponiveis)
with col3:
    raio_km = st.number_input("Raio (km)", min_value=1, value=100, step=10)

buscar_clicado = st.button("Analisar", type="primary")

# guarda o estado da busca em session_state: o componente de mapa (st_folium)
# dispara uma nova execução da página ao carregar/interagir, e nessa execução
# seguinte o st.button volta a ser False — sem isso, mapa e tabelas sumiriam
# quase na hora.
if buscar_clicado:
    st.session_state["busca_ativa"] = True
    st.session_state["cidade_busca"] = cidade_input
    st.session_state["uf_busca"] = uf_input
    st.session_state["raio_busca"] = raio_km

if st.session_state.get("busca_ativa"):
    cidade_input = st.session_state["cidade_busca"]
    uf_input = st.session_state["uf_busca"]
    raio_km = st.session_state["raio_busca"]

    if not cidade_input or not uf_input:
        st.warning("Informe a cidade e a UF.")
        st.stop()

    ref = municipios[
        (municipios["nome"].str.strip().str.lower() == cidade_input.strip().lower())
        & (municipios["uf"] == uf_input)
    ]

    if ref.empty:
        # tenta um match aproximado para ajudar o usuário
        candidatos = municipios[
            municipios["nome"].str.contains(cidade_input.strip(), case=False, na=False)
        ]
        st.error(f"Cidade '{cidade_input} - {uf_input}' não encontrada.")
        if not candidatos.empty:
            st.write("Você quis dizer:")
            st.dataframe(candidatos[["nome", "uf"]].head(10), hide_index=True)
        st.stop()

    lat_ref = ref.iloc[0]["latitude"]
    lon_ref = ref.iloc[0]["longitude"]
    nome_ref = ref.iloc[0]["nome"]

    # =========================================================================
    # 1) CÁLCULOS (tudo primeiro, para depois montar o mapa + as tabelas)
    # =========================================================================
    municipios["dist_km"] = haversine(
        lat_ref, lon_ref, municipios["latitude"], municipios["longitude"]
    )
    raio_df = municipios[municipios["dist_km"] <= raio_km].sort_values("dist_km").copy()

    polos["dist_km"] = haversine(lat_ref, lon_ref, polos["latitude"], polos["longitude"])
    polo_propria = polos[
        (polos["municipio_ibge"] == nome_ref) & (polos["uf"] == uf_input)
    ]
    prioritaria_propria = (
        (localidades["municipio_ibge"] == nome_ref)
        & (localidades["uf"] == uf_input)
    ).any()

    polos_raio = polos[polos["dist_km"] <= raio_km].sort_values("dist_km")

    chaves_prioritarias = pd.MultiIndex.from_frame(localidades[["municipio_ibge", "uf"]])
    raio_df["prioritaria"] = pd.MultiIndex.from_frame(raio_df[["nome", "uf"]]).isin(
        chaves_prioritarias
    )
    prioritarias = raio_df[raio_df["prioritaria"]]

    contagem = (
        alunos_por_cidade.drop(columns=["latitude", "longitude"])
        .merge(
            raio_df[["nome", "uf", "latitude", "longitude", "dist_km"]],
            left_on=["municipio_ibge", "uf"],
            right_on=["nome", "uf"],
            how="inner",
        )
        .drop(columns="nome")
        .sort_values("qtd_alunos", ascending=False)
    )
    total_alunos_raio = int(contagem["qtd_alunos"].sum())
    linha_propria = alunos_por_cidade[
        (alunos_por_cidade["municipio_ibge"] == nome_ref)
        & (alunos_por_cidade["uf"] == uf_input)
    ]
    alunos_propria = int(linha_propria["qtd_alunos"].sum())

    # =========================================================================
    # 2) RESUMO DA PRÓPRIA CIDADE PESQUISADA
    # =========================================================================
    st.markdown(f"### 📌 A própria cidade pesquisada: {nome_ref} - {uf_input}")
    col_a, col_b = st.columns(2)
    with col_a:
        if polo_propria.empty:
            st.info("Nenhum polo cadastrado na própria cidade (com os status selecionados).")
        else:
            ativos = (polo_propria["status"].str.lower() == "inserido").sum()
            st.success(
                f"{len(polo_propria)} polo(s) cadastrado(s) na própria cidade "
                f"({ativos} ativo(s))."
            )
            st.dataframe(
                polo_propria[["cidade_original", "bairro", "status"]].rename(
                    columns={"cidade_original": "Cidade", "bairro": "Bairro", "status": "Status"}
                ),
                hide_index=True,
            )
    with col_b:
        if prioritaria_propria:
            st.success("✅ A própria cidade é uma localidade prioritária para abertura.")
        else:
            st.info("A própria cidade não está na lista de prioridades.")

    # =========================================================================
    # 3) MAPA INTERATIVO
    # =========================================================================
    st.markdown("### 🗺️ Mapa")
    st.caption(
        "🔵 cidade pesquisada · ⭕ raio · ⭐ prioritária p/ abertura · "
        "🔴 alunos cadastrados (tamanho = quantidade)  \n"
        "**Polos por status:** 🟢 Inserido (ativo) · ⚪ Inativo · 🔴 Distrato · ⚫ Não realizado/Sem status"
    )

    mapa = folium.Map(location=[lat_ref, lon_ref], zoom_start=7, tiles="OpenStreetMap")

    # cidade pesquisada
    folium.Marker(
        location=[lat_ref, lon_ref],
        popup=f"<b>{nome_ref} - {uf_input}</b> (cidade pesquisada)",
        tooltip=nome_ref,
        icon=folium.Icon(color="blue", icon="star", prefix="fa"),
    ).add_to(mapa)

    # círculo do raio
    folium.Circle(
        location=[lat_ref, lon_ref],
        radius=raio_km * 1000,  # metros
        color="#3186cc",
        fill=True,
        fill_opacity=0.06,
        weight=1.5,
    ).add_to(mapa)

    # polos (no raio + na própria cidade, sem duplicar), coloridos por status
    polos_no_mapa = pd.concat([polo_propria, polos_raio]).drop_duplicates()
    for _, p in polos_no_mapa.iterrows():
        estilo = status_style(p.get("status"))
        folium.Marker(
            location=[p["latitude"], p["longitude"]],
            popup=(
                f"<b>Polo:</b> {p['cidade_original']}"
                f"{' - ' + p['bairro'] if p['bairro'] else ''}<br>"
                f"<b>Status:</b> {estilo['label']}<br>{p['dist_km']:.1f} km"
            ),
            tooltip=f"Polo ({estilo['label']}): {p['cidade_original']}",
            icon=folium.Icon(color=estilo["color"], icon=estilo["icon"], prefix="fa"),
        ).add_to(mapa)

    # cidades prioritárias no raio
    for _, c in prioritarias.iterrows():
        folium.Marker(
            location=[c["latitude"], c["longitude"]],
            popup=f"<b>Prioritária:</b> {c['nome']} - {c['uf']}<br>{c['dist_km']:.1f} km",
            tooltip=f"Prioritária: {c['nome']}",
            icon=folium.Icon(color="orange", icon="star", prefix="fa"),
        ).add_to(mapa)

    # cidades com alunos no raio (tamanho do círculo proporcional à quantidade)
    if not contagem.empty:
        max_alunos = contagem["qtd_alunos"].max()
        for _, a in contagem.iterrows():
            raio_px = 6 + 18 * (a["qtd_alunos"] / max_alunos)
            folium.CircleMarker(
                location=[a["latitude"], a["longitude"]],
                radius=raio_px,
                color="#d62728",
                fill=True,
                fill_opacity=0.5,
                weight=1,
                popup=f"<b>{a['municipio_ibge']}</b><br>{int(a['qtd_alunos'])} aluno(s)",
                tooltip=f"{a['municipio_ibge']}: {int(a['qtd_alunos'])} aluno(s)",
            ).add_to(mapa)

    st_folium(mapa, use_container_width=True, height=520, key="mapa_polos")

    # =========================================================================
    # 4) TABELAS DETALHADAS
    # =========================================================================
    st.subheader(f"Cidades em raio de {raio_km}km de {nome_ref} - {uf_input}")
    st.write(f"**{len(raio_df)} cidades** encontradas.")

    st.markdown("### 🏢 Polos nas cidades vizinhas (raio)")
    if polos_raio.empty:
        st.info("Nenhum polo cadastrado dentro do raio (com os status selecionados).")
    else:
        st.dataframe(
            polos_raio[["cidade_original", "bairro", "uf", "status", "dist_km"]].rename(
                columns={
                    "cidade_original": "Cidade",
                    "bairro": "Bairro",
                    "uf": "UF",
                    "status": "Status",
                    "dist_km": "Distância (km)",
                }
            ),
            hide_index=True,
        )

    # ---------------- localidades prioritárias no raio ----------------
    st.markdown("### ⭐ Cidades vizinhas prioritárias para abertura (raio)")
    if prioritarias.empty:
        st.info("Nenhuma cidade prioritária encontrada no raio.")
    else:
        st.success(f"{len(prioritarias)} cidade(s) prioritária(s) encontrada(s):")
        st.dataframe(
            prioritarias[["nome", "uf", "dist_km"]].rename(
                columns={"nome": "Cidade", "uf": "UF", "dist_km": "Distância (km)"}
            ),
            hide_index=True,
        )

    # ---------------- alunos no raio (sempre mostrado) ----------------
    st.markdown("### 🎓 Alunos cadastrados nas cidades do raio")
    st.write(f"**Total: {total_alunos_raio} alunos** no raio.")
    if not contagem.empty:
        st.dataframe(
            contagem[["municipio_ibge", "uf", "dist_km", "qtd_alunos"]].rename(
                columns={
                    "municipio_ibge": "Cidade",
                    "uf": "UF",
                    "dist_km": "Distância (km)",
                    "qtd_alunos": "Qtd. Alunos",
                }
            ),
            hide_index=True,
        )

    st.caption(f"Alunos na própria {nome_ref}: {alunos_propria}")
