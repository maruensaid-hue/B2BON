"""Registro único do que o RLS libera além do "tenant do usuário" (D-110). A migração `rls_primeira_etapa` e os testes leem as MESMAS definições, então política e código não divergem.

Três tipos de exceção, todas explícitas e estreitas:

1. `BUSCAS` — procurar UMA linha antes de saber o tenant (a pessoa que entra, o token de um convite). O escopo libera só `SELECT` e só a linha cuja chave coincide com
   `app.chave`; depois da busca o código troca para o contexto do tenant encontrado (`rls.definir_tenant`) e tudo o que muda dados acontece nele.
2. `CONTEXTOS_SISTEMA` — tarefas sem usuário (cron, webhooks). Cada nome lista as tabelas que pode tocar e se pode escrever. Não existe um contexto "tudo": quando a tarefa
   trabalha tenant a tenant, ela usa `rls.contexto_tenant` por volta, não um contexto de sistema.
3. `LEITURA_COMPARTILHADA` — dados que o produto mostra a outras empresas por desenho (diretório e feed do Shoal): a leitura é liberada, a escrita continua só do dono.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import rls_lado_comprador as _comprador


@dataclass(frozen=True)
class Busca:
    tabela: str
    predicado: str  # SQL booleano sobre as colunas da tabela e `b2bon_chave()`


BUSCAS: dict[str, tuple[Busca, ...]] = {
    "autenticacao": (Busca("usuario", "id::text = b2bon_chave()"),),
    "login": (Busca("usuario", "lower(email) = b2bon_chave()"),),
    "redefinicao": (
        Busca("redefinicao_senha", "token = b2bon_chave()"),
        Busca("usuario", "b2bon_usuario_tem_redefinicao(id)"),
    ),
    "convite-cadastro": (Busca("convite_cadastro", "codigo = b2bon_chave()"),),
    "convite-vitrine": (Busca("convite_vitrine", "codigo = b2bon_chave()"),),
    "whatsapp-numero": (Busca("configuracao_whatsapp", "phone_number_id = b2bon_chave()"),),
    "captura-lead": (Busca("link_captura_lead", "codigo = b2bon_chave()"),),
    "integracao-webhook": (Busca("conexao_integracao", "webhook_token_hash = b2bon_chave()"),),
    "portal-fornecedor": (Busca("participante_sourcing", "token_hash = b2bon_chave()"),),
    "chave-api": (Busca("chave_api_tenant", "chave_hash = b2bon_chave()"),),
    "recall-bot": (Busca("reuniao", "bot_id = b2bon_chave()"),),
    # o id vem da referência do pagamento que o provedor devolveu, depois de a assinatura do webhook ser conferida
    "pagamento-referencia": (
        Busca("pagamento_licenca", "id::text = b2bon_chave()"),
        Busca("compra_credito", "id::text = b2bon_chave()"),
        Busca("enriquecimento_compra", "id::text = b2bon_chave()"),
    ),
}

# nome -> {tabela: "ler" | "escrever"}
# PROVISÓRIO: as listas abaixo vêm do que os testes exercitam (sonda); as rotinas globais podem tocar mais do que a suíte cobre. Por isso nenhuma tabela que elas tocam
# entrou em `TENANT_DIRETO` nesta etapa, e só passam a valer como política depois de revisadas rotina a rotina.
CONTEXTOS_SISTEMA: dict[str, dict[str, str]] = {
    "cron-suspender-licencas-vencidas": {"assinatura_webhook_parceiro": "ler", "audit_log": "escrever", "licenca": "escrever"},
    "cron-podar-historicos": {"alerta_licitacao": "escrever", "cache_resposta_ia": "escrever", "coleta_site_conta": "ler", "entrega_webhook": "escrever", "evento_dominio": "escrever", "execucao_coleta_fonte": "ler", "licitacao": "ler"},
    "cron-podar-recorte-cnpj": {"icp": "ler"},
    "cron-disparar-webhooks-parceiros": {},
    "cron-processar-fila-enriquecimento": {"atividade": "escrever", "audit_log": "escrever", "carteira_creditos": "escrever", "coleta_site_conta": "escrever", "configuracao_credito_tenant": "escrever", "conta": "escrever", "conteudo_pagina_site": "escrever", "decisor": "ler", "enriquecimento_movimento": "escrever", "execucao_ia": "escrever", "fila_enriquecimento_conta": "escrever", "licenca": "ler", "lote_credito": "escrever", "movimento_credito": "escrever", "orcamento_ia": "ler", "registro_uso_ia": "escrever"},
    "cron-disparar-relatorios-periodicos": {"configuracao_relatorio": "ler"},
    "cron-enviar-lembretes-cobranca": {"licenca": "ler"},
    "cron-expirar-registros-oportunidade": {"registro_oportunidade": "escrever"},
    "cron-repassar-comissoes": {},
    "cron-processar-eventos": {"assinatura_webhook_tenant": "ler", "entrega_webhook": "escrever", "evento_dominio": "escrever"},
    "cron-creditos-ia": {"carteira_creditos": "escrever", "configuracao_credito_tenant": "ler", "enriquecimento_carteira": "ler", "enriquecimento_config_plano": "ler", "execucao_ia": "ler", "licenca": "ler", "lote_credito": "escrever", "movimento_credito": "escrever", "periodo_assinatura_governo": "ler"},
    "cron-integracoes-crm": {},
    "cron-integracoes-crm-diario": {},
    "cron-coletar-licitacoes": {"audit_log": "escrever", "configuracao_coleta_fonte": "ler", "execucao_coleta_fonte": "escrever", "licitacao": "escrever", "processo_sourcing": "escrever"},
    "cron-processar-alertas-licitacoes": {"regra_alerta_licitacao": "ler"},
    "cron-sourcing-sincronizar": {"contrato_venda_publica": "ler", "documento_licitacao": "ler", "licitacao": "ler", "requisito_licitacao": "ler"},
    "webhook-envio-verificacao": {"configuracao_email_api": "ler"},
}
for _nome, _tabelas in _comprador.SISTEMA.items():
    CONTEXTOS_SISTEMA[_nome].update(_tabelas)

# --- Classificação de TODAS as tabelas (primeira etapa) --------------------------------------------------------------------------------------------
# Protegidas por tenant direto: política `rls_tenant` (+ leitura ampliada pela hierarquia). Entram aqui só as tabelas que a sonda (tests/rls_sonda.py) viu, na suíte inteira,
# sendo tocadas apenas dentro do contexto do tenant dono da linha.
TENANT_DIRETO: tuple[str, ...] = (
    "alerta_credito", "alerta_detrator", "anexo_sourcing", "aprovacao",
    "avaliacao_sourcing", "bloqueio_contato", "cadencia", "campanha",
    "chave_api_tenant", "compra_credito", "conexao_integracao", "conexao_linkedin",
    "configuracao_canal", "configuracao_comunicacao", "configuracao_envio", "configuracao_notificacao",
    "configuracao_nps", "configuracao_qualificacao", "configuracao_whatsapp", "conversa_qualificacao",
    "convite_cadastro", "custo_aquisicao", "custo_direto_infra", "decisao_go_no_go",
    "descarte_conta", "documento_cofre", "documento_ri", "email_direto",
    "email_recebido", "enriquecimento_nota_fiscal", "enriquecimento_semanal_consumo", "envio_crm",
    "esclarecimento_sourcing", "estado_alertas_licitacao", "estagio_funil", "evento_aprendizado",
    "execucao_sync", "faq_item", "indicacao", "indicador_financeiro_conta",
    "indicador_ri", "item_template_proposta", "link_captura_lead", "lista_prospeccao",
    "material_oferta", "mensagem", "negocio", "notificacao_vendedor",
    "pagamento_licenca", "pausa_canal", "perfil_inteligencia", "pesquisa_decisores",
    "pesquisa_decisores_empresa", "pesquisa_decisores_transicao", "pesquisa_nps", "proposta_negocio",
    "qualificacao_score", "recebimento_governo", "registro_crm_externo", "registro_envio_diario",
    "registro_idempotencia", "registro_reputacao_canal", "registro_supressao_permanente", "regra_aprendida",
    "regra_auto_aprovacao", "tarefa_linkedin", "template_proposta", "template_whatsapp",
    "toque_cadencia", "turno_conversa", "vinculo_externo",
) + _comprador.TENANT_DIRETO

# Ligam duas empresas por desenho: cada parte vê e altera a linha (política `rls_partes`).
DUAS_PARTES: dict[str, tuple[str, str]] = {
    'conexao_empresa': ('tenant_id_origem', 'tenant_id_destino'),
    'mensagem_rede_social': ('tenant_id_remetente', 'tenant_id_destinatario'),
    'sala_corporativa': ('tenant_id_a', 'tenant_id_b'),
}

# Leitura compartilhada por desenho e escopo herdado: nenhuma tabela entra nesta etapa (os geradores existem em `rls_sql.py` e são testados em tabela de prova).
LEITURA_COMPARTILHADA: tuple[str, ...] = ()
HERDADAS: dict[str, tuple[str, str, bool]] = {}

# Ainda SEM política, cada uma com o motivo. É o que impede declarar A01 resolvido: nestas tabelas o isolamento continua só nos filtros do código.
PENDENTES: dict[str, str] = {**_comprador.PENDENTES, **{
    'assinatura_webhook_parceiro': 'tocada fora do contexto do tenant em: cron (suspender licenças, webhooks de parceiros) e provisionamento por chave de parceiro',
    'chave_api_parceiro': 'autenticada por hash de chave do parceiro, sem usuário, antes de saber o tenant (deps.get_chave_api_atual): falta a busca pré-tenant',
    'configuracao_relatorio': 'lida por cron global (disparar relatórios periódicos) em todos os tenants: falta revisar a lista do contexto de sistema',
    'evento_webhook_parceiro': 'sem tenant_id próprio (escopo herdado de `assinatura_webhook_parceiro`, também pendente)',
    'alerta_licitacao': 'tocada fora do contexto do tenant em: cron:podar_historicos',
    'apuracao_comissao': 'tocada fora do contexto do tenant em: comissoes:apuracoes, comissoes:criar_perfil, comissoes:recalcular, comissoes:registrar_cotacao, comissoes:waterfall, motor:margem_contribuicao, motor:waterfall_comissoes',
    'assinatura_webhook_tenant': 'tocada fora do contexto do tenant em: cron:processar_eventos',
    'atividade': 'tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento',
    'audit_log': 'tocada fora do contexto do tenant em: admin_enriquecimento:auditoria, admin_enriquecimento:decidir_estorno, admin_tenants:atualizar_licenca, admin_tenants:criar_tenant, admin_tenants:desativar_tenant, admin_tenants:reativar_tenant, agente_corporativo:perguntar, comissoes:alterar_politica_infra, comissoes:alterar_politica_margem, comissoes:atualizar_componente, comissoes:criar_componente, comissoes:criar_perfil, comissoes:criar_status_tributario, comissoes:decidir_alerta, comissoes:recalcular, comissoes:registrar_cotacao, cron:coletar_licitacoes, cron:processar_fila_enriquecimento, cron:suspender_licencas_vencidas, finops:ativar_catalogo, finops:criar_rascunho, finops:nova_versao_pacote, governo:criar_oportunidade, governo:nova_politica, governo:override_comissao, governo:transferir, map_performance:contato_efetivo, map_performance:definir_quota, map_performance:ofertas_familias, map_performance:vincular, motor:registrar_interacao, parceiros:provisionar_tenant, planos:atualizar_plano, planos:criar_plano, portal_fornecedor:enviar, ropa:criar_versao_ropa_plataforma, saude_conta:atribuir_vendedor, saude_conta:registrar_interacao',
    'autorizacao_oauth_pendente': 'tocada fora do contexto do tenant em: integracoes_crm_publico:callback_oauth',
    'cache_resposta_ia': 'tocada fora do contexto do tenant em: cron:podar_historicos',
    'campanha_destinatario': 'tocada fora do contexto do tenant em: app/api/deps:(dependência)',
    'campo_enriquecido': 'escopo herdado de `conta` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente',
    'canal_sala': 'escopo herdado de `sala_corporativa` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente',
    'carteira_creditos': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento',
    'coleta_site_conta': 'tocada fora do contexto do tenant em: cron:podar_historicos, cron:processar_fila_enriquecimento',
    'comentario_post': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'comissao_representante': 'tocada fora do contexto do tenant em: comissoes:criar_perfil, comissoes:recalcular, comissoes:registrar_cotacao, comissoes:waterfall, motor:margem_contribuicao, motor:waterfall_comissoes',
    'componente_contrato_governo': 'tocada fora do contexto do tenant em: governo:override_comissao, governo:transferir, motor:margem_contribuicao',
    'configuracao_agente_corporativo': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar',
    'configuracao_coleta_fonte': 'tocada fora do contexto do tenant em: cron:coletar_licitacoes',
    'configuracao_credito_tenant': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento',
    'configuracao_email_api': 'tocada fora do contexto do tenant em: app/api/deps:(dependência)',
    'configuracao_email_smtp': 'tocada fora do contexto do tenant em: app/api/deps:(dependência)',
    'configuracao_painel': 'tocada fora do contexto do tenant em: painel:ranking_assinantes',
    'conhecimento_corporativo': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar',
    'conta': 'tocada fora do contexto do tenant em: auth:demonstracao, cron:processar_fila_enriquecimento, saude_conta:atribuir_vendedor, saude_conta:listar_interacoes, saude_conta:score_risco, saude_conta:script_resgate, saude_conta:vendedores_disponiveis',
    'conta_franquia_consumo': 'tocada fora do contexto do tenant em: parceiros:obter_uso',
    'conteudo_pagina_site': 'tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento',
    'contrato_governo': 'tocada fora do contexto do tenant em: governo:transferir',
    'contrato_sourcing': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'contrato_venda_publica': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'convite_vitrine': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'decisor': 'tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento',
    'documento_licitacao': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'documento_sala': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'documento_sourcing': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'empresa_rede': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'enriquecimento_carteira': 'tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno, cron:creditos_ia',
    'enriquecimento_compra': 'tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno',
    'enriquecimento_config_plano': 'tocada fora do contexto do tenant em: admin_enriquecimento:aplicar_matriz, admin_enriquecimento:situacao_dos_planos, cron:creditos_ia, pesquisas_decisores:comprar_pacote, pesquisas_decisores:confirmar, pesquisas_decisores:criar_previa, pesquisas_decisores:pacotes_adicionais, pesquisas_decisores:painel_do_tenant, planos:criar_plano, relatorio_consumo:relatorio, relatorio_consumo:relatorio_csv',
    'enriquecimento_estorno_compra': 'tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno, admin_enriquecimento:listar_estornos',
    'enriquecimento_movimento': 'tocada fora do contexto do tenant em: admin_enriquecimento:decidir_estorno, cron:processar_fila_enriquecimento',
    'entrega_webhook': 'tocada fora do contexto do tenant em: cron:podar_historicos, cron:processar_eventos',
    'evento_contrato_sourcing': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'evento_dominio': 'tocada fora do contexto do tenant em: cron:podar_historicos, cron:processar_eventos',
    'evento_sourcing': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'execucao_coleta_fonte': 'tocada fora do contexto do tenant em: cron:coletar_licitacoes, cron:podar_historicos',
    'execucao_ia': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar, comissoes:registrar_cotacao, cron:creditos_ia, cron:processar_fila_enriquecimento, finops:resumo_plataforma',
    'fila_enriquecimento_conta': 'tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento',
    'icp': 'tocada fora do contexto do tenant em: cron:podar_recorte_cnpj',
    'intent': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'interacao_conta': 'tocada fora do contexto do tenant em: saude_conta:registrar_interacao',
    'interacao_tenant': 'tocada fora do contexto do tenant em: motor:dashboard, motor:listar_interacoes, motor:registrar_interacao, motor:saude_tenants, motor:score_risco, motor:script_resgate',
    'item_sourcing': 'tocada fora do contexto do tenant em: portal_fornecedor:enviar, portal_fornecedor:ver',
    'licenca': 'tocada fora do contexto do tenant em: admin_tenants:atualizar_licenca, admin_tenants:criar_tenant, admin_tenants:obter_licenca, agente_corporativo:perguntar, app/api/deps:(dependência), auth:demonstracao, cron:creditos_ia, cron:enviar_lembretes_cobranca, cron:processar_fila_enriquecimento, cron:suspender_licencas_vencidas, motor:score_risco, motor:script_resgate, parceiros:obter_billing, parceiros:provisionar_tenant',
    'licitacao': 'tocada fora do contexto do tenant em: cron:coletar_licitacoes, cron:podar_historicos, cron:sourcing_sincronizar',
    'lote_credito': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento, governo:transferir, motor:margem_contribuicao',
    'mensagem_sala': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'midia_post': 'escopo herdado de `post_rede_social` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente',
    'movimento_credito': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:creditos_ia, cron:processar_fila_enriquecimento',
    'necessidade_oportunidade': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'notificacao_rede_social': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'oferta': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar, map_performance:configuracao, map_performance:contato_efetivo, map_performance:daily, map_performance:ofertas_familias, rede_social:listar_empresas',
    'oportunidade_governo': 'tocada fora do contexto do tenant em: governo:criar_oportunidade',
    'orcamento_ia': 'tocada fora do contexto do tenant em: cron:processar_fila_enriquecimento',
    'participante_sala': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'participante_sourcing': 'tocada fora do contexto do tenant em: portal_fornecedor:_por_conta, portal_fornecedor:convites, portal_fornecedor:enviar',
    'perfil_empresa': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'pergunta_agente_corporativo': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'periodo_assinatura_governo': 'tocada fora do contexto do tenant em: cron:creditos_ia, governo:transferir, motor:margem_contribuicao',
    'post_rede_social': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'processo_sourcing': 'tocada fora do contexto do tenant em: app/api/deps:(dependência), cron:coletar_licitacoes, cron:sourcing_sincronizar, portal_fornecedor:convites, portal_fornecedor:enviar, portal_fornecedor:ver',
    'proposta_item_sourcing': 'tocada fora do contexto do tenant em: portal_fornecedor:enviar',
    'proposta_sourcing': 'tocada fora do contexto do tenant em: portal_fornecedor:enviar, portal_fornecedor:ver',
    'reacao_post': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'redefinicao_senha': 'escopo herdado de `usuario` (sem `tenant_id` próprio); a política só entra junto com a do pai, ainda pendente',
    'registro_oportunidade': 'tocada fora do contexto do tenant em: cron:expirar_registros_oportunidade, leads:criar_lead, registro_oportunidade:solicitar_desconto',
    'registro_uso_ia': 'tocada fora do contexto do tenant em: agente_corporativo:perguntar, cron:processar_fila_enriquecimento',
    'regra_alerta_licitacao': 'tocada fora do contexto do tenant em: cron:processar_alertas_licitacoes',
    'relacionamento_empresarial': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'requisito_licitacao': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'requisito_sourcing': 'tocada fora do contexto do tenant em: cron:sourcing_sincronizar',
    'reuniao': 'tocada fora do contexto do tenant em: painel:ranking_assinantes',
    'reuniao_sala': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'sala_compra': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'seguidor_empresa': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'sinal_oportunidade': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'solicitacao_desconto': 'tocada fora do contexto do tenant em: registro_oportunidade:decidir_solicitacao_desconto',
    'stakeholder_sala': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'tarefa_sala': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
    'usuario': 'tocada fora do contexto do tenant em: admin_tenants:criar_tenant, auth:demonstracao, indicacoes:converter_indicacao, map_performance:configuracao, map_performance:contato_efetivo, map_performance:daily, map_performance:equipe, map_performance:ofertas_familias, map_performance:usuarios_crm, parceiros:provisionar_tenant, rede_social:comentar_post, rede_social:compartilhar_post, rede_social:enviar_mensagem, rede_social:enviar_mensagem_canal, rede_social:listar_comentarios, rede_social:listar_feed, rede_social:reagir_post, rede_social:responder_conexao, rede_social:solicitar_conexao',
    'verificacao_empresa': 'cruzamento entre empresas por desenho (Shoal): política de partes ainda não validada com os fluxos',
}}

# Sem escopo de empresa por natureza (nunca recebem política por tenant).
GLOBAIS: dict[str, str] = {
    'alerta_capacidade_infra': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'cache_mercado_externo': 'cache global de cotação e notícias',
    'catalogo_credito': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'cnpj_estabelecimento': 'dado público nacional (Receita Federal)',
    'cnpj_socio': 'dado público nacional (Receita Federal)',
    'componente_infra': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'cotacao_cambio': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'enriquecimento_custo_provedor': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'enriquecimento_lote_compra': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'enriquecimento_orcamento_global': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'enriquecimento_pacote': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'enriquecimento_pagamento_provedor': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'enriquecimento_politica_provedor': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'enriquecimento_uso_provedor': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'envelope_capacidade': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'evento_licitacao_publica': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'licitacao_publica': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'pacote_credito': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'perfil_tributario': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'periodo_status_tributario': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'plano': 'catálogo comercial de planos',
    'politica_comissao': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'politica_creditos_ia': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'preco_modelo_ia': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'quota_comercial': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'recorte_cnpj_estado': 'controle do recorte público de CNPJ',
    'registro_tratamento': 'ROPA da plataforma (LGPD)',
    'representante': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'rotulo_tipo_tenant': 'rótulos de plataforma',
    'template_documento_comercial': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'tenant': 'cadastro das empresas; lido por hierarquia, rede e administração (não é dado de uma empresa só)',
    'uso_capacidade_infra': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
    'workload_ia': 'dado de plataforma sem escopo de empresa (catálogo, preço, custo de infraestrutura, política ou cotação)',
}
