# PHASE F — BUSINESS NETWORK INTEGRATION (acesso do fornecedor) · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, pré-autorização das próximas fases.
- **ADR**: D-066 · **Plano**: `18_STRATEGIC_SOURCING.md` §10.

## O que a Phase F pedia × o que existe

| Item (§42) | Estado | Onde |
|---|---|---|
| Publicação / convite | **novo**: o comprador gera um link secreto por participante (sem login, sem assento — Supplier Guest). Só o hash SHA-256 é guardado; gerar de novo revoga o anterior; o segredo vai no fragmento da URL (`#…`) e no cabeçalho `X-Convite-Token`, nunca no caminho nem no log | `procurement/portal.gerar_acesso`, `POST /sourcing/processos/{id}/participantes/{pid}/acesso` |
| Supplier matching | reutilizado da Phase E (`descobrir` + `criterios_fornecedor`); empresa da rede convidada passa a ver o convite na própria conta | `GET /rede/convites-sourcing` |
| Visibilidade controlada | **novo**: o fornecedor vê só o próprio convite: título, descrição, prazo, requisitos (sem peso), itens, esclarecimentos respondidos (sem quem perguntou) e as próprias propostas. Não vê valor estimado, avaliações, notas, aprovação nem outros participantes. Rascunho não existe para ele (404). Situação pública reduzida: aberto / em análise / em negociação (só para shortlist, ou RFQ) / encerrado / cancelado | `portal.visao`, `_situacao_publica` |
| Acesso do fornecedor para responder | **novo**: perguntas (esclarecimentos) respondidas pelo comprador e visíveis a todos; proposta pelo portal (canal `PORTAL`) com itens, prazo, pagamento e respostas; anexos PDF/TXT validados pelo mesmo `documentos.validar` (máx. 10 por proposta); declinar o convite. Nova rodada só quando o fluxo permite (negociação só para a shortlist) | `portal.*`, `api/v1/portal_fornecedor.py` |
| Lado do comprador | esclarecimentos com resposta, download dos anexos, marca "enviada pelo fornecedor", botão "Link de acesso" | `SourcingWorkspace.tsx`, `strategic_sourcing.py` |
| Telas | **novas**: `/portal-fornecedor` (pública, lê o segredo do `#`), `/convites-compra` (empresa da rede, logada); mesmo componente `PortalFornecedor` nas duas | `pages/portal/*` |

Confidencialidade (barreira §26): o convite recebido não vira dado do lado vendedor da empresa convidada (`/bids/licitacoes` continua vazio); nada da Phase F chama IA.

Fora do escopo (próximas fases): IA de avaliação/comparação (Phase G); e-mail automático do convite (o comprador envia o link; notificação transacional fica para quando houver canal de e-mail aprovado); plano comercial do módulo (Phase I).

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 11: migração `e1b3d5f7a9c0`, `procurement/portal.py`, `api/v1/portal_fornecedor.py`, `pages/portal/{PortalFornecedor,PortalLink,ConvitesRecebidos}`, `components/sourcing/{CamposProposta,lerProposta}`, `test_sourcing_fase_f.py`, `e2e/portal-fornecedor.spec.ts`, `perf/fase_f.json` |
| Arquivos modificados | 17 |
| LOC da aplicação | +1.148 / −67 (backend ≈ 520, telas ≈ 520, migração ≈ 110) |
| LOC de testes | +226 / −6 |
| Duplicação | 46 → **46** blocos (~2.193 linhas, sem novo). O formulário de proposta do portal repetia 12 linhas do formulário do comprador; extraído `CamposProposta` + `lerProposta`, usados pelos dois |
| Compartilhado criado | `CamposProposta`/`lerProposta`, `requisitar` + `API_BASE_URL` exportados em `lib/api.ts`, `participante_por_token`/`participantes_da_empresa` no repositório nativo, `limitador_portal` |
| Reutilizado | repositório nativo, workflow (`_pode_enviar` segue o mesmo fluxo), `estrategico.registrar_proposta` (canal), validação de documentos, privacidade da rede, auditoria, rate limit |

## Performance budget (§36)

| Medida | Phase E | Phase F |
|---|---|---|
| Rotas anteriores | — | consultas **iguais** |
| Workspace do comprador privado | 10 consultas · p95 ≈ 26 ms | **12** consultas (+ esclarecimentos, + anexos; constante com o volume) · p95 ≈ 28 ms |
| Comparação | 10 · p95 ≈ 25 ms | 10 · p95 ≈ 25 ms |
| Bundle | 1.325,2 KB / 62 | 1.335,1 KB / 66 (+10 KB: telas do portal em chunks próprios) |
| Inicialização / memória | 3.661 ms / 249,3 MB | 3.790 ms / 250,1 MB (ruído + dois routers) |

O conteúdo do anexo é coluna `deferred`: listar anexos no workspace não carrega os bytes.

## Validação

| Evidência | Resultado |
|---|---|
| `test_sourcing_fase_f.py`: link sem login vê só o próprio convite (sem peso, valor estimado, outros participantes, avaliações, justificativa interna); segredo fora do log; esclarecimento sem autor para os demais; proposta e anexo pelo portal chegam ao comprador; anexo inválido 422, em proposta alheia 404; após a avaliação não envia mais (409); sem assento e sem IA · link revogado/inventado/vazio → 404 igual, só hash guardado · negociação só para a shortlist, o outro não sabe que ela existe; declinar · empresa da rede vê só os próprios convites, outro tenant 404, e o convite não aparece no lado vendedor | ✅ 4/4 |
| Postgres 16: migração up/down/up (`PG_MIGRACOES_OK e1b3d5f7a9c0`), triggers de lado nas 2 tabelas novas | ✅ + 6/6 testes PG anteriores |
| Fitness: barreira Buy/Sell (API do portal declarada do lado comprador), tabelas unificadas só pelo núcleo (inclui esclarecimento e anexo), toda FK com índice | ✅ |
| Suíte completa (leitura dupla ESTRITA) | ✅ **2.071 passed** (+7 skipped: 6 Postgres, 1 medição) |
| E2E | ✅ **10/10** (inclui fornecedor num contexto sem login: abre o link, pergunta, envia proposta; comprador vê a proposta do portal) |
| Ruff 40 · oxlint 25 · build | ✅ sem novos |

## Próximo passo

Phase G — Intelligence (Requirement, Evaluation, Bid, Procurement e Supplier Intelligence, Risk, Recommendation) pelo AI Gateway existente, com testes de grounding.
