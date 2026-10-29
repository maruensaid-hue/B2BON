"""Funções de RLS que leem as tabelas unificadas de Sourcing (`*_sourcing`). Moram em `app/models` porque a barreira do Sourcing (`tests/unit/test_barreira_sourcing.py`)
só deixa o próprio contexto e `app/models` citarem essas tabelas em SQL; `app/db/rls_sql.py` apenas importa os textos."""

_DEFINER = "SECURITY DEFINER STABLE SET search_path = public, pg_temp"

# Convite de fornecedor endereçado ao tenant do contexto: empresa da rede convidada para um processo de OUTRO tenant. A empresa convidada lê o convite e o processo (para listar
# os convites que recebeu); a rodada em si (itens, propostas, anexos) ela só abre depois de a aplicação conferir o convite, no contexto do comprador (`portal.por_empresa`).
FUNCOES = (
    f"""CREATE OR REPLACE FUNCTION b2bon_processo_convidado(integer) RETURNS boolean LANGUAGE sql {_DEFINER} AS $$
    SELECT EXISTS (SELECT 1 FROM participante_sourcing p WHERE p.processo_id = $1 AND p.empresa_rede_tenant_id = b2bon_tenant()) $$""",
)
