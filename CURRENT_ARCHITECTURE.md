# CURRENT_ARCHITECTURE.md — B2B ON (auditoria factual, 2026-09-17)

Este documento descreve **o que existe hoje** no repositório, não uma
arquitetura desejada. Serve de base para `AI_CURRENT_ARCHITECTURE.md`,
`NETWORK_GAP_ANALYSIS.md`, `DATA_FLOW_MAP.md` e `SECURITY_BOUNDARIES.md`.

## 1. Stack e topologia de produção

- **Backend**: FastAPI + SQLAlchemy 2.0 + Pydantic v2, Alembic. Roda numa
  única instância Render (free/starter tier) — sem fila, sem worker,
  sem cache server (ver seção 6).
- **Banco relacional**: Postgres via Neon em produção; SQLite em dev/teste.
  `DATABASE_URL` é a única fonte — todo `tenant_id` é uma coluna, não um
  schema/banco separado por tenant.
- **Grafo**: Neo4j AuraDB Free, opcional/best-effort (ver seção 4 —
  `sincronizar_com_tolerancia` nunca deixa uma falha do Neo4j bloquear o
  banco relacional; a instância já caiu em produção por auto-pause do
  tier gratuito).
- **Frontend**: React + TypeScript + Vite, Tailwind v4 (config CSS-first
  em `frontend/src/index.css`, sem `tailwind.config.*`), PWA instalável,
  hospedado em Cloudflare Workers (static assets).
- **IA**: Anthropic (Claude) via SDK oficial — única implementação, sem
  fallback de provider (ver `AI_CURRENT_ARCHITECTURE.md`).
- **"Background jobs"**: não existem workers/filas — todo processamento
  assíncrono é GitHub Actions com cron chamando endpoints HTTP
  autenticados por segredo (`X-Cron-Secret`). Ver seção 6.

## 2. Autenticação e multi-tenancy

- JWT HS256 (`app/services/auth_service.py`), claims `sub`/`tenant_id`/
  `papel`/`iat`/`exp` — mas **a cada request**, `get_usuario_atual`
  (`app/api/deps.py`) só lê `sub` do token e busca o `Usuario` fresco no
  banco; `tenant_id`/`papel` efetivos vêm sempre da linha atual do
  banco, nunca do payload do token. Uma mudança de papel/tenant tem
  efeito imediato, sem precisar reemitir token.
- Papéis: `super_admin | admin | user` (`Usuario.papel`), checados via
  `exigir_papel`, `exigir_gestor_do_tenant`, `permitir_gestao_hierarquica`,
  `exigir_admin_distribuidor` (todos em `app/api/deps.py`).
- Hierarquia de tenant: `Tenant.tipo` (`distribuidor|revendedor|cliente`),
  auto-referência `tenant_pai_id`, profundidade máxima 5
  (`tenant_service.py`). `admin` vê a própria subárvore;
  `super_admin` vê tudo; `user` só o próprio tenant
  (`tenant_ids_no_escopo`).
- Isolamento de dados: **todo** modelo de negócio carrega `tenant_id`
  como coluna, filtrado em cada query de serviço — não é RLS de banco,
  é disciplina de código (ver `SECURITY_BOUNDARIES.md` para a única
  exceção deliberada: as tabelas de staging de CNPJ, que não têm
  `tenant_id` porque são dado público nacional, não dado de tenant).
- Chave de API de parceiro (`ChaveApiParceiro`) é um segundo mecanismo de
  auth, independente do JWT, para a API de provisionamento de
  Distribuidores (Fase 2 da hierarquia).

## 3. Módulos (por README.md, confirmado no código)

1. **CRM** — `Conta`, `Decisor`, `Negocio`, `EstagioFunil`, `Atividade`,
   `PropostaNegocio`, `CustoAquisicao`. Rotas: `app/api/v1/crm.py`,
   `contas.py`, `decisores.py`.
