"""Notificação por webhook de Discord ou Slack — canal alternativo ao
notifier/telegram.py, escolhido em notifier/canal.py pelo .env.

Por que existe: o Telegram exige criar um bot no @BotFather com uma conta
Telegram de verdade e descobrir o chat_id mandando mensagem pro bot. Webhook
de Discord/Slack é uma URL que se cria em dois cliques nas configurações do
canal — nenhuma conta de bot, nenhuma verificação. Para quem já usa um dos
dois, é o caminho mais curto até "o robô me avisa".

O QUE SE PERDE em relação ao Telegram: os botões 👍/👎 de feedback. Eles
dependem de callback_query, que só existe pra bot de verdade — webhook é via
de mão única (postar), sem canal de volta. Sem app registrado com endpoint
de interações (servidor público, fora do escopo "custo zero" do projeto),
não dá pra ter botão. Consequência prática: a coluna `feedback` do banco
para de ser alimentada, e relatorio_precisao.py fica sem dado novo pra
cruzar (o histórico já gravado continua lá).

O TEXTO das mensagens vem de notifier/telegram.py de propósito — é lá que
mora o template do cartão da vaga, e duplicar aqui garantia que os dois
divergissem no primeiro ajuste de layout. O que este módulo faz é traduzir
o HTML do Telegram pro markup do destino e postar. Só a ENTREGA é local.
"""

import html
import re
import time

import requests

from core.config import NOTIFICADOR_WEBHOOK_URL
from core.logger import get_logger
from notifier.telegram import montar_digest, texto_vaga, texto_vaga_exploratoria

logger = get_logger()

DISCORD = "discord"
SLACK = "slack"

# Limite de caracteres por mensagem em cada plataforma, com margem. Discord
# recusa (400) `content` acima de 2000; Slack aceita `text` bem maior, mas
# corta a exibição por volta de 3000. Os textos são MONTADOS em HTML do
# Telegram e só depois convertidos, e a conversão sempre encurta
# (`<a href="U">T</a>` -> `[T](U)` economiza 11 chars; `<b>x</b>` -> `**x**`
# economiza 3) — então medir o limite no HTML é conservador na direção
# segura: o que couber antes cabe depois.
_LIMITES = {DISCORD: 1800, SLACK: 2800}

# Espaçamento mínimo entre dois POSTs no mesmo webhook.
#
# MEDIDO no primeiro ciclo real: 79 notificações imediatas em rajada
# levaram a dois HTTP 429 do Discord (limite do webhook: 5 requisições por
# 2s no bucket, 30/min no geral). Recuperaram na retentativa, mas o digest
# é pior — 578 vagas na fila viram ~28 mensagens seguidas, e ali um 429 não
# custa uma vaga: enviar_digest só devolve True se TODAS as partes saírem,
# então uma falha no meio faz o dia inteiro ser reenviado do zero no ciclo
# seguinte, duplicando o que já chegou.
#
# REMEDIDO depois que o piso de relevância e a blocklist de empresa
# entraram (commit 9069a48), reprocessando as 3.756 vagas do banco vivo sob
# o perfil atual — os números acima são de ANTES dele:
#
#   imediatas   308 -> 276   (-10%)
#   digest    2.151 -> 859   (-60%)
#
# A rajada de imediatas quase não se mexe, e isso é estrutural, não sorte:
# LIMIAR_RELEVANCIA_MINIMA (6) é MENOR que LIMIAR_DIGEST_IMEDIATO (7), então
# toda vaga que o piso corta já iria pro digest de qualquer jeito — o piso
# não tem como derrubar uma notificação imediata. Os -10% são só a
# blocklist (32 das 308 eram BairesDev). Conclusão prática: o cenário que
# produziu os dois 429 continua de pé praticamente intacto, e o intervalo
# abaixo segue sendo o que segura a rajada — não afrouxar por achar que
# "agora vem menos vaga". O que encolheu de verdade foi o digest: as ~28
# mensagens seguidas viram ~11.
#
# 2,5s = 24 mensagens/min, com margem sob o teto de 30. Não é 2,0s porque
# a PRIMEIRA mensagem da rajada não espera (não tem anterior pra respeitar),
# então N mensagens levam (N-1)x o intervalo: a 2,0s exatos, 23 mensagens
# saem em 44s — 31/min, um passo ACIMA do limite. O teste
# test_digest_longo_nao_estoura_o_teto_de_30_por_minuto trava essa conta.
#
# Custo: 79 mensagens = ~3min a mais num ciclo de ~20min, que sobra.
_INTERVALO_MINIMO_S = 2.5
_ultimo_post = 0.0


