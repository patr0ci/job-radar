"""Regras de negocio do usuario, escritas como teste executavel.

Estas regras sao a especificacao do que o JobRadar deve ou nao notificar.
Ate aqui elas viviam so no config.py -- e a lista CIDADES tinha divergido
em dois sentidos ao mesmo tempo (faltava Manaus, sobravam quatro cidades
fora da regra) sem que nenhum dos 76 testes existentes percebesse.

Regra ATUAL (perfil BR recalibrado pra vaga de DESENVOLVEDOR), resumida:
  PERFIL BR -> SO remoto, de qualquer lugar do mundo. Presencial e
               hibrido sao rejeitados em qualquer cidade, e nenhum
               mercado e barrado -- "Remote - US only" e "Remote - India"
               entram igual a "Remoto - Brasil".
  EXTERIOR  -> perfil internacional segue como estava (Dados/BI, so
               remoto em mercado de lingua portuguesa/espanhola). Nao
               roda em producao hoje (main.py --perfil brasil), mas a
               regra continua testada pra nao apodrecer.

O requisito anterior (hibrido/presencial nas seis cidades do Nordeste,
remoto so de mercado Brasil/LATAM/Iberia) saiu inteiro. Os testes que o
verificavam nao foram apagados: foram INVERTIDOS, com as mesmas cidades e
os mesmos mercados, pra que a volta acidental da whitelist quebre teste
em vez de passar despercebida.
"""

import pytest

from core.job import Job
from core.perfis import PERFIL_BR, PERFIL_INTL


def _vaga(titulo, local, modalidade):
    return Job(
        titulo=titulo, empresa="Empresa Teste", local=local,
        link=f"https://exemplo.com/{abs(hash((titulo, local, modalidade)))}",
        site="Teste", modalidade=modalidade,
    )


# As cidades que a configuracao ANTERIOR aceitava presencial/hibrido: as
# seis obrigatorias do requisito antigo mais Maceio e Aracaju. Cidade com
# a UF DE VERDADE de cada uma.
#
# Continuam aqui de proposito, agora do lado do "rejeita": sao exatamente
# os casos que voltariam a passar se alguem repovoasse CIDADES sem
# perceber que o requisito mudou.
#
# (Antes era so a lista de nomes, e o teste montava o local como
# f"{cidade} - PB" pra todas — o que da "Maceio - PB", "Natal - PB",
# "Manaus - PB". Geograficamente errado, e passava porque o filtro so
# olhava o nome e ignorava a UF. Quando a checagem de UF entrou (ver
# _UF_DA_CIDADE em core/job.py), esses 12 casos falharam — corretamente.
# Fica registrado porque e um teste que dava verde afirmando algo falso.)
CIDADES_DO_REQUISITO_ANTIGO = [
    ("Campina Grande", "PB"),
    ("João Pessoa", "PB"),
    ("Recife", "PE"),
    ("Natal", "RN"),
    ("Caruaru", "PE"),
    ("Manaus", "AM"),
    ("Maceió", "AL"),
    ("Aracaju", "SE"),
]

TITULO_DEV = "Desenvolvedor Backend Python"


# ---------------------------------------------------------------- BRASIL

@pytest.mark.parametrize("modalidade", ["Híbrido", "Presencial"])
@pytest.mark.parametrize("cidade, uf", CIDADES_DO_REQUISITO_ANTIGO)
def test_br_hibrido_e_presencial_e_rejeitado_ate_nas_cidades_antigas(cidade, uf, modalidade):
    """Requisito atual e SO REMOTO -- nem as cidades que a configuracao
    anterior aceitava valem mais."""
    local = f"{cidade} - {uf}"
    assert not _vaga(TITULO_DEV, local, modalidade).combina_com(PERFIL_BR.regras)


# Variacoes de escrita que as fontes realmente usam -- separador, acento e
# caixa nao podem mudar o resultado. Com CIDADES so-remoto, nenhuma delas
# passa; o que este teste garante e que a rejeicao nao depende de grafia.
@pytest.mark.parametrize("local", [
    "Campina Grande", "Campina Grande - PB", "Campina Grande, PB",
    "Campina Grande/PB", "CAMPINA GRANDE - PB", "campina grande, pb",
    "João Pessoa - PB", "Joao Pessoa - PB",
    "Manaus - AM", "Manaus, AM", "Manaus/AM",
    "Recife - PE", "Caruaru, PE", "Natal/RN",
])
def test_br_variacoes_de_escrita_da_cidade_nao_furam_o_so_remoto(local):
    assert not _vaga(TITULO_DEV, local, "Híbrido").combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("modalidade", ["Híbrido", "Presencial"])
