> **Histórico (2026-09-17).** A referência atual de arquitetura está em
> [`docs/b2bon/`](docs/b2bon/00_MASTER_ARCHITECTURE.md) (Master Prompt v4, D-003).
> Este arquivo tem trechos desatualizados; em caso de divergência, vale `docs/b2bon/`.

# DATA_FLOW_MAP.md — B2B ON (2026-09-17)

Fluxos ponta a ponta dos processos mais relevantes hoje. Não confundir
com `docs/compliance/data-flow-map.md` (já existente) — aquele é o
mapa de conformidade LGPD/subprocessadores; este é o mapa técnico de
como o dado se move dentro do sistema.

## 1. Request HTTP genérico

```
Cliente (browser)
  → fetch com Authorization: Bearer <JWT>
  → FastAPI dependency: get_usuario_atual (decodifica JWT, SÓ usa o "sub",
    busca Usuario fresco no banco)
  → get_tenant_id (usuario.tenant_id da linha atual do banco, não do token)
  → exigir_licenca_ativa (se a rota estiver no grupo pago) — sobe até 5
    níveis de tenant_pai_id se modo_cobranca="consolidada"
  → handler da rota → service (filtra tenant_id em toda query)
  → resposta
```

Todo dado de negócio é filtrado por `tenant_id` no nível do serviço —
não há RLS de banco. Ver `SECURITY_BOUNDARIES.md`.

## 2. Prospecção — do ICP até a mensagem aprovada

```
ICP (cnae_codigos, ufs, porte) — só ICPs ativos entram no recorte
  ↓
GitHub Actions cron (a cada 30min) roda scripts/carregar_recorte_ci.py
  → cnpj_recorte_service.atualizar_recorte_automatico
  → une CNAE/UF de TODOS os ICPs ativos de TODOS os tenants numa carga só
  → baixa shards da Receita Federal (Empresas/Estabelecimentos/Socios)
  → grava em cnpj_estabelecimento/cnpj_socio (staging SEM tenant_id —
    dado público nacional, compartilhado entre todos os tenants)
  ↓
Usuário clica "Gerar lista" (POST /icp/{id}/contas/gerar)
  → conta_service.gerar_lista consulta cnpj_estabelecimento filtrando
    pelo CNAE/UF/porte DESSE ICP, deduplica contra Conta.cnpj já
    existente NESTE tenant, cria Conta(tenant_id=..., status="prospectada")
  → grafo.upsert_conta (Neo4j, best-effort — nunca bloqueia o commit)
  ↓
Mapear decisores (Receita Federal QSA e/ou Lusha, se configurado)
  → Decisor(conta_id=...)
  ↓
Gerar cadência (POST /cadencias/{id}/gerar)
  → cadencia_service.gerar_para_lote → llm_helpers.gerar (Claude) por
    toque × conta → aprovacao_service.criar_proposta
  → Mensagem(status="aguardando_aprovacao") + Aprovacao(status="pendente")
  ↓
Fila de Aprovação (humano aprova/edita/rejeita)
  → Mensagem.status="aprovado" só depois de Aprovacao.status="aprovado"
  ↓
Ativar cadência (POST /cadencias/{id}/ativar)
  → calcula Mensagem.agendado_para por decisor/toque, consome franquia
  ↓
Cron de 15min → POST /cron/processar-envios
  → envio_service.processar_pendentes (só pega status="aprovado",
    agendado_para <= agora) → provider real (SendGrid/Meta WhatsApp) →
    Mensagem.status="enviado" ou "falhou"
```

## 3. E-mail — abertura e bounce

```
Envio real via SendGrid (custom_args: tenant_id + mensagem_id ou
  campanha_destinatario_id)
  ↓
Pixel de rastreio (1x1, embutido no HTML) → GET /webhooks/email/
  aberto/{token} → Mensagem.aberto_em
  ↓
SendGrid Event Webhook (assinado ECDSA) → POST /webhooks/sendgrid/eventos
  → sendgrid_webhook_service.processar_eventos
  → reputacao_service.registrar_evento (contador agregado por
    tenant+canal+dia) → pausa automática do canal se bounce > 5%/7 dias
  → grava bounce_em/motivo_bounce na Mensagem/CampanhaDestinatario
    exata (via mensagem_id/campanha_destinatario_id ecoado)
```

