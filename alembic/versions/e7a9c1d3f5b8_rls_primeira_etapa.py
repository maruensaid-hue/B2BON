"""RLS, primeira etapa (D-110, auditoria A01): funções auxiliares e políticas por tenant nas tabelas já validadas.

Só PostgreSQL (no SQLite é um no-op). Liga o RLS e cria as políticas, mas **não muda o comportamento enquanto a aplicação conectar com o papel dono das tabelas** (o dono não
passa pelo RLS; não se usa `FORCE`). O efeito começa quando a API passa a conectar com um papel sem `BYPASSRLS` (docs/b2bon/RLS.md). As listas abaixo são cópia congelada do
registro (`app/db/rls_registro.py`) neste ponto da história: tabela nova ganha a política na própria migração dela.

Downgrade: remove toda política `rls_*`, desliga o RLS das tabelas e apaga as funções `b2bon_*`.

Revision ID: e7a9c1d3f5b8
Revises: d4f6a8c0e2b4
Create Date: 2026-10-28
"""
from alembic import op

from app.db import rls_sql

revision = "e7a9c1d3f5b8"
down_revision = "d4f6a8c0e2b4"
branch_labels = None
depends_on = None

TENANT_DIRETO = (
    "alerta_credito", "alerta_detrator", "anexo_sourcing", "aprovacao",
    "avaliacao_sourcing", "bloqueio_contato", "cadencia", "campanha",
    "chave_api_tenant", "compra_credito", "conexao_integracao", "conexao_linkedin",
    "configuracao_canal", "configuracao_comunicacao", "configuracao_envio", "configuracao_notificacao",
    "configuracao_nps", "configuracao_qualificacao", "configuracao_whatsapp", "conversa_qualificacao",
    "convite_cadastro", "custo_aquisicao", "custo_direto_infra", "decisao_go_no_go",
    "demanda_compra", "descarte_conta", "documento_cofre", "documento_ri",
    "email_direto", "email_recebido", "enriquecimento_nota_fiscal", "enriquecimento_semanal_consumo",
    "envio_crm", "esclarecimento_sourcing", "estado_alertas_licitacao", "estagio_funil",
    "evento_aprendizado", "execucao_sync", "faq_item", "fornecedor_compras",
    "indicacao", "indicador_financeiro_conta", "indicador_ri", "item_pca",
    "item_template_proposta", "link_captura_lead", "lista_prospeccao", "material_oferta",
    "mensagem", "negocio", "notificacao_vendedor", "orgao_publico",
    "pagamento_licenca", "pausa_canal", "perfil_inteligencia", "pesquisa_decisores",
    "pesquisa_decisores_empresa", "pesquisa_decisores_transicao", "pesquisa_nps", "pesquisa_preco",
    "plano_contratacao", "proposta_negocio", "qualificacao_score", "recebimento_governo",
    "registro_crm_externo", "registro_envio_diario", "registro_idempotencia", "registro_reputacao_canal",
    "registro_supressao_permanente", "regra_aprendida", "regra_auto_aprovacao", "tarefa_linkedin",
    "template_proposta", "template_whatsapp", "toque_cadencia", "turno_conversa",
    "unidade_compras", "vinculo_externo",
)

DUAS_PARTES = {
    "conexao_empresa": ("tenant_id_origem", "tenant_id_destino"),
    "mensagem_rede_social": ("tenant_id_remetente", "tenant_id_destinatario"),
    "sala_corporativa": ("tenant_id_a", "tenant_id_b"),
}

# (escopo, tabela, predicado): busca de uma linha antes de saber o tenant, só nas tabelas protegidas acima.
BUSCAS = (
    ('convite-cadastro', 'convite_cadastro', 'codigo = b2bon_chave()'),
    ('whatsapp-numero', 'configuracao_whatsapp', 'phone_number_id = b2bon_chave()'),
    ('captura-lead', 'link_captura_lead', 'codigo = b2bon_chave()'),
    ('integracao-webhook', 'conexao_integracao', 'webhook_token_hash = b2bon_chave()'),
    ('chave-api', 'chave_api_tenant', 'chave_hash = b2bon_chave()'),
    ('pagamento-referencia', 'pagamento_licenca', 'id::text = b2bon_chave()'),
    ('pagamento-referencia', 'compra_credito', 'id::text = b2bon_chave()'),
)


def _executar(comandos) -> None:
    for comando in comandos:
        op.execute(comando)


def upgrade() -> None:
    """Cria as funções, liga o RLS e cria as políticas das tabelas protegidas (só PostgreSQL)."""
    if op.get_bind().dialect.name != "postgresql":
        return
    _executar(rls_sql.sql_funcoes())
    for tabela in TENANT_DIRETO:
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_tenant_direto(tabela))
    for tabela, colunas in DUAS_PARTES.items():
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_duas_partes(tabela, colunas))
    for escopo, tabela, predicado in BUSCAS:
        _executar(rls_sql.sql_busca(escopo, tabela, predicado))


def downgrade() -> None:
    """Remove as políticas, desliga o RLS e apaga as funções (só PostgreSQL)."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for tabela in (*TENANT_DIRETO, *DUAS_PARTES):
        _executar(rls_sql.sql_reverter(tabela))
    _executar(rls_sql.sql_remover_funcoes())
