# NETWORK_GAP_ANALYSIS.md — B2B ON (2026-09-17)

Comparação honesta entre o que o master prompt "B2B ON Business
Operating System" descreve e o que existe de fato no repositório hoje.
Objetivo: não redescobrir/reconstruir o que já existe com outro nome, e
ser realista sobre o tamanho do que falta.

## Descoberta principal

**B2B ON já tem pedaços reais de quase todo conceito do master prompt
— construídos sob nomes em português, em ondas anteriores de
desenvolvimento ("Onda B", "Onda C", "E5-H1" etc.) — só que
fragmentados, sem uma camada de IA transversal amarrando tudo.** Não é
um projeto greenfield disfarçado de CRM: é um produto já maduro (964
testes, produção real, clientes reais) que já resolveu, à sua maneira,
boa parte dos problemas que o master prompt descreve.

## Mapa: conceito do master prompt → o que já existe

| Master prompt | Já existe? | Onde |
|---|---|---|
| Human-in-the-loop / approval gate | **Sim, robusto** | `Aprovacao`/`Mensagem`, ver `AI_CURRENT_ARCHITECTURE.md` §3 |
| AI Provider abstraction | **Sim (mas 1 provider só)** | `app/llm/base.py` |
| Company Connections (follow/connect/accept) | **Sim** | `ConexaoEmpresa` (`pendente\|aceita\|recusada`) |
| Corporate Profile (cartão de empresa) | **Parcial** | `PerfilEmpresa` — só `nome_exibicao/descricao/setor/site`, bem mais raso que o schema do master prompt (sem CNAE, funcionários, faturamento, certificações, tecnologias) |
| Company-to-company messaging | **Sim** | `MensagemRedeSocial`, exige conexão aceita |
| Corporate Rooms multi-canal (`GENERAL/COMMERCIAL/TECHNICAL/...`) | **Não** | A mensageria de Rede Social é 1:1, sem canais/threads/arquivos |
| Business Graph (nós/arestas tipadas) | **Parcial, e frágil** | Neo4j (`app/graph/client.py`) só modela Conta/Decisor/Interação/Indicação — não tenant-a-tenant, não SUPPLIER_OF/PARTNER_OF/etc.; instância já caiu em produção (Aura Free auto-pausa); zero consumo no frontend |
| Company Claim / verification states | **Não** | Toda `Conta` já "pertence" ao tenant que a criou/importou — não existe conceito de "empresa não reivindicada na rede" |
| Business Intent (marketplace de necessidades declaradas) | **Não** | Não existe `Intent`/`BusinessIntent` em lugar nenhum |
| Opportunity Signal / AI Match Engine | **Não, mas há adjacências fortes** | `QualificacaoScore` (score S.H.A.R.K. por conversa) e o cálculo de fit de ICP em `conta_service._score_aderencia` já fazem scoring explicável (critério + razão), só que não cruzam sinal de rede — hoje é 100% dados internos do próprio tenant |
| Agent Registry / AI Orchestrator | **Não** | Cada feature de IA é uma chamada direta e isolada a `generate()`, sem orquestrador escolhendo agente/ferramenta/modelo |
| ICP Agent / Intent Agent / Stakeholder Agent / Opportunity Agent / etc. | **Não como agentes — sim como funções soltas** | `_score_aderencia` (ICP), `qualificacao_service` (mais perto de "Intent/Stakeholder" que qualquer coisa), `saude_conta_service.gerar_script_resgate` (mais perto de "Sales Strategy Agent") — nenhum tem `agent_id`/tool-calling/memory_scope |
| Corporate Brain / Company Intelligence Profile | **Não** | Nenhuma memória persistente por tenant alimentando prompts futuros |
| User Intelligence Profile (aprender estilo do vendedor) | **Não** | Zero personalização por usuário nos prompts hoje |
| Learning Events / Feedback Loop | **Não estruturado** | Existe o dado bruto pra isso (131 pontos de `auditoria_service.registrar`, edições de mensagem com antes/depois) mas nada lê esse histórico de volta pra ajustar uma próxima geração |
| RAG / vector search / memória de longo prazo | **Não** | Zero embeddings, zero pgvector, zero histórico de conversa persistido entre chamadas de IA |
| Business Feed / Posts / reações / comentários | **Não** | Rede Social é diretório + conexão + DM; não existe conceito de post/feed |
| Notifications (central, tempo real) | **Muito parcial** | `NotificacaoVendedor` é o único tipo, sem WebSocket/SSE, **sem consumo nenhum no frontend** hoje — é infraestrutura órfã |
| Buying Room / Stakeholder Map / Pipeline Agent | **Não como tal** | `Negocio`/`EstagioFunil` cobre pipeline básico; Registro de Oportunidade (RO/PRIME) cobre dedupe de deal registration dentro de uma rede de distribuidores — mais perto de "channel conflict prevention" que de "digital buying room" |
| Trust Layer (verificação de CNPJ/domínio/e-mail corporativo) | **Não formalizado** | CNPJ é só um campo de texto (agora normalizado, ver memória de bug recente); não há fluxo de verificação/claim |
| Feature flags genéricos | **Não — é hardcoded por plano** | `PlanLimitsProvider`, ~10 métodos fixos, 1:1 com colunas de `Plano`; qualquer novo flag exige migração + código, não é data-driven |
| Multi-tenancy + isolamento | **Sim, maduro** | `tenant_id` em quase toda tabela, hierarquia de distribuidor/revendedor/cliente, escopo por papel — ver `SECURITY_BOUNDARIES.md` |
| Auditoria | **Sim, extenso (131 call sites)** | `AuditLog`, mas manual por call site, não estrutural (nada impede um novo código de esquecer de auditar) |
| Background jobs / workers | **Não — cron HTTP, sem fila** | GitHub Actions chamando endpoints; sem Celery/Redis/SQS |

