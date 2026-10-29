"""Imprime o SQL que cria (ou atualiza) o papel de execução da aplicação para o RLS (D-110). NÃO se conecta a nada: quem opera revisa o SQL e o roda no banco com o papel dono.

Uso:  RLS_SENHA_APP='<senha forte>' python scripts/ops/rls_papel_aplicacao.py [nome_do_papel] > papel.sql
A senha vem do ambiente (nunca de argumento de linha de comando, que fica no histórico do shell) e nada é gravado em arquivo pelo script.
"""

import os
import sys

from app.db.rls_sql import sql_papel_aplicacao


def main() -> int:
    senha = os.environ.get("RLS_SENHA_APP", "")
    if len(senha) < 24:
        print("Defina RLS_SENHA_APP com pelo menos 24 caracteres (ex.: python -c \"import secrets; print(secrets.token_urlsafe(32))\").", file=sys.stderr)
        return 2
    papel = sys.argv[1] if len(sys.argv) > 1 else "b2bon_app"
    for comando in sql_papel_aplicacao(papel, senha):
        print(comando + ";\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
