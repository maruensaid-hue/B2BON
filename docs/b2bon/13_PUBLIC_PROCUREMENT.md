# 13 — PUBLIC PROCUREMENT — BUY SIDE (Fase 10, §37–§51)

Contexto: `app/contexts/procurement/` (contrato: `contract.py`). API:
`/api/v1/procurement/*`, gate **módulo `procurement`** (B2B ON Public
Procurement). **Preço: PENDING_DEFINITION** (§71). Nenhum plano inclui o
módulo; nada foi precificado ou alterado. UI: **Compras públicas**
(`/compras`, `/compras/processos/:id`), visível só com o módulo.

## 1. Entregas

| §84 Fase 10 | Onde |
|---|---|
| Public Organization, Procurement Units | `orgao_publico` (regime jurídico e `parametros` configuráveis: não presumimos um regime único), `unidade_compras` |
| Demand Management | `demanda_compra` + análise determinística (duplicidade, processos similares, contratos existentes, informações faltantes, consolidação), sempre "para revisão humana". Aprovação só por admin |
| Procurement Planning / PCA | `plano_contratacao`, `item_pca`, painel (§39: planejado, comprometido, contratado, executado, % execução, atrasos, demandas em risco, próximas contratações). Aprovação do PCA só por admin |
| Procurement Process Workspace | `processo_contratacao` + `evento_processo` (aprovações, esclarecimentos, tarefas, marcos); workspace com demanda, planejamento, documentos (ETP/TR), preços, contrato, timeline, **auditoria** e AI Insights |
| Supplier 360 / Intelligence | `fornecedor_compras`; blocos **OFFICIAL / INTERNAL / SELF_DECLARED** (este último, do perfil público do fornecedor na rede, só se ele estiver no diretório); ranking por categoria |
| Price Research foundation | `pesquisa_preco` (todo preço com fonte); mediana, média, CV, amostras suficientes (≥3), cotações a ±30% da mediana. **A plataforma não gera preço** |
| Contract Management / Intelligence | `contrato_compra`, `evento_contrato_compra` (aditivo, entrega, fiscalização, pagamento, ocorrência...); saldo, % executado, aditivos, acréscimo, nota média |
| Procurement Risk Engine (§46) | 11 sinais; linguagem "requer revisão / sinal analítico / possível inconsistência"; sem conclusão jurídica; fragmentação só com limite configurado pelo órgão |
| Procurement Next Best Action (§45) | ações a partir dos sinais (ex.: "Considere iniciar o planejamento da contratação sucessora.") |
| Document Intelligence (§48) | `documento_compras` com hash, fonte, classificação (padrão CONFIDENTIAL), texto por página; IA `procurement.analise_documento` (C3) com o mesmo grounding da Fase 9; **RESTRICTED nunca vai para IA** |
| Audit Trail | toda mutação registrada; o workspace mostra a trilha do processo |

## 2. BARREIRA BUY/SELL (GATE §50, §80)

| Camada | Como |
|---|---|
| Tenant isolation | toda consulta filtra `tenant_id`; referência cruzada (ex.: `orgao_id` de outro tenant) = 404; `tenant_id` e campos de aprovação não vêm do corpo |
| Entitlement | módulo `procurement`; vendedor sem o módulo = 403 em tudo |
| Purpose limitation (estrutural) | fitness function `tests/unit/test_barreira_buy_sell.py`: só o contexto de procurement, a API do comprador e `app/models` importam os modelos ou citam as tabelas. Sell Side (Bids), PREDATOR, CRM, MAP, Opportunity, Business Network e Intelligence **não têm caminho de código** até esses dados |
| Corporate Brain | procurement não escreve no Brain (fitness), então o Agente Corporativo (que responde a outras empresas) não tem de onde tirar o plano de compras |
| Data classification | tudo CONFIDENTIAL; documento RESTRICTED fora da IA |
| Direção permitida | público → comprador (perfil público do fornecedor no Supplier 360). Nunca comprador → vendedor |

