"""Classificação de RLS das tabelas do lado comprador (Public Procurement). Mora em `app/models` porque a barreira Buy/Sell (`tests/unit/test_barreira_buy_sell.py`) só deixa o próprio
lado comprador, `app/models` e as migrações citarem essas tabelas pelo nome; `app/db/rls_registro.py` apenas importa estas constantes, sem nomear nenhuma delas."""

TENANT_DIRETO: tuple[str, ...] = (
    "demanda_compra",
    "fornecedor_compras",
    "item_pca",
    "orgao_publico",
    "pesquisa_preco",
    "plano_contratacao",
    "unidade_compras",
)

# Segunda etapa (D-111): tocadas pela rotina global de sincronização (contexto de sistema) e, por isso, ficaram de fora da primeira.
TENANT_DIRETO_ETAPA2: tuple[str, ...] = (
    "contrato_compra",
    "documento_compras",
    "evento_contrato_compra",
    "evento_processo",
    "processo_contratacao",
)

PENDENTES: dict[str, str] = {}

# Tabelas do lado comprador que os contextos de sistema (rotinas sem usuário) tocam. PROVISÓRIO, como o restante de `CONTEXTOS_SISTEMA`.
SISTEMA: dict[str, dict[str, str]] = {
    "cron-sourcing-sincronizar": {
        "contrato_compra": "ler",
        "documento_compras": "ler",
        "evento_contrato_compra": "ler",
        "evento_processo": "ler",
        "processo_contratacao": "ler"
    }
}
