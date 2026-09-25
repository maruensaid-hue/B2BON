# AI CREDITS — API, BILLING, ADMINISTRAÇÃO E USO (Fase 15)

Arquitetura e regras: `09_AI_FINOPS.md`. Preços e franquias:
`15_PRICING_AND_ENTITLEMENTS.md` §4.

## 1. API

### Público (sem login)

| Método | Rota | Uso |
|---|---|---|
| GET | `/api/v1/ai-credits/pacotes` | pacotes vigentes, franquias (pendentes como `null`) e regras |
| GET | `/api/v1/ai-credits/workloads` | quanto cada operação consome (catálogo ativo) |

### Tenant (login; `admin` para escrita, extrato e compras)

| Método | Rota | Uso |
|---|---|---|
| GET | `/ai-credits/carteira` | disponível, reservado, incluído, comprado, promocional, a vencer, uso do mês, dias estimados |
| GET | `/ai-credits/consumo?dias=7\|30\|90` | por módulo, workload, agente, gatilho |
| POST | `/ai-credits/estimativas` | `{workload, parametros}` → créditos estimados e `requer_confirmacao` |
| GET | `/ai-credits/extrato` · `/execucoes` · `/alertas` · `/lotes/{id}` | ledger e histórico (sem custo em USD) |
| POST/GET | `/ai-credits/compras` · `POST /compras/{id}/checkout` | compra de pacote e link de pagamento |
| GET/PUT | `/ai-credits/recarga-automatica` | ativar exige `consentimento: true` |
| GET/PUT | `/ai-credits/orcamento` | budget guard (mês, dia, usuário, API, % por módulo, agente) |
| GET | `/ai-credits/valor-de-negocio?dias=30\|90` | consumo × resultados registrados |
| GET | `/bids/documentos/{id}/estimativa`, `/procurement/documentos/{id}/estimativa` | estimativa antes da análise |
| POST | `…/documentos/{id}/analisar?confirmar=true` | sem confirmar e acima do limiar: **409** com `requer_confirmacao` |

Erros: **402** `CreditosInsuficientes` (com `detalhe`), **409**
`ConfirmacaoNecessaria` (com `requer_confirmacao: true`), **409** orçamento de IA atingido (`OrcamentoIaExcedido`, regra de negócio).

### Plataforma (super_admin)

| Método | Rota | Uso |
|---|---|---|
| GET | `/finops/economia?dias=` | KPIs de receita, custo, margem, passivo, excedente, cache |
| GET | `/finops/margens?dimensao=&dias=` | tenant, módulo, workload, agente, plano, provider, modelo, pacote |
| GET | `/finops/matriz-rentabilidade`, `/alertas-margem`, `/recomendacoes-peso`, `/economia-unitaria`, `/relatorio-calibracao?dias=7\|30\|90` | análise; nada é aplicado sozinho |
| GET/POST | `/finops/catalogo`, `/catalogo/rascunhos`, `/catalogo/{versao}/ativar` | catálogo versionado (auditado) |
| GET/POST | `/finops/pacotes`, `/pacotes/{codigo}/versoes` | preço versionado (auditado) |
| POST | `/finops/tenants/{id}/creditos` | ajuste/promoção com motivo (auditado) |
| PUT | `/finops/tenants/{id}/excedente` | pool Enterprise e excedente pós-pago |
| POST | `/finops/execucoes/{id}/estorno` | estorno com motivo |
| GET | `/finops/reconciliacao` | extrato × lotes × reservas |

### Cron

`POST /api/v1/cron/creditos-ia` (header `X-Cron-Secret`), **de hora em
hora**: libera reservas órfãs (> 30 min), expira lotes, concede a franquia
do mês, registra avisos 80/95/100%, detecta pico de consumo e alertas de
margem. Idempotente.

## 2. Billing

1. `POST /ai-credits/compras` congela pacote, versão e preço e cria a
   preferência no Mercado Pago (`referencia_externa = "creditos:{id}"`).
2. O webhook `/webhooks/mercadopago` valida a assinatura e despacha: licença
   (referência numérica) ou créditos (`creditos:`).
3. Créditos entram só com status aprovado **e** valor igual ao pedido
   (diferença → REJEITADA, log `CREDITOS_COMPRA_VALOR_DIVERGENTE`). Webhook
   repetido não credita de novo.
4. Lote TOPUP com validade de 12 meses e receita por crédito = preço ÷ créditos.
5. Excedente Enterprise: `CREDIT_OVERAGE` com `faturavel=true`; o
   faturamento pós-pago é feito a partir do extrato (TD-077).

## 3. Administração (super_admin: menu "FinOps IA")

- Acompanhar margem (alvo 80%) e alertas; margem sem câmbio aparece como
  indisponível até configurar `FINOPS_CAMBIO_USD_BRL`.
- Recalibrar pesos: ler recomendações → criar rascunho → ativar com motivo.
- Mudar preço de pacote: só com decisão do PO → nova versão.
- Ajustes e promoções: sempre com motivo; ficam no audit log com valor anterior e novo.
- Conferir reconciliação após migração e periodicamente (deve ser OK em todos os tenants).
- Configuração: `AI_CREDITOS_MODO` (ENFORCE), `AI_CREDITOS_LIMIAR_CONFIRMACAO` (100),
  `AI_MARGEM_ALVO/ALERTA/CRITICA` (0,80/0,75/0,65), `AI_CACHE_RESPOSTA_HORAS` (24).

## 4. Uso (cliente, menu "AI Credits")

- A carteira é da empresa. Os créditos do plano renovam todo mês e não
  acumulam; os comprados valem 12 meses. Sai primeiro o que vence primeiro.
- Operações grandes mostram "Consumo estimado: aproximadamente N AI Credits"
  e pedem confirmação.
- Falha da IA não consome créditos.
- O admin compra pacotes, liga a recarga automática (com consentimento) e
  define limites por mês, dia, usuário, módulo e API. Avisos em 80, 95 e 100%.