def _respeitar_intervalo():
    """Segura o próximo POST até fechar _INTERVALO_MINIMO_S desde o
    anterior. Estado em variável de módulo porque o limite é por WEBHOOK
    (não por mensagem nem por chamador) — notificação imediata e parte de
    digest disputam o mesmo balde e precisam contar juntas."""
    global _ultimo_post
    espera = _INTERVALO_MINIMO_S - (time.monotonic() - _ultimo_post)
    if espera > 0:
        time.sleep(espera)
    _ultimo_post = time.monotonic()


def _plataforma(url: str) -> str | None:
    """Discord ou Slack a partir da própria URL do webhook — evita uma
    segunda variável no .env só pra dizer o que a URL já diz. None quando
    não reconhece (erro de configuração, tratado em _postar)."""
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        return DISCORD
    if "hooks.slack.com" in url:
        return SLACK
    return None


_RE_LINK = re.compile(r'<a href="([^"]+)">(.*?)</a>', re.DOTALL)
_RE_NEGRITO = re.compile(r"<b>(.*?)</b>", re.DOTALL)
_RE_ITALICO = re.compile(r"<i>(.*?)</i>", re.DOTALL)

# Tags que este projeto realmente emite (ver telegram.py/main.py). Qualquer
# outra é removida ANTES da conversão, nunca depois: a sintaxe de link do
# Slack é `<url|texto>`, que uma limpeza genérica de "<...>" rodando no fim
# apagaria junto — o link inteiro sumia da mensagem. Já aconteceu; é o que o
# test_conversao_slack trava.
_TAGS_CONHECIDAS = {"b", "i", "a"}
_RE_QUALQUER_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)[^>]*>")
# Sobra de tag conhecida que a conversão não pegou (ex: <a href='aspas
# simples'>, que _RE_LINK não casa). Enumerada, não genérica, pela mesma
# razão acima — nenhum destes padrões colide com `<url|texto>`.
_RE_SOBRA_CONHECIDA = re.compile(r"</?[bi]>|</?a(?: [^>]*)?>")


def converter_markup(texto: str, plataforma: str) -> str:
    """HTML do Telegram -> markup do destino.

    Não é um conversor de HTML genérico e nem tenta ser: o universo de tags
    que este projeto emite é <b>, <i> e <a href="...">, tudo montado por
    f-string em telegram.py e main.py. Qualquer tag fora dessas é removida
    em vez de escapada — melhor perder a formatação do que despejar `<div>`
    no meio da vaga.

    Slack usa `<url|texto>` pra link e asterisco SIMPLES pra negrito; Discord
    usa markdown normal (`[texto](url)`, `**negrito**`). É a única diferença
    real de dialeto entre os dois, e é justamente a que faria a mensagem
    chegar ilegível se fosse ignorada.
    """
    texto = _RE_QUALQUER_TAG.sub(
        lambda m: m.group(0) if m.group(1).lower() in _TAGS_CONHECIDAS else "", texto
    )
    if plataforma == SLACK:
        texto = _RE_LINK.sub(r"<\1|\2>", texto)
        texto = _RE_NEGRITO.sub(r"*\1*", texto)
        texto = _RE_ITALICO.sub(r"_\1_", texto)
    else:
        texto = _RE_LINK.sub(r"[\2](\1)", texto)
        texto = _RE_NEGRITO.sub(r"**\1**", texto)
        texto = _RE_ITALICO.sub(r"*\1*", texto)
    texto = _RE_SOBRA_CONHECIDA.sub("", texto)
    # Entidades por último, depois que as tags sumiram: desescapar antes
    # transformaria um "&lt;b&gt;" literal do título da vaga em tag de
    # verdade, que aí seria removida pela linha acima.
    return html.unescape(texto)


