"""Carrega, numa leitura só e sempre filtrada pelo tenant, tudo que os
motores determinísticos precisam. Os motores (discovery, nbo, nba,
white_space) são funções puras sobre `DadosOportunidade`."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.map.contract import listar_interacoes, score_risco_conta
from app.contexts.opportunity import necessidades as necessidades_mod
from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.necessidade_oportunidade import NecessidadeOportunidade
from app.models.negocio import Negocio
from app.models.oferta import Oferta
from app.models.reuniao import Reuniao
from app.services.errors import NaoEncontrado


@dataclass
class DadosOportunidade:
    agora: datetime
    negocio: Negocio
    estagio: EstagioFunil
    conta: Conta
    decisores: list[Decisor]
    necessidades: list[NecessidadeOportunidade]
    necessidades_da_conta: list[NecessidadeOportunidade]
    ofertas: list[Oferta]
    ofertas_compradas_ids: set[int]
    valor_ganho_conta: float
    ultima_atividade_em: datetime | None
    reunioes: list[Reuniao]
    interacoes: list = field(default_factory=list)
    risco_map: dict | None = None

    @property
    def dias_sem_atividade(self) -> int:
        referencia = self.ultima_atividade_em or self.negocio.criado_em or self.agora
        return (self.agora - referencia.replace(tzinfo=UTC)).days

    @property
    def e_cliente(self) -> bool:
        return bool(self.ofertas_compradas_ids) or self.valor_ganho_conta > 0 or self.conta.cliente_desde is not None


def carregar(db: Session, tenant_id: str, negocio_id: int, agora: datetime | None = None) -> DadosOportunidade:
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")
    conta = db.query(Conta).filter_by(id=negocio.conta_id, tenant_id=tenant_id).one()
    estagio = db.query(EstagioFunil).filter_by(id=negocio.estagio_id).one()
    return _montar(db, tenant_id, conta, negocio=negocio, estagio=estagio, agora=agora)


def carregar_conta(db: Session, tenant_id: str, conta_id: int, agora: datetime | None = None) -> DadosOportunidade:
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return _montar(db, tenant_id, conta, negocio=None, estagio=None, agora=agora)


def _montar(db, tenant_id, conta, *, negocio, estagio, agora) -> DadosOportunidade:
    ganhos = (
        db.query(Negocio.oferta_id, Negocio.valor)
        .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(Negocio.tenant_id == tenant_id, Negocio.conta_id == conta.id, EstagioFunil.tipo == "ganho")
        .all()
    )
    ultima_atividade = None
    if negocio is not None:
        ultima_atividade = (
            db.query(func.max(Atividade.criado_em))
            .filter(Atividade.tenant_id == tenant_id, Atividade.negocio_id == negocio.id)
            .scalar()
        )
    interacoes = listar_interacoes(db, tenant_id, conta.id)
    return DadosOportunidade(
        agora=agora or datetime.now(UTC),
        negocio=negocio,
        estagio=estagio,
        conta=conta,
        decisores=db.query(Decisor).filter_by(tenant_id=tenant_id, conta_id=conta.id).all(),
        necessidades=necessidades_mod.listar(db, tenant_id, negocio.id) if negocio is not None else [],
        necessidades_da_conta=necessidades_mod.listar_da_conta(db, tenant_id, conta.id),
        ofertas=db.query(Oferta).filter_by(tenant_id=tenant_id, disponivel_para_venda=True).order_by(Oferta.id).all(),
        ofertas_compradas_ids={oferta_id for oferta_id, _ in ganhos if oferta_id is not None},
        valor_ganho_conta=float(sum(valor or 0 for _, valor in ganhos)),
        ultima_atividade_em=ultima_atividade,
        reunioes=(
            db.query(Reuniao).filter_by(tenant_id=tenant_id, conta_id=conta.id).order_by(Reuniao.data_hora.desc()).limit(10).all()
        ),
        interacoes=interacoes,
        risco_map=score_risco_conta(db, conta) if (interacoes or ganhos or conta.cliente_desde) else None,
    )
