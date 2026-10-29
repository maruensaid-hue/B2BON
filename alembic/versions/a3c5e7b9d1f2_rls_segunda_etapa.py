"""RLS, segunda etapa (D-111, auditoria A01): as 98 tabelas que a primeira etapa deixou pendentes, mais o acesso dos contextos privilegiados.

Só PostgreSQL (no SQLite é um no-op). Continua sem mudar comportamento enquanto a aplicação conectar com o papel dono das tabelas; o efeito é de quem conecta com o papel de
execução (`b2bon_app`). O que esta migração faz:
- cria as funções auxiliares da segunda etapa (`rls_sql.FUNCOES_ETAPA2`);
- liga o RLS e cria as políticas das tabelas novas (tenant direto, duas partes, leitura compartilhada, escopo herdado e as políticas avulsas);
- cria as buscas antes do tenant das tabelas novas (entrar, redefinir senha, convite, chave de parceiro, retorno do OAuth...);
- acrescenta `rls_privilegiado` (contextos `plataforma` e `sistema:*`) a TODAS as tabelas protegidas, as da primeira etapa também.

As listas abaixo são cópia congelada do registro (`app/db/rls_registro.py`) neste ponto da história.

Downgrade: remove as políticas e o RLS das tabelas novas, tira `rls_privilegiado` das da primeira etapa e apaga as funções da segunda.

Revision ID: a3c5e7b9d1f2
Revises: e7a9c1d3f5b8
Create Date: 2026-10-29
"""
from alembic import op

from app.db import rls_sql

revision = "a3c5e7b9d1f2"
down_revision = "e7a9c1d3f5b8"
branch_labels = None
depends_on = None

# Protegidas na primeira etapa: só ganham `rls_privilegiado`.
ETAPA1 = (
    "alerta_credito", "alerta_detrator", "anexo_sourcing", "aprovacao",
    "avaliacao_sourcing", "bloqueio_contato", "cadencia", "campanha",
    "chave_api_tenant", "compra_credito", "conexao_empresa", "conexao_integracao",
    "conexao_linkedin", "configuracao_canal", "configuracao_comunicacao", "configuracao_envio",
    "configuracao_notificacao", "configuracao_nps", "configuracao_qualificacao", "configuracao_whatsapp",
    "conversa_qualificacao", "convite_cadastro", "custo_aquisicao", "custo_direto_infra",
    "decisao_go_no_go", "demanda_compra", "descarte_conta", "documento_cofre",
    "documento_ri", "email_direto", "email_recebido", "enriquecimento_nota_fiscal",
    "enriquecimento_semanal_consumo", "envio_crm", "esclarecimento_sourcing", "estado_alertas_licitacao",
    "estagio_funil", "evento_aprendizado", "execucao_sync", "faq_item",
    "fornecedor_compras", "indicacao", "indicador_financeiro_conta", "indicador_ri",
    "item_pca", "item_template_proposta", "link_captura_lead", "lista_prospeccao",
    "material_oferta", "mensagem", "mensagem_rede_social", "negocio",
    "notificacao_vendedor", "orgao_publico", "pagamento_licenca", "pausa_canal",
    "perfil_inteligencia", "pesquisa_decisores", "pesquisa_decisores_empresa", "pesquisa_decisores_transicao",
    "pesquisa_nps", "pesquisa_preco", "plano_contratacao", "proposta_negocio",
    "qualificacao_score", "recebimento_governo", "registro_crm_externo", "registro_envio_diario",
    "registro_idempotencia", "registro_reputacao_canal", "registro_supressao_permanente", "regra_aprendida",
    "regra_auto_aprovacao", "sala_corporativa", "tarefa_linkedin", "template_proposta",
    "template_whatsapp", "toque_cadencia", "turno_conversa", "unidade_compras",
    "vinculo_externo",
)

