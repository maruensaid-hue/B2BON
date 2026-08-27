"""Carrega o recorte de CNPJ direto de um runner do GitHub Actions.

FALLBACK DELIBERADO (raio-X 2026-08-27): o carregamento automático via
`POST /cron/atualizar-recorte-cnpj` baixa e descompacta os shards da
Receita Federal (Estabelecimentos sozinho passa de 4GB) num diretório
temporário — no Render, esse `/tmp` tem uma cota fixa de 2GB por
instância, bem menor que o volume de dado. Estourar essa cota mata e
recria a instância no meio do processo (raio-X: aconteceu repetidas
vezes, cada tentativa deixando lixo pra trás e piorando a próxima),
matando a tarefa em segundo plano sem nunca terminar.

Este script roda exatamente a mesma lógica (`cnpj_recorte_service.
atualizar_recorte_automatico`), só que num runner do GitHub Actions —
~14GB de disco livre, bem mais que suficiente — conectando direto no
banco de produção via `DATABASE_URL`. Uso only via workflow_dispatch
manual (`.github/workflows/carregar-recorte-manual.yml`), não agendado:
é só pra destravar a carga inicial pesada; a atualização mensal seguinte
já cabe tranquilamente na rotina automática de 30 em 30 minutos do
Render (`POST /cron/atualizar-recorte-cnpj`), que só baixa o que mudou.

Uso: DATABASE_URL=postgresql://... python scripts/carregar_recorte_ci.py
"""

import sys

from app.db.session import SessionLocal
from app.services import cnpj_recorte_service


def main() -> None:
    db = SessionLocal()
    try:
        resultado = cnpj_recorte_service.atualizar_recorte_automatico(db)
        print(resultado, flush=True)
        if not resultado.get("executado", True) and resultado.get("motivo") not in (
            None,
            "recorte já cobre todos os ICPs ativos neste mês de competência",
        ):
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
