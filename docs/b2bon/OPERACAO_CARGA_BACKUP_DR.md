# Operação — carga, backup/restore e DR (Fase 17)

## 1. Teste de carga

Script: `scripts/carga/carga_api.py` (login único, semeadura opcional, leituras
concorrentes ponderadas, p50/p95/p99 por rota, reprova acima de p95 800 ms ou
1% de erro). Nunca rodar contra produção (a semeadura grava dados).

Medição de referência (2026-09-25, container de desenvolvimento, Postgres 16
local, uvicorn com 4 workers, 300 contas/negócios, 20 clientes, 45 s):

| Rodada | Vazão | p50 | p95 | p99 | Erros |
|---|---|---|---|---|---|
| Antes da correção | 66,7 req/s | 144 ms | 1.464 ms | 2.214 ms | 0% (REPROVADO) |
| Depois (N+1 do MAP corrigido) | 121,9 req/s | 108 ms | 507 ms | 669 ms | 0% (APROVADO) |

Achado: `/crm/dashboard/economia` fazia uma consulta de interações por conta
(303 consultas com 300 contas; p50 1.490 ms). Corrigido carregando as interações
do tenant de uma vez quando a avaliação passa de uma conta (6 consultas; p50
145 ms). Regressão coberta por `test_desempenho_consultas.py`.

Os números valem para este ambiente; o dimensionamento de produção precisa de
uma rodada no ambiente de staging real (TD-074).

## 2. Backup e restore

Script: `scripts/ops/verificar_backup_restore.sh` (`pg_dump -Fc` da origem,
`pg_restore` num banco de verificação novo, compara versão do Alembic e a
contagem de linhas de todas as tabelas; falha se divergir).

Execução de referência: 140 tabelas, 2.430 linhas, dump 580 KB, dump 1 s,
restore 1 s, versão `c4f1a9e7d2b3` igual, contagens iguais → `RESTORE_OK`.

Rotina recomendada: rodar o script contra o backup mais recente num banco
descartável pelo menos uma vez por semana e após cada migração de schema.

## 3. DR (recuperação de desastre)

1. Provisionar Postgres novo (mesma versão maior).
2. Restaurar o último backup (`pg_restore --no-owner`) e conferir com o script acima.
3. Subir a API com as MESMAS variáveis de segredo (`SECRET_KEY`, `JWT_SECRET_KEY`,
   `CONFIGURACAO_WHATSAPP_ENCRYPTION_KEY`). Sem a chave Fernet original, as
   credenciais de conectores e do WhatsApp gravadas no banco ficam ilegíveis:
   a chave precisa de cópia fora do banco (cofre de segredos).
4. `alembic current` deve mostrar o head do código implantado; se o backup for
   anterior, `alembic upgrade head`.
5. Verificar `/health` (`database: ok`) e o E2E de login.

Metas de RPO/RTO não foram definidas (OI-016): o restore medido acima é o
piso técnico deste volume, não um compromisso de serviço.
