"""Leitura da resposta da API Voyager (vagas recomendadas do LinkedIn).

Mesma escolha do test_senior.py: o que vale testar aqui e a TRADUCAO da
resposta pra Job, nao a chamada de rede. O parse e funcao pura -- recebe
dicionario, devolve Job -- e e onde mora o risco de verdade desta fonte,
porque a resposta vem "normalizada": nada aninhado, um vetor `included` com
objetos soltos de tipos diferentes que precisam ser casados por URN.

Testar isso sem rede tambem e o unico jeito honesto: a chamada real exige
um cookie li_at valido, que e credencial pessoal e nao pode entrar no CI.
"""

import pytest

from core.job import Job
from scrapers.linkedin_recomendadas import (
    _data_de_publicacao,
    _extrair_id,
    montar_cabecalhos,
    montar_job,
    parsear_resposta,
)

# 21/08/2026 00:00 UTC em milissegundos -- o formato que o footerItem
# LISTED_DATE usa (epoch em MILI, nao em segundos; ler como segundos daria
# uma data em 1970).
EPOCH_MS = 1787270400000

URN_VAGA = "urn:li:fsd_jobPosting:4123456789"
# Card usa chave COMPOSTA e parentetizada -- formato diferente do da vaga.
# E exatamente por causa dessa diferenca que o casamento entre os dois
# precisa de cuidado (ver _extrair_id).
#
# MEDIDO na resposta real: vem DOIS cards por vaga, 48 pra 24 vagas. O
# JOB_COLLECTIONS_RECOMMENDED e o que carrega empresa/local/data; o
# JOB_DETAILS chega VAZIO, so com entityUrn. A ordem entre eles dentro de
# `included` varia de vaga pra vaga -- e foi exatamente isso que quebrou a
# primeira versao (ver o teste de regressao mais abaixo).
URN_CARD = "urn:li:fsd_jobPostingCard:(4123456789,JOB_COLLECTIONS_RECOMMENDED)"
URN_CARD_VAZIO = "urn:li:fsd_jobPostingCard:(4123456789,JOB_DETAILS)"


def _card_vazio():
    """O stub que o LinkedIn manda junto do card de verdade: mesmo id,
    mesmo tipo, nenhum dado."""
    return {
        "$type": "com.linkedin.voyager.dash.jobs.JobPostingCard",
        "entityUrn": URN_CARD_VAZIO,
    }


def _payload(incluidos, total=137):
    return {
        "included": incluidos,
        "data": {
            "data": {
                "jobsDashJobCardsByJobCollections": {
                    "paging": {"start": 0, "count": 24, "total": total}
                }
            }
        },
    }


def _vaga_bruta(urn=URN_VAGA, titulo="Desenvolvedor Backend Python"):
    return {
        "$type": "com.linkedin.voyager.dash.jobs.JobPosting",
        "entityUrn": urn,
        "title": titulo,
        "repostedJob": False,
    }


def _card_bruto(urn=URN_CARD, empresa="Acme Tech", local="Brasil (Remoto)"):
    return {
        "$type": "com.linkedin.voyager.dash.jobs.JobPostingCard",
        "entityUrn": urn,
        "jobPostingTitle": "Desenvolvedor Backend Python",
        "primaryDescription": {"text": empresa},
        "secondaryDescription": {"text": local},
        "footerItems": [
            {"type": "LISTED_DATE", "timeAt": EPOCH_MS},
            {"type": "EASY_APPLY_TEXT"},
        ],
    }


# ------------------------------------------------------- EXTRACAO DE ID

@pytest.mark.parametrize("urn, esperado", [
    # Forma simples: a do JobPosting.
    ("urn:li:fsd_jobPosting:4123456789", "4123456789"),
    # Forma parentetizada: a do JobPostingCard. Era o caso que quebrava
    # quando o casamento usava so a primeira expressao -- o id existe, mas
    # nao vem precedido de ":".
    ("urn:li:fsd_jobPostingCard:(4123456789,JOB_DETAILS)", "4123456789"),
    ("urn:li:fsd_jobPostingCard:(4123456789,JOBS_OCCUPANCY_TOPCARD)", "4123456789"),
    (None, None),
    ("", None),
    ("urn:li:fsd_jobPosting:sem-numero", None),
])
def test_extrair_id_cobre_as_duas_formas_de_urn(urn, esperado):
    assert _extrair_id(urn) == esperado


# ------------------------------------------------------------ PARSE