## 4. WhatsApp — janela de 24h e botão de redirecionamento

```
Toque de WhatsApp de uma cadência: SEMPRE via template aprovado (regra
  de negócio, no máximo 1 toque de WhatsApp por cadência)
  ↓
envio_service._processar_whatsapp resolve o vendedor da conta
  (Conta.vendedor_usuario_id → Usuario.whatsapp_pessoal)
  ↓
MetaWhatsAppProvider.enviar_template inclui o botão "Visitar site"
  (https://wa.me/{{1}}) preenchido com o WhatsApp pessoal do vendedor
  ↓
Cliente responde pelo botão → conversa continua no WhatsApp de verdade
  do vendedor, FORA da plataforma — sem registro automático no CRM
  (usuário registra manualmente em Atividade, decisão consciente)
```

Webhook `POST /webhooks/whatsapp/meta` (inbound, tenant resolvido por
`phone_number_id`, não por header) alimenta
`resposta_service.marcar_resposta` (cancela mensagens pendentes só se
`Cadencia.cancelar_ao_responder=True`, opt-in) e
`qualificacao_service.processar_mensagem_recebida` (S.H.A.R.K., ver
`AI_CURRENT_ARCHITECTURE.md`).

## 5. Neo4j — escrita best-effort, nunca no caminho crítico

```
conta_service.criar_manual/criar_lead/atualizar
  → commit no Postgres (sempre primeiro, sempre síncrono)
  → sincronizar_com_tolerancia(graph.upsert_conta, ...) — try/except,
    loga e retorna False em qualquer falha, NUNCA propaga
```

Isso existe porque a instância Neo4j AuraDB Free já caiu em produção
(auto-pause por inatividade) e um bug real (commit `f73134a`)
mostrava 500 pro usuário quando isso acontecia — o wrapper foi
retrofitado depois desse incidente. Hoje: Neo4j pode estar fora do ar
o tempo inteiro sem afetar nada visível pro usuário — ao custo de o
grafo poder ficar defasado silenciosamente (nenhum reconciliation job
existe pra detectar/corrigir isso).

## 6. Rede Social — tenant-a-tenant, exige conexão aceita

```
PerfilEmpresa (1:1 com Tenant) aparece no diretório (GET /rede-social/empresas)
  ↓
POST /rede-social/conexoes (tenant A pede conexão a tenant B)
  → ConexaoEmpresa(status="pendente")
  ↓
PUT /rede-social/conexoes/{id} (tenant B aceita/recusa)
  ↓
Só com status="aceita": POST /rede-social/mensagens é permitido
  (rede_social_service.enviar_mensagem bloqueia senão)
  → MensagemRedeSocial(tenant_id_remetente, tenant_id_destinatario,
    usuario_remetente_id, texto)
```

Sem feed, sem post, sem grafo tipado — é diretório + connection
request + DM, ponto a ponto. Ver `NETWORK_GAP_ANALYSIS.md`.

## 7. Auditoria — write-side-effect em toda mutação relevante

```
Qualquer ação de negócio relevante (criar/editar/aprovar/cancelar/
  enviar/etc.)
  → auditoria_service.registrar(db, tenant_id, evento_tipo,
    entidade_tipo, entidade_id, ator_id, detalhes, conta_id?, canal?)
  → AuditLog (imutável, sem update/delete em lugar nenhum do código)
```

131 call sites, 34 arquivos — manual em cada um, não interceptado por
middleware/ORM hook. `auditoria_service.consultar` aplica janela de
retenção conforme o plano do tenant (`PlanLimitsProvider.
obter_retencao_dias_auditoria`).

## 8. Cron — GitHub Actions como único agendador

```
GitHub Actions (schedule) → curl -X POST com X-Cron-Secret
  → app/api/v1/cron.py (cada endpoint itera todos os tenants ativos,
    isola falha por tenant — rollback + Sentry, continua o loop)
```

Não existe fila; um endpoint de cron lento bloqueia a requisição HTTP
inteira até terminar (mitigado hoje só por rodar pouco volume por
tenant a cada 15/30min).

---
Ver `CURRENT_ARCHITECTURE.md` para o inventário completo de entidades,
`SECURITY_BOUNDARIES.md` para os limites de confiança em cada fronteira
acima.
