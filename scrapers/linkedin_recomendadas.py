"""Vagas RECOMENDADAS do LinkedIn — API privada Voyager, sem navegador.

Diferente do scrapers/linkedin.py, que consulta o endpoint público de
convidado (`jobs-guest/.../seeMoreJobPostings/search`) com um termo de busca,
esta fonte lê a coleção `recommended`: a lista que o LinkedIn monta PRA VOCÊ,
a partir do seu perfil e do seu histórico. Por isso ela ignora
`termos_busca` — não existe termo a passar, a personalização é a consulta.

De onde veio: portada do backend do projeto Otium (NestJS/TypeScript), em
teste-tecnico/new-app/src/modules/linkedin-search. O que foi trazido é a
MECÂNICA de acesso (derivar sessão, montar cabeçalho, paginar, ler a
resposta); o que foi deliberadamente DEIXADO PRA TRÁS é a camada de
avaliação de lá (score de compatibilidade via Gemini) e o filtro próprio de
remoto/data — aqui quem decide isso é combina_com()/pontuar_relevancia(),
igual pra toda fonte. Reimplementar filtro de remoto aqui seria criar um
segundo lugar que decide a mesma coisa, que é a classe de bug mais cara
desta base (ver extrair_escopo_remoto em core/job.py).

AUTENTICAÇÃO — o ponto sensível desta fonte. São dois cookies:

  li_at       Sessão de longa duração da sua conta. É o segredo de verdade:
              quem tem esse valor está logado como você. Vem de
              LINKEDIN_LI_AT (secret do repositório), nunca do código.
  JSESSIONID  Token de sessão curto, que também serve de CSRF. NÃO precisa
              ser fornecido: obter_jsessionid() deriva um novo a cada
              execução, a partir do li_at, pedindo /feed/ e lendo o
              set-cookie da resposta — mesmo caminho do refreshSession() do
              Otium. LINKEDIN_JSESSIONID existe só como escape manual, pra
              quando essa derivação falhar.

Não há renovação de li_at: quando ele expira, o LinkedIn responde o /feed/
com redirecionamento e não devolve JSESSIONID nenhum. Isso vira
SessaoLinkedInExpirada, que sobe como falha do scraper — com esta fonte
sozinha no perfil, a maioria das fontes falhou e o alerta de saúde do
main.py dispara no Telegram. É de propósito: cookie vencido tem que virar
aviso, não silêncio (a fonte simplesmente pararia de trazer vaga, e um
radar que não acha nada é indistinguível de um mercado parado).

AVISO — mesmo risco de IP que a Senior (ver scrapers/senior.py): isto bate
numa API PRIVADA do LinkedIn, autenticado como você. Rodar do GitHub
Actions significa acessar sua conta a partir de um IP de datacenter, o que
é justamente o padrão que dispara bloqueio. O custo de errar aqui não é
perder uma fonte, é a conta pessoal. Daí a cadência de 2 em 2 dias, o teto
de páginas e a pausa entre elas. Ver docs/linkedin-recomendadas.md.
"""

import os
import random
import re
import time
from datetime import datetime, timezone

import requests

from core.job import Job
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

HOST = "https://www.linkedin.com"
URL_FEED = f"{HOST}/feed/"
URL_GRAPHQL = f"{HOST}/voyager/api/graphql"
URL_VAGA = f"{HOST}/jobs/view/"

# Hash da query GraphQL que devolve os cards da coleção de vagas. É opaco e
# versionado pelo LinkedIn: quando eles publicam uma versão nova do
# voyager-web, o hash antigo para de existir e a chamada passa a responder
# 400. É a parte mais frágil desta fonte, e não há como derivá-lo — sai da
# leitura do tráfego real do site. Se um dia o log mostrar 400 constante
# aqui, é este valor que precisa ser recapturado (ver docs/).
QUERY_ID = "voyagerJobsDashJobCards.93590893e4adb90623f00d61719b838c"

# 24 é o tamanho de página que o próprio site usa. Mantido igual de
# propósito: valor diferente do que o navegador real pede é exatamente o
# tipo de assinatura que distingue cliente automatizado.
VAGAS_POR_PAGINA = 24

TIMEOUT_SEGUNDOS = 30

_TIPO_VAGA = "com.linkedin.voyager.dash.jobs.JobPosting"
_TIPO_CARD = "com.linkedin.voyager.dash.jobs.JobPostingCard"

