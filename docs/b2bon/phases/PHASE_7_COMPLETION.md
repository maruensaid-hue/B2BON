# PHASE 7 — BUSINESS NETWORK FOUNDATION · Completion Report

- **Data**: 2026-09-25 · **Branch**: `staging` · **Autorização**: PO (autorização geral das Fases 1–17)

## 1. Entregas (§84 Fase 7)

| Item | Entrega |
|---|---|
| Company Identity | `empresa_rede` (tenant ou não reivindicada), backfill dos perfis existentes, `GET /rede-social/identidade` |
| Company Claim | relacionamento por CNPJ com empresa fora da rede; reivindicação por empresa verificada com o mesmo CNPJ; arestas re-apontadas, identidade antiga MESCLADA |
| Membership | projeção usuário → empresa; ADMIN × MEMBRO; `GET /rede-social/membros` |
| Connections | existentes; CONNECTED_TO derivada no grafo; visibilidade `conexoes` passa a funcionar |
| Business Graph | aresta com source, visibility, confidence, verification, validity, creator, metadata (canônico `BusinessEdge`); `GET /rede-social/grafo/{empresa}` |
| Company Profile | `visivel_no_diretorio` (controle do admin) |
| Business Feed foundation | bloqueio aplicado ao feed |
| Intent Marketplace foundation | regra única de visibilidade (inclui bloqueio) |
| UI | card "Identidade da empresa na rede" (claim, visibilidade, relacionamento por CNPJ); ações de identidade escondidas para `user` |

## 2. GATE — privacidade e tenant boundaries

| Evidência | Resultado |
|---|---|
| Aresta privada: só o autor (nem a empresa citada) | ✅ corrigido (antes vazava) |
| Aresta de conexões: partes e conexões do autor | ✅ implementado |
| Bloqueio esconde arestas, feed e intents públicas (qualquer direção) | ✅ |
| CONNECTED_TO só no grafo da própria empresa | ✅ |
| Empresa fora do diretório só para conexões | ✅ |
| Dado de CRM (conta, margem, ticket, objeções, e-mail de usuário) não aparece em 6 endpoints da rede | ✅ |
| Membros: só a própria empresa | ✅ |
| Membership: `user` não muda identidade pública, mas participa | ✅ |
| Claim: sem verificação 409, CNPJ diferente 403, sucesso re-aponta e confirma | ✅ |
| Identidade não reivindicada expõe só CNPJ e nome | ✅ |
| `tests/integration/test_privacidade_rede.py` | ✅ 14 testes |
| Unitários CNPJ + Membership | ✅ `tests/unit/test_rede_identidade_membership.py` |
| Suite completa | ✅ **1.795 passed** |
| Frontend lint (25) + typecheck + build | ✅ |
| E2E | ✅ 4/4 |
| Migração `7dc1428d524f` em SQLite e Postgres 16, **backfill testado com dados** | ✅ |

## 3. Decisões

D-024 (grafo relacional), D-025 (Membership como projeção), D-026
(identidade pública só por admin), D-027 (privada = só autor).

## 4. Pendências

- **OI-014** (PO): empresas novas visíveis no diretório por padrão?
- TD-054 (Neo4j legado), TD-055 (bloqueio simétrico), TD-056 (nome oficial da empresa citada).
- Testes que declaravam relacionamento com tenant inexistente foram ajustados (fixture `tenants_da_rede`; na API agora é 404). Antes só passavam porque o SQLite não aplica FK; em Postgres a FK já recusava.
- OI-001, OI-010, OI-012, OI-013 continuam. Nenhum preço ou plano alterado.

## 5. Próxima fase

**PHASE 8 — NETWORK INTELLIGENCE.**