## O que isso significa pra sequenciar o roadmap do master prompt

O master prompt pede, na Fase 0.5, construir **antes de qualquer rede
social**: AI Provider abstraction (✅ já existe), AI Orchestrator (❌),
Context Engine (❌), Corporate Brain (❌), Agent Registry (❌),
Learning Loop (❌), RAG isolado por tenant (❌).

Isso é, na prática, pedir para construir **do zero** uma camada de
orquestração de agentes + memória corporativa + RAG multi-tenant —
não é uma refatoração incremental de algo que já existe parcialmente,
é infraestrutura nova, cara, e de alto risco se malfeita (a seção 69
do master prompt, "RAG Isolation", é exatamente o tipo de coisa que
vaza dado entre tenants se apressada — e isolamento entre tenants é a
regra mais crítica de todo este produto, reforçada dezenas de vezes no
próprio master prompt).

Ao mesmo tempo, **as Fases 1-2 (Network Foundation + Business Social)**
do master prompt já estão, em grande parte, **feitas** sob o nome
"Rede Social" — reconstruir isso do zero com nomenclatura em inglês
seria retrabalho puro, sem ganho.

## Recomendação (não uma decisão tomada — pra validar com você)

1. **Não seguir a ordem literal do master prompt** (Fase 0.5 =
   Orchestrator/Corporate Brain antes de qualquer coisa). Isso
   significa meses de infraestrutura especulativa antes de qualquer
   valor visível, em cima de um produto que já está em produção com
   clientes reais (ex.: o trabalho desta mesma sessão — bug de CNPJ,
   relatório de entrega — são o tipo de coisa que compete por atenção
   com isso).
2. Se o objetivo é genuinely caminhar pra "Business Operating System",
   o approval gate + audit trail + provider abstraction já dão uma
   base sólida — o primeiro passo de maior ROI provavelmente é
   **fechar o loop de aprendizado mais simples que já tem dado pronto**:
   ligar as 131 auditorias + os pares antes/depois de edição de
   mensagem a alguma coisa que realmente influencie a próxima geração
   (mesmo que simples: "estas 5 aberturas de frase foram removidas
   repetidamente, não use de novo") — é pequeno, mede-se resultado
   rápido, e é literalmente o "Feedback Learning Loop" da seção 13/14
   do master prompt, sem precisar de Corporate Brain/RAG genérico.
3. Rede Social → Business Graph de verdade é o segundo maior gap real
   (hoje é 1:1, sem posts, sem grafo tipado, Neo4j não confiável em
   produção) — mas só vale investir aqui se houver evidência de que
   clientes usam ou pediriam usar essa parte hoje pouco usada.
4. Business Intent / Match Engine / Buying Rooms são, honestamente, o
   maior salto de escopo do documento — produtos inteiros por si só.
   Não recomendo comprometer com eles sem antes validar demanda real.

**Pergunta em aberto pra você decidir, não pra eu decidir sozinho**:
quer que eu trate este master prompt como norte de longo prazo (e a
gente prioriza pedaço por pedaço, com plano/aprovação a cada fase,
como já fazemos nesta sessão) ou você já tem um pedaço específico em
mente pra atacar primeiro?
