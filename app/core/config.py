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

    materiais_storage_path: str = "./storage/materiais"

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


settings = Settings()