def fatiar(texto: str, limite: int) -> list[str]:
    """Rede de segurança: quebra texto acima do limite da plataforma em
    pedaços, preferindo cortar em quebra de linha.

    O digest já sai pré-quebrado por montar_digest (com o limite certo, ver
    enviar_digest), mas enviar_mensagem é chamada de main.py com texto de
    tamanho imprevisível — o aviso de abortar, por exemplo, embute a
    mensagem de uma exceção. Sem isso, um texto comprido viraria HTTP 400 no
    Discord e a notificação sumiria inteira em vez de chegar em duas partes.
    """
    if len(texto) <= limite:
        return [texto]

    pedacos, atual = [], ""
    for linha in texto.split("\n"):
        # Linha sozinha maior que o limite: corta na força bruta, não tem
        # fronteira melhor disponível.
        while len(linha) > limite:
            if atual:
                pedacos.append(atual)
                atual = ""
            pedacos.append(linha[:limite])
            linha = linha[limite:]
        if atual and len(atual) + len(linha) + 1 > limite:
            pedacos.append(atual)
            atual = ""
        atual = f"{atual}\n{linha}" if atual else linha
    if atual:
        pedacos.append(atual)
    return pedacos


def _payload(texto: str, plataforma: str) -> dict:
    if plataforma == SLACK:
        return {"text": texto}
    # allowed_mentions vazio: título de vaga com "@" (ou um "@everyone"
    # literal vindo de uma descrição qualquer) não vira menção real e não
    # notifica o servidor inteiro. O Discord só respeita isso se o campo
    # vier explícito.
    return {"content": texto, "allowed_mentions": {"parse": []}}


def _postar(texto: str) -> bool:
    """POST de um pedaço já convertido e dentro do limite.

    Tratamento de erro segue a mesma disciplina de telegram.py e pela mesma
    razão: a URL do webhook É a credencial (quem tem ela posta no seu canal),
    e a mensagem padrão de erro de conexão do requests inclui a URL que
    falhou. Por isso nunca `{e}` cru, nunca a URL — HTTPError loga status e
    motivo (vêm da resposta, não da URL), o resto loga só o tipo da exceção.
    """
    plataforma = _plataforma(NOTIFICADOR_WEBHOOK_URL)
    _respeitar_intervalo()
    try:
        resposta = requests.post(NOTIFICADOR_WEBHOOK_URL, json=_payload(texto, plataforma), timeout=10)
        # 429 é esperado, não é falha: o digest manda várias partes seguidas
        # e o Discord limita 5 requisições por 2s no mesmo webhook. Uma
        # tentativa a mais respeitando o Retry-After resolve o caso normal;
        # insistir além disso só empurra o problema (o chamador já trata
        # False como "tenta no próximo ciclo").
        if resposta.status_code == 429:
            # Rede de segurança, não o mecanismo principal (esse é o
            # espaçamento acima). O teto existe porque o Retry-After do
            # Discord já veio com 400s numa rajada em que 30s de espera
            # bastaram — dormir o valor cru travaria o ciclo inteiro por
            # quase 7 minutos por mensagem. Loga o valor cru pra dar pra
            # reavaliar esse teto com dado real, se voltar a acontecer.
            bruto = float(resposta.headers.get("Retry-After", 1) or 1)
            espera = min(bruto, 60)
            logger.info(
                f"Webhook limitou a taxa (429), Retry-After={bruto:.0f}s, "
                f"reenviando em {espera:.0f}s."
            )
            time.sleep(espera)
            _respeitar_intervalo()
            resposta = requests.post(NOTIFICADOR_WEBHOOK_URL, json=_payload(texto, plataforma), timeout=10)
        resposta.raise_for_status()
        return True
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        motivo = e.response.reason if e.response is not None else "sem detalhe"
        logger.error(f"Erro ao postar no webhook: HTTP {status} ({motivo})")
        return False
    except requests.RequestException as e:
        logger.error(
            f"Erro ao postar no webhook: {type(e).__name__} "
            "(falha de conexão, sem resposta do servidor)"
        )
        return False


