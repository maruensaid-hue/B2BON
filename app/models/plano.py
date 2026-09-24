from sqlalchemy import JSON, Boolean, Float, Integer, String
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
    # Nulo = sem limite — mesmo padrão dos limites de enriquecimento e
    # retenção abaixo. Usado pelo plano "Teste" (raio-X 2026-09-22: admin
    # gratuito precisa convidar quantos vendedores quiser, sem tocar nas
    # demais restrições do plano).
    max_usuarios: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    # Mesmo padrão nullable=sem-teto dos limites de enriquecimento acima,
    # mas de ciclo MENSAL (não semanal) — raio-X 2026-09-22, pedido do
    # usuário pra restringir também por volume de cadência/campanha
    # criada, não só por usuários e franquia de contas.
    limite_cadencias_mes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limite_campanhas_mes: Mapped[int | None] = mapped_column(Integer, nullable=True)

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

    # Contratação avulsa por módulo (raio-X 2026-09-24) — lista de
    # "map"/"predator"/"crm" que esse plano libera (mesmo padrão JSON já
    # usado em `Cadencia.canais`/`Usuario.tutoriais_modulo_vistos`).
    # `categoria` só organiza a exibição no picker de checkout ("suite" =
    # os 5 planos originais, com os 3 módulos sempre juntos; "modulo" =
    # os planos avulsos novos, com só 1 módulo cada) — não tem nenhum
    # papel na checagem de acesso, que olha só `modulos_contratados`.
    modulos_contratados: Mapped[list] = mapped_column(JSON, default=list)
    categoria: Mapped[str] = mapped_column(String, default="suite", server_default="suite")