TENANT_DIRETO = (
    "alerta_licitacao", "apuracao_comissao", "assinatura_webhook_parceiro", "assinatura_webhook_tenant",
    "atividade", "audit_log", "autorizacao_oauth_pendente", "cache_resposta_ia",
    "campanha_destinatario", "carteira_creditos", "chave_api_parceiro", "coleta_site_conta",
    "comissao_representante", "componente_contrato_governo", "configuracao_agente_corporativo", "configuracao_coleta_fonte",
    "configuracao_credito_tenant", "configuracao_email_api", "configuracao_email_smtp", "configuracao_painel",
    "configuracao_relatorio", "conhecimento_corporativo", "conta", "conta_franquia_consumo",
    "conteudo_pagina_site", "contrato_compra", "contrato_governo", "contrato_sourcing",
    "contrato_venda_publica", "decisor", "documento_compras", "documento_licitacao",
    "documento_sourcing", "enriquecimento_carteira", "enriquecimento_compra", "enriquecimento_estorno_compra",
    "enriquecimento_movimento", "entrega_webhook", "evento_contrato_compra", "evento_contrato_sourcing",
    "evento_dominio", "evento_processo", "evento_sourcing", "execucao_coleta_fonte",
    "execucao_ia", "fila_enriquecimento_conta", "icp", "interacao_conta",
    "interacao_tenant", "item_sourcing", "licenca", "licitacao",
    "lote_credito", "movimento_credito", "necessidade_oportunidade", "notificacao_rede_social",
    "oferta", "orcamento_ia", "participante_sourcing", "periodo_assinatura_governo",
    "processo_contratacao", "processo_sourcing", "proposta_item_sourcing", "proposta_sourcing",
    "registro_oportunidade", "registro_uso_ia", "regra_alerta_licitacao", "requisito_licitacao",
    "requisito_sourcing", "reuniao", "sinal_oportunidade", "solicitacao_desconto",
    "usuario", "verificacao_empresa",
)

TENANT_NULAVEL = ('empresa_rede', 'enriquecimento_config_plano', 'oportunidade_governo')

TENANT_COLUNA = {'sala_compra': 'tenant_id_vendedor'}

DUAS_PARTES = {'convite_vitrine': ('tenant_id_origem', 'tenant_id_gerado'),
 'seguidor_empresa': ('tenant_id_seguidor', 'tenant_id_seguido'),
 'relacionamento_empresarial': ('tenant_id_origem', 'tenant_id_destino'),
 'pergunta_agente_corporativo': ('tenant_id_alvo', 'tenant_id_perguntante')}

LEITURA_COMPARTILHADA = ('perfil_empresa', 'post_rede_social', 'comentario_post', 'reacao_post', 'intent')

HERDADAS = {'midia_post': ('post_id', 'b2bon_post_cascata_do_tenant', True),
 'campo_enriquecido': ('conta_id', 'b2bon_conta_do_tenant', False),
 'redefinicao_senha': ('usuario_id', 'b2bon_usuario_do_tenant', False),
 'evento_webhook_parceiro': ('assinatura_id', 'b2bon_assinatura_parceiro_do_tenant', False),
 'canal_sala': ('sala_id', 'b2bon_sala_do_tenant', False),
 'mensagem_sala': ('canal_id', 'b2bon_canal_do_tenant', False),
 'documento_sala': ('sala_id', 'b2bon_sala_do_tenant', False),
 'participante_sala': ('sala_id', 'b2bon_sala_do_tenant', False),
 'reuniao_sala': ('sala_id', 'b2bon_sala_do_tenant', False),
 'stakeholder_sala': ('sala_id', 'b2bon_sala_do_tenant', False),
 'tarefa_sala': ('sala_id', 'b2bon_sala_do_tenant', False)}

