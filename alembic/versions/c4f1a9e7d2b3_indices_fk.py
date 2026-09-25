"""Fase 17: índices das chaves estrangeiras (exceto colunas de autoria).

Revision ID: c4f1a9e7d2b3
Revises: 855accb19354
Create Date: 2026-09-25
"""

from alembic import op

revision = "c4f1a9e7d2b3"
down_revision = "855accb19354"
branch_labels = None
depends_on = None

INDICES = (
    ("icp", "clonado_de_id"),
    ("oferta", "icp_id"),
    ("tenant", "tenant_pai_id"),
    ("tenant", "representante_id"),
    ("empresa_rede", "mesclada_em_id"),
    ("licenca", "plano_id"),
    ("material_oferta", "oferta_id"),
    ("pagamento_licenca", "plano_id"),
    ("regra_aprendida", "icp_id"),
    ("regra_aprendida", "oferta_id"),
    ("conexao_linkedin", "usuario_id"),
    ("convite_vitrine", "tenant_id_gerado"),
    ("demanda_compra", "unidade_id"),
    ("lista_prospeccao", "icp_id"),
    ("mensagem_rede_social", "usuario_remetente_id"),
    ("participante_sala", "usuario_id"),
    ("participante_sala", "tenant_id"),
    ("post_rede_social", "usuario_autor_id"),
    ("post_rede_social", "post_original_id"),
    ("relacionamento_empresarial", "empresa_origem_id"),
    ("reuniao_sala", "tenant_id"),
    ("stakeholder_sala", "tenant_id"),
    ("tarefa_sala", "tenant_id"),
    ("comentario_post", "usuario_id"),
    ("conta", "icp_id"),
    ("conta", "lista_prospeccao_id"),
    ("conta", "vendedor_usuario_id"),
    ("documento_sala", "canal_id"),
    ("documento_sala", "tenant_id"),
    ("mensagem_sala", "tenant_id_remetente"),
    ("mensagem_sala", "usuario_id"),
    ("reacao_post", "usuario_id"),
    ("cadencia", "conta_id"),
    ("cadencia", "icp_id"),
    ("cadencia", "oferta_id"),
    ("campo_enriquecido", "conta_id"),
    ("conta_franquia_consumo", "conta_id"),
    ("decisor", "conta_id"),
    ("descarte_conta", "conta_id"),
    ("licitacao", "conta_id"),
    ("licitacao", "oferta_id"),
    ("processo_contratacao", "unidade_id"),
    ("processo_contratacao", "item_pca_id"),
    ("registro_oportunidade", "vendedor_usuario_id"),
    ("registro_oportunidade", "conta_id"),
    ("campanha_destinatario", "decisor_id"),
    ("contrato_compra", "processo_id"),
    ("contrato_venda_publica", "licitacao_id"),
    ("contrato_venda_publica", "conta_id"),
    ("conversa_qualificacao", "conta_id"),
    ("conversa_qualificacao", "decisor_id"),
    ("email_direto", "decisor_id"),
    ("email_recebido", "decisor_id"),
    ("indicacao", "promotor_decisor_id"),
    ("indicacao", "promotor_conta_id"),
    ("indicacao", "conta_gerada_id"),
    ("negocio", "conta_id"),
    ("negocio", "vendedor_usuario_id"),
    ("negocio", "decisor_id"),
    ("negocio", "estagio_id"),
    ("negocio", "oferta_id"),
    ("pesquisa_nps", "conta_id"),
    ("pesquisa_nps", "decisor_id"),
    ("reuniao", "conta_id"),
    ("reuniao", "decisor_id"),
    ("reuniao", "reagendado_de_id"),
    ("solicitacao_desconto", "registro_oportunidade_id"),
    ("toque_cadencia", "cadencia_id"),
    ("alerta_detrator", "pesquisa_nps_id"),
    ("alerta_detrator", "conta_id"),
    ("alerta_detrator", "decisor_id"),
    ("atividade", "usuario_id"),
    ("documento_compras", "processo_id"),
    ("documento_compras", "contrato_id"),
    ("evento_contrato_compra", "contrato_id"),
    ("mensagem", "cadencia_id"),
    ("mensagem", "decisor_id"),
    ("mensagem", "toque_cadencia_id"),
    ("notificacao_vendedor", "conversa_id"),
    ("proposta_negocio", "enviada_por_usuario_id"),
    ("qualificacao_score", "conta_id"),
    ("qualificacao_score", "decisor_id"),
    ("qualificacao_score", "conversa_id"),
    ("requisito_licitacao", "documento_id"),
    ("sala_compra", "tenant_id_vendedor"),
    ("sala_compra", "negocio_id"),
    ("sinal_oportunidade", "conta_id_gerada"),
    ("sinal_oportunidade", "negocio_id_gerado"),
    ("turno_conversa", "conversa_id"),
    ("aprovacao", "mensagem_id"),
    ("tarefa_linkedin", "mensagem_id"),
    ("tarefa_linkedin", "decisor_id"),
)


def _nome(tabela: str, coluna: str) -> str:
    return f"ix_{tabela}_{coluna}"[:63]


def upgrade() -> None:
    for tabela, coluna in INDICES:
        op.create_index(_nome(tabela, coluna), tabela, [coluna], if_not_exists=True)


def downgrade() -> None:
    for tabela, coluna in reversed(INDICES):
        op.drop_index(_nome(tabela, coluna), table_name=tabela, if_exists=True)
