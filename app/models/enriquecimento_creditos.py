"""Governança de créditos de ENRIQUECIMENTO (pesquisa de decisores em provedor pago).

Contabilidade separada dos créditos de IA (`creditos_ia`/`carteira_creditos`): nenhuma tabela, lote ou movimento é compartilhado, então
não existe conversão nem compensação entre as duas categorias. A unidade é **1 crédito = 1 contato revelado pelo provedor**; é uma
convenção de contagem, não um preço (o custo monetário por contato não está definido no sistema e não é inferido). Ver
`docs/b2bon/GOVERNANCA_CREDITOS_ENRIQUECIMENTO.md`.

Regras que o modelo carrega:

* o razão (`enriquecimento_movimento`) é **append-only**: atualizar ou apagar uma linha pelo ORM levanta erro; correção é novo lançamento;
* saldo e reservado são somas do razão, nunca um número solto (`delta_saldo` / `delta_reservado`);
* configuração de plano e orçamento global são versionadas (nova versão = nova linha; a anterior ganha `valido_ate`);
* campo de configuração nulo significa "não definido" e bloqueia (nunca vira número padrão).
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnriquecimentoCarteira(Base):
    """Linha-trava por tenant (`SELECT … FOR UPDATE`): serializa reservas, consumos e concessões do mesmo tenant. Não guarda saldo."""

    __tablename__ = "enriquecimento_carteira"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EnriquecimentoConfigPlano(Base):
    """Parâmetros de enriquecimento de um plano (ou, com `tenant_id`, condição contratual de um tenant que prevalece sobre o plano).

    Exatamente um entre `plano_id` e `tenant_id` é preenchido. Todo número é decisão comercial e vem de quem cadastra; nulo = não definido
    (a pesquisa fica bloqueada e o tenant é encaminhado ao comercial). Os campos obrigatórios para liberar a pesquisa estão em
    `app/contexts/enriquecimento/config.py::CAMPOS_OBRIGATORIOS`."""

    __tablename__ = "enriquecimento_config_plano"
    __table_args__ = (
        UniqueConstraint("plano_id", "versao", name="uq_enriq_config_plano_versao"),
        UniqueConstraint("tenant_id", "versao", name="uq_enriq_config_tenant_versao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plano_id: Mapped[int | None] = mapped_column(ForeignKey("plano.id"), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenant.id"), nullable=True, index=True)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    franquia_creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)  # concedida a cada período
    periodicidade: Mapped[str | None] = mapped_column(String, nullable=True)  # mensal | unica (POC / Free Trial)
    decisores_por_empresa_padrao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decisores_por_empresa_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    itens_por_lote_max: Mapped[int | None] = mapped_column(Integer, nullable=True)  # empresas por pesquisa
    limite_periodo_creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)  # teto extra de consumo+reserva no mês (opcional)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    valido_de: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valido_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EnriquecimentoOrcamentoGlobal(Base):
    """Orçamento global de créditos por provedor (soma de todos os tenants). Sem linha vigente com limite = chamadas ao provedor bloqueadas.
    Alterar o limite cria nova versão (administrativo, auditado)."""

    __tablename__ = "enriquecimento_orcamento_global"
    __table_args__ = (UniqueConstraint("provedor", "versao", name="uq_enriq_orcamento_provedor_versao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provedor: Mapped[str] = mapped_column(String, index=True)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    limite_creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)  # por mês-calendário (UTC)
    alerta_percentual: Mapped[int] = mapped_column(Integer, default=80)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    valido_de: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valido_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PesquisaDecisores(Base):
    """Uma pesquisa de decisores sobre um conjunto EXPLÍCITO de empresas. Nasce numa prévia (estado `criada`, com estimativa) e só avança
    quando o usuário confirma essa mesma prévia (`selecao_hash`). Estados: criada, validada, reservada, enviada, em_processamento,
    concluida, parcial, falha, cancelada, reconciliada."""

    __tablename__ = "pesquisa_decisores"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_pesquisa_decisores_idempotencia"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provedor: Mapped[str] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String, index=True)
    decisores_por_empresa: Mapped[int] = mapped_column(Integer)
    origem_decisores: Mapped[str] = mapped_column(String)  # padrao_plano | informado_usuario
    config_origem: Mapped[str] = mapped_column(String)  # tenant | plano
    config_id: Mapped[int] = mapped_column(Integer)
    config_versao: Mapped[int] = mapped_column(Integer)
    total_empresas: Mapped[int] = mapped_column(Integer, default=0)  # selecionadas
    total_maximo: Mapped[int] = mapped_column(Integer, default=0)  # créditos no pior caso (a buscar × empresas elegíveis)
    estimativa: Mapped[dict] = mapped_column(JSON, default=dict)
    selecao_hash: Mapped[str] = mapped_column(String)
    previa_expira_em: Mapped[datetime] = mapped_column(DateTime)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmada_por: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creditos_reservados: Mapped[int] = mapped_column(Integer, default=0)
    creditos_consumidos: Mapped[int] = mapped_column(Integer, default=0)
    requer_reconciliacao: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PesquisaDecisoresEmpresa(Base):
    """Uma empresa selecionada na pesquisa. Estados: pendente, deduplicada, enviado, concluido, sem_resultados, falha, ambiguo, cancelado."""

    __tablename__ = "pesquisa_decisores_empresa"
    __table_args__ = (UniqueConstraint("pesquisa_id", "conta_id", name="uq_pesquisa_decisores_empresa_conta"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pesquisa_id: Mapped[str] = mapped_column(ForeignKey("pesquisa_decisores.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    estado: Mapped[str] = mapped_column(String, default="pendente")
    decisores_existentes: Mapped[int] = mapped_column(Integer, default=0)  # já obtidos do mesmo provedor antes
    decisores_solicitados: Mapped[int] = mapped_column(Integer, default=0)  # o que ainda falta buscar (limite enviado ao provedor)
    decisores_retornados: Mapped[int] = mapped_column(Integer, default=0)
    creditos_reservados: Mapped[int] = mapped_column(Integer, default=0)
    creditos_consumidos: Mapped[int] = mapped_column(Integer, default=0)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    ids_provedor: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ids opacos devolvidos pelo provedor (sem dado pessoal)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PesquisaDecisoresTransicao(Base):
    """Histórico de transições (da pesquisa, ou de uma empresa quando `item_id` está preenchido). Append-only."""

    __tablename__ = "pesquisa_decisores_transicao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pesquisa_id: Mapped[str] = mapped_column(ForeignKey("pesquisa_decisores.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado_anterior: Mapped[str | None] = mapped_column(String, nullable=True)
    estado_novo: Mapped[str] = mapped_column(String)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    ator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EnriquecimentoMovimento(Base):
    """Razão imutável de créditos de enriquecimento. `delta_saldo` mexe no saldo; `delta_reservado` mexe na parte retida por pesquisa em curso.
    Disponível = Σ delta_saldo − Σ delta_reservado.

    Tipos: CONCESSAO, RENOVACAO, RESERVA, CONSUMO, LIBERACAO, ESTORNO, EXPIRACAO, AJUSTE, RECONCILIACAO."""

    __tablename__ = "enriquecimento_movimento"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_enriq_movimento_idempotencia"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo: Mapped[str] = mapped_column(String, index=True)
    delta_saldo: Mapped[int] = mapped_column(Integer, default=0)
    delta_reservado: Mapped[int] = mapped_column(Integer, default=0)
    disponivel_apos: Mapped[int] = mapped_column(Integer, default=0)
    provedor: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    periodo: Mapped[str | None] = mapped_column(String, nullable=True)  # AAAA-MM do evento
    pesquisa_id: Mapped[str | None] = mapped_column(ForeignKey("pesquisa_decisores.id"), nullable=True, index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origem: Mapped[str | None] = mapped_column(String, nullable=True)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    ator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # só em concessão de franquia
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


def _bloquear_alteracao(_mapper, _connection, alvo) -> None:
    raise RuntimeError(f"{type(alvo).__name__} é append-only: corrija com um novo lançamento, nunca alterando ou apagando o existente.")


for _modelo in (EnriquecimentoMovimento, PesquisaDecisoresTransicao):
    event.listen(_modelo, "before_update", _bloquear_alteracao)
    event.listen(_modelo, "before_delete", _bloquear_alteracao)
