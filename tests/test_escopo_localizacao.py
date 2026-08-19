"""Regressao da extracao de escopo geografico de vaga remota.

Cada caso aqui saiu do jobradar.log real, da linha "Descarte por escopo"
-- o log lista o texto cru que derrubou a vaga e quantas vagas cada um
derrubou. Sao falsos negativos: vaga em pais que o projeto ACEITA, barrada
porque o texto de local nao foi reconhecido.

A metade de baixo do arquivo e o oposto: casos que PRECISAM continuar
sendo rejeitados ou resolvidos como estao. Sem eles, "consertar" o
reconhecimento de cidade reabre o vazamento de vaga americana que a
allowlist de mercado existe pra fechar.
"""

import pytest

from core.job import extrair_escopo_remoto


# (texto de local, escopo esperado) -- todos com modalidade="Remoto",
# que e como a fonte com filtro nativo (LinkedIn f_WT=2) entrega.
@pytest.mark.parametrize("local, esperado", [
    # 179 descartes no log: preposicao solta sobrando depois de tirar a
    # raiz "remot" do texto. Nao e escopo -- e remoto sem restricao.
    ("En remoto", set()),
    ("en remoto", set()),
    ("España (En remoto)", {"Espanha"}),
    # "100%" sobrevivia ao filtro de digito por causa do "%".
    ("100% remoto", set()),
    ("Remoto 100%", set()),
    # Cidade de pais aceito, sem o pais escrito junto.
    ("Zaragoza", {"Espanha"}),
    ("Braga", {"Portugal"}),
    ("Funchal", {"Portugal"}),
    ("Mendoza", {"Argentina"}),
    ("Rosario", {"Argentina"}),
    ("Bucaramanga", {"Colômbia"}),
    ("Ciudad Real", {"Espanha"}),
    # Formato "Cidade, Provincia" -- o casamento por candidato inteiro
    # nunca batia, agora casa segmento a segmento.
    ("Móstoles, Madrid", {"Espanha"}),
    ("Alcorcón, Madrid", {"Espanha"}),
    ("Itziar, Guipuzcoa", {"Espanha"}),
    ("Campanillas, Málaga provincia", {"Espanha"}),
    ("Palma de Mallorca, Illes Balears", {"Espanha"}),
    ("Madrid, Madrid provincia", {"Espanha"}),
    # Formato "Greater X" / "X Metropolitan Area" do LinkedIn.
    ("Greater Buenos Aires", {"Argentina"}),
    ("Medellín Metropolitan Area", {"Colômbia"}),
    ("Porto Metropolitan Area", {"Portugal"}),
    ("Lisbon Metropolitan Area", {"Portugal"}),
    ("Santiago Metropolitan Area", {"Chile"}),
    # Codigo postal na frente do nome.
    ("4000 Porto", {"Portugal"}),
    ("08015, Barcelona, Barcelona provincia", {"Espanha"}),
    # Sigla de estado mexicano abreviada com ponto e espaco.
    ("Monterrey, N.L.", {"México"}),
    ("San Luis Potosí, S. L. P.", {"México"}),
])
def test_escopo_de_mercado_aceito_e_reconhecido(local, esperado):
    assert extrair_escopo_remoto(local, "Remoto") == esperado


@pytest.mark.parametrize("local, esperado", [
    # Mercado de lingua inglesa: tem que continuar sendo reconhecido pra
    # poder ser rejeitado pelo filtro de mercado.
    ("Remote - US only", {"Estados Unidos"}),
    ("Remote (Austin, TX)", {"Estados Unidos"}),
    ("Remote (Seattle, WA)", {"Estados Unidos"}),
    ("Remote, but candidates must be located in the United States", {"Estados Unidos"}),
    ("Remote - India", {"Índia"}),
    # Regiao americana sem sigla: continua NAO reconhecida, que e o que
    # faz a vaga ser barrada. Se virasse "sem restricao", passaria.
    ("Remote (Greater Seattle Area)", {"seattle"}),
    # Pais fora da lista: continua reconhecido como escopo declarado
    # desconhecido (nao-vazio = reprova), nao como "sem restricao".
    ("Remote - Vietnam", {"vietnam"}),
    ("Remote - Nigeria", {"nigeria"}),
])
def test_escopo_de_mercado_nao_aceito_continua_reconhecido(local, esperado):
    assert extrair_escopo_remoto(local, "Remoto") == esperado


