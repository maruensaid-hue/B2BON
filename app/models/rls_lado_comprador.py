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

PENDENTES: dict[str, str] = {
    'contrato_compra': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'documento_compras': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'evento_contrato_compra': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'evento_processo': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'processo_contratacao': 'tocada fora do contexto do tenant em: app/api/deps:(dependência), cron:sourcing_sincronizar',
}

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
