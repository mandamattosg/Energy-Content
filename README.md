# Energy Radar

Coleta semanal de notícias do setor elétrico brasileiro (portais especializados, imprensa geral, ANEEL/ONS/EPE/CCEE/MME, Reddit e Google Trends), filtra duplicadas, classifica e ranqueia, gera um resumo com o Gemini e envia para um bot do Telegram.

```
coleta ─► janela de 7 dias ─► classificação (setor + categoria) ─► dedup (inclusive semanas anteriores)
       ─► ranking (top 40) ─► Gemini (ranking de importância) ─► Telegram ─► Postgres
```

## Estrutura

```
content_radar/
├── collectors/   news.py · energy_sources.py · reddit.py · google_trends.py
├── processing/   deduplication.py · classification.py · ranking.py
├── llm/          gemini.py · weekly_summary.py · prompts/weekly_summary.md
├── outputs/      telegram.py (fase 1) · teams.py (fase 2, stub)
├── db/           models.py · repository.py · session.py
├── config/       settings.py · sources.yaml (fontes, palavras-chave, categorias, pesos)
└── pipeline.py
main.py           entrypoint do cron (roda uma vez e sai)
```

Para ajustar fontes, termos ou categorias, edite só `content_radar/config/sources.yaml`.

## Como funciona

- **Feeds gerais** (G1, Folha, Estadão, InfoMoney, Agência Brasil, Valor, CNN) marcados com `general: true` só deixam passar itens com termos do setor.
- **Órgãos oficiais** não têm RSS público acessível; são buscados via Google News com `site:` e exibidos com o nome do órgão.
- **Dedup**: por URL, hash de conteúdo e títulos quase iguais (≥ 85% de similaridade). A mesma notícia em vários veículos vira um só sinal com `duplicates_count`, o que aumenta o score. Itens já gravados no banco (semanas anteriores) são descartados.
- **Ranking**: o score heurístico só escolhe os 40 sinais que vão para o LLM; a ordem final do "Ranking da semana" é do Gemini.
- **Fontes**: o Gemini só devolve ids (`s1`, `s2`...); o código converte em veículo + link. Item sem correspondência direta sai sem fonte, nunca com link inventado. Mostra até 3 fontes por item, com os órgãos oficiais primeiro.
- **Transação única**: se o Gemini ou o Telegram falharem, nada é marcado como visto e os mesmos sinais voltam na próxima execução. A falha fica registrada em `weekly_runs`.

## Rodar localmente

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # preencher GEMINI_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DATABASE_URL
alembic upgrade head
```

```powershell
python main.py --skip-llm   # só coleta/classifica e imprime o ranking (não grava nada)
python main.py --dry-run    # gera o resumo com o Gemini e imprime a mensagem (não envia nem grava)
python main.py              # execução real
pytest
```

Sem Postgres local, dá para testar com SQLite: `DATABASE_URL=sqlite:///energy_radar.db`.

## Bot do Telegram (novo)

1. No Telegram, fale com `@BotFather` → `/newbot` → copie o token para `TELEGRAM_TOKEN`.
2. Mande qualquer mensagem para o bot novo e abra `https://api.telegram.org/bot<TOKEN>/getUpdates`; o `chat.id` é o `TELEGRAM_CHAT_ID`.
   Para enviar num grupo, adicione o bot ao grupo e use o id do grupo (começa com `-`).

## Deploy no Railway (cron semanal)

1. Crie um projeto no Railway e adicione um serviço **PostgreSQL**.
2. Adicione um serviço a partir deste repositório. O `railway.json` já define:
   - `cronSchedule: "0 11 * * 1"` → toda segunda às 08:00 de Brasília (o cron do Railway é em UTC);
   - `startCommand: alembic upgrade head && python main.py`;
   - `restartPolicyType: NEVER` (o processo termina ao fim da execução).
3. Variáveis do serviço:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (o código converte `postgresql://` para o driver psycopg)
   - `GEMINI_API_KEY`, `GEMINI_MODEL_NAME` (padrão `gemini-3.8-flash`)
   - `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`
4. Para testar, rode o job manualmente pelo painel e confira os logs e a tabela `weekly_runs`.

## Fase 2: Microsoft Teams

`outputs/teams.py` já implementa a mesma interface `Output` (só falta o envio). O caminho previsto é um webhook do Teams Workflows ("Post to a channel when a webhook request is received") recebendo um Adaptive Card.
