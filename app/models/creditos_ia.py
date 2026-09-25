"""B2B ON AI Credits — modelo comercial (Fase 15).

Crédito é capacidade de inteligência, não token. O preço ao cliente vem
do catálogo de pacotes (versionado) e o consumo vem do catálogo de
workloads (pesos versionados); o custo real (LLM, dados, busca…) é medido
à parte, e a margem é a diferença. Ver `docs/b2bon/09_AI_FINOPS.md`.

Saldo não é um número solto: é a soma dos lotes (`lote_credito`) ativos,
e toda mudança passa pelo extrato (`movimento_credito`).
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PacoteCreditos(Base):
    """Pacote de top-up, versionado. `creditos`/`preco` nulos = sob consulta
    (Enterprise). Nova versão = nova linha; a anterior ganha `valido_ate`."""

    __tablename__ = "pacote_credito"
    __table_args__ = (UniqueConstraint("codigo", "versao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    moeda: Mapped[str] = mapped_column(String, default="BRL")
    creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preco: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String, default="ATIVO")  # ATIVO | CONTACT_SALES | INATIVO
    validade_meses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    valido_de: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valido_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CatalogoCreditos(Base):
    """Versão do catálogo de workloads (CREDIT_CATALOG_V1, V2…). Só uma
    ATIVA por vez; a troca exige aprovação administrativa auditada."""

    __tablename__ = "catalogo_credito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    versao: Mapped[str] = mapped_column(String, unique=True)
    numero: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="RASCUNHO")  # RASCUNHO | ATIVO | ARQUIVADO
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    aprovado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    vigente_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WorkloadIa(Base):
    """Operação de IA vendida em créditos. `creditos_base` é o peso; com
    `politica_variavel` (ex.: por página) o consumo fica entre
    `creditos_min` e `creditos_max`."""

    __tablename__ = "workload_ia"
    __table_args__ = (UniqueConstraint("catalogo_id", "codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalogo_id: Mapped[int] = mapped_column(ForeignKey("catalogo_credito.id"), index=True)
    codigo: Mapped[str] = mapped_column(String)
    modulo: Mapped[str] = mapped_column(String)
    nome: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    classe: Mapped[str] = mapped_column(String)  # C0 | C1 | C2 | C3
    creditos_base: Mapped[float] = mapped_column(Numeric(12, 2))
    creditos_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    creditos_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    politica_variavel: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    politica_modelo: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    custo_max_usd: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    margem_alvo: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    requer_aprovacao: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class LoteCreditos(Base):
    """Bucket de créditos do tenant (carteira compartilhada = soma dos lotes)."""

    __tablename__ = "lote_credito"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)  # SUBSCRIPTION | TOPUP | PROMOTIONAL | ADJUSTMENT | ENTERPRISE_OVERAGE
    origem: Mapped[str] = mapped_column(String)
    referencia: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    concedido_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quantidade_original: Mapped[float] = mapped_column(Numeric(18, 4))
    quantidade_restante: Mapped[float] = mapped_column(Numeric(18, 4))
    receita_por_credito_brl: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    status: Mapped[str] = mapped_column(String, default="ATIVO")  # ATIVO | ESGOTADO | EXPIRADO | ESTORNADO


class ExecucaoIa(Base):
    """Uma execução de workload: estimativa → reserva → execução →
    liquidação (ou liberação/estorno). Idempotente por `idempotency_key`:
    retry técnico nunca cobra duas vezes."""

    __tablename__ = "execucao_ia"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String)
    workload_codigo: Mapped[str] = mapped_column(String, index=True)
    catalogo_versao: Mapped[str] = mapped_column(String)
    classe: Mapped[str] = mapped_column(String)
    modulo: Mapped[str] = mapped_column(String, index=True)
    feature: Mapped[str | None] = mapped_column(String, nullable=True)
    agente: Mapped[str | None] = mapped_column(String, nullable=True)
    gatilho: Mapped[str | None] = mapped_column(String, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plano_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parametros: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)  # RESERVADA | LIQUIDADA | LIBERADA | ESTORNADA
    creditos_estimados: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    creditos_reservados: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    creditos_liquidados: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    creditos_excedente: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    chamadas: Mapped[int] = mapped_column(Integer, default=0)
    custo_llm_usd: Mapped[float] = mapped_column(Numeric(14, 6), default=0)
    custo_dados_usd: Mapped[float] = mapped_column(Numeric(14, 6), default=0)
    custo_total_usd: Mapped[float] = mapped_column(Numeric(14, 6), default=0)
    custo_desconhecido: Mapped[bool] = mapped_column(Boolean, default=False)
    economia_cache_usd: Mapped[float] = mapped_column(Numeric(14, 6), default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    cambio_usd_brl: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    custo_total_brl: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    receita_brl: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    lucro_bruto_brl: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    margem_bruta: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    motivo_estorno: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    liquidado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CompraCreditos(Base):
    """Compra de pacote (top-up). Os créditos só entram com o pagamento
    confirmado pelo webhook (idempotente por `pagamento_id_externo`)."""

    __tablename__ = "compra_credito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    pacote_id: Mapped[int] = mapped_column(ForeignKey("pacote_credito.id"), index=True)
    pacote_codigo: Mapped[str] = mapped_column(String)
    pacote_versao: Mapped[int] = mapped_column(Integer)
    creditos: Mapped[int] = mapped_column(Integer)
    preco: Mapped[float] = mapped_column(Numeric(14, 2))
    moeda: Mapped[str] = mapped_column(String, default="BRL")
    validade_meses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origem: Mapped[str] = mapped_column(String, default="MANUAL")  # MANUAL | AUTO_RECARGA
    status: Mapped[str] = mapped_column(String, default="PENDENTE")  # PENDENTE | APROVADA | REJEITADA
    preferencia_id_externo: Mapped[str | None] = mapped_column(String, nullable=True)
    url_checkout: Mapped[str | None] = mapped_column(String, nullable=True)
    pagamento_id_externo: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lote_credito.id"), nullable=True, index=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConfiguracaoCreditosTenant(Base):
    """Preferências e limites do tenant: recarga automática (só com
    consentimento explícito), excedente pós-pago (Enterprise) e budget guard."""

    __tablename__ = "configuracao_credito_tenant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), unique=True)
    franquia_personalizada: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Enterprise: pool próprio
    recarga_ativa: Mapped[bool] = mapped_column(Boolean, default=False)
    recarga_limiar: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recarga_pacote_codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    recarga_consentido_por: Mapped[str | None] = mapped_column(String, nullable=True)
    recarga_consentido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    excedente_ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    excedente_orcamento_mensal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excedente_limite_suave: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excedente_limite_rigido: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excedente_aprovado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    orcamento_mensal_creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limite_diario_creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limite_usuario_creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limite_api_creditos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limites_modulo_percentual: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    limites_agente_creditos: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    percentual_alerta: Mapped[int] = mapped_column(Integer, default=80)
    parada_rigida: Mapped[bool] = mapped_column(Boolean, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AlertaCreditos(Base):
    """Limiar de uso atingido no período (80/95/100%), uma vez por nível."""

    __tablename__ = "alerta_credito"
    __table_args__ = (UniqueConstraint("tenant_id", "periodo", "nivel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    periodo: Mapped[str] = mapped_column(String)
    nivel: Mapped[int] = mapped_column(Integer)
    percentual: Mapped[float] = mapped_column(Numeric(6, 2))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CacheRespostaIa(Base):
    """Cache de resposta por tenant (só features marcadas como cacheáveis).
    O hit não chama o provedor; créditos continuam cobrados (a economia
    vira margem, salvo política comercial explícita)."""

    __tablename__ = "cache_resposta_ia"

    chave: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    feature: Mapped[str] = mapped_column(String)
    modelo: Mapped[str | None] = mapped_column(String, nullable=True)
    conteudo: Mapped[str] = mapped_column(String)
    custo_original_usd: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime)
