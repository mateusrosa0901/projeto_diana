# Mapa de Polos x Alunos

App em [Streamlit](https://streamlit.io) que, a partir de uma cidade de
referência, encontra todas as cidades dentro de um raio (padrão: 100 km) e
cruza essa região com as bases do setor:

1. **Polos** cadastrados na própria cidade e nas vizinhas, com status
2. **Cidades prioritárias** para abertura de polo dentro do raio
3. **Quantidade de alunos** em cada cidade do raio
4. Um **mapa interativo** com tudo isso (zoom e clique nos marcadores para ver detalhes)

As bases de alunos, polos e localidades prioritárias são lidas **direto das
planilhas do Google Sheets** mantidas pelo setor. Quando alguém atualiza uma
planilha, o app passa a mostrar os dados novos sozinho, sem precisar mexer no
código ou no repositório.

---

## Como usar

1. Digite a **cidade de referência** e escolha a **UF**.
2. Ajuste o **raio (km)**, se quiser.
3. Clique em **Analisar**.

Na barra lateral dá para filtrar os **status dos polos** exibidos (vale para o
mapa e para as tabelas). Ali também aparecem o horário da última leitura das
planilhas e o botão **Recarregar agora**.

Se a cidade digitada não for encontrada, o app sugere nomes parecidos.

### Legenda do mapa

| Símbolo | Significado |
|---|---|
| 🔵 estrela azul | Cidade pesquisada |
| ⭕ círculo azul claro | Raio definido |
| 🟢 prédio verde | Polo com status **Inserido** (ativo) |
| ⚪ prédio cinza claro | Polo **Inativo** |
| 🔴 ícone vermelho | Polo com **Distrato** |
| ⚫ ícone cinza | Polo **Não realizado**, sem status ou com outro status |
| 🟠 estrela laranja | Cidade prioritária para abertura |
| 🔴 círculo vermelho | Cidade com alunos (tamanho proporcional à quantidade) |

---

### Reconhecimento das cidades

Nas planilhas, a cidade está escrita "do jeito que foi digitada". O
`dados.py` converte esse texto no município oficial do IBGE para obter as
coordenadas:

- Acentos, maiúsculas, hífens, apóstrofos e textos entre parênteses são
  ignorados. Assim, `"Betim (Filadélfia) - Mg"` vira Betim/MG.
- A UF pode vir como sigla (`MG`), por extenso (`Minas Gerais`) ou junto da
  cidade (`Contagem - MG`, `Contagem/MG`).
- Em seguida, o texto é procurado em `referencia/aliases.csv`, que guarda
  correções manuais. Exemplo: `Campo Grande, RJ` → Rio de Janeiro, porque é um
  bairro do Rio e não o município de MS.
- Por último, pequenos erros de digitação são tolerados, mas **só dentro da
  mesma UF**. Exemplo: `Itacoatira` → Itacoatiara.
- Qualquer valor de UF `DF` vira Brasília, que é o único município do DF.

Linhas cuja cidade não é reconhecida **ficam fora da análise**. Elas aparecem
na barra lateral em **"⚠️ Cidades para conferir nas planilhas"**, junto com as
que foram reconhecidas por aproximação. Para corrigir um caso, há dois
caminhos:

- ajustar o texto na própria planilha; ou
- adicionar uma linha em `referencia/aliases.csv`:

```csv
cidade_digitada,uf,municipio_ibge
Campo Grande,RJ,Rio de Janeiro
Pinheiros,SP,São Paulo
```

---

## Estrutura do repositório

```
├── app.py                          # interface: busca, cálculos, tabelas e mapa
├── dados.py                        # leitura das planilhas e reconhecimento das cidades
├── referencia/                     # dados públicos versionados
│   ├── municipios.csv
│   ├── estados.csv
│   └── aliases.csv
├── .streamlit/
│   └── secrets.toml.example        # modelo de configuração (sem valores reais)
├── .devcontainer/                  # ambiente pronto para GitHub Codespaces
├── requirements.txt
└── LICENSE
```

Arquivos que **nunca** devem ir para o GitHub (já estão no `.gitignore`):
`.streamlit/secrets.toml`, a pasta `credentials/` e a pasta `data/`.

---

## Configuração (feita uma vez)

### 1. Google Cloud

1. No [Google Cloud Console](https://console.cloud.google.com), crie ou
   escolha um projeto.
2. Em **APIs e serviços → Biblioteca**, ative **as duas** APIs:
   - **Google Sheets API**
   - **Google Drive API**

   > Sem elas o app falha com `PermissionError`. Depois de ativar, pode levar
   > alguns minutos para funcionar.
3. Em **IAM e administrador → Contas de serviço**, crie uma conta de serviço.
4. Na conta criada, vá em **Chaves → Adicionar chave → JSON** e baixe o
   arquivo. Ele contém a chave privada, então guarde-o fora do repositório.

### 2. Compartilhar as planilhas

Compartilhe **cada uma** das três planilhas com o e-mail da conta de serviço
(o `client_email` do JSON, algo como `nome@projeto.iam.gserviceaccount.com`)
com permissão de **Leitor**.

As bases precisam ser **Planilhas Google** nativas. Um `.xlsx` guardado no
Drive não funciona. Se o setor tiver um arquivo Excel, use
*Arquivo → Salvar como Planilhas Google*. Isso cria um **arquivo novo, com
outro ID**, e ele precisa ser compartilhado de novo com a conta de serviço.

### 3. Criar o `secrets.toml`

Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e
preencha as três seções abaixo.

**`[google_service_account]`**: copie os campos do JSON baixado no passo 1.

**`[fontes]`**: onde está cada planilha e como se chamam as colunas.

| Chave | Obrigatória | Descrição |
|---|---|---|
| `ttl_minutos` | não | Intervalo, em minutos, entre as releituras das planilhas (padrão 10). Uma mudança aqui só vale depois de reiniciar o app. |
| `sheet_id` | sim* | ID da planilha: o trecho da URL entre `/d/` e `/edit`. |
| `titulo` | sim* | Alternativa ao `sheet_id`: nome do arquivo dentro da pasta `[google_drive] FOLDER_ID`. |
| `aba` | não | Nome da aba. Se ficar vazio, o app lê a primeira aba. |
| `linha_cabecalho` | não | Linha onde estão os nomes das colunas (padrão 1). |
| `col_cidade` | sim | Nome da coluna com a cidade. |
| `col_uf` | não | Nome da coluna com a UF. Deixe vazio se a UF vier junto da cidade. |
| `col_status` | não (polos) | Coluna com o status do polo. |
| `col_bairro` | não (polos) | Coluna com o bairro do polo. |

\* Informe `sheet_id` **ou** `titulo`.

Os nomes de coluna são comparados sem diferenciar maiúsculas, acentos e
espaços nas pontas. Por isso `"cidade"` encontra a coluna `Cidade`.

Exemplo de configuração:

```toml
[fontes]
ttl_minutos = 10

[fontes.alunos]
sheet_id = "ID_DA_PLANILHA_DE_ALUNOS"
aba = "Agosto"
col_cidade = "cidade"
col_uf = "uf"

[fontes.polos]
sheet_id = "ID_DA_PLANILHA_DE_POLOS"
aba = "Polos"
col_cidade = "Cidade"
col_uf = "UF"
col_status = "Cadastros (Pincel e Gestor)"
col_bairro = "Bairro"

[fontes.localidades]
sheet_id = "ID_DA_PLANILHA_DE_LOCALIDADES"
aba = "Página1"
col_cidade = "Cidade"
col_uf = "UF"
```

**`[google_drive]`**: opcional. `FOLDER_ID` só é usado quando alguma fonte usa
`titulo` no lugar de `sheet_id`.

> ⚠️ O app lê **somente** a aba informada em `aba`. Se o setor criar uma aba
> nova por mês, atualize esse valor, ou deixe `aba` vazio e mantenha a aba
> vigente como a primeira da planilha.

---

## Rodando localmente

Pré-requisito: [Python 3.9+](https://www.python.org/downloads/).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Mac/Linux

pip install -r requirements.txt
streamlit run app.py
```

O app abre no navegador, normalmente em `http://localhost:8501`.

> Depois de alterar o `secrets.toml`, pare o app (Ctrl+C) e rode de novo.

### Modo local (sem Google)

Sem a seção `[fontes]` no `secrets.toml`, o app entra em **modo local** e lê
CSVs da pasta `data/`, que é ignorada pelo git. Serve para testar sem acesso
às planilhas. A barra lateral indica a fonte em uso.

| Arquivo | Colunas usadas |
|---|---|
| `data/alunos.csv` | `municipio_ibge`, `uf` |
| `data/polos.csv` | `cidade_original`, `uf_original`, `status`, `bairro` |
| `data/localidades_prioritarias.csv` | `municipio_ibge`, `uf` |

---

## Deploy no Streamlit Community Cloud

1. Em [share.streamlit.io](https://share.streamlit.io), crie um app apontando
   para este repositório, branch `main`, arquivo `app.py`.
2. Em **Settings → Secrets**, cole o conteúdo completo do seu `secrets.toml`.
3. Salve. Sempre que alterar os secrets, use **Reboot app**.

O repositório também tem um `.devcontainer`, que permite abrir e rodar o
projeto no **GitHub Codespaces** sem instalar nada. No Codespaces o
`secrets.toml` também precisa ser criado, porque ele não vem do repositório.

---

## Solução de problemas

| Erro / sintoma | Causa provável | O que fazer |
|---|---|---|
| `PermissionError` ao abrir a planilha | API desativada, planilha não compartilhada ou ID errado | Confira se as APIs **Sheets** e **Drive** estão ativas, se a planilha foi compartilhada com o `client_email` e se o `sheet_id` é o da planilha (não de uma pasta ou de um `.xlsx`). |
| `SpreadsheetNotFound` | ID ou título incorreto | Copie o ID de novo a partir da URL da planilha. |
| `WorksheetNotFound` | O nome em `aba` não existe | Confira o nome exato da aba, inclusive acentos, por exemplo `Página1`. |
| `Coluna 'X' não encontrada` | Coluna renomeada na planilha | A mensagem lista as colunas disponíveis. Atualize `col_*` no secrets. |
| Dados novos não aparecem | Cache ainda válido | Clique em **Recarregar agora** ou aguarde `ttl_minutos`. |
| Cidade fora da análise | Nome não reconhecido | Veja "⚠️ Cidades para conferir" e corrija a planilha ou o `aliases.csv`. |

---

## Observações

- A distância é calculada em linha reta (fórmula de Haversine) a partir do
  **centro do município**, e não do endereço exato do aluno ou do polo nem
  pela rota de estrada.
- O código é público, mas os dados não estão no repositório. Ainda assim, **o
  app publicado mostra polos e contagens de alunos para quem tiver o link**.
  Se isso for sensível, restrinja o acesso ao app.

## Licença

[MIT](LICENSE)