@pytest.mark.parametrize("local", [
    # O motivo de _CIDADES_MERCADO casar por igualdade e nao por
    # substring: "porto" e pedaco de "Porto Alegre"/"Porto Velho", e
    # "santiago" de "Santiago do Cacem". Casar por SEGMENTO mantem essa
    # protecao -- o segmento inteiro e "porto alegre", nao "porto".
    "Remoto (Porto Alegre, RS)",
    "Remoto (Porto Alegre)",
    "Porto Velho",
    "Remoto (Maceió, AL)",
    "Remoto (Belém, PA)",
    "São Paulo - SP",
    "Campo Grande, MS",
])
def test_cidade_brasileira_nao_vira_pais_estrangeiro(local):
    assert extrair_escopo_remoto(local, "Remoto") == {"Brasil"}


@pytest.mark.parametrize("local", [
    "Remoto", "Remote", "Não informado", "Home Office",
    "Remote - Worldwide", "Remote (Anywhere)",
    "Remoto (Barueri + 35 cidades)",
])
def test_remoto_sem_escopo_declarado_nao_restringe(local):
    """Conjunto vazio significa "nao ha base pra rejeitar" -- diferente de
    escopo declarado que nao foi reconhecido, que reprova."""
    assert extrair_escopo_remoto(local, "Remoto") == set()


# --------------------------------- MODALIDADE QUANDO A FONTE NAO INFORMA

from core.job import Job                     # noqa: E402
from core.perfis import PERFIL_BR, PERFIL_INTL  # noqa: E402


def _vaga(local, modalidade, titulo="Desenvolvedor Backend Python"):
    return Job(
        titulo=titulo, empresa="Empresa Teste", local=local,
        link=f"https://exemplo.com/{abs(hash((local, modalidade, titulo)))}",
        site="Teste", modalidade=modalidade,
    )


@pytest.mark.parametrize("local", [
    "Home Office", "100% Remoto", "Trabalhe de casa", "Teletrabalho",
    "Teletrabajo", "Trabajo a distancia", "Remoto", "Remote", "Anywhere",
])
def test_remoto_reconhecido_quando_a_fonte_nao_preenche_modalidade(local):
    """Nem toda fonte expoe modalidade no card. Sem o fallback pelo texto
    de local, todo o vocabulario de TERMOS_REMOTO ficava inalcancavel e a
    vaga remota era descartada."""
    assert _vaga(local, "").combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local, modalidade", [
    # A fonte declarou a modalidade: texto solto no local NAO sobrepoe.
    ("Home Office - São Paulo, SP", "Presencial"),
    ("Remoto (São Paulo, SP)", "Híbrido"),
    ("100% Remoto - Curitiba, PR", "Presencial"),
])
def test_texto_do_local_nao_sobrepoe_modalidade_declarada(local, modalidade):
    assert not _vaga(local, modalidade).combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local", ["São Paulo - SP", "Bloomington, IN"])
def test_fallback_de_modalidade_nao_abre_vaga_fora_da_regra(local):
    """Local sem nenhum vocabulario de remoto continua sendo presencial,
    mesmo com a fonte deixando o campo modalidade vazio."""
    assert not _vaga(local, "").combina_com(PERFIL_BR.regras)


def test_fallback_de_modalidade_vale_para_mercado_estrangeiro():
    """"Remote - US only" estava no teste acima, do lado do rejeita, quando
    MERCADOS_REMOTO_ACEITOS barrava mercado nao-lusofono. Com o filtro de
    mercado desligado (so remoto, pais indiferente), ele passou pro lado do
    aceita -- e continua exercitando o fallback, que e o que este arquivo
    testa: modalidade vazia, remoto reconhecido pelo texto do local."""
    assert _vaga("Remote - US only", "").combina_com(PERFIL_BR.regras)


def test_titulo_nunca_serve_de_sinal_de_local():
    """Bug original desta base: titulo e local eram concatenados, entao
    vaga americana com "Hybrid Remote" no TITULO batia "remot" e passava
    como remota. O fallback le SO o campo local."""
    vaga = _vaga("Bloomington, IN", "", titulo="Backend Developer (Hybrid Remote)")
    assert not vaga.combina_com(PERFIL_BR.regras)
