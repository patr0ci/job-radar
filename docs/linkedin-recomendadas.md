# LinkedIn Recomendadas

Fonte que lê as **vagas recomendadas** da sua conta do LinkedIn — a lista
que ele monta pra você a partir do seu perfil e do seu histórico, não uma
busca por palavra-chave.

Roda **de 2 em 2 dias**, num workflow separado do ciclo principal, e entrega
as vagas no mesmo formato de todas as outras fontes: passam pelo mesmo
filtro, ganham a mesma pontuação, respeitam a mesma blocklist de empresa e o
mesmo piso de relevância, e caem no mesmo banco com a mesma deduplicação.

---

## ⚠️ Leia isto antes

Esta fonte é diferente de todas as outras do projeto em um ponto que importa:

- As demais leem páginas **públicas** de vagas.
- Esta usa a **API privada do LinkedIn (Voyager)**, autenticada **como
  você**, com o cookie da sua sessão.

Consequências práticas:

| Risco | Por quê |
|---|---|
| **Bloqueio da conta** | O LinkedIn não autoriza esse tipo de acesso. Uso intenso pode restringir ou banir sua conta pessoal. |
| **IP de datacenter** | Rodando no GitHub Actions, sua conta é acessada de um IP de servidor — exatamente o padrão que dispara detecção. Foi assim que o Indeed passou a bloquear o projeto. |
| **O cookie é a conta** | Quem tiver o `li_at` está logado como você. Não é "uma senha a menos": é acesso completo, sem MFA. |

Por isso os limites padrão são conservadores (5 páginas, pausa de ~8s entre
elas, 1 execução a cada 2 dias). **Não aumente sem necessidade.**

Se preferir não correr esse risco, simplesmente **não configure o secret** —
o projeto continua funcionando normalmente sem esta fonte (ela se
autodesliga com um aviso no log).

---

## Os dois cookies

| Cookie | Para que serve | Você precisa pegar? |
|---|---|---|
| `li_at` | Sessão da sua conta. É o segredo de verdade. | **Sim, sempre.** |
| `JSESSIONID` | Token de sessão curto, que também faz papel de CSRF. | **Normalmente não** — é obtido automaticamente a partir do `li_at`. |

