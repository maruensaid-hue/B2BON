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

---

# Fase 8 — NETWORK INTELLIGENCE

| Item | Onde | O que mudou |
|---|---|---|
| Business Matching | `sinal_oportunidade_service` (fit ICP, match de intent) | candidatos passam por `privacidade.perfis_visiveis` (sem bloqueadas, sem ocultas não conectadas); explicação por IA também |
| Intent Intelligence | sinal `intent_compativel` | lado vendedor: intents abertas de outras empresas, **visíveis** para o tenant, que o perfil dele atende (evidência `intent:<id>`) |
| Relationship Intelligence | `network/relacionamento.py` | `forca` FORTE/MODERADA/FRACA/NENHUMA com motivos: conexão (+2), relacionamento confirmado (+2) ou declarado (+1), interação ≤14 dias (+2) ou ≤30 (+1) |
| Opportunity Signals | `sinal_oportunidade` | aresta privada não vira sinal; empresa bloqueada não gera sinal |
| Network → CRM | `network/conversao.py` + `crm.contract.abrir_ou_reaproveitar_oportunidade` | conta + negócio (origem `rede_signal`, sem decisor inventado) |
| Network → PREDATOR | idem, `destino=predator` | só a conta, como lead de prospecção |
| Corporate Rooms foundation | `sala_corporativa_service` | só as duas empresas; sem conexão ativa (desconexão/bloqueio) a sala fica só leitura |

## GATE — sinal vira oportunidade sem duplicação

`POST /inteligencia-rede/sinais/{id}/converter?destino=crm|predator`
(padrão: CRM se o plano tiver; destino sem o módulo = 403).

1. **Conta**: reaproveita a do tenant para a mesma empresa: gerada por
   outro sinal dela, mesmo CNPJ ou mesmo domínio. Só cria se não houver.
2. **Negócio** (CRM): reaproveita o negócio aberto da conta; senão cria no
   primeiro estágio e publica `OpportunityCreated` uma vez.
3. **Sinais irmãos**: todos os sinais em aberto da mesma empresa-alvo são
   fechados juntos com a mesma conta/negócio. Sinal novo de empresa já
   convertida nasce convertido. Reconverter = 409.
4. Empresa bloqueada: 409.

Limite: dois cliques simultâneos em sinais diferentes da mesma empresa
podem, em teoria, criar duas contas (sem lock; TD-057).

## Privacidade adicional

Os matches de uma intent podem ser vistos por qualquer empresa que vê a
intent. Antes, os "sinais" do match revelavam a terceiros a conexão e
relacionamentos (inclusive privados) entre o autor e o candidato. Agora a
conexão só aparece para as partes e o relacionamento só se o consultante
puder ver a aresta.

---

# Fase 11 — CORPORATE ROOMS & BUYING ROOMS

Módulo `app/contexts/network/salas.py`; rotas em `/rede-social/salas/*`;
UI: painel da sala (tarefas, reuniões, documentos, comitê) no modal da Sala Corporativa.

| §84 Fase 11 | Entrega |
|---|---|
| Corporate Rooms, channels, messages | existentes (Fase 4A/5A) + permissão por usuário em todas as rotas |
| permissions | `participante_sala`: se a empresa definir participantes, só eles (EDITOR/LEITOR) e os admins dela entram; LEITOR não escreve; cada empresa define e vê só o próprio lado |
| documents | `documento_sala` com hash; documento em canal herda o escopo do canal |
| tasks | `tarefa_sala`; tarefa interna não pode ter a outra empresa como responsável |
| meetings | `reuniao_sala` |
| Buying Rooms | `sala_compra` + título e fase **compartilhados** (DESCOBERTA…IMPLANTACAO) |
| stakeholders | `stakeholder_sala` (lado, BuyingRole, notas), **interno por padrão**; notas nunca vão para a outra empresa, mesmo em item compartilhado |
| shared/internal boundaries | regra única `salas.visivel(escopo, dono, consultante)` |

## GATE — nenhum dado interno exposto indevidamente

- Canal, mensagem, documento, tarefa, reunião e stakeholder **internos** não
  aparecem no workspace nem por id para a outra empresa (404).
- **Correção**: antes, o comprador via o nome interno do negócio e o estágio
  do funil do vendedor na sala de compra. Agora vê só o título e a fase que o
  vendedor compartilhou (padrão "Proposta em andamento"); valor, probabilidade,
  nome e estágio ficam no CRM do vendedor.
- Participantes: usuário fora da lista é barrado (403); o comprador não vê
  quem participa pelo vendedor.
- Empresa de fora da sala: 403 em todas as rotas.

Testes: `tests/integration/test_salas_corporativas.py` (4) + testes das
Fases 4A/5A/8 ajustados (o de sala de compra agora exige que o comprador
**não** veja o nome do negócio).