# Vocabulário de "é remota" aplicado ao texto que o LinkedIn devolve. NÃO é
# o filtro de remoto do projeto (esse é _confirma_remoto/combina_com, em
# core/job.py) — serve só pra PREENCHER Job.modalidade a partir do que a
# fonte afirma, do mesmo jeito que os outros scrapers preenchem. Deixa ""
# quando não dá pra afirmar: campo vazio ainda tem o texto de `local` como
# segunda chance no filtro, campo errado não tem (ver senior.py).
_MARCAS_REMOTO = ("remot", "home office", "trabalho remoto")


class SessaoLinkedInExpirada(RuntimeError):
    """li_at inválido ou vencido — precisa recadastrar o cookie à mão."""


class LinkedInBloqueou(RuntimeError):
    """429/403: rate limit ou bloqueio. Parar de insistir nesta execução."""


def _env_int(nome: str, padrao: int) -> int:
    """Lê inteiro do ambiente sem derrubar o ciclo por causa de um valor
    mal digitado no secret — cai no padrão e avisa."""
    bruto = os.getenv(nome)
    if not bruto:
        return padrao
    try:
        return int(bruto)
    except ValueError:
        logger.warning(f"[LinkedIn Rec] {nome}={bruto!r} não é inteiro — usando {padrao}.")
        return padrao


def _gerar_page_instance() -> str:
    """Sufixo aleatório do cabeçalho x-li-page-instance. O navegador manda
    um valor diferente a cada carregamento de página; repetir o mesmo em
    toda requisição é assinatura de automação."""
    alfabeto = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    return "".join(random.choice(alfabeto) for _ in range(22)) + "=="


def montar_cabecalhos(li_at: str, jsessionid: str) -> dict:
    """Cabeçalhos que a Voyager exige. Três coisas não são decoração:

    - `csrf-token` TEM que ser o JSESSIONID prefixado de "ajax:" — é assim
      que o CSRF do LinkedIn funciona (o token é a própria sessão ecoada de
      volta). Errar isso dá 403, não erro de CSRF explícito.
    - `accept` na variante `normalized+json` é o que faz a resposta vir no
      formato achatado que parsear_resposta() espera (lista `included`).
    - `x-restli-protocol-version: 2.0.0` é obrigatório na Voyager.

    O resto imita um Chrome 122 real. Não é sofisticação: é o mínimo pra não
    se anunciar como script.
    """
    jsession_limpo = jsessionid.replace('"', "").replace("ajax:", "")
    return {
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "cookie": f'li_at={li_at}; JSESSIONID="ajax:{jsession_limpo}"; liap=true',
        "csrf-token": f"ajax:{jsession_limpo}",
        "x-li-lang": "pt_BR",
        "x-li-page-instance": (
            "urn:li:page:d_flagship3_job_collections_discovery_landing;"
            + _gerar_page_instance()
        ),
        "x-li-track": (
            '{"clientVersion":"1.13.41695","mpVersion":"1.13.41695","osName":"web",'
            '"timezoneOffset":-3,"timezone":"America/Sao_Paulo",'
            '"deviceFormFactor":"DESKTOP","mpName":"voyager-web",'
            '"displayDensity":1,"displayWidth":1920,"displayHeight":1080}'
        ),
        "x-restli-protocol-version": "2.0.0",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }


def obter_jsessionid(li_at: str, sessao: requests.Session | None = None) -> str:
    """Deriva um JSESSIONID novo a partir do li_at (porte do refreshSession()
    do Otium): pede /feed/ e lê o set-cookie da resposta.

    `allow_redirects=False` é essencial: cookie vencido responde 302/303 pra
    tela de login, e seguir esse redirecionamento devolveria 200 de uma
    página que não tem JSESSIONID nenhum — o erro apareceria depois, como
    "sem cookie na resposta", em vez de aqui, como sessão expirada.
    """
    sessao = sessao or requests.Session()
    resposta = sessao.get(
        URL_FEED,
        headers={
            "user-agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "cookie": f"li_at={li_at}",
        },
        timeout=TIMEOUT_SEGUNDOS,
        allow_redirects=False,
    )

    jsessionid = resposta.cookies.get("JSESSIONID")
    if jsessionid:
        return jsessionid.replace('"', "").replace("ajax:", "")

    if resposta.status_code in (302, 303):
        raise SessaoLinkedInExpirada(
            "LinkedIn redirecionou /feed/ para login — o li_at venceu ou foi revogado."
        )
    raise SessaoLinkedInExpirada(
        f"LinkedIn não devolveu JSESSIONID (HTTP {resposta.status_code})."
    )


