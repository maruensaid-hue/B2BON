# 10 — BUSINESS NETWORK FOUNDATION (Fase 7, §27–§29)

Contexto: `app/contexts/network/` (contrato: `contract.py`). A rede já
existia como "Rede Social / Shoal" (D-004): perfil, diretório, conexões,
seguidores, mensagens, feed, intents, salas, verificação. A Fase 7 não
reescreve isso (strangler). Ela cria a camada de identidade, grafo e
privacidade que as Fases 8–10 consomem, e passa as regras de
visibilidade para um lugar só.

| Conceito §27 | Onde | Estado |
|---|---|---|
| Corporate / Company Identity | `empresa_rede` + `network/identidade.py` | **novo** |
| Company Claim | `identidade.reivindicar`, `POST /rede-social/identidades/{id}/reivindicar` | **novo** |
| Membership | `network/membership.py`, `GET /rede-social/membros` | **novo** (projeção, D-025) |
| Company Connections | `conexao_empresa` (existente) | privacidade unificada |
| Business Graph | `relacionamento_empresarial` (+ identidade, fonte, validade) + CONNECTED_TO derivada; `GET /rede-social/grafo/{empresa}` | **completado** |
| Company Profile | `perfil_empresa` (+ `visivel_no_diretorio`) | privacidade |
| Business Feed foundation | `post_rede_social` (existente) | bloqueio aplicado |
| Intent Marketplace foundation | `intent` (existente) | regra única de visibilidade |

## 1. Company Identity e Claim

- Toda empresa-cliente tem uma identidade (`status` REIVINDICADA ou
  VERIFICADA, sincronizado com a verificação do perfil). A migração cria
  as identidades dos perfis existentes e liga as arestas antigas.
- Uma empresa fora da rede pode ser citada por CNPJ
  (`POST /rede-social/relacionamentos/por-cnpj`): nasce NAO_REIVINDICADA,
  com CNPJ (dígitos verificadores conferidos) e o nome informado por quem
  citou (`origem = DECLARADA_POR_TERCEIRO`). Citações seguintes do mesmo
  CNPJ reaproveitam a identidade; CNPJ que já tem dono aponta para o tenant.
- **Claim**: admin de empresa **verificada** cujo CNPJ é igual. As
  arestas passam a apontar para o tenant (que então pode confirmá-las) e a
  identidade antiga fica MESCLADA. Sem verificação: 409. CNPJ diferente: 403.

## 2. Business Graph (§28, §29)

Implementado sobre tabelas relacionais (D-024), sem graph database. Cada
aresta canônica (`shared/canonical/network.BusinessEdge`) tem:

| §28 | Campo |
|---|---|
| source | `fonte`: DECLARADA, CONFIRMADA, CONEXAO |
| visibility | `publica` / `conexoes` / `privada` |
| confidence | ALTA (confirmada pela contraparte ou conexão), MEDIA (autodeclarada), BAIXA (fora da validade) |
| verification | `autodeclarada`, `confirmada_pela_contraparte`, `conexao_aceita` |
| validity | `valido_desde`, `valido_ate` |
| creator | tenant que declarou (+ `criado_por` usuário) |
| metadata | `metadados` |

Tipos: os 12 do §28 (CONNECTED_TO derivada de conexão aceita, não
gravada duas vezes) + INVESTS_IN legado. Grafos lógicos: COMPANY e
RELATIONSHIP aqui; PEOPLE (decisores) continua privado do tenant e fora
da rede; OPPORTUNITY e PROCUREMENT entram nas Fases 8–10 na mesma forma.
O Neo4j legado (`app/graph`) modela só dados internos do CRM e não é
usado pela rede (TD-054).

## 3. Privacidade (GATE)

Regra única: `network.privacidade.pode_ver(consultante, autor, visibilidade, partes)`.

| Visibilidade | Quem vê |
|---|---|
| `publica` | toda a rede, **menos** empresas com bloqueio (qualquer direção) |
| `conexoes` | autor, partes citadas e empresas com conexão aceita com o autor |
| `privada` | só o autor. **Nem a empresa citada vê** (antes via; corrigido) |

Aplicada a arestas do grafo, intents e feed (bloqueio). CONNECTED_TO só
aparece no grafo da própria empresa. `visivel_no_diretorio = false` tira
a empresa do diretório para quem não é conexão (padrão: visível, OI-014).
Dado de CRM (contas, negócios, necessidades, margens, ticket, objeções) não
é lido pelo contexto: a vitrine mostra só nome e descrição da oferta
ativa. Identidade não reivindicada expõe só CNPJ e nome.

## 4. Membership (D-025, D-026)

Usuário pertence à empresa do seu tenant. ADMIN (`admin`, `super_admin`)
muda a identidade pública: editar perfil, declarar/confirmar/remover
relacionamento, reivindicar, visibilidade no diretório. MEMBRO (`user`)
participa: publicar, comentar, mensagens, conexões, intents, salas.
Antes da Fase 7, qualquer usuário editava o perfil e declarava
relacionamentos em nome da empresa.

## 5. Endpoints novos

| Método | Path | Quem |
|---|---|---|
| GET | `/rede-social/identidade` | membro (identidade + reivindicáveis) |
| POST | `/rede-social/identidades/{id}/reivindicar` | admin |
| POST | `/rede-social/relacionamentos/por-cnpj` | admin |
| GET | `/rede-social/grafo/{empresa_id}` | membro (arestas visíveis) |
| GET | `/rede-social/membros` | membro (só a própria empresa) |
| PUT | `/rede-social/perfil/visibilidade` | admin |

## 6. Fora do escopo desta fase

Business Matching, Relationship Intelligence, sinais → CRM/PREDATOR e
Corporate Rooms (Fase 8). Nome oficial da empresa citada via BrasilAPI
(TD-056). Disputa de claim com revisão humana (hoje a regra é CNPJ +
verificação).