def enviar_mensagem(texto: str, reply_markup: dict | None = None) -> bool:
    """Mesma assinatura de notifier/telegram.py — é o contrato que
    notifier/canal.py troca em tempo de import.

    `reply_markup` (o teclado 👍/👎) é aceito e IGNORADO de propósito: webhook
    não tem canal de volta pra receber clique (ver docstring do módulo).
    Recusar o argumento quebraria notificar_vaga sem ganho nenhum; aceitar e
    ignorar entrega a vaga, que é o que importa.
    """
    if not NOTIFICADOR_WEBHOOK_URL:
        logger.warning("Webhook não configurado (NOTIFICADOR_WEBHOOK_URL ausente no .env). Pulando envio.")
        return False

    plataforma = _plataforma(NOTIFICADOR_WEBHOOK_URL)
    if plataforma is None:
        logger.error(
            "NOTIFICADOR_WEBHOOK_URL não parece ser de Discord nem de Slack "
            "(esperado discord.com/api/webhooks/... ou hooks.slack.com/services/...)."
        )
        return False

    convertido = converter_markup(texto, plataforma)
    # all() sem short-circuit útil aqui seria pior: se o pedaço 2 de 3
    # falhar, não adianta mandar o 3 — chega texto sem começo nem meio. Para
    # no primeiro erro e devolve False; o chamador reenvia tudo depois.
    for pedaco in fatiar(convertido, _LIMITES[plataforma]):
        if not _postar(pedaco):
            return False
    return True


def notificar_vaga(job) -> bool:
    return enviar_mensagem(texto_vaga(job))


def notificar_vaga_exploratoria(job) -> bool:
    return enviar_mensagem(texto_vaga_exploratoria(job))


def enviar_digest(vagas: list[tuple], rotulo_perfil: str) -> bool:
    """Mesmo contrato do enviar_digest do Telegram, inclusive o "só True se
    TODAS as partes confirmarem" — é desse retorno que main.py depende pra
    decidir se limpa a fila do digest (ver marcar_digest_enviado). Falha
    parcial mantém tudo pendente: duplicar uma parte é aceitável, perder
    vaga não.

    O limite passado pro montar_digest é o da plataforma, não o do Telegram:
    o mesmo digest que cabe em 1 mensagem lá precisa de 2 no Discord, e é
    melhor quebrar com o cabeçalho "parte 1/2" certo do que deixar o fatiar()
    cortar depois, sem cabeçalho nenhum na segunda metade.
    """
    if not vagas:
        return True
    plataforma = _plataforma(NOTIFICADOR_WEBHOOK_URL)
    if plataforma is None:
        logger.error("Digest não enviado: NOTIFICADOR_WEBHOOK_URL ausente ou não reconhecida.")
        return False
    return all(
        enviar_mensagem(mensagem)
        for mensagem in montar_digest(vagas, rotulo_perfil, _LIMITES[plataforma])
    )


def processar_feedback_pendente():
    """No-op — webhook não recebe clique de volta (ver docstring do módulo).

    Existe pra fechar o contrato que main.py importa; sem ela, trocar o canal
    quebraria a chamada em _rodar_um_ciclo_de_cada.
    """
    return
