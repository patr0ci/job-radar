
from collections import Counter

from core.job import Job, RegrasFiltro


def filtrar_vagas(
    vagas: list[Job], regras: RegrasFiltro
) -> tuple[list[Job], Counter, Counter]:
    """Além da lista aprovada, devolve dois Counters de diagnóstico — ver
    MEDIDO em Job.escopo_rejeitado_por_mercado pro motivo de existirem
    (descarte era invisível no log: só dava pra ver bruta → filtrada →
    nova, nunca o porquê):

    1. escopos que causaram reprovação por mercado (quantas vagas cada um
       levou);
    2. empresas bloqueadas que derrubaram vaga que TERIA passado (ver
       Job.empresa_rejeitada_por_bloqueio) — é o número que denuncia
       entrada mal escolhida na blocklist.

    Os dois são contados no mesmo laço porque uma vaga reprovada pode ter
    mais de um motivo, e cada método já decide sozinho se o motivo dele foi
    o decisivo — não é if/elif entre eles.
    """
    aprovadas = []
    descartes_escopo: Counter = Counter()
    descartes_empresa: Counter = Counter()
    for v in vagas:
        if v.combina_com(regras):
            v.relevancia = v.pontuar_relevancia(regras)
            v.motivo = v.motivo_aprovacao(regras)
            aprovadas.append(v)
        else:
            escopo = v.escopo_rejeitado_por_mercado(regras)
            if escopo:
                descartes_escopo[", ".join(sorted(escopo))] += 1
            empresa = v.empresa_rejeitada_por_bloqueio(regras)
            if empresa:
                descartes_empresa[empresa] += 1
    return aprovadas, descartes_escopo, descartes_empresa