"""Corrige nomes de empresas e contatos já gravados com a codificação trocada ("QuÃ©bec" no lugar de "Québec").

Por padrão só SIMULA: mostra quantos registros têm o defeito e alguns exemplos de nome de empresa. Com --aplicar, grava as correções (uma auditoria por tenant).

    python scripts/ops/corrigir_codificacao_dados.py            # simulação
    python scripts/ops/corrigir_codificacao_dados.py --aplicar  # grava

Usa o DATABASE_URL do ambiente. Com o papel restrito do RLS (b2bon_app) funciona porque abre o contexto de plataforma, que enxerga todos os tenants.
"""

import argparse
import json

from app.db import rls
from app.db.session import SessionLocal
from app.services import codificacao_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="grava as correções (sem isto, só simula)")
    argumentos = parser.parse_args()

    db = SessionLocal()
    try:
        rls.definir_plataforma(db)
        relatorio = codificacao_service.corrigir_dados_gravados(db, aplicar=argumentos.aplicar)
    finally:
        db.close()
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    if not argumentos.aplicar:
        print("\nSimulação: nada foi alterado. Rode com --aplicar para gravar.")


if __name__ == "__main__":
    main()
