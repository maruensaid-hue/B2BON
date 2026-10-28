# PREDATOR — CURRENT STATE (Fase 0, 2026-09-25)

PREDATOR é o maior módulo: **26 dos 55 routers** estão sob
`_exige_predator`. Parte do que é PREDATOR, porém, está sob o gate do
CRM (ver §3).

## 1. Capacidades vs Master Prompt §8

| Capacidade (§8) | Estado | Onde | IA? |
|---|---|---|---|
| Criação de ICP | ✅ manual, versionado (`nova_versao`, `clonar`, `historico`, `performance`) | `icp_service`, router `icp` | Não. O ICP é formulário, não é gerado por IA. |
| Descoberta de empresas | ✅ | `conta_service.gerar_lista` sobre o recorte local de CNPJ (`cnpj_estabelecimento`), `score_aderencia` | Não |
| Pesquisa empresarial / análise de website | ✅ | `conta_service.enriquecer` (`site_fetcher` + Brave web search + LLM resume o site) | Sim, **não medida** (`conta_service.py:1345` usa `llm_helpers.gerar`). Maior exposição a prompt injection indireto (HTML de terceiro no prompt). |
| Enriquecimento | ✅ | BrasilAPI (`enriquecer_via_brasilapi`), fila semanal (`enriquecimento_fila_service`, cron), limites semanais por plano | Parcial |
| Identificação de decisores | ✅ | `mapear_decisores` (QSA da Receita + Lusha), `criar_decisor_manual`, `sugerir_papel_comite_compra` (regra por cargo) | Não |
| Prospecção / listas | ✅ | `lista_prospeccao_service`, router `leads`, `listas_prospeccao` | Não |
| Mensagens | ✅ | `cadencia_service._gerar_conteudo_toque` / `gerar_para_lote` | Sim, **não medida**. Passa por aprovação. |
| Cadências multicanal | ✅ e-mail / WhatsApp / LinkedIn (manual), A/B, cancelar ao responder | `cadencia_service`, `toque_cadencia` | — |
| Aprovação humana | ✅ robusta | `aprovacao_service`, `envio_service.processar_pendentes` (filtra `status in (aprovado, falhou)`) | — |
| Campanhas em massa | ✅ sem IA. Marcadores `[Nome]`/`[Empresa]`, envio só aos selecionados, edição de destinatário, lista de bloqueio, rastreio de entrega/abertura | `campanha_service`, `campanha_personalizacao`, `bloqueio_contato_service` | Não |
| Respostas assistidas | ⚠️ parcial | `qualificacao_service` (S.H.A.R.K.) gera sugestão de resposta a inbound de WhatsApp/e-mail, grava em `TurnoConversa` e **não envia** ao lead. Só notifica o vendedor. | Sim, **não medida**, disparada por webhook externo |
| Reuniões / NPS / dossiê | ✅ | `reuniao_service`, `nps_service`, `dossie_service`, `meeting_bot_service` (Recall → resumo por IA) | Resumo por IA, não medido |
| Aprendizado | ✅ | `regra_aprendida_service`: regras escritas por humano entram no prompt de cadência. Há sugestão de regra por IA. | Sim, não medida |
| Inteligência comercial | ✅ | `sinal_oportunidade_service` (fit de ICP, match de Intent, riscos de pipeline, atribuição), `agente_corporativo_service` (responde a outras empresas do Shoal sob aprovação), `conta_service.sugerir_estrategia_venda` | Sim. 2 de 4 chamadas medidas. |
| Indicações | ✅ | `indicacao_service.solicitar` (texto por IA, sob aprovação) | Sim, não medida |
| Webmail / e-mail direto | ✅ humano | `email_direto_service` | Não |
| LinkedIn | ✅ só tarefas manuais (nunca auto-envio, por risco de ban); tela **Tarefas de LinkedIn** com contador no menu (D-107) | `linkedin_service`, `tarefa_linkedin`, `pages/linkedin/TarefasLinkedin.tsx` | Não |
| LGPD (opt-out, ROPA, titulares, supressão) | ✅ | `optout_service`, `ropa_service`, `titular_service` | Não |

## 2. Fontes de dados externas usadas

Receita Federal (recorte local por CNAE/UF, carregado no runner do
GitHub Actions), BrasilAPI, HTML do site institucional, Brave Search,
Lusha, SendGrid/SMTP, Meta WhatsApp Cloud, Recall.ai, Google Calendar.

## 3. Acoplamentos (detalhe em `DOMAIN_DEPENDENCY_MAP.md`)

- **C3**: geração de lista por ICP, enriquecimento (site, BrasilAPI,
  lote) e mapeamento de decisores estão em `app/api/v1/contas.py`, sob
  `_exige_crm`. Um tenant **só-PREDATOR não consegue gerar lista nem
  enriquecer**. Um tenant só-CRM recebe essas rotas.
- **C4**: `POST /leads/contas` (PREDATOR) é o caminho usado pelo Kanban
  do CRM para criar conta.
- **C5**: `ofertas` (PREDATOR) é referenciada por `Negocio.oferta_id` (CRM).
- `conta_service.py` (1.683 linhas) mistura CRM, PREDATOR e Intelligence.
- `CrmProvider` é a única porta formal PREDATOR → CRM
  (`criar_ou_atualizar_oportunidade`, `anexar_nota`). O restante
  acessa o ORM do CRM diretamente.