2. **Shoal** (ex-"Rede Social", renomeado 2026-09-20) — B2B entre tenants
   (não entre usuários finais). Cresceu bem além do diretório+DM
   original (atualização 2026-09-20 — ver `MANUAL_DO_USUARIO.md` seção
   3 pro detalhamento funcional completo): `PerfilEmpresa` (cartão de
   visita, com verificação — `VerificacaoEmpresa`), `ConexaoEmpresa`
   (pedido/aceite, bloqueio, desconexão), `SeguidorEmpresa` (seguir
   unidirecional, sem aceite), `MensagemRedeSocial` (DM 1:1),
   `SalaCorporativa`/`CanalSala`/`MensagemSala` (mensageria mais
   estruturada, com canais), `PostRedeSocial`/`MidiaPost`/
   `ComentarioPost`/`ReacaoPost` (feed com carrossel de foto/vídeo, 9
   reações, repost), `Intent` (Necessidades da Rede),
   `RelacionamentoEmpresarial` (grafo tipado tenant-a-tenant),
   `NotificacaoRedeSocial`. Único módulo liberado sem licença ativa
   (funil de entrada via `ConviteVitrine`). Rotas: `rede_social.py`,
   `verificacao_empresa.py`.
3. **MAP** — motor de risco de churn dos tenants-clientes:
   `InteracaoConta`/`InteracaoTenant` (sinais manuais), `AlertaDetrator`
   (NPS), script de resgate gerado por IA (texto para humano copiar,
   nunca enviado automaticamente). Rotas: `saude_conta.py`, `motor.py`.
4. **PREDATOR** — motor de prospecção: `ICP`, geração de contas a partir
   de um recorte local de CNPJ (Receita Federal), enriquecimento
   (BrasilAPI, site via IA, contatos via Lusha), `Cadencia`/
   `ToqueCadencia`/`Mensagem` multicanal (e-mail/WhatsApp/LinkedIn) com
   fila de aprovação humana (`Aprovacao`), `Campanha` (disparo em massa,
   sem IA), reuniões + NPS + qualificação conversacional S.H.A.R.K.
   (`ConversaQualificacao`/`TurnoConversa`/`QualificacaoScore`). Ganhou,
   em fases posteriores (ver `MANUAL_DO_USUARIO.md` seções 5.9-5.12),
   Relatório de Entrega (bounce/abertura/resposta), `RegraAprendida`
   (loop de aprendizado — regra escrita por humano entra sozinha no
   próximo prompt de cadência), `SinalOportunidade` (fit de ICP/match
   de Intent/risco de pipeline/atribuição de receita, cruzando com o
   Shoal) e `ConfiguracaoAgenteCorporativo`/`PerguntaAgenteCorporativo`
   (Agente Corporativo — IA responde, sob aprovação humana, perguntas
   de outras empresas do Shoal sobre a sua). Rotas: `regras_
   aprendidas.py`, `inteligencia_rede.py`, `agente_corporativo.py`.

Módulos administrativos/transversais que não são "um módulo do
usuário" mas atravessam todos os outros: billing (`Plano`/`Licenca`/
`PagamentoLicenca`), hierarquia de distribuidores, Registro de
Oportunidade/PRIME (dedupe de deal registration dentro da rede),
LGPD (`RegistroTratamento`, `RegistroSupressaoPermanente`, titulares),
auditoria (`AuditLog`), parceiros/webhooks (API de provisionamento).

## 4. Inventário de dados (72 classes em `app/models/`, 70 arquivos)

Agrupado por domínio — ver `DATA_FLOW_MAP.md` para os fluxos entre eles.

- **CRM core**: `Conta`, `Decisor`, `Negocio`, `EstagioFunil`,
  `Atividade`, `DescarteConta`, `PropostaNegocio`, `InteracaoConta`.
- **Cadência/Mensagem/Aprovação**: `Cadencia`, `ToqueCadencia`,
  `Mensagem`, `Aprovacao`, `RegraAutoAprovacao`, `PausaCanal`,
  `RegistroEnvioDiario`.