@pytest.mark.parametrize("local", [
    "São Paulo - SP", "Belo Horizonte, MG", "Salvador - BA",
    "Rio de Janeiro, RJ", "Curitiba - PR", "Brasília, DF",
    "Fortaleza - CE", "Porto Alegre - RS",
    "Jaboatão dos Guararapes - PE", "Teresina - PI",
    "São Luís - MA", "Petrolina - PE",
])
def test_br_hibrido_e_presencial_fora_das_cidades_e_rejeitado(local, modalidade):
    assert not _vaga(TITULO_DEV, local, modalidade).combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local", [
    "Remoto", "Remoto (São Paulo, SP)", "Remoto (Manaus, AM)",
    "Remoto - Brasil", "Remote, Brazil", "Remoto (Belo Horizonte, MG)",
])
def test_br_remoto_no_brasil_e_aceito_de_qualquer_cidade(local):
    """Remoto nao tem restricao de cidade -- a cidade que aparece entre
    parenteses e so a sede da empresa."""
    assert _vaga(TITULO_DEV, local, "Remoto").combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local", [
    "Remote - US only", "Remote, United States", "Remote (Austin, TX)",
    "Remote - India", "Remote - Worldwide", "Remote - Europe",
    "Remote - Canada", "Remote (Anywhere)",
])
def test_br_remoto_de_qualquer_mercado_e_aceito(local):
    """INVERSAO DELIBERADA do teste anterior (era
    test_br_remoto_de_mercado_nao_aceito_e_rejeitado, com US e India do
    lado do rejeita): o requisito passou a ser "o pais nao importa, o
    importante e ser remoto", implementado com
    MERCADOS_REMOTO_ACEITOS = None.

    Vale saber o que se abre mão aqui: vaga "Remote - US only" costuma
    exigir residencia/autorizacao de trabalho no pais, e agora chega no
    Telegram igual as outras. Foi decisao explicita, nao descuido -- pra
    voltar a barrar, basta repovoar MERCADOS_REMOTO_ACEITOS em config.py
    (a lista antiga esta registrada la em comentario)."""
    assert _vaga(TITULO_DEV, local, "Remoto").combina_com(PERFIL_BR.regras)


# --------------------------------------------------------- INTERNACIONAL

@pytest.mark.parametrize("local", [
    "Remote - Spain", "Madrid, Spain", "España (En remoto)",
    "Remote - Mexico", "Ciudad de México, México", "Remote - Portugal",
    "Remote - Latin America", "Remote - Colombia", "Buenos Aires, Argentina",
])
def test_intl_remoto_em_mercado_aceito_e_aceito(local):
    assert _vaga("Data Analyst", local, "Remoto").combina_com(PERFIL_INTL.regras)


@pytest.mark.parametrize("modalidade", ["Híbrido", "Presencial"])
@pytest.mark.parametrize("local", [
    "Madrid, Spain", "Barcelona, España", "Lisboa, Portugal",
    "Ciudad de México, México", "Buenos Aires, Argentina",
])
def test_intl_hibrido_e_presencial_sempre_rejeitado(local, modalidade):
    """Do exterior so interessa vaga remota -- nem mesmo em Portugal ou
    Espanha vale presencial/hibrida."""
    assert not _vaga("Data Analyst", local, modalidade).combina_com(PERFIL_INTL.regras)


@pytest.mark.parametrize("local", [
    "Remote - US only", "Remote, United States", "Remote (Seattle, WA)",
    "Remote, but candidates must be located in the United States",
    "Remote - India", "Remote - United Kingdom",
])
def test_intl_remoto_de_mercado_de_lingua_inglesa_e_rejeitado(local):
    assert not _vaga("Data Analyst", local, "Remoto").combina_com(PERFIL_INTL.regras)


def test_intl_titulo_hibrido_vence_a_classificacao_da_fonte():
    """O filtro nativo do LinkedIn as vezes marca como remota uma vaga que
    o proprio anuncio chama de hibrida -- o titulo vence."""
    vaga = _vaga("Data Analyst (Analista de Datos) - Hybrid", "Madrid, Spain", "Remoto")
    assert vaga.modalidade == "Híbrido"
    assert not vaga.combina_com(PERFIL_INTL.regras)


