"""Testes do canal de webhook (notifier/webhook.py) que não dependem de
rede — detecção de plataforma pela URL, conversão do HTML do Telegram pro
markup de cada destino, e a quebra por limite de caracteres.

Mesma restrição do test_telegram.py: chamada HTTP de verdade não é testável
aqui (o sandbox não alcança a internet). O POST em si é exercitado com um
`requests.post` falso, que é o suficiente pra travar o que interessa — que o
payload sai no formato que cada plataforma espera e que o link da vaga
sobrevive à conversão.
"""

import pytest

from core.job import Job
from notifier import webhook
from notifier.webhook import DISCORD, SLACK, _payload, _plataforma, converter_markup, fatiar

_URL_DISCORD = "https://discord.com/api/webhooks/123456789/abcdefgh"
_URL_SLACK = "https://hooks.slack.com/services/T000/B000/XXXX"


CASOS_PLATAFORMA = [
    ("discord", _URL_DISCORD, DISCORD),
    ("discord-dominio-legado", "https://discordapp.com/api/webhooks/1/x", DISCORD),
    ("slack", _URL_SLACK, SLACK),
    # URL que não é de webhook nenhum: melhor devolver None e falhar com log
    # explícito do que adivinhar uma plataforma e postar em formato errado.
    ("desconhecida", "https://example.com/webhook", None),
    ("vazia", "", None),
]


@pytest.mark.parametrize(
    "nome,url,esperado", CASOS_PLATAFORMA, ids=[c[0] for c in CASOS_PLATAFORMA]
)
def test_plataforma_detectada_pela_url(nome, url, esperado):
    assert _plataforma(url) == esperado


def test_conversao_discord():
    html = '<b>Empresa:</b> ACME\n<a href="https://x.com/vaga">Dev Python</a>'
    assert converter_markup(html, DISCORD) == "**Empresa:** ACME\n[Dev Python](https://x.com/vaga)"


def test_conversao_slack():
    # Slack não entende [texto](url) nem **negrito** — o dialeto é outro, e
    # este é exatamente o erro que faria a mensagem chegar ilegível.
    html = '<b>Empresa:</b> ACME\n<a href="https://x.com/vaga">Dev Python</a>'
    assert converter_markup(html, SLACK) == "*Empresa:* ACME\n<https://x.com/vaga|Dev Python>"


def test_conversao_remove_tag_desconhecida_e_desescapa_entidade():
    assert converter_markup("<div>a &amp; b</div>", DISCORD) == "a & b"


def test_conversao_nao_deixa_tag_sobrando():
    # Rede de segurança pro conjunto todo: nenhuma mensagem pode chegar no
    # canal com HTML cru visível.
    html = "<b>a</b> <i>b</i> <u>c</u> <code>d</code>"
    for plataforma in (DISCORD, SLACK):
        assert "<" not in converter_markup(html, plataforma)


def test_conversao_slack_preserva_link_junto_de_tag_desconhecida():
    # Regressão: a limpeza de tags residuais rodava DEPOIS da conversão e
    # apagava o `<url|texto>` do Slack junto com o HTML — a vaga chegava sem
    # link nenhum, que é o único pedaço insubstituível da mensagem.
    html = '<div><a href="https://x.com/v">Vaga</a></div>'
    assert converter_markup(html, SLACK) == "<https://x.com/v|Vaga>"


def test_fatiar_respeita_limite_e_preserva_tudo():
    texto = "\n".join(f"linha {i} com algum conteudo" for i in range(50))
    pedacos = fatiar(texto, 200)
    assert all(len(p) <= 200 for p in pedacos)
    # Nada pode se perder na quebra — o digest depende disso.
    assert "\n".join(pedacos) == texto


def test_fatiar_corta_linha_maior_que_o_limite():
    # Sem esse caminho, uma linha única gigante (mensagem de exceção no
    # aviso de abortar) devolveria um pedaço acima do limite e viraria 400.
    pedacos = fatiar("x" * 500, 100)
    assert all(len(p) <= 100 for p in pedacos)
    assert "".join(pedacos) == "x" * 500


def test_fatiar_texto_curto_nao_mexe():
    assert fatiar("mensagem curta", 100) == ["mensagem curta"]


def test_payload_discord_nao_permite_mencao():
    # Título de vaga com "@everyone" não pode notificar o servidor inteiro.
    assert _payload("oi", DISCORD)["allowed_mentions"] == {"parse": []}
    assert _payload("oi", DISCORD)["content"] == "oi"


def test_payload_slack_usa_campo_text():
    assert _payload("oi", SLACK) == {"text": "oi"}


class _RespostaFalsa:
    status_code = 204
    headers: dict = {}

    def raise_for_status(self):
        return None


@pytest.fixture
def capturar_post(monkeypatch):
    """Substitui requests.post e devolve a lista de payloads enviados."""
    enviados = []

    def post_falso(url, json=None, timeout=None):
        enviados.append(json)
        return _RespostaFalsa()

    monkeypatch.setattr(webhook.requests, "post", post_falso)
    return enviados


