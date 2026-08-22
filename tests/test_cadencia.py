"""Cadencia das fontes de baixa frequencia (a cada N dias).

Ate aqui "baixa frequencia" tinha um significado so: uma vez por dia. O
perfil linkedin precisa de 2 em 2 dias, e por um motivo diferente do
original -- FREQUENCIA_BAIXA nasceu pra fonte de baixo rendimento nao pesar
no custo de todo ciclo; aqui o que esta em jogo e bloqueio da conta pessoal
do usuario numa API privada.

Por isso a trava mora no CODIGO e nao so no cron do workflow: agendamento
nao impede um workflow_dispatch manual, nem um "re-run" do GitHub Actions,
de bater no LinkedIn de novo no mesmo dia. O metadado no banco impede.

Estes testes trocam obter_metadado por um valor fixo em vez de montar um
banco: o que esta sendo verificado e a aritmetica de datas, e o banco aqui
seria so armazenamento -- montar um esconderia a regra atras de setup.
"""

from datetime import date, timedelta

import pytest

import main
from core.perfis import PERFIL_BR, PERFIL_LINKEDIN


def _com_ultimo_dia(monkeypatch, valor):
    monkeypatch.setattr(main, "obter_metadado", lambda _chave: valor)


def _dias_atras(n):
    return (date.today() - timedelta(days=n)).isoformat()


# ------------------------------------------- PERFIL DIARIO (o de sempre)

def test_sem_registro_roda(monkeypatch):
    """Primeira execucao de todas -- nada salvo, entao nao ha intervalo a
    respeitar."""
    _com_ultimo_dia(monkeypatch, None)
    assert not main._baixa_frequencia_ainda_no_intervalo(PERFIL_BR)


def test_perfil_diario_pula_se_ja_rodou_hoje(monkeypatch):
    """Comportamento identico ao de antes do intervalo existir: com o
    default de 1 dia, a pergunta e "a data salva e hoje?"."""
    _com_ultimo_dia(monkeypatch, _dias_atras(0))
    assert main._baixa_frequencia_ainda_no_intervalo(PERFIL_BR)


def test_perfil_diario_roda_de_novo_no_dia_seguinte(monkeypatch):
    _com_ultimo_dia(monkeypatch, _dias_atras(1))
    assert not main._baixa_frequencia_ainda_no_intervalo(PERFIL_BR)


# ------------------------------------------- PERFIL LINKEDIN (2 em 2 dias)

def test_linkedin_esta_configurado_pra_dois_dias():
    """Se alguem baixar isso pra 1, o radar passa a bater na API privada do
    LinkedIn todo dia -- e o teste que trava essa mudanca sem querer."""
    assert PERFIL_LINKEDIN.intervalo_baixa_frequencia_dias == 2


@pytest.mark.parametrize("dias", [0, 1])
def test_linkedin_pula_dentro_da_janela_de_dois_dias(monkeypatch, dias):
    """Rodou hoje ou ontem: nao roda. O caso `dias=1` e o que separa esta
    cadencia da diaria -- com a regra antiga ("ja rodou hoje?"), ontem
    liberava."""
    _com_ultimo_dia(monkeypatch, _dias_atras(dias))
    assert main._baixa_frequencia_ainda_no_intervalo(PERFIL_LINKEDIN)


@pytest.mark.parametrize("dias", [2, 3, 30])
def test_linkedin_roda_passados_dois_dias(monkeypatch, dias):
    _com_ultimo_dia(monkeypatch, _dias_atras(dias))
    assert not main._baixa_frequencia_ainda_no_intervalo(PERFIL_LINKEDIN)


# ------------------------------------------------------------ BORDAS

def test_data_ilegivel_libera_a_execucao(monkeypatch):
    """Valor invalido no metadado so acontece com banco mexido a mao ou
    corrompido. Rodar a mais e o erro barato; travar a fonte pra sempre
    passaria despercebido."""
    _com_ultimo_dia(monkeypatch, "ontem")
    assert not main._baixa_frequencia_ainda_no_intervalo(PERFIL_LINKEDIN)


def test_data_no_futuro_segura_a_execucao(monkeypatch):
    """Relogio do runner atrasado, ou metadado adulterado: a diferenca da
    negativa. Na duvida espera -- e o lado seguro justamente pra fonte que
    tem risco de bloqueio de conta."""
    futuro = (date.today() + timedelta(days=5)).isoformat()
    _com_ultimo_dia(monkeypatch, futuro)
    assert main._baixa_frequencia_ainda_no_intervalo(PERFIL_LINKEDIN)


def test_string_vazia_conta_como_sem_registro(monkeypatch):
    _com_ultimo_dia(monkeypatch, "")
    assert not main._baixa_frequencia_ainda_no_intervalo(PERFIL_LINKEDIN)
