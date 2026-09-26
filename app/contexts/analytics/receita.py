"""Revenue Intelligence — lado vendedor (Fase 16).

Toda métrica é calculada do que está registrado, nunca estimada, e volta
com `metodologia` (o que conta e o que não conta) e `amostra` (quantos
registros sustentam o número). Sem denominador, a taxa é `None`, não zero.

Atribuição não é causalidade: "assistido por IA" e "influenciado pela
rede" dizem que houve toque registrado, não que ele causou o resultado.

Barreira Buy/Sell: nada aqui lê tabela de Public Procurement. As
métricas do lado comprador ficam no próprio contexto `procurement`.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.bids import contract as bids
from app.models.alerta_detrator import AlertaDetrator
from app.models.conta import Conta
from app.models.estagio_funil import EstagioFunil
from app.models.necessidade_oportunidade import NecessidadeOportunidade
from app.models.negocio import Negocio
from app.models.oferta import Oferta
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.sala_compra import SalaCompra
from app.models.sinal_oportunidade import SinalOportunidade

DIAS_PADRAO = 90
DIAS_RENOVACAO = 120
FEATURE_RESGATE = "map.script_resgate_conta"
# Sinais da rede por família (ver `sinal_oportunidade_service.gerar_sinais`).
TIPOS_INTENT = ("intent_compativel",)  # intenção publicada por outra empresa compatível com a minha oferta
TIPOS_MATCH = ("fit_icp", "match_intent")  # empresa que casa com meu ICP / com a minha intenção


def metrica(valor, unidade: str, metodologia: str, amostra: int, **detalhe) -> dict:
    return {"valor": valor, "unidade": unidade, "metodologia": metodologia, "amostra": amostra, **detalhe}


def _taxa(parte: int, total: int) -> float | None:
    return round(parte / total, 4) if total else None


def _janela(inicio: datetime | None, fim: datetime | None) -> tuple[datetime, datetime]:
    fim = fim or datetime.now(UTC)
    return inicio or fim - timedelta(days=DIAS_PADRAO), fim


def _sem_tz(momento: datetime) -> datetime:
    """O banco grava UTC sem fuso; compara na mesma base."""
    return momento.astimezone(UTC).replace(tzinfo=None) if momento.tzinfo else momento


class _Negocios:
    """Negócios do tenant com o tipo do estágio, carregados uma vez."""

    def __init__(self, db: Session, tenant_id: str) -> None:
        linhas = (
            db.query(Negocio, EstagioFunil.tipo)
            .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
            .filter(Negocio.tenant_id == tenant_id)
            .all()
        )
        self.todos = [(n, tipo) for n, tipo in linhas]

    def abertos(self, ids: set[int] | None = None) -> list[Negocio]:
        return [n for n, tipo in self.todos if tipo == "aberto" and (ids is None or n.id in ids)]

    def ganhos(self, inicio: datetime, fim: datetime, ids: set[int] | None = None) -> list[Negocio]:
        i, f = _sem_tz(inicio), _sem_tz(fim)
        return [n for n, tipo in self.todos
                if tipo == "ganho" and n.ganho_em and i <= _sem_tz(n.ganho_em) < f and (ids is None or n.id in ids)]


def _soma(negocios: list[Negocio]) -> float:
    return round(sum(n.valor or 0 for n in negocios), 2)


def _pipeline(negocios: list[Negocio], metodologia: str) -> dict:
    return metrica(_soma(negocios), "BRL", metodologia, len(negocios), negocios=len(negocios))


def _ids_originados_pela_rede(db: Session, tenant_id: str, negocios: _Negocios) -> set[int]:
    por_sinal = {i for (i,) in db.query(SinalOportunidade.negocio_id_gerado).filter(
        SinalOportunidade.tenant_id == tenant_id, SinalOportunidade.negocio_id_gerado.isnot(None)).all()}
    contas_da_rede = {i for (i,) in db.query(Conta.id).filter_by(tenant_id=tenant_id, origem="rede_social_signal").all()}
    return por_sinal | {n.id for n, _ in negocios.todos if n.origem == "rede_social_signal" or n.conta_id in contas_da_rede}


def _ids_influenciados_pela_rede(db: Session, tenant_id: str, negocios: _Negocios, originados: set[int]) -> set[int]:
    com_sala = {i for (i,) in db.query(SalaCompra.negocio_id).filter(SalaCompra.tenant_id_vendedor == tenant_id).all()}
    contas_com_sinal = {i for (i,) in db.query(SinalOportunidade.conta_id_gerada).filter(
        SinalOportunidade.tenant_id == tenant_id, SinalOportunidade.conta_id_gerada.isnot(None)).all()}
    tocados = com_sala | {n.id for n, _ in negocios.todos if n.conta_id in contas_com_sinal}
    return tocados - originados


def _ids_assistidos_por_ia(db: Session, tenant_id: str, negocios: _Negocios) -> set[int]:
    uso = db.query(RegistroUsoIa.entidade_tipo, RegistroUsoIa.entidade_id).filter(
        RegistroUsoIa.tenant_id == tenant_id, RegistroUsoIa.status == "sucesso",
        RegistroUsoIa.entidade_tipo.in_(("negocio", "conta")), RegistroUsoIa.entidade_id.isnot(None),
    ).distinct().all()
    negocios_ia = {i for tipo, i in uso if tipo == "negocio"}
    contas_ia = {i for tipo, i in uso if tipo == "conta"}
    necessidades = {i for (i,) in db.query(NecessidadeOportunidade.negocio_id).filter(
        NecessidadeOportunidade.tenant_id == tenant_id, NecessidadeOportunidade.origem == "ia",
        NecessidadeOportunidade.status != "descartada").distinct().all()}
    return negocios_ia | necessidades | {n.id for n, _ in negocios.todos if n.origem == "ia" or n.conta_id in contas_ia}


def _conversao_sinais(db: Session, tenant_id: str, negocios: _Negocios, inicio: datetime, fim: datetime,
                      tipos: tuple[str, ...] | None, metodologia: str) -> dict:
    consulta = db.query(SinalOportunidade).filter(
        SinalOportunidade.tenant_id == tenant_id, SinalOportunidade.criado_em >= _sem_tz(inicio),
        SinalOportunidade.criado_em < _sem_tz(fim))
    if tipos:
        consulta = consulta.filter(SinalOportunidade.tipo_sinal.in_(tipos))
    sinais = consulta.all()
    convertidos = [s for s in sinais if s.status == "convertido"]
    ids_ganhos = {n.id for n, tipo in negocios.todos if tipo == "ganho"}
    ganhos = [s for s in convertidos if s.negocio_id_gerado in ids_ganhos]
    por_tipo: dict[str, dict] = {}
    for s in sinais:
        item = por_tipo.setdefault(s.tipo_sinal, {"gerados": 0, "convertidos": 0})
        item["gerados"] += 1
        item["convertidos"] += s.status == "convertido"
    for item in por_tipo.values():
        item["taxa"] = _taxa(item["convertidos"], item["gerados"])
    return metrica(_taxa(len(convertidos), len(sinais)), "taxa", metodologia, len(sinais),
                   gerados=len(sinais), convertidos=len(convertidos), convertidos_em_ganho=len(ganhos),
                   taxa_ganho=_taxa(len(ganhos), len(sinais)), por_tipo=por_tipo)


def _conversao_ofertas(db: Session, tenant_id: str, negocios: _Negocios, inicio: datetime, fim: datetime) -> dict:
    i, f = _sem_tz(inicio), _sem_tz(fim)
    nomes = {o.id: o.nome for o in db.query(Oferta).filter_by(tenant_id=tenant_id).all()}
    por_oferta: dict = {}
    for n, tipo in negocios.todos:
        fechado_em = n.ganho_em if tipo == "ganho" else n.perdido_em if tipo == "perdido" else None
        if fechado_em is None or not (i <= _sem_tz(fechado_em) < f):
            continue
        chave = n.oferta_id
        item = por_oferta.setdefault(chave, {"oferta_id": chave, "oferta": nomes.get(chave, "Sem oferta vinculada"),
                                             "ganhos": 0, "perdidos": 0, "valor_ganho": 0.0})
        item["ganhos" if tipo == "ganho" else "perdidos"] += 1
        if tipo == "ganho":
            item["valor_ganho"] = round(item["valor_ganho"] + (n.valor or 0), 2)
    itens = sorted(por_oferta.values(), key=lambda x: x["valor_ganho"], reverse=True)
    for item in itens:
        item["taxa_ganho"] = _taxa(item["ganhos"], item["ganhos"] + item["perdidos"])
    ganhos = sum(x["ganhos"] for x in itens)
    fechados = ganhos + sum(x["perdidos"] for x in itens)
    return metrica(_taxa(ganhos, fechados), "taxa",
                   "Negócios fechados no período (ganho ou perdido) por oferta vinculada; taxa = ganhos / fechados.",
                   fechados, por_oferta=itens)


def _prevencao_churn(db: Session, tenant_id: str, negocios: _Negocios, inicio: datetime, fim: datetime) -> dict:
    i, f = _sem_tz(inicio), _sem_tz(fim)
    resgates = {c for (c,) in db.query(RegistroUsoIa.entidade_id).filter(
        RegistroUsoIa.tenant_id == tenant_id, RegistroUsoIa.feature == FEATURE_RESGATE, RegistroUsoIa.status == "sucesso",
        RegistroUsoIa.entidade_tipo == "conta", RegistroUsoIa.criado_em >= i, RegistroUsoIa.criado_em < f).all()}
    detratores = {c for (c,) in db.query(AlertaDetrator.conta_id).filter(
        AlertaDetrator.tenant_id == tenant_id, AlertaDetrator.criado_em >= i, AlertaDetrator.criado_em < f).all()}
    em_risco = resgates | detratores
    ativos = {c.id for c in db.query(Conta).filter(Conta.tenant_id == tenant_id, Conta.id.in_(em_risco or [-1]),
                                                   Conta.cliente_desde.isnot(None), Conta.cliente_cancelado_em.is_(None)).all()}
    doze_meses = f - timedelta(days=365)
    receita = [n for n, tipo in negocios.todos if tipo == "ganho" and n.conta_id in ativos and n.ganho_em and _sem_tz(n.ganho_em) >= doze_meses]
    return metrica(
        _soma(receita), "BRL",
        "Receita ganha nos últimos 12 meses de clientes que, no período, estiveram em risco com ação registrada "
        "(roteiro de resgate gerado ou alerta de detrator) e continuam clientes. Mostra o valor preservado com ação, "
        "não prova que a ação evitou o churn.",
        len(em_risco), clientes_em_risco_com_acao=len(em_risco), clientes_retidos=len(ativos),
        taxa_retencao=_taxa(len(ativos), len(em_risco)),
    )


def _renovacao_contratos_publicos(db: Session, tenant_id: str, hoje: date) -> dict:
    vigentes = bids.repositorio.VENDA.contratos_vigentes(db, tenant_id)  # só lado vendedor (S2)
    sem_fim = [c for c in vigentes if c.vigencia_fim is None]
    vencendo = [c for c in vigentes if c.vigencia_fim and 0 <= (c.vigencia_fim - hoje).days <= DIAS_RENOVACAO]
    vencidos = [c for c in vigentes if c.vigencia_fim and c.vigencia_fim < hoje]
    nao_renovaveis = [c for c in vencendo if not c.renovavel]
    return metrica(
        round(sum(c.valor or 0 for c in vencendo), 2), "BRL",
        f"Contratos públicos vigentes (lado vendedor) que vencem em até {DIAS_RENOVACAO} dias; não renováveis exigem "
        "nova licitação. Contratos sem data de fim não entram no valor e são listados à parte.",
        len(vigentes), vencendo=len(vencendo), nao_renovaveis=len(nao_renovaveis),
        valor_nao_renovavel=round(sum(c.valor or 0 for c in nao_renovaveis), 2),
        vencidos_ainda_vigentes=len(vencidos), sem_data_de_fim=len(sem_fim),
    )


def metricas(db: Session, tenant_id: str, inicio: datetime | None = None, fim: datetime | None = None,
             incluir_licitacoes: bool = False, hoje: date | None = None) -> dict:
    inicio, fim = _janela(inicio, fim)
    negocios = _Negocios(db, tenant_id)
    originados = _ids_originados_pela_rede(db, tenant_id, negocios)
    influenciados = _ids_influenciados_pela_rede(db, tenant_id, negocios, originados)
    assistidos = _ids_assistidos_por_ia(db, tenant_id, negocios)
    resultado = {
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "network_sourced_pipeline": _pipeline(
            negocios.abertos(originados),
            "Negócios abertos criados a partir de sinal da rede (sinal convertido, ou conta nascida de sinal)."),
        "network_influenced_pipeline": _pipeline(
            negocios.abertos(influenciados),
            "Negócios abertos não originados pela rede, mas com toque dela: sala de compra ou conta que recebeu sinal."),
        "ai_assisted_pipeline": _pipeline(
            negocios.abertos(assistidos),
            "Negócios abertos com uso de IA bem-sucedido registrado no negócio ou na conta, necessidade extraída por IA "
            "não rejeitada, ou negócio criado pela IA. Toque registrado, não causalidade."),
        "ai_assisted_revenue": _pipeline(
            negocios.ganhos(inicio, fim, assistidos),
            "Negócios ganhos no período que tiveram toque de IA registrado (mesmo critério do pipeline assistido)."),
        "signal_conversion": _conversao_sinais(db, tenant_id, negocios, inicio, fim, None,
                                               "Sinais da rede gerados no período; taxa = convertidos / gerados."),
        "intent_conversion": _conversao_sinais(db, tenant_id, negocios, inicio, fim, TIPOS_INTENT,
                                               "Sinais de intenção de compra publicada por outra empresa, compatível com a sua oferta."),
        "match_conversion": _conversao_sinais(db, tenant_id, negocios, inicio, fim, TIPOS_MATCH,
                                              "Sinais de empresas que casam com o seu ICP ou com a sua intenção."),
        "offer_conversion": _conversao_ofertas(db, tenant_id, negocios, inicio, fim),
        "churn_prevention_value": _prevencao_churn(db, tenant_id, negocios, inicio, fim),
    }
    if incluir_licitacoes:
        resultado["contract_renewal_risk"] = _renovacao_contratos_publicos(db, tenant_id, hoje or date.today())
    return resultado

