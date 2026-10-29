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
    "shoal-notificar-por-email": {"usuario": "ler"},
    "webhook-parceiro-enfileirar": {"assinatura_webhook_parceiro": "ler", "evento_webhook_parceiro": "escrever"},
    "reivindicacao-identidade": {"empresa_rede": "escrever", "relacionamento_empresarial": "escrever"},
}
for _nome, _tabelas in _comprador.SISTEMA.items():
    CONTEXTOS_SISTEMA[_nome].update(_tabelas)

# --- Classificação de TODAS as tabelas (primeira etapa) --------------------------------------------------------------------------------------------
# Protegidas por tenant direto: política `rls_tenant` (+ leitura ampliada pela hierarquia). Entram aqui só as tabelas que a sonda (tests/rls_sonda.py) viu, na suíte inteira,
# sendo tocadas apenas dentro do contexto do tenant dono da linha.
TENANT_DIRETO_ETAPA1: tuple[str, ...] = (
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
DUAS_PARTES_ETAPA1: dict[str, tuple[str, str]] = {
    'conexao_empresa': ('tenant_id_origem', 'tenant_id_destino'),
    'mensagem_rede_social': ('tenant_id_remetente', 'tenant_id_destinatario'),
    'sala_corporativa': ('tenant_id_a', 'tenant_id_b'),
}

# --- Segunda etapa (D-111) ---------------------------------------------------------------------------------------------------------------------------
# Tabelas com `tenant_id` NOT NULL: política `rls_tenant` + leitura ampliada pela hierarquia (como na primeira etapa).
TENANT_DIRETO_ETAPA2: tuple[str, ...] = (
    "alerta_licitacao", "apuracao_comissao", "assinatura_webhook_parceiro", "assinatura_webhook_tenant",
    "atividade", "audit_log", "autorizacao_oauth_pendente", "cache_resposta_ia",
    "campanha_destinatario", "carteira_creditos", "chave_api_parceiro", "coleta_site_conta",
    "comissao_representante", "componente_contrato_governo", "configuracao_agente_corporativo", "configuracao_coleta_fonte",
    "configuracao_credito_tenant", "configuracao_email_api", "configuracao_email_smtp", "configuracao_painel",
    "configuracao_relatorio", "conhecimento_corporativo", "conta", "conta_franquia_consumo",
    "conteudo_pagina_site", "contrato_governo", "contrato_sourcing", "contrato_venda_publica",
    "decisor", "documento_licitacao", "documento_sourcing", "enriquecimento_carteira",
    "enriquecimento_compra", "enriquecimento_estorno_compra", "enriquecimento_movimento", "entrega_webhook",
    "evento_contrato_sourcing", "evento_dominio", "evento_sourcing", "execucao_coleta_fonte",
    "execucao_ia", "fila_enriquecimento_conta", "icp", "interacao_conta",
    "interacao_tenant", "item_sourcing", "licenca", "licitacao",
    "lote_credito", "movimento_credito", "oferta", "orcamento_ia",
    "periodo_assinatura_governo", "processo_sourcing", "proposta_item_sourcing", "proposta_sourcing",
    "registro_oportunidade", "registro_uso_ia", "regra_alerta_licitacao", "requisito_licitacao",
    "requisito_sourcing", "reuniao", "solicitacao_desconto", "usuario",
    "participante_sourcing", "sinal_oportunidade", "verificacao_empresa", "necessidade_oportunidade",
    "notificacao_rede_social",
) + _comprador.TENANT_DIRETO_ETAPA2

# `tenant_id` pode ser nulo: a linha sem dono é de plataforma (só os contextos privilegiados a gravam; a leitura segue a política de cada tabela em POLITICAS_ESPECIAIS).
TENANT_NULAVEL_ETAPA2: tuple[str, ...] = ("enriquecimento_config_plano", "oportunidade_governo", "empresa_rede")

# O dono do dado está em outra coluna que não `tenant_id`.
TENANT_COLUNA_ETAPA2: dict[str, str] = {"sala_compra": "tenant_id_vendedor"}

DUAS_PARTES_ETAPA2: dict[str, tuple[str, str]] = {
    "convite_vitrine": ("tenant_id_origem", "tenant_id_gerado"),
    "seguidor_empresa": ("tenant_id_seguidor", "tenant_id_seguido"),
    "relacionamento_empresarial": ("tenant_id_origem", "tenant_id_destino"),
    "pergunta_agente_corporativo": ("tenant_id_alvo", "tenant_id_perguntante"),
}

# Dado que o produto mostra a outras empresas por desenho (diretório, feed, necessidades da rede): qualquer contexto de tenant LÊ, só o dono grava. A visibilidade fina
# (`conexoes` x `publica`, bloqueio entre empresas) continua nos filtros do código: aqui o banco só impede que uma empresa grave ou apague o que é de outra.
LEITURA_COMPARTILHADA_ETAPA2: tuple[str, ...] = ("perfil_empresa", "post_rede_social", "comentario_post", "reacao_post", "intent")

# Sem `tenant_id` próprio ou com dono por relação: o escopo vem do pai por função `SECURITY DEFINER` (tabela -> (coluna do pai, função do pai, leitura compartilhada)).
HERDADAS_ETAPA2: dict[str, tuple[str, str, bool]] = {
    "midia_post": ("post_id", "b2bon_post_cascata_do_tenant", True),
    "campo_enriquecido": ("conta_id", "b2bon_conta_do_tenant", False),
    "redefinicao_senha": ("usuario_id", "b2bon_usuario_do_tenant", False),
    "evento_webhook_parceiro": ("assinatura_id", "b2bon_assinatura_parceiro_do_tenant", False),
    "canal_sala": ("sala_id", "b2bon_sala_do_tenant", False),
    "mensagem_sala": ("canal_id", "b2bon_canal_do_tenant", False),
    "documento_sala": ("sala_id", "b2bon_sala_do_tenant", False),
    "participante_sala": ("sala_id", "b2bon_sala_do_tenant", False),
    "reuniao_sala": ("sala_id", "b2bon_sala_do_tenant", False),
    "stakeholder_sala": ("sala_id", "b2bon_sala_do_tenant", False),
    "tarefa_sala": ("sala_id", "b2bon_sala_do_tenant", False),
}

# Políticas avulsas por tabela: (nome, comando, USING, WITH CHECK).
POLITICAS_ESPECIAIS_ETAPA2: dict[str, tuple[tuple[str, str, str | None, str | None], ...]] = {
    # A licença que vale é a do tenant que PAGA (cobrança consolidada sobe para o pai): `deps.verificar_licenca_ativa` lê a licença do pai.
    "licenca": (("rls_cobradora", "SELECT", "tenant_id = b2bon_cobrador()", None),),
    # O conflito de CNPJ (PRIME) vale na rede inteira, não só no tenant que registra.
    "registro_oportunidade": (("rls_rede", "SELECT", "rede_raiz_tenant_id = b2bon_raiz_da_rede()", None),),
    # Linha sem dono = configuração padrão do plano: todo tenant lê.
    "enriquecimento_config_plano": (("rls_padrao_do_plano", "SELECT", "tenant_id IS NULL AND b2bon_escopo() = 'tenant'", None),),
    # Cadastro de identidades da rede (CNPJ, razão social, nome): dado público. Qualquer tenant lê, cria e ajusta, porque ao declarar um relacionamento a aplicação cria a
    # identidade do OUTRO lado (de um tenant ou de um CNPJ citado) com os dados públicos dele. Quem pode reivindicar o quê (verificada, CNPJ igual) é regra do código;
    # apagar identidade é só dos contextos privilegiados.
    "empresa_rede": (
        ("rls_diretorio", "SELECT", "b2bon_escopo() = 'tenant'", None),
        ("rls_identidade_cria", "INSERT", None, "b2bon_escopo() = 'tenant'"),
        ("rls_identidade_ajusta", "UPDATE", "b2bon_escopo() = 'tenant'", "b2bon_escopo() = 'tenant'"),
    ),
    # Quem comenta, reage ou notifica outra empresa insere; ler e apagar o que é dele continua só do dono.
    "notificacao_rede_social": (("rls_insercao_entre_tenants", "INSERT", None, "b2bon_escopo() = 'tenant'"),),
    # Quem publicou o original apaga os reposts e o que pendura neles.
    "post_rede_social": (("rls_apagar_repost", "DELETE", "b2bon_post_cascata_do_tenant(id)", None),),
    "comentario_post": (("rls_apagar_do_post", "DELETE", "b2bon_post_cascata_do_tenant(post_id)", None),),
    "reacao_post": (("rls_apagar_do_post", "DELETE", "b2bon_post_cascata_do_tenant(post_id)", None),),
    # Relacionamento comercial declarado como público, ou para quem está conectado.
    "relacionamento_empresarial": (
        ("rls_visibilidade", "SELECT", "visibilidade = 'publica' OR (visibilidade = 'conexoes' AND (b2bon_conectado(tenant_id_origem) OR b2bon_conectado(tenant_id_destino)))", None),
    ),
    # Negócio vinculado à sala: as duas empresas da sala veem.
    "sala_compra": (("rls_sala", "SELECT", "b2bon_sala_do_tenant(sala_corporativa_id)", None),),
    # Fornecedor (empresa da rede) convidado para um processo de OUTRO tenant: lê o convite e o processo para listar os convites que recebeu. A rodada em si (itens,
    # propostas, anexos) é aberta pela aplicação no contexto do comprador, depois de conferir o convite (`portal.por_empresa`).
    "participante_sourcing": (("rls_convidado_le", "SELECT", "empresa_rede_tenant_id = b2bon_tenant()", None),),
    "processo_sourcing": (("rls_convidado", "SELECT", "b2bon_processo_convidado(id)", None),),
}

# Buscas da segunda etapa: só as tabelas protegidas por ela entram na migração dela (as da primeira já estão na outra).
BUSCAS_ETAPA2: dict[str, tuple[Busca, ...]] = {
    "chave-api-parceiro": (Busca("chave_api_parceiro", "chave_hash = b2bon_chave()"),),
}
for _escopo, _itens in BUSCAS_ETAPA2.items():
    BUSCAS[_escopo] = _itens

# Conjunto completo, sem distinguir a etapa (o resto do código e os testes usam estes nomes).
TENANT_DIRETO: tuple[str, ...] = TENANT_DIRETO_ETAPA1 + TENANT_DIRETO_ETAPA2
DUAS_PARTES: dict[str, tuple[str, str]] = {**DUAS_PARTES_ETAPA1, **DUAS_PARTES_ETAPA2}
LEITURA_COMPARTILHADA: tuple[str, ...] = LEITURA_COMPARTILHADA_ETAPA2
HERDADAS: dict[str, tuple[str, str, bool]] = dict(HERDADAS_ETAPA2)

# Ainda SEM política, cada uma com o motivo. É o que impede declarar A01 resolvido: nestas tabelas o isolamento continua só nos filtros do código.
PENDENTES: dict[str, str] = {**_comprador.PENDENTES}

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
