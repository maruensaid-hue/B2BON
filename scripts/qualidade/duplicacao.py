"""Análise de duplicação de código (plano unificado §35).

Procura blocos de N linhas iguais (após normalizar espaços e descartar
linhas vazias, comentários e imports) em `app/` e `frontend/src/`. Não
depende de ferramenta externa.

    python scripts/qualidade/duplicacao.py                # relatório
    python scripts/qualidade/duplicacao.py --json saida.json
    python scripts/qualidade/duplicacao.py --arquivos a.py b.py   # só blocos que tocam estes arquivos
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTAS = (("app", "*.py"), ("frontend/src", "*.ts"), ("frontend/src", "*.tsx"))
IGNORAR = re.compile(r"^(#|//|\*|/\*|import |from \S+ import |export \* from|[)\]}]+[,;]?$)")


def _linhas(arquivo: Path) -> list[tuple[int, str]]:
    saida = []
    for numero, linha in enumerate(arquivo.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        normalizada = " ".join(linha.split())
        if normalizada and not IGNORAR.match(normalizada):
            saida.append((numero, normalizada))
    return saida


def analisar(janela: int) -> list[dict]:
    """Blocos duplicados: janelas iguais em lugares diferentes, fundidas em trechos contínuos."""
    ocorrencias: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for pasta, padrao in PASTAS:
        for arquivo in sorted((RAIZ / pasta).rglob(padrao)):
            if "__pycache__" in arquivo.parts or "node_modules" in arquivo.parts:
                continue
            linhas = _linhas(arquivo)
            nome = str(arquivo.relative_to(RAIZ))
            for i in range(len(linhas) - janela + 1):
                trecho = "\n".join(t for _, t in linhas[i:i + janela])
                chave = hashlib.sha1(trecho.encode()).hexdigest()
                ocorrencias[chave].append((nome, linhas[i][0], linhas[i + janela - 1][0]))
    # funde janelas consecutivas do mesmo par de lugares num bloco só
    blocos: dict[tuple, dict] = {}
    for lugares in ocorrencias.values():
        if len(lugares) < 2:
            continue
        chave = tuple(sorted({(nome) for nome, _, _ in lugares})) + (len(lugares),)
        for nome, inicio, fim in lugares:
            bloco = blocos.setdefault(chave, {"arquivos": {}})
            atual = bloco["arquivos"].get(nome)
            if atual is None or inicio > atual[-1][1] + janela:
                bloco["arquivos"].setdefault(nome, []).append([inicio, fim])
            else:
                atual[-1][1] = max(atual[-1][1], fim)
    resultado = []
    for bloco in blocos.values():
        trechos = [(nome, inicio, fim) for nome, faixas in bloco["arquivos"].items() for inicio, fim in faixas]
        if len(trechos) < 2:
            continue
        resultado.append({"linhas": max(fim - inicio + 1 for _, inicio, fim in trechos),
                          "trechos": [f"{nome}:{inicio}-{fim}" for nome, inicio, fim in trechos]})
    return sorted(resultado, key=lambda b: -b["linhas"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--janela", type=int, default=8, help="linhas significativas iguais para contar como duplicação")
    parser.add_argument("--arquivos", nargs="*", help="só blocos que envolvem estes arquivos")
    parser.add_argument("--json")
    args = parser.parse_args()
    blocos = analisar(args.janela)
    if args.arquivos:
        alvo = tuple(args.arquivos)
        blocos = [b for b in blocos if any(t.split(":")[0] in alvo for t in b["trechos"])]
    total = sum(b["linhas"] * (len(b["trechos"]) - 1) for b in blocos)
    print(f"{len(blocos)} bloco(s) duplicado(s) (janela {args.janela}); ~{total} linhas repetidas")
    for bloco in blocos[:25]:
        print(f"  {bloco['linhas']:>4} linhas  " + "  |  ".join(bloco["trechos"][:4]))
    if args.json:
        Path(args.json).write_text(json.dumps({"janela": args.janela, "blocos": blocos, "linhas_repetidas": total},
                                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
