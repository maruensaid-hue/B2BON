"""Carrega o recorte de CNPJ direto de um runner do GitHub Actions.

Baixa e descompacta os shards da Receita Federal (Estabelecimentos
sozinho passa de 4GB) num diretório temporário — precisa rodar num
runner com disco de sobra (~14GB livres aqui), nunca no Render: o `/tmp`
dele tem cota fixa de 2GB por instância, bem menor que o volume de dado.
Estourar essa cota mata e recria a instância no meio do processo
(raio-X 2026-08-27, reconfirmado 2026-09-09 quando a rotina automática
ainda chamava `POST /cron/atualizar-recorte-cnpj` no Render — o download
de um ICP novo foi grande o bastante pra estourar a cota durante a
própria transferência, antes mesmo da limpeza automática do diretório
temporário rodar).

Este script roda a mesma lógica (`cnpj_recorte_service.
atualizar_recorte_automatico`, idempotente — sem CNAE/UF novo, só
confere e não baixa nada), conectando direto no banco de produção via
`DATABASE_URL`. É usado por dois workflows: `carregar-recorte-manual.yml`
(workflow_dispatch manual, pra destravar a carga inicial pesada) e
`cron-envios.yml` (agendado a cada 30 min, pra manter o recorte
atualizado conforme ICPs novos aparecem) — os dois só no GitHub Actions,
nunca chamando o Render.

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
