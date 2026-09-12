from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Plano(Base):
    """Plano comercial — linha de dados, não constante no código (Onda A).

    POC/Starter/Professional/Enterprise nascem como registros aqui, não
    como valores fixos no código — mesma regra seguida em toda onda
    anterior para número de decisão comercial.
    """

    __tablename__ = "plano"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True)
    franquia_contas_mes: Mapped[int] = mapped_column(Integer)
    max_usuarios: Mapped[int] = mapped_column(Integer)
    preco_mensal: Mapped[float] = mapped_column(Float)
    # False só pro plano "Teste" (raio-X): esse plano só pode ser
    # concedido por convite gratuito administrativo, nunca escolhido
    # livremente no cadastro self-service (POST /auth/registrar-vitrine).
    visivel_self_service: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Nulo = sem limite (nenhum plano hoje). Todo plano tem valor
    # configurado, proporcional à franquia mensal (raio-X 2026-08-28) —
    # pesquisas de enriquecimento de site/contatos ficam bloqueadas até a
    # semana seguinte quando o limite estoura (`enriquecimento_limite_
    # service`); campo continua nullable pra suportar um plano futuro
    # deliberadamente sem teto.
    limite_enriquecimento_site_semanal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limite_enriquecimento_contatos_semanal: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Gancho de upgrade além de volume (raio-X 2026-09-09): recursos que só
    # fazem sentido pra quem já opera em escala (teste A/B, auto-aprovação,
    # webhook, API de parceiros, revenda), não recursos do dia a dia — por
    # isso ficam de fora do "core" (CRM, cadência básica, WhatsApp/e-mail).
    permite_ab_teste_cadencia: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    permite_auto_aprovacao: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    permite_webhook_relatorio: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    permite_api_parceiros: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    permite_subtenants: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    permite_registro_oportunidade: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Nulo = sem limite — mesmo padrão dos limites de enriquecimento acima.
    retencao_dias_relatorio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retencao_dias_auditoria: Mapped[int | None] = mapped_column(Integer, nullable=True)
