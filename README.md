<div align="center">

<!-- ![JobRadar](assets/cover.png) -->

# 📡 JobRadar
### Monitor Automatizado de Vagas de Dados & BI

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Scraping-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Banco%20versionado-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Cron-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)
![Tests](https://img.shields.io/badge/testes-73%20passing-success?style=for-the-badge)
![Status](https://img.shields.io/badge/status-em%20produção-success?style=for-the-badge)

**Autora:** Liliam Kezia Oliveira Souza

</div>

---

> ### ℹ️ Sobre este fork
>
> Este é um **fork** do [JobRadar original](https://github.com/liliamkezia-star/job-radar), da Liliam Kezia — todo o crédito de arquitetura, motor de filtro e engenharia registrada abaixo é dela.
>
> Duas coisas mudam aqui, e só elas:
>
> - **O alvo do radar.** As listas de `core/config.py` foram recalibradas de **Dados/BI** para **vaga de desenvolvedor** (backend / frontend / fullstack). O motor não muda — ele nunca soube de que área é a vaga.
> - **Onde roda.** Em vez do GitHub Actions, roda num container Docker em servidor próprio, em loop contínuo. O workflow `jobradar.yml` fica desabilitado neste fork; o `testes.yml` continua ativo.
>
> Regra de localização deste fork: **só vaga remota, de qualquer país** (`CIDADES = ["Remoto"]`, `MERCADOS_REMOTO_ACEITOS = None`). O texto abaixo descreve o projeto original — onde ele fala em cargos de Dados/BI ou em cidades do Nordeste, vale o que está no `config.py`.

---

## 💎 Proposta de valor

> Em cidade pequena, vaga boa de Dados/BI aparece pouco e some rápido — quem checa o board duas vezes por dia perde pra quem checou na primeira hora. **JobRadar** é um sistema de monitoramento contínuo que substitui essa checagem manual: varre **8 fontes** a cada **3 horas**, filtra por cargo/cidade/mercado/idioma com três níveis de confiança, pontua cada vaga por relevância e notifica no Telegram — rodando de graça, sem servidor próprio, 24 horas por dia.

## 📄 Resumo executivo

Entre 07 e 15 de agosto, o sistema já processou **1.052 vagas únicas**, sem intervenção manual nenhuma — mas os números também expõem os riscos reais da arquitetura atual:

| Achado | Número |
|---|---|
| 📊 Vagas processadas (deduplicadas) | **1.052** |
| 🔗 Concentração numa única fonte (LinkedIn) | **89,5%** |
| 🧪 Testes automatizados (CI a cada push) | **73** |
| 🌎 Fontes monitoradas em paralelo | **8** |
| ⏱️ Frequência de checagem | **a cada 3h** |
| 💰 Custo de infraestrutura | **R$ 0** |

A concentração em LinkedIn é um risco medido, não ignorado: o endpoint usado não é oficial e o próprio código documenta a chance de bloqueio — por isso parte do trabalho recente foi medir o rendimento de cada fonte secundária e paginar mais fundo nelas, em vez de só empilhar fonte nova.

---

## 📸 Como chega pra você

<!-- ![Notificação no Telegram](assets/screenshots/notificacao.png) -->

Vaga de alta relevância chega na hora, com motivo da aprovação, nível e link. O resto do dia entra num resumo único, ranqueado — sem virar spam.

---

## 🗂️ Sumário

- [Como funciona (pipeline)](#-como-funciona-pipeline)
- [Arquitetura técnica](#%EF%B8%8F-arquitetura-técnica)
- [Estrutura do repositório](#-estrutura-do-repositório)
- [Como rodar](#-como-rodar)
- [Testes](#-testes)

---

## 🧭 Como funciona (pipeline)

| Etapa | O que faz |
|---|---|
| **Busca** | Varre as fontes em paralelo, com rodízio de termos pra controlar custo por ciclo |
| **Filtra** | Cargo (forte / ambíguo + qualificador / ferramenta + cargo), cidade ou mercado remoto, idioma |
| **Pontua** | Score 0–10 por vaga: cargo, ferramenta, senioridade, mercado, idioma — soma de sinais, sem IA |
| **Deduplica** | Por link e por empresa+título, pra pegar a mesma vaga republicada em fonte diferente |
| **Notifica** | Alta relevância na hora; o resto num resumo diário ranqueado, melhor vaga no topo |
| **Aprende** | Botão 👍/👎 em cada notificação — feedback vira dado pra medir precisão por fonte e por semana |

## 🏗️ Arquitetura técnica

- **Filtro em 3 níveis de confiança:** cargo inequívoco passa sozinho; cargo ambíguo (ex: "Business Analyst") só conta com qualificador de dados junto no título; ferramenta (ex: "Power BI") só conta com palavra de cargo junto — nada aprova por palavra-chave solta.
- **Score de relevância sem ML:** 5 sinais conhecidos (cargo, ferramenta, senioridade, mercado, idioma), pesos calibrados contra o histórico real do banco, não chutados.
- **Zero infraestrutura:** GitHub Actions como motor de cron, SQLite como banco — versionado no próprio Git, o histórico de vagas já vistas *é* o commit.
- **Resiliente:** nunca marca vaga como "vista" sem confirmar que a notificação saiu; alerta automático se metade das fontes falhar num ciclo; heartbeat diário confirmando que o robô ainda está de pé.
- **73 testes automatizados em CI:** cada caso documenta um bug real já corrigido nesta base — não é cenário hipotético, é regressão registrada.

## 📁 Estrutura do repositório

obradar/
├── README.md
├── requirements.txt
├── main.py ← motor único: um ciclo de busca por perfil
├── perfis.py ← Brasil vs Internacional (dado, não lógica duplicada)
├── config.py / config_intl.py ← cargos, cidades, termos de busca, pesos
├── job.py ← Job, filtro, score de relevância
├── relatorio_precisao.py ← aprovadas/notificadas por fonte e por semana
├── database/
│ └── database.py ← SQLite: dedup, fila de digest, metadados
├── notifier/
│ ├── canal.py ← escolhe Telegram ou webhook pelo .env
│ ├── telegram.py ← notificação individual, digest, botão 👍/👎
│ └── webhook.py ← mesmo contrato, via Discord/Slack
├── scrapers/ ← um módulo por fonte (LinkedIn, Gupy, Indeed...)
├── utils/
│ └── filtro.py
├── tests/ ← 443 casos, roda em CI a cada push
├── data/
│ └── jobs.db ← banco versionado (histórico de dedup)
└── .github/workflows/
├── jobradar.yml ← cron de produção (a cada 3h)
├── linkedin-recomendadas.yml ← cron das vagas recomendadas (a cada 2 dias)
└── testes.yml ← CI

## 💻 Como rodar

```bash
git clone <repo>
cd jobradar
python -m venv venv && venv\Scripts\activate   # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Criar `.env` na raiz com `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` (via [@BotFather](https://t.me/BotFather)), depois:

```bash
python main.py --perfil brasil internacional --once
```

**Alternativa ao Telegram:** preenchendo `NOTIFICADOR_WEBHOOK_URL` no `.env` com uma URL de webhook do Discord ou do Slack, o robô passa a notificar por lá e ignora o Telegram — a plataforma é detectada pela própria URL, sem variável de "modo" separada. Criar o webhook leva dois cliques nas configurações do canal, contra criar um bot no @BotFather e descobrir o `chat_id`. O que se perde são os botões 👍/👎 de feedback, que dependem de bot de verdade (webhook é via de mão única). Rodando no GitHub Actions, a URL precisa entrar como *repository secret*: ela **é** a credencial — quem tem a URL posta no seu canal.

Há ainda o perfil `linkedin`, que lê as **vagas recomendadas** da sua conta do LinkedIn (API privada, exige o cookie `li_at`) e roda num cron próprio, de 2 em 2 dias. É opcional: sem o cookie configurado ele se desliga sozinho. Como configurar, onde pegar os cookies e quais os riscos estão em [`docs/linkedin-recomendadas.md`](docs/linkedin-recomendadas.md).

## 🧪 Testes

```bash
pytest tests/ -v
```

443 casos parametrizados, cobrindo a camada de filtro, o parsing de callback do Telegram, a conversão de markup do webhook e o relatório de precisão — todos rodando automaticamente a cada push via GitHub Actions.

---

<div align="center">

*Case de portfólio em automação de dados — Python, Playwright, SQLite, GitHub Actions e engenharia de filtro sem ML.*

</div>
