# Mapa de Polos x Alunos

App simples (Streamlit) que replica a análise que fizemos no chat: dado uma
cidade de referência, calcula as cidades num raio de 100km (baseado no centro
do município, dados do IBGE), e mostra:

1. Polos já ativos na região
2. Cidades prioritárias para abertura de polo, dentro do raio
3. Quantidade de alunos cadastrados em cada cidade do raio
4. Um **mapa interativo** com tudo isso plotado (zoom, clique nos marcadores
   para ver detalhes)

### Legenda do mapa

| Símbolo | Significado |
|---|---|
| 🔵 estrela azul | Cidade pesquisada |
| ⭕ círculo azul claro | Raio definido |
| 🟢 prédio verde | Polo ativo |
| 🟠 estrela laranja | Cidade prioritária para abertura |
| 🔴 círculo vermelho | Cidade com alunos cadastrados (tamanho proporcional à quantidade) |


## Como instalar

Pré-requisito: [Python 3.9+](https://www.python.org/downloads/) instalado.

1. Baixe/extraia esta pasta no seu computador.
2. Abra um terminal (cmd, PowerShell ou terminal do Mac/Linux) dentro dela.
3. (Opcional, mas recomendado) crie um ambiente virtual:
   ```
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # Mac/Linux
   ```
4. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

## Como rodar

```
streamlit run app.py
```

Isso abre automaticamente uma aba no seu navegador (geralmente em
`http://localhost:8501`) com a interface: você digita a cidade, escolhe a UF,
ajusta o raio se quiser, e clica em "Analisar".

## Estrutura de dados (pasta `data/`)

| Arquivo | Conteúdo |
|---|---|
| `municipios.csv` | Nome, UF e coordenadas (lat/lon) de todos os municípios do Brasil (fonte: IBGE, via repositório público [kelvins/Municipios-Brasileiros](https://github.com/kelvins/Municipios-Brasileiros)) |
| `estados.csv` | Código e sigla de cada UF |
| `alunos.csv` | Alunos já cruzados com o município oficial e coordenadas (nome, municipio_ibge, uf, latitude, longitude) |
| `polos.csv` | Polos ativos já cruzados com o município oficial e coordenadas |
| `localidades_prioritarias.csv` | Lista atual de cidades prioritárias para abertura, já cruzada com coordenadas |

## Atualizando as bases

Se você tiver uma base de alunos, polos ou localidades prioritárias mais
recente, é só gerar um CSV novo no mesmo formato (colunas
`municipio_ibge`/`uf`/`latitude`/`longitude`, além dos campos que quiser
manter) e substituir o arquivo correspondente em `data/`. Se preferir, me
envie a planilha bruta aqui no chat que eu já devolvo ela limpa e
geocodificada nesse formato.

## Observações importantes

- A distância é calculada do **centro do município** (não do endereço exato
  do aluno/polo), pela fórmula de Haversine (linha reta, não rota de estrada).
- Cidades cujo nome/UF não bateram com a base do IBGE (poucas exceções, ex.
  cidades no exterior ou campo em branco) não entram na análise — no total
  isso afetou ~3,4% da base de alunos original.