Teste crítico (`tests/integration/test_public_procurement.py`):
**sem acesso** (403 sem módulo), **sem recuperação** (outro tenant com o
módulo vê listas vazias e 404), **sem vazamento** (9 superfícies do lado
vendedor e da rede respondem 200 sem o segredo, o valor ou o preço), **sem
revelação indireta por IA** (o Agente Corporativo do comprador responde a um
vendedor e o prompt enviado à IA não contém o plano), e **mesmo tenant com
os dois módulos**: análise de edital, matriz e Go/No-Go do lado vendedor não
recebem dado do lado comprador.

## 3. Fora do escopo

Publicação de processos para fornecedores (projeção pública), integração
com sistemas oficiais de compras, OCR, precificação do módulo (Fase 15,
depende do PO).

## 4. Correção 2026-09-26 — Buy Side em dois segmentos (D-055)

Public Procurement é o segmento público do Buy Side. **Enterprise Strategic Sourcing** (RFI/RFP/RFQ
emitidos por empresa, convite, propostas, comparação, qualificação e negociação) é o segmento privado:
não existe hoje (gap G2) e será configuração do mesmo núcleo `sourcing` com ruleset
`ENTERPRISE_SOURCING`. Documentos, achados (hoje JSON), processo, eventos e contrato migram para as
tabelas compartilhadas; PCA, demanda e pesquisa de preço ficam aqui (regulatórios). As regras hoje
fixas (`DOCUMENTOS_ESPERADOS`, sigilo, fragmentação) viram o ruleset `PUBLIC_PROCUREMENT_BR_14133`.
**A barreira Buy/Sell não muda de garantia**: muda de mecanismo (repositório por lado + fitness function
reescrita antes da migração), `18_STRATEGIC_SOURCING.md` §2.3.

**Executado (S2, D-057)**: `RepositorioCompra` (lado fixo BUY) atende workspace e sinais de risco; a fitness
nova `tests/unit/test_barreira_sourcing.py` roda junto com a antiga e cobre também as tabelas do vendedor e a
neutralidade do núcleo `sourcing`.

**Executado (S3, D-058)**: os dados do comprador são espelhados em `*_sourcing` com `lado = BUY` (imutável),
incluindo os achados de documento como requisitos; leituras conferidas contra as tabelas novas. Só o núcleo
`sourcing` acessa as tabelas unificadas e só o comprador passa `Lado.COMPRA` a ele (fitness).

## 5. Posição comercial (D-059)

- **B2B ON Public Procurement** é o produto do comprador público (*planejar e executar contratações públicas*).
- Preço continua **PENDING_DEFINITION** e a franquia de AI Credits continua PENDING_FINAL_DEFINITION (OI-017).
- É distinto do **B2B ON Strategic Sourcing** (comprador privado), mas os dois usam os mesmos engines, cada um com
  ruleset, permissões e barreira próprios.

## 6. B2B ON Government (D-072)

O órgão público contrata pelo modelo **Government**: licença institucional + implantação + subscrição anual (ou só subscrição
anual, quando o edital exigir), com pool anual de AI Credits. As três ofertas (Department, Professional — recomendada —,
Enterprise) liberam inicialmente este módulo (`procurement`) e estão em `15_PRICING_AND_ENTITLEMENTS.md` §6.

- O preço mensal do Public Procurement para clientes privados continua **PENDING_DEFINITION** (OI-017): o Government é outro
  modelo de cobrança, não um preço do módulo avulso.
- A contratação ativa a licença do tenant no plano Government sem vencimento automático nem cobrança mensal (o contrato e seus
  períodos mandam); a barreira Buy/Sell e o isolamento por tenant não mudam.
- Limites por tier (usuários, unidades administrativas, SLA, armazenamento, volume documental...) ficam "conforme contrato"
  até o PO definir (OI-024).

## 7. BASIC × FULL (D-076)

Um motor só. O nível do plano (`entitlements.public_procurement`: BASIC | FULL) decide as capabilities
(`app/contexts/shared/entitlements.py`, `Entitlements.has_capability`, dependência `exigir_capacidade`). BASIC: demandas,
workspace de processos, PCA, cadastro de fornecedores, pesquisa de preços básica, documentos, tarefas, prazos, workflow
básico, contratos, painel e auditoria. FULL acrescenta Supplier 360, Document Intelligence, Risk Engine, Next Best Action,
inteligência de contrato e as demais capabilities de inteligência; as rotas correspondentes respondem 403 no BASIC. Plano
sem nível (privado) continua com tudo.