# Id de vaga do LinkedIn é numérico e longo (10 dígitos hoje). O mínimo de 4
# evita capturar número curto que aparece por outro motivo dentro do URN
# (versão de esquema, índice), sem depender de saber o tamanho exato.
_NUMERO_LONGO = re.compile(r"\d{4,}")


def _extrair_id(urn: str | None) -> str | None:
    """Puxa o id numérico da vaga de dentro do URN
    ("urn:li:fsd_jobPosting:4123456789" -> "4123456789").

    Duas formas, porque a Voyager usa as duas: o JobPosting vem no formato
    simples (`:4123456789`), e o JobPostingCard vem parentetizado, com
    chave composta (`:(4123456789,JOB_DETAILS)`). A primeira expressão é a
    do Otium, que casa a forma simples; o fallback pro primeiro número
    longo cobre a parentetizada.

    O Otium não precisava desse fallback porque nunca extraía id de card:
    ele casava card com vaga por substring (`entityUrn.includes(jobId)`).
    Aqui o casamento é por índice (ver parsear_resposta), então o id do
    card precisa ser extraível de verdade.
    """
    if not urn:
        return None
    achado = re.search(r":(\d+)(?:,|$|\))", urn)
    if achado:
        return achado.group(1)
    achado = _NUMERO_LONGO.search(urn)
    return achado.group(0) if achado else None


def _texto(no: dict | None, *caminho: str) -> str:
    """Desce por dicionários aninhados devolvendo "" em vez de estourar. A
    resposta da Voyager é opcional em quase todo nível (card sem descrição,
    descrição sem texto), e encadear .get() na chamada deixaria o parse
    ilegível."""
    atual = no
    for chave in caminho:
        if not isinstance(atual, dict):
            return ""
        atual = atual.get(chave)
    return atual.strip() if isinstance(atual, str) else ""


def _data_de_publicacao(card: dict) -> str:
    """footerItem LISTED_DATE traz epoch em MILISSEGUNDOS. Convertido pra
    ISO (AAAA-MM-DD), mesmo formato que a Senior grava.

    Vale saber o efeito: Job.publicacao_antiga só reage a texto relativo
    ("há 3 meses"), então data absoluta sempre devolve False — a vaga nunca
    é tratada como estagnada por aqui. É o comportamento documentado lá, não
    um descuido: sem ano não dá pra calcular idade, e o que se ganha é ter a
    data real gravada no banco pra medir latência depois.
    """
    for item in card.get("footerItems") or []:
        if isinstance(item, dict) and item.get("type") == "LISTED_DATE":
            ms = item.get("timeAt")
            if isinstance(ms, (int, float)) and ms > 0:
                try:
                    return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat()
                except (ValueError, OSError, OverflowError):
                    return ""
    return ""


def _modalidade(titulo: str, local: str) -> str:
    texto = f"{titulo} {local}".lower()
    return "Remoto" if any(m in texto for m in _MARCAS_REMOTO) else ""


def _card_tem_conteudo(card: dict) -> bool:
    """O card traz algum dos campos que montar_job() lê? Serve pra separar
    o card real do stub vazio que vem junto (ver parsear_resposta)."""
    return any(
        card.get(campo)
        for campo in ("primaryDescription", "secondaryDescription", "footerItems")
    )


def montar_job(posting: dict, card: dict | None) -> Job | None:
    """Converte um par (JobPosting, JobPostingCard) num Job. None quando a
    vaga não tem id ou título — sem os dois não dá pra deduplicar nem
    filtrar, então não serve pra nada.

    Separada da rede de propósito, igual montar_job() da Senior: é a parte
    que vale testar, e dá pra testar com a resposta real capturada, sem
    tocar na rede nem precisar de cookie válido.

    Os dois objetos vêm SEPARADOS na resposta e precisam ser casados pelo id
    (ver parsear_resposta): o JobPosting tem o título, e o JobPostingCard
    tem empresa, local e data. Card ausente não descarta a vaga — o título
    sozinho já passa pelo filtro de cargo, e empresa/local viram "Não
    informada"/"Não informado", que é como as outras fontes representam
    campo que a origem não deu.
    """
    card = card or {}

    id_vaga = _extrair_id(posting.get("entityUrn"))
    titulo = _texto(posting, "title")
    if not id_vaga or not titulo:
        return None

    local = _texto(card, "secondaryDescription", "text")

    return Job(
        titulo=titulo,
        empresa=_texto(card, "primaryDescription", "text") or "Não informada",
        local=local or "Não informado",
        link=f"{URL_VAGA}{id_vaga}",
        site="LinkedIn Recomendadas",
        publicado_em=_data_de_publicacao(card),
        modalidade=_modalidade(titulo, local),
    )


