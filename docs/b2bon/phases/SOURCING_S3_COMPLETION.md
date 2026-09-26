# SOURCING S3 · Schema unificado (expand) · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, "Autorizado" sobre "S3: criar as tabelas unificadas e migrar os dados aos poucos, mantendo as tabelas antigas até os resultados baterem".
- **Plano**: `18_STRATEGIC_SOURCING.md` §8 · **ADR**: D-058. As tabelas antigas **continuam a fonte da verdade**. S4–S8 não autorizadas.

## Entregas

| Item | Onde |
|---|---|
| 6 tabelas unificadas: `processo_sourcing`, `documento_sourcing`, `requisito_sourcing`, `contrato_sourcing`, `evento_sourcing`, `evento_contrato_sourcing` | `app/models/sourcing.py`, migração `a3d5f7b9c1e2` |
| `lado` SELL/BUY em CHECK e **imutável**: evento do ORM + trigger (SQLite e Postgres) | idem |
| Mapa id antigo → novo: `origem_tabela` + `origem_id` (+ `origem_indice` para achados em JSON), único | idem |
| Espelho: toda escrita nas tabelas antigas é copiada na mesma transação, em SAVEPOINT; falha vira log e não derruba o usuário | `bids/espelho.py`, `procurement/espelho.py` → `sourcing/espelho.py` (neutro) |
| Backfill idempotente em lotes, com remoção de órfãos | `POST /cron/sourcing-sincronizar`, agendado 1x/dia em `cron-envios.yml` |
| Leitura dupla: os repositórios respondem pelas tabelas antigas e conferem as novas; `SOURCING_LEITURA_DUPLA` = COMPARAR (produção, loga `SOURCING_DIVERGENCIA`), ESTRITA (suíte), DESLIGADA | `sourcing/paridade.py`, `bids/repositorio.py`, `procurement/repositorio.py` |
| Fitness da barreira | `test_barreira_sourcing.py`: tabelas unificadas só pelo núcleo; `Lado.COMPRA` só no comprador; `Lado.VENDA` só no vendedor |

Mapeamentos:
- `PRIVATE_RFP` → segmento ENTERPRISE, `RFP`, `ENTERPRISE_RFP_SELL@1`, ruleset `PRIVATE_RFP@1`;
- demais licitações → PUBLIC, `PUBLIC_TENDER_SELL@1`;
- processos do comprador → `PUBLIC_PROCUREMENT_BUY@1` / `PUBLIC_PROCUREMENT_BR_14133@1`, CONFIDENTIAL;
- achados do documento de compras → requisitos BUY `grounded`, por posição.

## Desvios do desenho (explícitos)

- **6 tabelas, não 9**: participante, proposta e avaliação ganham tabela no primeiro fluxo que gravar nelas (S7/S8).
- **Versão no nome** do workflow e do ruleset (`…@1`), sem coluna separada.
- **Sem blobs**: `documento_sourcing` guarda metadados; o arquivo e o texto continuam na origem até a S6 (TD-088).
- **Sem `ON DELETE CASCADE`**, pela convenção do projeto (falha fechado): o núcleo apaga as filhas explicitamente.

## Validação (critério da S3: paridade 100% em SQLite e Postgres)

| Evidência | Resultado |
|---|---|
| Suíte completa com leitura dupla **ESTRITA** em todo teste (cada leitura de licitação, processo, documento, requisito, achado e tipo de documento é conferida) | ✅ **2.027 passed** (+4 skipped: Postgres) |
| `test_sourcing_s3.py` | ✅ 9/9: espelho com lado certo, RFP privado → ENTERPRISE, divergência detectada nos três modos, backfill idempotente com órfão removido, cron, lado imutável (ORM, trigger, filha de outro lado recusada), falha de espelho não derruba a escrita, apagar sem cascata, conferência de 41 requisitos em ≤ 5 consultas |
| Migração sobre dados anteriores + backfill + leitura estrita + trigger (SQLite migrado) | ✅ `test_alembic_upgrade.py` |
| **Postgres 16**: migração (upgrade/downgrade/upgrade), espelho com FKs reais, SAVEPOINT no flush, leitura estrita, trigger, backfill | ✅ `PG_MIGRACOES_OK a3d5f7b9c1e2`; `test_sourcing_s3_pg.py` 2/2; concorrência (Fase 15) 2/2 |
| Barreira antiga + nova + fronteiras | ✅ |
| Ruff 40 (sem novos) · frontend sem mudança · E2E 6/6 (sem `SOURCING_ESPELHO_FALHOU` nem divergência) | ✅ |

## Operação após o deploy

1. `alembic upgrade head` (o deploy já roda). As tabelas nascem vazias.
2. Rodar o workflow **"Disparar envios pendentes" manualmente** (workflow_dispatch). Isso executa o backfill `/cron/sourcing-sincronizar`, que devolve quantas linhas espelhou e quantos órfãos removeu por tabela.
3. Acompanhar os logs `SOURCING_DIVERGENCIA` e `SOURCING_ESPELHO_FALHOU`. O esperado é zero; o backfill diário corrige qualquer linha que escape.

## Próximo passo (não autorizado)

S4: workflow e rulesets declarativos no lugar das tuplas de status e de `DOCUMENTOS_ESPERADOS`. A troca de leitura para as tabelas novas e a remoção das antigas são a S6.
