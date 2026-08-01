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


settings = Settings()