def test_parsear_resposta_casa_vaga_com_card_apesar_do_urn_diferente():
    """O teste central desta fonte: titulo vem do JobPosting, empresa/local
    vem do JobPostingCard, e os dois so se encontram pelo id dentro de URNs
    de formatos diferentes. Se o casamento falhar, a vaga ainda e
    notificada -- so que sem empresa nem local, silenciosamente."""
    vagas, total = parsear_resposta(_payload([_vaga_bruta(), _card_bruto()]))

    assert total == 137
    assert len(vagas) == 1
    vaga = vagas[0]
    assert vaga.titulo == "Desenvolvedor Backend Python"
    assert vaga.empresa == "Acme Tech"
    assert vaga.local == "Brasil (Remoto)"
    assert vaga.link == "https://www.linkedin.com/jobs/view/4123456789"
    assert vaga.site == "LinkedIn Recomendadas"
    assert vaga.publicado_em == "2026-08-21"
    assert vaga.modalidade == "Remoto"


def test_parsear_resposta_ignora_objetos_de_outros_tipos():
    """`included` mistura tipos -- perfil, empresa, imagem. So JobPosting
    vira vaga."""
    lixo = [
        {"$type": "com.linkedin.voyager.dash.organization.Company", "name": "Acme"},
        {"$type": "com.linkedin.common.VectorImage", "rootUrl": "https://x/"},
        "nao e dicionario",
    ]
    vagas, _ = parsear_resposta(_payload(lixo + [_vaga_bruta(), _card_bruto()]))
    assert len(vagas) == 1


def test_parsear_resposta_sem_paginacao_devolve_total_zero():
    """Resposta sem o bloco de paging nao pode estourar -- so nao informa
    total (o scraper para de paginar por lista vazia, nao por total)."""
    vagas, total = parsear_resposta({"included": [_vaga_bruta(), _card_bruto()]})
    assert len(vagas) == 1
    assert total == 0


def test_parsear_resposta_vazia():
    vagas, total = parsear_resposta({})
    assert vagas == []
    assert total == 0


def test_vaga_sem_card_ainda_e_aproveitada():
    """Card ausente nao descarta: o titulo sozinho ja passa pelo filtro de
    cargo. Empresa/local caem no vocabulario que as outras fontes usam pra
    campo que a origem nao deu."""
    vagas, _ = parsear_resposta(_payload([_vaga_bruta()]))
    assert len(vagas) == 1
    assert vagas[0].empresa == "Não informada"
    assert vagas[0].local == "Não informado"


def test_vaga_sem_titulo_e_descartada():
    """Sem titulo nao da pra filtrar por cargo nem montar
    chave_secundaria -- a vaga nao serve pra nada."""
    sem_titulo = _vaga_bruta()
    sem_titulo["title"] = None
    vagas, _ = parsear_resposta(_payload([sem_titulo]))
    assert vagas == []


def test_vaga_identificada_so_pelo_sufixo_do_urn_tambem_entra():
    """O Otium aceita como vaga tanto `$type` de JobPosting quanto URN que
    contenha "fsd_jobPosting" -- respostas reais trazem as duas coisas."""
    sem_tipo = {"entityUrn": URN_VAGA, "title": "Desenvolvedor Backend Python"}
    vagas, _ = parsear_resposta(_payload([sem_tipo]))
    assert len(vagas) == 1


def test_card_vazio_nao_rouba_o_lugar_do_card_com_dados():
    """REGRESSAO (achado rodando contra a API real): toda vaga vem com DOIS
    cards -- um vazio (JOB_DETAILS, so entityUrn) e o de verdade
    (JOB_COLLECTIONS_RECOMMENDED). Indexando "o primeiro que aparecer", 14
    das 24 vagas da pagina real perdiam empresa e local.

    O estrago era silencioso e duplo: a vaga chegava como "Nao informada", e
    -- sem texto de local -- o filtro de remoto ainda a descartava. Ou seja,
    vaga boa sumia sem aparecer em lugar nenhum do log.

    O stub vem PRIMEIRO aqui de proposito: e a ordem que quebrava."""
    incluidos = [_card_vazio(), _vaga_bruta(), _card_bruto()]
    vagas, _ = parsear_resposta(_payload(incluidos))

    assert len(vagas) == 1
    assert vagas[0].empresa == "Acme Tech"
    assert vagas[0].local == "Brasil (Remoto)"