def parsear_resposta(payload: dict) -> tuple[list[Job], int]:
    """Devolve (vagas, total_disponivel) de uma página da Voyager.

    A resposta vem "normalizada": em vez de vaga aninhada, um vetor
    `included` com objetos soltos de tipos diferentes, ligados por URN. Os
    dois que interessam são JobPosting (título) e JobPostingCard (empresa,
    local, data) — casados pelo id numérico, que aparece dentro do URN dos
    dois.

    O casamento é feito por índice (dicionário id -> card) e não varrendo a
    lista de cards pra cada vaga: são 24 vagas e 24 cards por página, e a
    busca linear dentro do laço tornaria o parse quadrático à toa.
    """
    incluidos = payload.get("included") or []

    # MEDIDO na resposta real: vêm DOIS cards por vaga, não um — 48 cards
    # para 24 vagas. Um é `(<id>,JOB_DETAILS)`, que chega VAZIO (só
    # entityUrn, sem descrição nem rodapé), e o outro é
    # `(<id>,JOB_COLLECTIONS_RECOMMENDED)`, que carrega empresa, local e
    # data. A ordem dos dois dentro de `included` varia de vaga pra vaga.
    #
    # Indexar "o primeiro que aparecer" fazia 14 das 24 vagas perderem
    # empresa e local em silêncio: elas ainda eram notificadas, só que como
    # "Não informada"/"Não informado" — e, sem o texto de local, o filtro de
    # remoto as descartava. Por isso o stub é pulado: o que decide não é a
    # ordem nem o sufixo do URN (que o LinkedIn pode renomear), é o card
    # TER o conteúdo que se vai ler dele.
    #
    # O id é procurado em todo número longo do URN porque a chave é
    # composta — é o equivalente barato do `includes(jobId)` que o Otium
    # fazia, sem varrer a lista de cards dentro do laço de vagas (24x24
    # comparações por página à toa).
    cards: dict[str, dict] = {}
    for item in incluidos:
        if not isinstance(item, dict) or item.get("$type") != _TIPO_CARD:
            continue
        if not _card_tem_conteudo(item):
            continue
        for numero in _NUMERO_LONGO.findall(item.get("entityUrn") or ""):
            cards.setdefault(numero, item)

    vagas: list[Job] = []
    for item in incluidos:
        if not isinstance(item, dict):
            continue
        urn = item.get("entityUrn") or ""
        e_vaga = item.get("$type") == _TIPO_VAGA or "fsd_jobPosting" in urn
        if not e_vaga or not isinstance(item.get("title"), str):
            continue

        id_vaga = _extrair_id(urn)
        job = montar_job(item, cards.get(id_vaga or ""))
        if job is not None:
            vagas.append(job)

    paginacao = payload.get("data") or {}
    for chave in ("data", "jobsDashJobCardsByJobCollections", "paging"):
        paginacao = paginacao.get(chave) or {} if isinstance(paginacao, dict) else {}
    total = paginacao.get("total") if isinstance(paginacao, dict) else None

    return vagas, int(total) if isinstance(total, int) else 0


