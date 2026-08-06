import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./predator.db"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Fallback de desenvolvimento apenas — franquia real é decisão comercial
    # pendente e vem do núcleo via PlanLimitsProvider (Seção 11 da especificação).
    franquia_contas_mes_stub_default: int = 50

    # Placeholder até a integração real com o núcleo B2B ON existir.
    core_api_base_url: str = ""

    # WhatsApp Business API (Meta) — vazio usa StubWhatsAppProvider em dev/teste.
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""

    # SMTP — vazio usa StubEmailProvider em dev/teste.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Usado para assinar tokens de opt-out (HMAC) — trocar em produção.
    secret_key: str = "changeme-dev-secret-key"

    # Degraus de rampa de aquecimento (dias de uso do canal -> limite diário).
    # Parâmetro de entregabilidade, ajustável por configuração — não é uma
    # curva comercial fechada.
    rampa_degraus_whatsapp: list[dict] = [
        {"dias": 3, "limite": 20},
        {"dias": 7, "limite": 50},
        {"dias": 14, "limite": 100},
        {"dias": 999999, "limite": 500},
    ]
    rampa_degraus_email: list[dict] = [
        {"dias": 3, "limite": 30},
        {"dias": 7, "limite": 80},
        {"dias": 14, "limite": 200},
        {"dias": 999999, "limite": 1000},
    ]

    # Google Calendar API — vazio usa StubCalendarProvider em dev/teste.
    google_calendar_access_token: str = ""
    google_calendar_id: str = "primary"

    # Padrão recomendado do limiar de qualificação — ajustável por tenant
    # (E5-H2 pede explicitamente um "padrão recomendado").
    limiar_qualificacao_padrao: float = 60.0

    # Confiança mínima (z-score) para declarar vencedora no teste A/B —
    # parâmetro estatístico, não decisão comercial (E3-H5). 1.96 ≈ 95%.
    ab_teste_confianca_z: float = 1.96

    # Limiares de entregabilidade que disparam pausa automática de canal —
    # ajustáveis por configuração, não uma curva comercial fechada (E10-H2).
    limiar_bounce_padrao: float = 0.05
    limiar_spam_padrao: float = 0.001

    # Padrão recomendado de dias após a reunião realizada para disparar a
    # pesquisa de NPS — ajustável por tenant via ConfiguracaoNps (E11-H1).
    nps_dias_apos_reuniao_padrao: int = 30

    # Retenção automática de titulares prospectados (raio-X/LGPD) — 24
    # meses sem nenhuma interação e sem ter virado cliente.
    dias_retencao_titular_inativo: int = 730

    # Autenticação real do núcleo (Onda A). Chave dedicada — não reaproveita
    # secret_key (usada para HMAC de links públicos) para segregar o risco.
    jwt_secret_key: str = "changeme-dev-jwt-secret-key-min-32-bytes-long"
    jwt_expiracao_minutos: int = 1440
    google_oauth_client_id: str = ""

    # Limiares de alerta de risco de churn dos tenants (Onda D — Motor de
    # Alta Performance) — parâmetro de alerta, ajustável, não uma curva
    # comercial fechada. O cálculo do score em si é metodologia (função
    # pura em motor_service.py), como o scoring S.H.A.R.K. do PREDATOR.
    limiar_risco_critico_tenant: float = 75.0
    limiar_risco_atencao_tenant: float = 45.0

    # Mesma metodologia acima, aplicada às contas (clientes/prospects) DE
    # um tenant — MAP de contas, visível a user/admin/super_admin dentro do
    # próprio tenant, distinto do MAP de tenants (só super_admin, cross-tenant).
    limiar_risco_critico_conta: float = 75.0
    limiar_risco_atencao_conta: float = 45.0

    # Origens do frontend autorizadas a chamar a API (CORS) — Vite dev
    # server por padrão; a origem de produção (Cloudflare Pages, Onda G)
    # entra via env var, sem mudar código (Onda F1). Texto puro (não
    # `list[str]`) de propósito: o pydantic-settings decodifica campos de
    # lista como JSON *antes* de qualquer validador rodar, e um campo de
    # texto num painel como o do Render é fácil de preencher sem colchetes
    # e aspas exatas — ver `origens_cors` abaixo para o parsing tolerante.
    cors_origins: str = "http://localhost:5173"

    # Segredo compartilhado do disparador de envio agendado (Onda I) — sem
    # ele, POST /cron/processar-envios sempre recusa (nunca abre exceção
    # pra segredo vazio). Gerado com `secrets.token_urlsafe(32)`, o mesmo
    # valor vai no Render (env var) e no GitHub Actions (repo secret).
    cron_secret: str = ""

    # URL pública onde a própria API responde — precisa ser absoluta pra
    # entrar em link/pixel dentro do corpo de um e-mail (o cliente de
    # e-mail do destinatário não sabe resolver caminho relativo). Onda I.
    url_base_api: str = "http://localhost:8000/api/v1"

    # Observabilidade (raio-X de produção) — vazio desliga o Sentry por
    # completo (no-op), sem quebrar nada em dev/teste. Preencher só exige
    # criar a conta grátis em sentry.io e colar a DSN aqui/no Render.
    sentry_dsn: str = ""

    @property
    def origens_cors(self) -> list[str]:
        """Aceita tanto JSON (`["https://a.com"]`) quanto uma lista simples
        separada por vírgula (`https://a.com,https://b.com`) (Onda G)."""
        texto = self.cors_origins.strip()
        if texto.startswith("["):
            return json.loads(texto)
        return [origem.strip() for origem in texto.split(",") if origem.strip()]

    @property
    def e_ambiente_producao(self) -> bool:
        """SQLite é usado só em dev/teste (ver `app/main.py`); qualquer outro
        banco (Postgres/Neon) é produção de verdade — sinal mais confiável
        que `app_env`, que nunca é setado de fato no Render."""
        return not self.database_url.startswith("sqlite")

    def validar_segredos_de_producao(self) -> None:
        """Recusa subir em produção com os segredos padrão do repo — sem
        isso, `secret_key`/`jwt_secret_key` ficarem no default (visível pra
        qualquer um que leia o código) deixa qualquer pessoa forjar um JWT
        de super_admin ou um token de opt-out válido, silenciosamente."""
        if not self.e_ambiente_producao:
            return
        segredos_fracos = {
            "secret_key": self.secret_key == "changeme-dev-secret-key",
            "jwt_secret_key": self.jwt_secret_key == "changeme-dev-jwt-secret-key-min-32-bytes-long",
        }
        fracos = [nome for nome, esta_fraco in segredos_fracos.items() if esta_fraco]
        if fracos:
            raise RuntimeError(
                f"Configuração insegura: {', '.join(fracos)} ainda está no valor padrão do "
                "repositório. Gere um valor forte (ex.: secrets.token_urlsafe(32)) e configure "
                "a variável de ambiente correspondente antes de subir em produção."
            )


settings = Settings()