- **Campanha**: `Campanha`, `CampanhaDestinatario`.
- **ICP/Prospecção**: `ICP`, `ListaProspeccao`, `FilaEnriquecimentoConta`,
  `CampoEnriquecido`. (O staging de CNPJ em si —
  `CnpjEstabelecimento`/`CnpjSocio` — vive fora de `app/models/`, em
  `app/providers/account_data/receita_federal_models.py`, e é a única
  tabela sem `tenant_id` do sistema; `RecorteCnpjEstado` é só o
  rastreador de qual CNAE/UF/mês já foi carregado.)
- **Tenant/Usuario/Licenca/Plano**: `Tenant`, `Usuario`, `Licenca`,
  `Plano`, `PagamentoLicenca`, `ConviteCadastro`, `ConviteVitrine`,
  `RotuloTipoTenant`, `SolicitacaoDesconto`.
- **Canais (config)**: `ConfiguracaoWhatsApp`, `ConfiguracaoEmailSmtp`,
  `ConfiguracaoComunicacao`, `ConfiguracaoCanal`, `ConfiguracaoEnvio`,
  `ConfiguracaoNotificacao`, `TemplateWhatsApp`, `RegistroReputacaoCanal`.
- **Registro de Oportunidade**: `RegistroOportunidade`.
- **Rede Social/LinkedIn/Qualificação**: `PerfilEmpresa`,
  `ConexaoEmpresa`, `MensagemRedeSocial`, `ConexaoLinkedin`,
  `TarefaLinkedin`, `ConversaQualificacao`, `TurnoConversa`,
  `QualificacaoScore`, `ConfiguracaoQualificacao`.
- **Reuniões/NPS**: `Reuniao`, `PesquisaNps`, `ConfiguracaoNps`,
  `AlertaDetrator`.
- **Notificações**: `NotificacaoVendedor` (único tipo existente).
- **Auditoria**: `AuditLog` (`audit_log`).
- **Parceiros/webhooks**: `ChaveApiParceiro`,
  `AssinaturaWebhookParceiro`, `EventoWebhookParceiro`.
- **LGPD**: `RegistroTratamento`, `RegistroSupressaoPermanente`.
- **Ofertas/Propostas/FAQ/Painel/Indicações**: `Oferta`,
  `MaterialOferta`, `TemplateProposta`, `ItemTemplateProposta`,
  `FaqItem`, `ConfiguracaoPainel`, `ConfiguracaoRelatorio`, `Indicacao`,
  `InteracaoTenant`, `CustoAquisicao`.

**Colunas reais — núcleo CRM** (para quem for desenhar o Business Graph
no futuro, ver `NETWORK_GAP_ANALYSIS.md`):

```
Conta: id, tenant_id, icp_id?, lista_prospeccao_id?, cnpj, nome,
  nome_fantasia, dominio, vendedor_usuario_id?, porte, segmento, regiao,
  score_aderencia, status, motivo_descarte, origem, nps_classificacao,
  nps_nota, cliente_desde, cliente_cancelado_em, proximo_passo,
  proximo_passo_em, resumo_site, observacoes, neo4j_node_id,
  criado_em, atualizado_em

Decisor: id, tenant_id, conta_id, nome, cargo, canal_provavel,
  linkedin_url, email, telefone, neo4j_node_id, origem,
  ultima_interacao_em, suprimido_em, criado_em

Negocio: id, tenant_id, conta_id, vendedor_usuario_id?, decisor_id?,
  estagio_id, nome, valor, probabilidade, origem, ganho_em,
  perdido_em, motivo_perda, chave_importacao, criado_em, atualizado_em

Cadencia: id, tenant_id, conta_id?, icp_id?, oferta_id?, nome, canais,
  status, tipo, data_inicio, cancelar_ao_responder, criado_em

Mensagem: id, tenant_id, cadencia_id?, decisor_id, toque_cadencia_id?,
  canal, template_id, conteudo, variante_ab, status, agendado_para,
  enviado_em, aberto_em, bounce_em, motivo_bounce, motivo_falha,
  tentativas_envio, criado_em
```