O radar deriva o `JSESSIONID` sozinho a cada execução: ele pede a página
`/feed/` usando o `li_at` e lê o cookie que o LinkedIn devolve na resposta.
Só pegue o `JSESSIONID` à mão se essa derivação falhar (ver
[Problemas](#problemas-comuns)).

---

## Passo 1 — Pegar o `li_at` no LinkedIn

1. Abra o [LinkedIn](https://www.linkedin.com) no navegador e **faça login**.
2. Abra as ferramentas de desenvolvedor: `F12` (ou `Ctrl+Shift+I`; no Mac,
   `Cmd+Option+I`).
3. Vá até os cookies:
   - **Chrome / Edge / Brave:** aba **Application** → menu lateral
     **Storage** → **Cookies** → `https://www.linkedin.com`
   - **Firefox:** aba **Storage** (ou "Armazenamento") → **Cookies** →
     `https://www.linkedin.com`
4. Na lista, encontre a linha com **Name = `li_at`**.
   (Tem uma caixa de filtro no topo — digite `li_at` para achar rápido.)
5. Clique nela e copie o campo **Value**.

O valor é uma sequência longa de letras e números, mais ou menos assim:

```
AQEDAQ7v8xYBc9dEAAABkq3...  (~200 caracteres)
```

> **Copie o valor inteiro**, sem aspas e sem o `li_at=` na frente.

### Quanto tempo dura

O `li_at` vale cerca de **1 ano**, mas é invalidado antes disso se você:

- fizer logout no navegador de onde copiou;
- trocar a senha;
- encerrar as sessões em *Configurações → Entrar e segurança → Onde você
  está conectado*.

Não existe renovação automática — quando vence, você repete este passo.
O radar avisa no Telegram quando isso acontece (ver
[Problemas](#problemas-comuns)).

> 💡 **Dica:** não faça logout no navegador de onde copiou o cookie. Fechar
> a aba ou o navegador é indiferente; *logout* é o que mata a sessão.

---

## Passo 2 — Pegar o `JSESSIONID` (opcional)

Só faça isto se o log acusar falha ao derivar a sessão automaticamente.

É o **mesmo caminho** do passo anterior — na mesma lista de cookies,
procure **Name = `JSESSIONID`**. O valor costuma vir assim:

```
"ajax:1234567890123456789"
```

Pode copiar do jeito que estiver. As três formas abaixo funcionam, porque o
código normaliza antes de usar:

- `"ajax:1234567890123456789"` (com aspas e prefixo)
- `ajax:1234567890123456789` (só o prefixo)
- `1234567890123456789` (só o número)

> ⚠️ O `JSESSIONID` é **muito** mais curto que o `li_at` e expira em horas
> ou dias. Por isso ele não é a forma recomendada: preenchido à mão, vira
> manutenção recorrente. Prefira deixar o radar derivá-lo.

---

## Passo 3 — Configurar no GitHub

O cookie **nunca** vai para o código. Ele entra como *secret* do repositório:

1. No repositório, vá em **Settings** → **Secrets and variables** →
   **Actions**.
2. Clique em **New repository secret**.
3. Crie:

| Name | Secret | Obrigatório |
|---|---|---|
| `LINKEDIN_LI_AT` | o valor do passo 1 | ✅ sim |
| `LINKEDIN_JSESSIONID` | o valor do passo 2 | ❌ só se necessário |

Os secrets do Telegram (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) já são os
mesmos que o radar principal usa — não precisa criar de novo.

Pronto. O workflow **LinkedIn Recomendadas** passa a rodar sozinho a cada
2 dias, às 9h UTC (6h de Brasília).

### Rodar na hora, sem esperar

**Actions** → **LinkedIn Recomendadas** → **Run workflow**.

Se já tiver rodado nas últimas 48h, ele vai **pular a busca de propósito** —
a trava de 2 dias vive no código, não só no agendamento, justamente para que
uma execução manual não bata no LinkedIn duas vezes no mesmo dia. O log
mostra o ciclo terminando com `0 brutas` e nenhuma linha `[LinkedIn Rec]`.

---

## Rodar localmente

```bash
export LINKEDIN_LI_AT='cole-o-valor-aqui'

# Opcional: só se a derivação automática falhar
# export LINKEDIN_JSESSIONID='ajax:1234567890123456789'

python main.py --perfil linkedin --once
```

Para testar sem mexer no banco de verdade (recomendado na primeira vez):

```bash
JOBRADAR_DB_PATH=/tmp/teste.db python main.py --perfil linkedin --once
```

> Use aspas **simples** no `export`: o valor do cookie pode conter
> caracteres que o shell interpretaria.

---

## Ajustes finos

Todos opcionais, via variável de ambiente ou secret:

| Variável | Padrão | O que faz |
|---|---|---|
| `LINKEDIN_MAX_PAGINAS` | `5` | Páginas por execução. Cada uma traz até 24 vagas (5 ≈ 120). |
| `LINKEDIN_PAUSA_SEGUNDOS` | `8` | Pausa entre páginas, mais um jitter aleatório de até 2s. |

Para mudar a **cadência**, edite `intervalo_baixa_frequencia_dias` no
`PERFIL_LINKEDIN` (`core/perfis.py`) — e ajuste o `cron` do workflow junto.

> Subir o número de páginas ou baixar a pausa aumenta o risco de bloqueio.
> Os padrões vieram do projeto de origem, que usava 8s entre lotes.

---

## Como as vagas são avaliadas

Nada de especial: **exatamente como qualquer outra fonte.**

```
API Voyager → Job → combina_com() → pontuar_relevancia() → piso → notificação
```

- **Filtro de cargo e remoto:** as mesmas regras do perfil de desenvolvedor
  (`_REGRAS_BR`).
- **Blocklist de empresa:** vale aqui também (BairesDev não passa).
- **Piso de relevância:** vaga abaixo de `LIMIAR_RELEVANCIA_MINIMA` é
  descartada — salva no banco para não voltar, mas sem notificar.
- **Notificação:** nota ≥ `LIMIAR_DIGEST_IMEDIATO` chega na hora; o resto
  entra no digest diário.
- **Deduplicação:** por URL **e** por empresa+título. Uma vaga que o radar
  já tinha achado no LinkedIn público **não** é notificada de novo.

No Telegram e no `relatorio_precisao.py` ela aparece com a origem
`LinkedIn Recomendadas`, separada do `LinkedIn` público — dá pra comparar
qual das duas rende mais.

---

## Problemas comuns

### "LINKEDIN_LI_AT não configurado — fonte ignorada"

O secret não existe ou está vazio. A fonte se desliga sozinha e o resto do
radar segue normal. Refaça o [passo 3](#passo-3--configurar-no-github).

### "o li_at venceu ou foi revogado"

O cookie expirou. Como o perfil só tem essa fonte, o alerta de saúde
dispara no Telegram (`⚠️ JobRadar LinkedIn Recomendadas com problema`).

**Solução:** repita o [passo 1](#passo-1--pegar-o-li_at-no-linkedin) e
atualize o secret `LINKEDIN_LI_AT`.

> É de propósito que isso vire alerta: sem ele, a fonte simplesmente pararia
> de trazer vaga — e um radar que não acha nada é indistinguível de um
> mercado parado.

### "LinkedIn não devolveu JSESSIONID"

A derivação automática falhou (mudança no `/feed/`, ou algum bloqueio).
Pegue o `JSESSIONID` à mão pelo [passo 2](#passo-2--pegar-o-jsessionid-opcional)
e configure o secret `LINKEDIN_JSESSIONID`.

Lembre que ele expira rápido — se precisar disso com frequência, o problema
de fundo é outro (cookie inválido ou conta sob restrição).

### "LinkedIn respondeu 429 (rate limit)"

Acessos demais. Aumente `LINKEDIN_PAUSA_SEGUNDOS`, reduza
`LINKEDIN_MAX_PAGINAS` e **espere alguns dias** antes de tentar de novo.

### "o QUERY_ID provavelmente expirou" (HTTP 400)

A API Voyager identifica cada consulta por um hash versionado. Quando o
LinkedIn publica uma versão nova do site, o hash antigo deixa de existir.

É a parte mais frágil desta fonte e não dá para contornar sozinho — o valor
precisa ser recapturado:

1. Abra <https://www.linkedin.com/jobs/collections/recommended/> logado.
2. `F12` → aba **Network** → filtro **Fetch/XHR**.
3. Role a lista de vagas até carregar mais resultados.
4. Procure a requisição para `voyager/api/graphql`.
5. Na URL dela, copie o valor do parâmetro `queryId`
   (algo como `voyagerJobsDashJobCards.<hash>`).
6. Substitua a constante `QUERY_ID` em
   `scrapers/linkedin_recomendadas.py`.

---

## Segurança

- **Nunca** faça commit do `li_at`. Ele vive só em secret do GitHub ou em
  variável de ambiente local.
- Não cole o valor em issue, PR, log ou chat. O código foi escrito para
  nunca imprimir o cookie nem a URL completa das requisições.
- Se achar que vazou: **LinkedIn → Configurações → Entrar e segurança →
  Onde você está conectado → encerrar sessões**. Isso invalida o cookie na
  hora (e você precisará gerar um novo).
- Um secret do GitHub é legível por quem tem acesso de escrita ao
  repositório e por qualquer workflow dele. Em repositório público, cuidado
  redobrado com Actions de terceiros.

---

## Referências no código

| Arquivo | O que tem |
|---|---|
| `scrapers/linkedin_recomendadas.py` | O scraper: sessão, cabeçalhos, paginação, parse. |
| `core/perfis.py` → `PERFIL_LINKEDIN` | Perfil, cadência de 2 dias, regras aplicadas. |
| `.github/workflows/linkedin-recomendadas.yml` | O cron separado. |
| `tests/test_linkedin_recomendadas.py` | Testes do parse (sem rede). |
| `tests/test_cadencia.py` | Testes da trava de 2 dias. |

Origem: portado do backend do projeto **Otium**
(`teste-tecnico/new-app/src/modules/linkedin-search`), que usa a mesma API.
Foi trazida a mecânica de acesso; a avaliação de compatibilidade de lá (via
Gemini) ficou de fora de propósito — quem pontua aqui é o
`pontuar_relevancia()` do próprio radar.
