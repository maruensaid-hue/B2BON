"""Exporta um corpus ANONIMIZADO das mensagens de prospecção de um tenant, para pesquisa (avaliação de afirmações sem lastro).

SOMENTE LEITURA: nada é gravado no banco (a transação é desfeita no fim). O arquivo de saída é JSON Lines (uma mensagem por linha).

    python scripts/ops/exportar_corpus_anonimizado.py --tenant cyberfort --saida corpus.jsonl
    python scripts/ops/exportar_corpus_anonimizado.py --tenant cyberfort --revisar 15          # só mostra 15 mensagens anonimizadas, sem gravar arquivo
    python scripts/ops/exportar_corpus_anonimizado.py --tenant cyberfort --saida corpus.jsonl --mapa mapa.json

Opções úteis: --desde AAAA-MM-DD, --ate AAAA-MM-DD, --limite N.

ANTES DE COMPARTILHAR o arquivo, faça a revisão manual (--revisar): um nome de terceiro que não esteja no cadastro da conta não é detectado.
`--mapa` grava a correspondência entre as referências (msg_0001) e os ids reais; guarde esse arquivo à parte e nunca junto do corpus.

Usa o DATABASE_URL do ambiente e abre o contexto do tenant informado (nunca o de plataforma).
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from app.db import rls
from app.db.session import SessionLocal
from app.services import corpus_pesquisa_service


def _data(valor: str) -> date:
    return date.fromisoformat(valor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", required=True, help="id do tenant (ex.: cyberfort)")
    parser.add_argument("--saida", help="arquivo .jsonl de saída (obrigatório, a menos que use --revisar)")
    parser.add_argument("--mapa", help="grava referência -> id real (guarde à parte; NÃO compartilhe com o corpus)")
    parser.add_argument("--revisar", type=int, metavar="N", help="mostra N mensagens anonimizadas na tela para revisão manual e não grava arquivo")
    parser.add_argument("--desde", type=_data)
    parser.add_argument("--ate", type=_data)
    parser.add_argument("--limite", type=int)
    argumentos = parser.parse_args()

    if not argumentos.revisar and not argumentos.saida:
        parser.error("informe --saida ou --revisar")

    db = SessionLocal()
    try:
        rls.definir_tenant(db, argumentos.tenant)
        linhas = list(corpus_pesquisa_service.montar_corpus(
            db, argumentos.tenant, desde=argumentos.desde, ate=argumentos.ate, limite=argumentos.revisar or argumentos.limite))
    finally:
        db.rollback()  # leitura apenas: nada do que foi aberto é gravado
        db.close()

    mapa = {linha["mensagem_ref"]: linha.pop("_mensagem_id") for linha in linhas}
    if argumentos.revisar:
        for linha in linhas:
            print(json.dumps(linha, ensure_ascii=False, indent=2))
        print(f"\nRevisão: {len(linhas)} mensagem(ns). Procure nomes, empresas, cidades ou qualquer dado que identifique alguém.", file=sys.stderr)
        return 0

    Path(argumentos.saida).write_text("".join(json.dumps(linha, ensure_ascii=False) + "\n" for linha in linhas), encoding="utf-8")
    if argumentos.mapa:
        Path(argumentos.mapa).write_text(json.dumps(mapa, indent=2), encoding="utf-8")
    por_decisao: dict[str, int] = {}
    for linha in linhas:
        por_decisao[linha["decisao"]] = por_decisao.get(linha["decisao"], 0) + 1
    print(json.dumps({"mensagens": len(linhas), "por_decisao": por_decisao, "arquivo": argumentos.saida, "mapa": argumentos.mapa}, ensure_ascii=False, indent=2))
    print("\nFaça a revisão manual (--revisar) antes de compartilhar o arquivo.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