`ConexaoEmpresa` — a única tabela relacional de **relacionamento
empresa-empresa** hoje (fora do Neo4j): `id, tenant_id_origem,
tenant_id_destino, status (pendente|aceita|recusada), criado_em,
respondida_em`, unique em `(tenant_id_origem, tenant_id_destino)`.

## 5. Superfície de API (`app/api/v1/`, 49 arquivos de rota)

`admin_tenants, aprovacoes, auditoria, auth, busca, cadencias,
campanhas, canais, comunicacao, configuracao_email_smtp,
configuracao_envio, configuracao_whatsapp, contas, conversas, convites,
crm, cron, decisores, envios, faq, icp, indicacoes, integracoes, leads,
linkedin, listas_prospeccao, motor, notificacoes, nps, ofertas,
onboarding, optout, painel, parceiros, planos, qualificacao,
rede_social, registro_oportunidade, relatorio_entrega, relatorios,
reunioes, ropa, rotulos_hierarquia, saude_conta, template_proposta,
titulares, usuarios, webhooks, whatsapp`.

Módulos pagos (`_exige_licenca` em `router.py`) ficam bloqueados sem
licença ativa; `webhooks`, `optout`, `cron`, `auth`, `convites`,
`planos`, `admin_tenants`, `rede_social` ficam fora desse gate
(públicos/administrativos/free-tier por desenho).

## 6. "Background jobs" — não há fila nem worker

Confirmado por grep (`celery`, `redis`, `rq`, `sqs`, `kafka` → zero
hits reais em `app/`/`pyproject.toml`). Todo trabalho assíncrono é:

- **GitHub Actions cron** (`.github/workflows/cron-envios.yml`),
  3 agendamentos (`*/15 * * * *`, `0 6 * * *` diário, `*/30 * * * *`)
  chamando `POST /cron/*` com header `X-Cron-Secret` — disparo de
  cadência/campanha, lembretes de reunião+NPS, webhooks de parceiro,
  fila de enriquecimento em lote, expiração LGPD, suspensão de
  licença, cobrança, relatórios periódicos, poda de recorte de CNPJ.
- Um job separado (`atualizar-recorte-cnpj`, mesmo workflow) roda o
  script de carga do recorte de CNPJ **direto no runner do GitHub
  Actions** (não via HTTP) — decisão deliberada depois de um incidente
  real (download de >4GB estourava a cota de `/tmp` do Render e matava
  a instância).
- Rate limiting é **em memória, por processo** (`app/core/rate_limit.py`)
  — comentário explícito no código diz que precisaria virar Redis se a
  API algum dia escalar horizontalmente (hoje não escala).

## 7. Frontend

- `frontend/src/pages/<módulo>/` — uma pasta por módulo, lazy-loaded
  por rota em `App.tsx`.
- `frontend/src/components/ui/`: `Badge`, `Button`, `Card`, `Input`,
  `KpiCard`, `Modal`, `SeletorArquivo` — kit próprio, pequeno, sem
  biblioteca externa de componentes.
- `frontend/src/lib/api.ts` — wrapper `fetch` fino, `ApiError` com
  `status`, sessão em `localStorage`.
- `frontend/src/lib/auth.tsx` — modelo de sessão do cliente:
  `Usuario` (inclui `recursos_plano`, o espelho client-side dos
  feature-flags de plano) + `AuthContextValue` com todos os fluxos de
  login/registro/self-service hoje existentes.
- Sem WebSocket/SSE em lugar nenhum do frontend ou backend — toda
  atualização de tela é request/response tradicional.

## 8. Testes

`pytest`, `tests/unit/` (regra de negócio isolada) e
`tests/integration/` (`TestClient` fim a fim contra SQLite temporário
por teste). Suite completa: 964 testes passando (checado nesta mesma
sessão, 2026-09-16/17).

---
Ver também: `AI_CURRENT_ARCHITECTURE.md` (camada de IA em detalhe),
`NETWORK_GAP_ANALYSIS.md` (o que falta pra virar "Business Operating
System"), `DATA_FLOW_MAP.md` (fluxos ponta a ponta),
`SECURITY_BOUNDARIES.md` (isolamento, auth, segredos, LGPD).
