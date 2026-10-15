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
from app.models.icp import ICP
from app.models.interacao_conta import InteracaoConta
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


def carregar(
    db: Session, tenant_id: str, negocio_id: int, agora: datetime | None = None,
    usuario_id: int | None = None, restrito: bool = False,
) -> DadosOportunidade:
    consulta = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id)
    if restrito:
        consulta = (
            consulta.join(Conta, Conta.id == Negocio.conta_id)
            .outerjoin(ICP, ICP.id == Conta.icp_id)
            .filter(
                Conta.tenant_id == tenant_id,
                Negocio.vendedor_usuario_id == usuario_id,
                ((Conta.vendedor_usuario_id == usuario_id) | (Conta.criado_por_usuario_id == usuario_id)
                 | (ICP.criador_usuario_id == usuario_id)),
                ((Conta.vendedor_usuario_id.is_(None)) | (Conta.vendedor_usuario_id == usuario_id)),
            )
        )
    negocio = consulta.one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")
    conta = db.query(Conta).filter_by(id=negocio.conta_id, tenant_id=tenant_id).one()
    estagio = db.query(EstagioFunil).filter_by(id=negocio.estagio_id).one()
    return _montar(
        db, tenant_id, conta, negocio=negocio, estagio=estagio, agora=agora,
        usuario_id=usuario_id, restrito=restrito,
    )


def carregar_conta(
    db: Session, tenant_id: str, conta_id: int, agora: datetime | None = None,
    usuario_id: int | None = None, restrito: bool = False,
) -> DadosOportunidade:
    consulta = db.query(Conta).outerjoin(ICP, ICP.id == Conta.icp_id).filter(
        Conta.id == conta_id, Conta.tenant_id == tenant_id
    )
    if restrito:
        consulta = consulta.filter(
            ((Conta.vendedor_usuario_id == usuario_id) | (Conta.criado_por_usuario_id == usuario_id)
             | (ICP.criador_usuario_id == usuario_id)),
            ((Conta.vendedor_usuario_id.is_(None)) | (Conta.vendedor_usuario_id == usuario_id)),
        )
    conta = consulta.one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return _montar(
        db, tenant_id, conta, negocio=None, estagio=None, agora=agora,
        usuario_id=usuario_id, restrito=restrito,
    )


def _montar(db, tenant_id, conta, *, negocio, estagio, agora, usuario_id=None, restrito=False) -> DadosOportunidade:
    ganhos_query = (
        db.query(Negocio.oferta_id, Negocio.valor)
        .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(Negocio.tenant_id == tenant_id, Negocio.conta_id == conta.id, EstagioFunil.tipo == "ganho")
    )
    if restrito:
        ganhos_query = ganhos_query.filter(Negocio.vendedor_usuario_id == usuario_id)
    ganhos = ganhos_query.all()
    ultima_atividade = None
    if negocio is not None:
        ultima_atividade = (
            db.query(func.max(Atividade.criado_em))
            .filter(Atividade.tenant_id == tenant_id, Atividade.negocio_id == negocio.id)
            .scalar()
        )
    if restrito:
        interacoes = (
            db.query(InteracaoConta)
            .filter_by(tenant_id=tenant_id, conta_id=conta.id, criado_por_usuario_id=usuario_id)
            .order_by(InteracaoConta.criado_em.desc())
            .all()
        )
    else:
        interacoes = listar_interacoes(db, tenant_id, conta.id)
    consulta_decisores = db.query(Decisor).filter_by(tenant_id=tenant_id, conta_id=conta.id)
    if restrito:
        icp_proprio = (
            conta.icp_id is not None
            and db.query(ICP.id).filter_by(id=conta.icp_id, tenant_id=tenant_id, criador_usuario_id=usuario_id).first()
            is not None
        )
        if not icp_proprio:
            consulta_decisores = consulta_decisores.filter(Decisor.criado_por_usuario_id == usuario_id)
    decisores = consulta_decisores.all()
    consulta_reunioes = db.query(Reuniao).filter_by(tenant_id=tenant_id, conta_id=conta.id)
    if restrito:
        decisor_ids = [d.id for d in decisores]
        if decisor_ids:
            consulta_reunioes = consulta_reunioes.filter(Reuniao.decisor_id.in_(decisor_ids))
        else:
            consulta_reunioes = consulta_reunioes.filter(Reuniao.id == -1)
    reunioes = consulta_reunioes.order_by(Reuniao.data_hora.desc()).limit(10).all()
    return DadosOportunidade(
        agora=agora or datetime.now(UTC),
        negocio=negocio,
        estagio=estagio,
        conta=conta,
        decisores=decisores,
        necessidades=necessidades_mod.listar(db, tenant_id, negocio.id) if negocio is not None else [],
        necessidades_da_conta=necessidades_mod.listar_da_conta(
            db, tenant_id, conta.id, usuario_id=usuario_id, restrito=restrito
        ),
        ofertas=db.query(Oferta).filter_by(tenant_id=tenant_id, disponivel_para_venda=True).order_by(Oferta.id).all(),
        ofertas_compradas_ids={oferta_id for oferta_id, _ in ganhos if oferta_id is not None},
        valor_ganho_conta=float(sum(valor or 0 for _, valor in ganhos)),
        ultima_atividade_em=ultima_atividade,
        reunioes=reunioes,
        interacoes=interacoes,
        # Score MAP da conta agrega histórico de todo o tenant; não exibi-lo
        # a um vendedor evita inferir atividade/receita de oportunidades alheias.
        risco_map=None if restrito else (score_risco_conta(db, conta) if (interacoes or ganhos or conta.cliente_desde) else None),
    )