def test_vaga_com_apenas_o_card_vazio_nao_estoura():
    """Se um dia so vier o stub, a vaga ainda entra -- sem empresa/local,
    como qualquer fonte que nao informa esses campos."""
    vagas, _ = parsear_resposta(_payload([_card_vazio(), _vaga_bruta()]))
    assert len(vagas) == 1
    assert vagas[0].empresa == "Não informada"


# ------------------------------------------------------------ CAMPOS

def test_data_de_publicacao_converte_epoch_em_milissegundos():
    assert _data_de_publicacao(_card_bruto()) == "2026-08-21"


@pytest.mark.parametrize("card", [
    {},
    {"footerItems": []},
    {"footerItems": [{"type": "PROMOTED"}]},          # sem LISTED_DATE
    {"footerItems": [{"type": "LISTED_DATE"}]},        # sem timeAt
    {"footerItems": [{"type": "LISTED_DATE", "timeAt": None}]},
    {"footerItems": [{"type": "LISTED_DATE", "timeAt": "ontem"}]},
])
def test_data_de_publicacao_ausente_ou_ilegivel_vira_vazio(card):
    """Vazio e o que as outras fontes gravam quando nao sabem a data --
    afirmar uma data errada seria pior (ver Job.publicacao_antiga)."""
    assert _data_de_publicacao(card) == ""


@pytest.mark.parametrize("titulo, local, esperado", [
    ("Desenvolvedor Backend", "Brasil (Remoto)", "Remoto"),
    ("Desenvolvedor Backend", "Remote - Brazil", "Remoto"),
    ("Desenvolvedor Backend (Home Office)", "São Paulo", "Remoto"),
    # Sem marca nenhuma: fica vazio de proposito. Campo vazio ainda tem o
    # texto de `local` como segunda chance no filtro; campo errado nao tem.
    ("Desenvolvedor Backend", "São Paulo, SP", ""),
])
def test_modalidade_sai_do_texto_da_propria_fonte(titulo, local, esperado):
    vaga = montar_job(
        _vaga_bruta(titulo=titulo),
        _card_bruto(local=local),
    )
    assert vaga.modalidade == esperado


def test_montar_job_devolve_none_sem_id():
    assert montar_job({"entityUrn": "urn:li:algo:sem-numero", "title": "Dev"}, None) is None


def test_vaga_recomendada_e_um_job_igual_ao_das_outras_fontes():
    """O ponto do pedido: "mesmo formato e avaliacao". A vaga que vem da
    Voyager tem que ser indistinguivel de uma vaga do Gupy ou do Catho pro
    resto do sistema -- mesma classe, mesma dedup, mesmo filtro."""
    vaga = montar_job(_vaga_bruta(), _card_bruto())
    assert isinstance(vaga, Job)
    # id e chave_secundaria sao o que a dedup usa (ver database.ja_vista).
    assert vaga.id
    assert vaga.chave_secundaria == "acme tech|desenvolvedor backend python"


# ------------------------------------------------------------ SESSAO

def test_cabecalhos_derivam_o_csrf_do_jsessionid():
    """O CSRF do LinkedIn e a propria sessao ecoada de volta, prefixada de
    "ajax:". Errar isso responde 403 seco, sem dizer que foi CSRF -- e o
    tipo de bug que custa horas pra diagnosticar."""
    cab = montar_cabecalhos("LI_AT_XYZ", "SESSAO123")

    assert cab["csrf-token"] == "ajax:SESSAO123"
    assert 'JSESSIONID="ajax:SESSAO123"' in cab["cookie"]
    assert "li_at=LI_AT_XYZ" in cab["cookie"]


@pytest.mark.parametrize("bruto", ['ajax:SESSAO123', '"ajax:SESSAO123"', 'SESSAO123'])
def test_cabecalhos_normalizam_o_jsessionid_venha_como_vier(bruto):
    """O valor chega com aspas e/ou prefixo "ajax:" dependendo de onde foi
    copiado (set-cookie, DevTools, colado a mao). Os tres tem que produzir
    o mesmo cabecalho, senao "funciona pra mim" vira bug de quem copiou de
    outro lugar."""
    cab = montar_cabecalhos("LI_AT", bruto)
    assert cab["csrf-token"] == "ajax:SESSAO123"


def test_cabecalhos_pedem_a_variante_normalizada_da_api():
    """E o `accept` que faz a resposta vir no formato de lista `included`
    que parsear_resposta espera. Trocar isso quebra o parse inteiro."""
    cab = montar_cabecalhos("LI_AT", "SESSAO")
    assert cab["accept"] == "application/vnd.linkedin.normalized+json+2.1"
    assert cab["x-restli-protocol-version"] == "2.0.0"