# (tabela, nome, comando, USING, WITH CHECK)
POLITICAS_ESPECIAIS = [('comentario_post', 'rls_apagar_do_post', 'DELETE', 'b2bon_post_cascata_do_tenant(post_id)', None),
 ('empresa_rede', 'rls_diretorio', 'SELECT', "b2bon_escopo() = 'tenant'", None),
 ('empresa_rede', 'rls_identidade_ajusta', 'UPDATE', "b2bon_escopo() = 'tenant'", "b2bon_escopo() = 'tenant'"),
 ('empresa_rede', 'rls_identidade_cria', 'INSERT', None, "b2bon_escopo() = 'tenant'"),
 ('enriquecimento_config_plano', 'rls_padrao_do_plano', 'SELECT', "tenant_id IS NULL AND b2bon_escopo() = 'tenant'", None),
 ('licenca', 'rls_cobradora', 'SELECT', 'tenant_id = b2bon_cobrador()', None),
 ('notificacao_rede_social', 'rls_insercao_entre_tenants', 'INSERT', None, "b2bon_escopo() = 'tenant'"),
 ('participante_sourcing', 'rls_convidado_le', 'SELECT', 'empresa_rede_tenant_id = b2bon_tenant()', None),
 ('post_rede_social', 'rls_apagar_repost', 'DELETE', 'b2bon_post_cascata_do_tenant(id)', None),
 ('processo_sourcing', 'rls_convidado', 'SELECT', 'b2bon_processo_convidado(id)', None),
 ('reacao_post', 'rls_apagar_do_post', 'DELETE', 'b2bon_post_cascata_do_tenant(post_id)', None),
 ('registro_oportunidade', 'rls_rede', 'SELECT', 'rede_raiz_tenant_id = b2bon_raiz_da_rede()', None),
 ('relacionamento_empresarial', 'rls_visibilidade', 'SELECT',
  "visibilidade = 'publica' OR (visibilidade = 'conexoes' AND (b2bon_conectado(tenant_id_origem) OR b2bon_conectado(tenant_id_destino)))", None),
 ('sala_compra', 'rls_sala', 'SELECT', 'b2bon_sala_do_tenant(sala_corporativa_id)', None)]

# (escopo, tabela, predicado)
BUSCAS = [('autenticacao', 'usuario', 'id::text = b2bon_chave()'), ('chave-api-parceiro', 'chave_api_parceiro', 'chave_hash = b2bon_chave()'),
 ('convite-vitrine', 'convite_vitrine', 'codigo = b2bon_chave()'), ('login', 'usuario', 'lower(email) = b2bon_chave()'),
 ('pagamento-referencia', 'enriquecimento_compra', 'id::text = b2bon_chave()'),
 ('portal-fornecedor', 'participante_sourcing', 'token_hash = b2bon_chave()'), ('recall-bot', 'reuniao', 'bot_id = b2bon_chave()'),
 ('redefinicao', 'redefinicao_senha', 'token = b2bon_chave()'), ('redefinicao', 'usuario', 'b2bon_usuario_tem_redefinicao(id)')]


def _executar(comandos) -> None:
    for comando in comandos:
        op.execute(comando)


def _tabelas_novas() -> list[str]:
    return sorted({*TENANT_DIRETO, *TENANT_NULAVEL, *TENANT_COLUNA, *DUAS_PARTES, *LEITURA_COMPARTILHADA, *HERDADAS})


def upgrade() -> None:
    """Funções, políticas das tabelas novas, buscas e `rls_privilegiado` em todas (só PostgreSQL)."""
    if op.get_bind().dialect.name != "postgresql":
        return
    _executar(rls_sql.sql_funcoes_etapa2())
    for tabela in TENANT_DIRETO:
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_tenant_direto(tabela))
    for tabela in TENANT_NULAVEL:
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_tenant_direto(tabela))
    for tabela, coluna in TENANT_COLUNA.items():
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_tenant_direto(tabela, coluna))
    for tabela, colunas in DUAS_PARTES.items():
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_duas_partes(tabela, colunas))
    for tabela in LEITURA_COMPARTILHADA:
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_leitura_compartilhada(tabela))
    for tabela, (coluna_fk, funcao, compartilhada) in HERDADAS.items():
        _executar(rls_sql.sql_habilitar(tabela))
        _executar(rls_sql.sql_herdada(tabela, coluna_fk, funcao, leitura_compartilhada=compartilhada))
    for tabela, nome, comando, usando, verificando in POLITICAS_ESPECIAIS:
        _executar(rls_sql.sql_politica(tabela, nome, comando, usando, verificando))
    for escopo, tabela, predicado in BUSCAS:
        _executar(rls_sql.sql_busca(escopo, tabela, predicado))
    for tabela in (*ETAPA1, *_tabelas_novas()):
        _executar(rls_sql.sql_privilegiado(tabela))


def downgrade() -> None:
    """Desfaz a segunda etapa: tabelas novas voltam a ficar sem política e sem RLS; as da primeira só perdem `rls_privilegiado` (só PostgreSQL)."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for tabela in ETAPA1:
        op.execute(f"DROP POLICY IF EXISTS rls_privilegiado ON {tabela}")
    for tabela in _tabelas_novas():
        _executar(rls_sql.sql_reverter(tabela))
    _executar(rls_sql.sql_remover_funcoes_etapa2())