- PREDATOR escreve `Conta`/`Decisor`, que são do CRM. Na prática,
  Organization/Person são shared kernel, sem estar declarados assim.

## 4. Defeito de plano avulso

Os 3 planos "PREDATOR Starter/Professional/Enterprise" foram
inseridos com `franquia_contas_mes=0`, `limite_cadencias_mes=0`,
`limite_campanhas_mes=0` e limites de enriquecimento 0. O comentário
na migração diz que esses zeros deveriam valer só para MAP/CRM. Com
0, `limite_criacao_service`/`franquia_service` bloqueiam o uso. Ver
`PRICING_CURRENT_STATE.md` §4 e `OPEN_ISSUES.md` OI-001.

## 5. O que falta para o PREDATOR virar bounded context consumível por API (§8, §66)

1. Mover as rotas de prospecção de `contas.py` para um router
   PREDATOR, mantendo os paths (compatibilidade), e partir
   `conta_service` em serviços por contexto.
2. Declarar Organization/Person (Conta/Decisor) como shared kernel com
   interface de leitura/escrita. O PREDATOR escreve via contrato.
3. Endpoints `/api/v1/predator/*` (Fase 3) sobre esses serviços.
4. Medir todas as chamadas de IA (Fases 4/5).

## 6. Mudanças da Fase 1 (2026-09-25)

- Prospecção (gerar lista, enriquecimento de site/BrasilAPI/lote,
  mapeamento de decisores, descoberta de domínio) extraída para
  `app/contexts/predator/prospeccao.py`, com contrato em
  `app/contexts/predator/contract.py`.
- Rotas correspondentes em `app/api/v1/prospeccao_contas.py`, sob o
  gate do PREDATOR, com os mesmos paths (C3).
- `leads`, `contas`, `decisores`: CRM **ou** PREDATOR (C4, D-007).
  `ofertas`: CRM ou PREDATOR (C5). `nps`: MAP ou PREDATOR (C6).
- Os limites 0 dos planos PREDATOR avulsos (OI-001) **continuam**: o
  tenant só-PREDATOR agora alcança as rotas, mas a franquia continua
  bloqueando o uso.

## 7. Campanhas, envio e entrega (2026-10-24 a 2026-10-28, D-104 a D-108)

- **Disparo**: "Marcar como pronta" reserva a campanha (`campanha.processando_ate`, 10 min) e envia em segundo plano, um destinatário por vez com um
  commit por envio (`campanha_service._enviar_pendentes`); o agendador (`/cron/processar-campanhas`) retoma o que ficou parado. Falha de rede para o ciclo e
  retoma depois; nada é reenviado. Status do destinatário: `pendente`, `enviado`, `falhou`, `optout`, `retido`, `nao_enviado`.
- **Envio seletivo**: `POST /campanhas/{id}/marcar-pronta` aceita `destinatario_ids`; os demais pendentes ficam `retido` até o fim da rodada e a campanha
  volta a `rascunho`. `POST /campanhas/{id}/voltar-para-rascunho` permite editar uma campanha já enviada (quem recebeu não recebe de novo).
- **Personalização**: `[Nome]`, `[Nome completo]`, `[Empresa]` (`campanha_personalizacao.renderizar`); sem nome o marcador some com a pontuação, sem empresa
  entra "a sua empresa". `GET /campanhas/{id}/previa` mostra o resultado. `app/core/texto.corrigir_codificacao` conserta acentos trocados na lista colada.
- **Destinatários**: `PUT .../destinatarios/{id}` (trocar e-mail zera entrega/abertura/bounce e devolve à fila; quem já recebeu exige `reenviar`) e
  `POST .../nao-quer-receber` (grava em `bloqueio_contato` e aplica o opt-out completo se o contato veio do CRM). `GET/DELETE /bloqueios-contato` (liberar: admin).
- **Canal de e-mail**: duas contas por tenant, a API do cliente (`configuracao_email_api`, `GET/PUT/DELETE /configuracao-email-api`, `POST .../testar`) com
  prioridade sobre o SMTP (`configuracao_email_smtp`). Só a API devolve entrega/bounce/spam, pelo aviso assinado `POST /webhooks/envio/eventos`; a abertura vem
  do pixel (`rastreamento_service`, indicador aproximado). Com SMTP, `POST /relatorio-entrega/bounces-manuais` registra os e-mails que voltaram.
- **Erros de SMTP**: `smtp.py` informa a etapa (conexão, TLS, login, remetente, destinatário, envio) e o IP; `SMTPRecipientsRefused` é tratado antes de `OSError`
  (é subclasse dele) e e-mail de formato inválido vira `nao_enviado`, nunca falha nem bounce.
- **LinkedIn**: `GET /linkedin/tarefas`, `GET /linkedin/tarefas/contagem` (menu) e `POST /linkedin/tarefas/{id}/marcar` (idempotente).
- **Limites por plano**: `limite_cadencias_mes` e `limite_campanhas_mes` contam criações no mês (`limite_criacao_service`); ver `PRICING_CURRENT_STATE.md`.