def test_intl_remoto_sem_mercado_declarado_exige_idioma_no_titulo():
    """Sem pais declarado nao da pra saber o mercado -- ai o titulo precisa
    dizer o idioma. Sem nenhum dos dois sinais, a vaga nao entra."""
    assert _vaga("Data Analyst (Spanish speaker)", "Remote - Worldwide", "Remoto").combina_com(PERFIL_INTL.regras)
    assert not _vaga("Data Analyst", "Remote - Worldwide", "Remoto").combina_com(PERFIL_INTL.regras)


# ------------------------------------------------------------------ CARGO

@pytest.mark.parametrize("titulo, esperado", [
    # --- cargo forte: passa sozinho
    ("Desenvolvedor de Software Pleno", True),
    ("Software Engineer", True),
    ("Frontend Developer", True),
    ("Desenvolvedor Web", True),

    # --- cargo ambiguo: so com qualificador tecnico junto. E este caminho,
    # nao o de cargo forte, que cobre a forma como Gupy e LinkedIn de fato
    # escrevem titulo de vaga -- casamento por substring, entao pega
    # "Desenvolvedor(a)", "Desenvolvedora" e "Pessoa Desenvolvedora".
    ("Desenvolvedor", False),
    ("Desenvolvedor(a) Back-end", True),
    ("Pessoa Desenvolvedora Fullstack", True),
    ("Desenvolvedora Front-end React", True),
    ("Analista de Sistemas", False),
    ("Analista de Sistemas .NET", True),

    # --- ferramenta no titulo: so com palavra de cargo junto
    ("Especialista React", True),
    ("Recrutador Tech para squad React", False),

    # --- ruido que o novo vocabulario poderia deixar entrar
    ("Desenvolvedor de Negócios", False),      # vendas
    ("Business Developer", False),             # vendas
    ("Engenheiro Civil", False),
    ("Engenheiro de Produção", False),
    ("Programador de Produção", False),        # PCP na industria, nao software
    ("Vendedor Externo", False),

    # --- area vizinha que NAO e o alvo: o radar mudou de dados pra dev,
    # entao o vocabulario antigo tem que ficar de fora agora.
    ("Analista de Dados Pleno", False),
    ("Analista de BI", False),
    ("Engenheiro de Dados", False),
    ("Analista de Power BI", False),
])
def test_cargo_no_titulo(titulo, esperado):
    assert _vaga(titulo, "Remoto", "Remoto").combina_com(PERFIL_BR.regras) is esperado


# ---------------------------------- LOCAL PRESENCIAL, EM QUALQUER GRAFIA
#
# A checagem de UF (_UF_DA_CIDADE em core/job.py) foi escrita pra separar
# "Campina Grande - PB" de "Campina Grande do Sul - PR" quando CIDADES era
# uma whitelist de verdade. Hoje nada presencial passa, entao os dois lados
# daquela distincao caem no mesmo lugar -- o que este bloco garante e que
# NENHUMA grafia de cidade fura o so-remoto, nem a que era aceita nem a que
# era rejeitada.
#
# A logica de UF continua exercitada pelos testes de escopo REMOTO (ver
# test_filtro.py: "Remoto (Maceió, AL)" tem que resolver Brasil e nao
# Alabama), que e onde ela ainda muda resultado.
@pytest.mark.parametrize("local", [
    # Cidade que a whitelist antiga aceitava.
    "Campina Grande - PB", "CAMPINA GRANDE - PB", "Campina Grande, PB",
    "Campina Grande/PB", "Natal - RN", "Recife - PE", "Recife, PE",
    "Manaus - AM", "Caruaru - PE", "Joao Pessoa - PB", "Maceio - AL",
    "Aracaju - SE",
    # Cidade de nome parecido, estado diferente -- MEDIDO numa fonte real:
    # "CAMPINA GRANDE DO SUL - PR" era aceita como se fosse Campina
    # Grande/PB. Sao cidades diferentes, a 2.500 km.
    "Campina Grande do Sul - PR", "Natal da Serra - MG",
    "Recife - SP", "Manaus - PR",
    # Sem UF declarada.
    "Recife", "Natal", "Manaus", "Campina Grande",
    "Vaga em Recife", "Recife, Pernambuco, Brasil",
])
def test_nenhuma_cidade_passa_em_presencial(local):
    assert not _vaga(TITULO_DEV, local, "Presencial").combina_com(PERFIL_BR.regras)
