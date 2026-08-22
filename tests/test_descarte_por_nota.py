"""Contrato de persistencia da vaga cortada pelo piso de relevancia.

O corte em si (relevancia < LIMIAR_RELEVANCIA_MINIMA) mora em
ciclo_de_busca, no main.py, junto de scraper/Telegram/banco -- caro de
testar inteiro. O que da pra fixar barato, e que e onde mora o risco de
verdade, e o CONTRATO DE BANCO que o corte depende:

1. vaga cortada precisa ficar SALVA, senao ja_vista() nao a reconhece e ela
   volta como "nova" a cada ciclo de 3h, pra sempre -- o mesmo bug de
   renotificacao em massa que BancoVazioSuspeito existe pra evitar, so que
   silencioso e permanente;
2. vaga cortada NAO pode entrar na fila do digest, senao o corte nao corta
   nada -- so atrasa a notificacao em algumas horas.

Os dois lados sao faceis de quebrar sem perceber: (1) some se alguem trocar
o salvar_vaga por um `continue`, achando que vaga descartada nao precisa ir
pro banco; (2) some se o default de digest_pendente mudar.
"""

import importlib

import pytest

import core.config


@pytest.fixture
def db(monkeypatch, tmp_path):
    """Banco descartavel -- e pra isso que JOBRADAR_DB_PATH existe (ver
    comentario em config.py). Recarrega os dois modulos porque DB_PATH e
    lido no import, nao a cada chamada."""
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobs_de_teste.db"))
    importlib.reload(core.config)
    import database.database as banco
    importlib.reload(banco)
    banco.iniciar_db()
    yield banco
    # Devolve os modulos ao estado do banco real, senao o proximo teste do
    # arquivo herda o tmp_path deste.
    monkeypatch.delenv("JOBRADAR_DB_PATH", raising=False)
    importlib.reload(core.config)
    importlib.reload(banco)


def _vaga(titulo="Desenvolvedor Backend Python", empresa="Empresa Teste", relevancia=4):
    from core.job import Job

    v = Job(
        titulo=titulo, empresa=empresa, local="Remoto",
        link=f"https://exemplo.com/{titulo}-{empresa}".replace(" ", "-"),
        site="Teste", modalidade="Remoto",
    )
    v.relevancia = relevancia
    return v


def test_vaga_descartada_conta_como_vista(db):
    """Sem isso ela reaparece como nova a cada ciclo, pra sempre."""
    vaga = _vaga()
    assert not db.ja_vista(vaga)

    db.salvar_vaga(vaga, perfil_chave="brasil", situacao="descartada")

    assert db.ja_vista(vaga)


def test_vaga_descartada_nao_entra_no_digest(db):
    """Se entrasse, o piso nao cortaria nada -- so adiaria a notificacao."""
    db.salvar_vaga(_vaga(), perfil_chave="brasil", situacao="descartada")

    assert db.obter_vagas_pendentes_digest("brasil") == []


def test_vaga_de_digest_continua_entrando_no_digest(db):
    """Controle do teste acima: o que muda o resultado e o
    digest_pendente, nao o fato de existir uma situacao nova."""
    db.salvar_vaga(_vaga(relevancia=6), perfil_chave="brasil", digest_pendente=True)

    pendentes = db.obter_vagas_pendentes_digest("brasil")
    assert len(pendentes) == 1


def test_situacao_padrao_continua_nova(db):
    """O parametro `situacao` entrou com default -- vaga notificada
    normalmente nao pode ter mudado de situacao junto."""
    vaga = _vaga(relevancia=8)
    db.salvar_vaga(vaga, perfil_chave="brasil")

    with db._conectar() as conn:
        situacao = conn.execute(
            "SELECT situacao FROM vagas_vistas WHERE id = ?", (vaga.id,)
        ).fetchone()[0]
    assert situacao == "nova"


def test_descartada_e_gravada_com_a_situacao_certa(db):
    """A situacao e o que permite ao relatorio_precisao.py separar depois o
    que o piso derrubou do que foi notificado de verdade."""
    vaga = _vaga()
    db.salvar_vaga(vaga, perfil_chave="brasil", situacao="descartada")

    with db._conectar() as conn:
        situacao, pendente = conn.execute(
            "SELECT situacao, digest_pendente FROM vagas_vistas WHERE id = ?",
            (vaga.id,),
        ).fetchone()
    assert situacao == "descartada"
    assert pendente == 0
