#!/usr/bin/env bash
# Verificação de backup/restore (Fase 17, DR).
#
# Faz dump do banco de ORIGEM, restaura num banco de VERIFICAÇÃO novo e
# compara: versão do Alembic e contagem de linhas de todas as tabelas.
# Mede os tempos de dump e restore (base para o RTO real do ambiente).
#
# Uso:
#   ORIGEM_URL=postgresql://user@host:5432/b2bon \
#   VERIFICACAO_URL=postgresql://user@host:5432/b2bon_restore_check \
#   scripts/ops/verificar_backup_restore.sh [arquivo_dump]
#
# O banco de VERIFICAÇÃO é apagado e recriado: nunca aponte para produção.
set -euo pipefail

: "${ORIGEM_URL:?defina ORIGEM_URL}"
: "${VERIFICACAO_URL:?defina VERIFICACAO_URL}"
if [[ "$VERIFICACAO_URL" == "$ORIGEM_URL" ]]; then
  echo "VERIFICACAO_URL não pode ser igual a ORIGEM_URL" >&2
  exit 2
fi
DUMP="${1:-$(mktemp -d)/b2bon_$(date -u +%Y%m%dT%H%M%SZ).dump}"
BANCO_VERIFICACAO="${VERIFICACAO_URL##*/}"
URL_ADMIN="${VERIFICACAO_URL%/*}/postgres"

contagens() {
  psql "$1" -At -c "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1" |
    while read -r tabela; do
      echo "$tabela $(psql "$1" -At -c "select count(*) from \"$tabela\"")"
    done
}

inicio=$(date +%s)
pg_dump --format=custom --no-owner --file "$DUMP" "$ORIGEM_URL"
t_dump=$(( $(date +%s) - inicio ))

psql "$URL_ADMIN" -q -c "drop database if exists \"$BANCO_VERIFICACAO\";" -c "create database \"$BANCO_VERIFICACAO\";"
inicio=$(date +%s)
pg_restore --no-owner --exit-on-error --dbname "$VERIFICACAO_URL" "$DUMP"
t_restore=$(( $(date +%s) - inicio ))

versao_origem=$(psql "$ORIGEM_URL" -At -c "select version_num from alembic_version")
versao_restaurada=$(psql "$VERIFICACAO_URL" -At -c "select version_num from alembic_version")
diff <(contagens "$ORIGEM_URL") <(contagens "$VERIFICACAO_URL") > /dev/null && linhas_ok=sim || linhas_ok=nao
tabelas=$(contagens "$VERIFICACAO_URL" | wc -l)
linhas=$(contagens "$VERIFICACAO_URL" | awk '{s+=$2} END {print s}')

echo "dump=$DUMP tamanho=$(du -h "$DUMP" | cut -f1) tempo_dump=${t_dump}s tempo_restore=${t_restore}s"
echo "alembic origem=$versao_origem restaurado=$versao_restaurada tabelas=$tabelas linhas=$linhas contagens_iguais=$linhas_ok"
if [[ "$versao_origem" == "$versao_restaurada" && "$linhas_ok" == "sim" ]]; then
  echo "RESTORE_OK"
else
  echo "RESTORE_FALHOU" >&2
  exit 1
fi
