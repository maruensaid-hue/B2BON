"""Teste de carga da API (Fase 17).

Faz login uma vez, semeia um volume de dados do próprio tenant e dispara
leituras concorrentes nas rotas mais usadas por um tempo fixo. Mede
latência por rota (p50/p95/p99), vazão e taxa de erro, e sai com código
1 se passar dos limites (`--p95-max-ms`, `--erro-max`).

Uso (servidor já rodando, ex.: `uvicorn app.main:app --port 8000`):

    python scripts/carga/carga_api.py --base http://localhost:8000 \
        --email e2e@teste.com.br --senha 'SenhaE2E123!' --semear 200 \
        --concorrencia 20 --segundos 60

Não rode contra produção: a semeadura cria contas e negócios.
"""

import argparse
import asyncio
import random
import statistics
import sys
import time
from collections import defaultdict

import httpx

ROTAS = (  # (peso, caminho)
    (5, "/api/v1/crm/negocios"),
    (3, "/api/v1/crm/dashboard/funil"),
    (2, f"/api/v1/crm/dashboard/economia?periodo={time.strftime('%Y-%m')}"),
    (3, "/api/v1/leads/contas"),
    (2, "/api/v1/auth/eu"),
    (2, "/api/v1/inteligencia/receita/metricas"),
    (1, "/api/v1/assinatura"),
    (1, "/api/v1/catalogo"),
    (1, "/health"),
)


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(round(p / 100 * (len(ordenados) - 1))))]


async def _semear(cliente: httpx.AsyncClient, quantidade: int) -> None:
    for i in range(quantidade):
        conta = (await cliente.post("/api/v1/leads/contas", json={"nome": f"Carga {i}"})).json()
        decisor = (await cliente.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": f"Decisor {i}"})).json()
        await cliente.post("/api/v1/crm/negocios", json={"conta_id": conta["id"], "decisor_id": decisor["id"],
                                                         "nome": f"Negócio carga {i}", "valor": 1000 + i})


async def _trabalhador(cliente: httpx.AsyncClient, fim: float, latencias: dict, erros: dict, pesos: list, caminhos: list) -> None:
    while time.perf_counter() < fim:
        caminho = random.choices(caminhos, weights=pesos)[0]
        inicio = time.perf_counter()
        try:
            resposta = await cliente.get(caminho)
            ok = resposta.status_code < 400
        except httpx.HTTPError:
            ok = False
        latencias[caminho].append((time.perf_counter() - inicio) * 1000)
        if not ok:
            erros[caminho] += 1


async def principal(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient(base_url=args.base, timeout=30) as cliente:
        login = await cliente.post("/api/v1/auth/login", json={"email": args.email, "senha": args.senha})
        login.raise_for_status()
        cliente.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        if args.semear:
            await _semear(cliente, args.semear)
        latencias: dict[str, list[float]] = defaultdict(list)
        erros: dict[str, int] = defaultdict(int)
        pesos, caminhos = [p for p, _ in ROTAS], [c for _, c in ROTAS]
        inicio = time.perf_counter()
        fim = inicio + args.segundos
        await asyncio.gather(*(_trabalhador(cliente, fim, latencias, erros, pesos, caminhos) for _ in range(args.concorrencia)))
        duracao = time.perf_counter() - inicio

    total = sum(len(v) for v in latencias.values())
    total_erros = sum(erros.values())
    todas = [x for v in latencias.values() for x in v]
    print(f"requisições={total} duração={duracao:.1f}s vazão={total / duracao:.1f} req/s erros={total_erros} "
          f"({total_erros / total:.2%}) concorrência={args.concorrencia}")
    print(f"{'rota':45} {'n':>6} {'p50':>8} {'p95':>8} {'p99':>8} {'erros':>6}")
    for caminho in caminhos:
        valores = latencias.get(caminho, [])
        print(f"{caminho:45} {len(valores):6} {_percentil(valores, 50):8.1f} {_percentil(valores, 95):8.1f} "
              f"{_percentil(valores, 99):8.1f} {erros.get(caminho, 0):6}")
    p95 = _percentil(todas, 95)
    print(f"geral: p50={statistics.median(todas):.1f}ms p95={p95:.1f}ms p99={_percentil(todas, 99):.1f}ms")
    falhou = p95 > args.p95_max_ms or (total_erros / total) > args.erro_max
    print("RESULTADO:", "REPROVADO" if falhou else "APROVADO", f"(limites p95≤{args.p95_max_ms}ms, erros≤{args.erro_max:.0%})")
    return 1 if falhou else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--senha", required=True)
    parser.add_argument("--semear", type=int, default=0)
    parser.add_argument("--concorrencia", type=int, default=20)
    parser.add_argument("--segundos", type=int, default=30)
    parser.add_argument("--p95-max-ms", type=float, default=800.0)
    parser.add_argument("--erro-max", type=float, default=0.01)
    sys.exit(asyncio.run(principal(parser.parse_args())))