def _configurar(monkeypatch, url):
    monkeypatch.setattr(webhook, "NOTIFICADOR_WEBHOOK_URL", url)


def test_notificar_vaga_manda_o_link_convertido(monkeypatch, capturar_post):
    _configurar(monkeypatch, _URL_DISCORD)
    vaga = Job(
        titulo="Desenvolvedor Backend Python",
        empresa="ACME",
        local="Remoto",
        link="https://exemplo.com/vaga/1",
        site="Gupy",
    )

    assert webhook.notificar_vaga(vaga) is True
    assert len(capturar_post) == 1
    texto = capturar_post[0]["content"]
    # O link é a única parte insubstituível da notificação — o resto é
    # contexto, mas sem ele a mensagem não serve pra nada.
    assert "https://exemplo.com/vaga/1" in texto
    assert "ACME" in texto
    assert "<b>" not in texto


def test_sem_url_configurada_nao_posta(monkeypatch, capturar_post):
    _configurar(monkeypatch, "")
    assert webhook.enviar_mensagem("oi") is False
    assert capturar_post == []


def test_url_irreconhecivel_nao_posta(monkeypatch, capturar_post):
    # Falha explícita e sem envio: postar payload de Discord numa URL
    # desconhecida não tem como dar certo, e o log diz o que corrigir.
    _configurar(monkeypatch, "https://example.com/webhook")
    assert webhook.enviar_mensagem("oi") is False
    assert capturar_post == []


def test_digest_quebra_no_limite_da_plataforma(monkeypatch, capturar_post):
    _configurar(monkeypatch, _URL_DISCORD)
    vagas = [(f"Vaga numero {i}", "ACME", f"https://exemplo.com/{i}", 6, False) for i in range(60)]

    assert webhook.enviar_digest(vagas, "Brasil") is True
    assert len(capturar_post) > 1, "60 vagas não cabem em uma mensagem do Discord"
    for payload in capturar_post:
        assert len(payload["content"]) <= 2000  # limite real da API
        assert "Digest diário" in payload["content"]


def test_digest_vazio_nao_posta(monkeypatch, capturar_post):
    # Contrato do chamador: True sem enviar nada (ver _enviar_digest_diario).
    _configurar(monkeypatch, _URL_DISCORD)
    assert webhook.enviar_digest([], "Brasil") is True
    assert capturar_post == []


def test_processar_feedback_pendente_e_no_op(monkeypatch, capturar_post):
    # Webhook não tem canal de volta; a função existe só pra fechar o
    # contrato que main.py importa.
    _configurar(monkeypatch, _URL_DISCORD)
    assert webhook.processar_feedback_pendente() is None
    assert capturar_post == []


class _RelogioFalso:
    """Relógio e sleep de mentira pra medir o espaçamento sem gastar o tempo
    de verdade — 30 mensagens a 2s travariam a suíte por um minuto."""

    def __init__(self):
        self.agora = 1000.0
        self.dormidas = []

    def monotonic(self):
        return self.agora

    def sleep(self, segundos):
        self.dormidas.append(segundos)
        self.agora += segundos


@pytest.fixture
def relogio(monkeypatch):
    falso = _RelogioFalso()
    monkeypatch.setattr(webhook.time, "monotonic", falso.monotonic)
    monkeypatch.setattr(webhook.time, "sleep", falso.sleep)
    # Zera o estado de módulo entre testes: _ultimo_post é global de
    # propósito (o limite é por webhook), então vaza de um teste pro outro.
    monkeypatch.setattr(webhook, "_ultimo_post", 0.0)
    return falso


def test_posts_seguidos_ficam_espacados(monkeypatch, capturar_post, relogio):
    # A rajada real que gerou 429: várias mensagens sem pausa nenhuma.
    _configurar(monkeypatch, _URL_DISCORD)
    for _ in range(5):
        webhook.enviar_mensagem("oi")

    assert len(capturar_post) == 5
    # A primeira não espera (o relógio começa muito depois de _ultimo_post=0);
    # cada uma das seguintes segura o intervalo cheio.
    assert relogio.dormidas == [2.5, 2.5, 2.5, 2.5]


def test_digest_longo_nao_estoura_o_teto_de_30_por_minuto(monkeypatch, capturar_post, relogio):
    # 578 vagas (o tamanho real da fila acumulada) viram dezenas de
    # mensagens; o que não pode é elas saírem mais rápido que 30/min.
    _configurar(monkeypatch, _URL_DISCORD)
    vagas = [(f"Vaga {i}", "ACME", f"https://exemplo.com/{i}", 6, False) for i in range(578)]

    assert webhook.enviar_digest(vagas, "Brasil") is True

    mensagens = len(capturar_post)
    assert mensagens > 20, "578 vagas deveriam render dezenas de mensagens"
    duracao = relogio.agora - 1000.0
    assert duracao >= (mensagens - 1) * 2.5
    assert mensagens / max(duracao / 60, 1e-9) <= 30, "acima do teto de 30 msg/min do Discord"
