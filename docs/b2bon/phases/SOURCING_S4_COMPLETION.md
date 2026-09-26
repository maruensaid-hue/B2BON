# SOURCING S4 · Workflow e rulesets declarativos · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, "S4: pode trocar".
- **Plano**: `18_STRATEGIC_SOURCING.md` §8 · **ADR**: D-060. S5–S8 não autorizadas. Sem mudança de schema.

## Entregas

| Item | Onde |
|---|---|
| Motor de workflow neutro: estados, inicial, finais, transições marcadas pela ação (`status`, `go_no_go`, `resultado`) e origem opcional; registro por código versionado (redefinir o mesmo código é recusado) | `app/contexts/sourcing/workflow.py` |
| Motor de ruleset neutro: documentos esperados por etapa e parâmetros com padrão, sobrescritos pela configuração do cliente; parâmetro sem padrão fica sem avaliação | `app/contexts/sourcing/ruleset.py` |
| Vendedor: `PUBLIC_TENDER_SELL@1`, `ENTERPRISE_RFP_SELL@1` (mesmo fluxo, código próprio para a S7 nascer como v2), ruleset `PRIVATE_RFP@1` (sem regra regulatória) | `app/contexts/bids/fluxo.py` |
| Comprador: `PUBLIC_PROCUREMENT_BUY@1` e `PUBLIC_PROCUREMENT_BR_14133@1` (documentos por etapa; `dias_alerta_contrato` 120 e `limite_fragmentacao` sem padrão, ambos configuráveis por órgão; `desvio_orcamento` 0,2; `desvio_alerta_preco` 0,30) | `app/contexts/procurement/fluxo.py` |
| Validação pelo workflow em `mudar_status`, `decidir` (Go/No-Go), `registrar_resultado` e na atualização de processo de compra; estado inicial vindo do workflow | `bids/licitacoes.py`, `procurement/cadastros.py` |
| `STATUS_LICITACAO`, `STATUS_FINAIS`, `STATUS_PROCESSO`, `STATUS_PROCESSO_FINAIS`, `DOCUMENTOS_ESPERADOS` e as constantes de risco e preço viram aliases derivados | `bids/tipos.py`, `procurement/{tipos,riscos,precos}.py` |
| O espelho grava os códigos de workflow e ruleset do registro (mesmos valores da S3: sem divergência, sem backfill extra) | `bids/espelho.py`, `procurement/espelho.py` |

## Validação (critério da S4: transições atuais reproduzidas por teste)

| Evidência | Resultado |
|---|---|
| `test_sourcing_s4.py`: retrato do código anterior; **todas** as combinações origem × destino × ação comparadas com o workflow (mesmo aceite, mesma exceção, mesma mensagem) — 130 por fluxo de venda, 156 no de compra; aliases iguais aos valores antigos; ruleset com padrão e configuração por órgão; todo código gravado pelo espelho existe no registro; lado do workflow = lado de quem grava; redefinição recusada; restrição de origem suportada pelo motor | ✅ 10/10 |
| `test_sourcing_s4_api.py`: mesmas respostas HTTP e mensagens pela API, em licitação pública e RFP privado, e no processo de compra | ✅ 3/3 |
| Suíte completa (leitura dupla ESTRITA) | ✅ **2.040 passed** (+4 skipped: Postgres) |
| Postgres 16 (`test_sourcing_s3_pg.py`, concorrência da Fase 15) | ✅ 4/4 |
| Ruff 40 (sem novos) · frontend sem mudança · E2E | ✅ 6/6 |
| Barreira antiga + nova + fronteiras de contexto | ✅ (o núcleo não importa nenhum lado; `Lado.COMPRA` só no comprador) |

## Desvio de comportamento (único, D-060)

`mudar_status` carrega a licitação antes de validar, porque o fluxo depende da modalidade. Licitação inexistente (ou de outro tenant) com status inválido ou reservado passa a responder **404** em vez de 422/409. Nenhum dado é exposto.

## Fora do escopo

- Estados de demanda, plano, item do PCA e contrato continuam em tuplas: não são processo de sourcing.
- Limiares analíticos sem base regulatória continuam em `riscos.py` (TD-089); o de acréscimo (25%) deve ir para `PUBLIC_PROCUREMENT_BR_14133@2`.

## Operação após o deploy

Nada novo: sem migração, e os códigos gravados no espelho não mudaram. Continua valendo o passo da S3 (rodar o backfill uma vez, se ainda não foi rodado).

## Próximo passo (não autorizado)

S5: `ProcessWorkspace` compartilhado na UI. A implementação comercial de D-059 depende de OI-021.