class LinkedInRecomendadasScraper(BaseScraper):
    """`termos_busca` é aceito e IGNORADO: a coleção recomendada não recebe
    consulta, ela É a consulta (o LinkedIn monta a lista a partir do seu
    perfil). O parâmetro existe só porque _construir_scrapers() em main.py
    passa termos_busca pra toda fonte — mudar essa assinatura pra abrir
    exceção a uma única fonte custaria mais do que aceitar e ignorar.
    """

    def __init__(self, termos_busca: list[str] | None = None, li_at: str | None = None):
        self.li_at = li_at if li_at is not None else os.getenv("LINKEDIN_LI_AT", "")
        self.jsessionid_manual = os.getenv("LINKEDIN_JSESSIONID", "")
        self.max_paginas = _env_int("LINKEDIN_MAX_PAGINAS", 5)
        self.pausa_segundos = _env_int("LINKEDIN_PAUSA_SEGUNDOS", 8)

    def buscar_vagas(self) -> list[Job]:
        if not self.li_at:
            # Não é exceção: sem cookie configurado a fonte simplesmente não
            # está em uso, e derrubar o ciclo por isso impediria os outros
            # perfis de rodar. Lista vazia já conta como "fonte com
            # problema" no funil do main.py, que é o sinal certo.
            logger.warning(
                "[LinkedIn Rec] LINKEDIN_LI_AT não configurado — fonte ignorada. "
                "Ver docs/linkedin-recomendadas.md."
            )
            return []

        sessao = requests.Session()
        jsessionid = self.jsessionid_manual or obter_jsessionid(self.li_at, sessao)
        origem = "informado à mão" if self.jsessionid_manual else "derivado do li_at"
        logger.info(f"[LinkedIn Rec] Sessão pronta (JSESSIONID {origem}).")

        cabecalhos = montar_cabecalhos(self.li_at, jsessionid)

        vagas: list[Job] = []
        vistos: set[str] = set()
        total_disponivel = None

        for pagina in range(self.max_paginas):
            if pagina:
                # Pausa ANTES da página seguinte, com jitter. O intervalo
                # fixo do Otium (8s cravados) é ele próprio um padrão
                # detectável — requisição a cada exatos 8.000 ms não é
                # comportamento humano.
                time.sleep(self.pausa_segundos + random.uniform(0, 2))

            try:
                payload = self._consultar_pagina(sessao, cabecalhos, pagina)
            except (SessaoLinkedInExpirada, LinkedInBloqueou):
                raise
            except requests.RequestException as e:
                # Nunca loga str(e): a mensagem do requests embute a URL, e
                # aqui a URL carrega parâmetro de sessão. Mesmo hábito de
                # senior.py e notifier/telegram.py.
                logger.warning(
                    f"[LinkedIn Rec] {type(e).__name__} na página {pagina + 1} — "
                    "parando de paginar."
                )
                break

            da_pagina, total = parsear_resposta(payload)
            if total_disponivel is None and total:
                total_disponivel = total

            if not da_pagina:
                break

            # A coleção recomendada repete vaga entre páginas quando o
            # LinkedIn reordena a lista no meio da paginação. Sem cortar
            # aqui, a mesma vaga chegaria duas vezes ao filtro no mesmo
            # ciclo (ja_vista() só protege ENTRE ciclos, porque só consulta
            # o que já está salvo no banco).
            for vaga in da_pagina:
                if vaga.id not in vistos:
                    vistos.add(vaga.id)
                    vagas.append(vaga)

            if total_disponivel and (pagina + 1) * VAGAS_POR_PAGINA >= total_disponivel:
                break

        logger.info(
            f"[LinkedIn Rec] {len(vagas)} vaga(s) recomendada(s) coletada(s)"
            + (f" de {total_disponivel} disponíveis." if total_disponivel else ".")
        )
        return vagas

    def _consultar_pagina(self, sessao, cabecalhos: dict, pagina: int) -> dict:
        inicio = pagina * VAGAS_POR_PAGINA
        variaveis = (
            f"(count:{VAGAS_POR_PAGINA},jobCollectionSlug:recommended,"
            f"query:(origin:GENERIC_JOB_COLLECTIONS_LANDING),start:{inicio})"
        )
        # `variables` NÃO pode ser percent-encoded: a Voyager espera os
        # parênteses e dois-pontos literais nessa sintaxe (RestLi), e
        # deixar o requests montar via params= quebraria com 400. Daí a URL
        # ser concatenada à mão.
        url = f"{URL_GRAPHQL}?variables={variaveis}&queryId={QUERY_ID}"

        resposta = sessao.get(url, headers=cabecalhos, timeout=TIMEOUT_SEGUNDOS)

        if resposta.status_code in (401, 403):
            raise SessaoLinkedInExpirada(
                f"LinkedIn recusou a sessão (HTTP {resposta.status_code}) — "
                "li_at provavelmente vencido."
            )
        if resposta.status_code == 429:
            raise LinkedInBloqueou(
                "LinkedIn respondeu 429 (rate limit). Aumente LINKEDIN_PAUSA_SEGUNDOS "
                "ou reduza LINKEDIN_MAX_PAGINAS."
            )
        if resposta.status_code == 400:
            raise LinkedInBloqueou(
                "LinkedIn respondeu 400 — o QUERY_ID provavelmente expirou. "
                "Ver docs/linkedin-recomendadas.md."
            )
        resposta.raise_for_status()
        return resposta.json()
