"""Inventário de segurança de TODAS as rotas efetivas do app (inclui routers aninhados), extraído do FastAPI real.

Para cada rota: métodos, caminho, handler, dependências (árvore completa), classe de autenticação, origem do tenant e parâmetros sensíveis.
Uso: python scripts/qualidade/inventario_rotas.py [--json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import warnings
from dataclasses import asdict, dataclass, field

warnings.filterwarnings("ignore")

AUTENTICADORES = {"get_usuario_atual": "sessao", "autenticar_api": "chave_api", "get_chave_api_atual": "chave_api"}
PARAMS_TENANT = re.compile(r"tenant", re.I)


@dataclass
class Rota:
    metodos: list[str]
    caminho: str
    handler: str
    deps: list[str] = field(default_factory=list)
    autenticacao: str = "nenhuma"
    papeis: list[str] = field(default_factory=list)
    escopo_objeto: list[str] = field(default_factory=list)
    tenant_de: str = "nao_aplicavel"
    params_caminho: list[str] = field(default_factory=list)
    params_tenant_do_cliente: list[str] = field(default_factory=list)


def _percorrer(dependant, acumulador: list[str]) -> None:
    for sub in dependant.dependencies:
        nome = getattr(sub.call, "__qualname__", None) or repr(sub.call)
        acumulador.append(nome)
        _percorrer(sub, acumulador)


def _closure_papeis(call) -> list[str]:
    fechamento = getattr(call, "__closure__", None) or ()
    papeis: list[str] = []
    for cel in fechamento:
        try:
            valor = cel.cell_contents
        except ValueError:
            continue
        if isinstance(valor, tuple) and all(isinstance(v, str) for v in valor):
            papeis.extend(valor)
    return papeis


def _papeis_da_rota(dependant) -> list[str]:
    achados: list[str] = []
    for sub in dependant.dependencies:
        if "exigir_papel" in (getattr(sub.call, "__qualname__", "") or ""):
            achados.extend(_closure_papeis(sub.call))
        achados.extend(_papeis_da_rota(sub))
    return sorted(set(achados))


def contextos_efetivos() -> list:
    """Contextos brutos do FastAPI (dependant, schemas, métodos) de todas as rotas aninhadas."""
    from app.main import app

    incluido = [r for r in app.routes if type(r).__name__ == "_IncludedRouter"]
    return [c for r in incluido for c in r.effective_route_contexts()]


def carregar() -> list[Rota]:
    contextos = contextos_efetivos()
    resultado: list[Rota] = []
    for ctx in contextos:
        deps: list[str] = []
        _percorrer(ctx.dependant, deps)
        nomes = sorted(set(deps))
        auth = "nenhuma"
        for chave, rotulo in AUTENTICADORES.items():
            if any(chave in n for n in nomes):
                auth = rotulo
                break
        escopo = sorted(n for n in nomes if n.startswith("exigir_escopo_"))
        if "get_tenant_id" in nomes:
            tenant = "token(get_tenant_id)"
        elif auth == "sessao":
            tenant = "token(usuario)"
        elif auth == "chave_api":
            tenant = "chave_api"
        else:
            tenant = "nao_aplicavel"
        params_caminho = [p.name for p in ctx.dependant.path_params]
        do_cliente = [p.name for p in (*ctx.dependant.query_params, *ctx.dependant.path_params) if PARAMS_TENANT.search(p.name)]
        corpo = [f.name for f in ctx.dependant.body_params]
        resultado.append(
            Rota(
                metodos=sorted(ctx.methods or []), caminho=ctx.path,
                handler=f"{ctx.endpoint.__module__}.{ctx.endpoint.__name__}", deps=nomes, autenticacao=auth,
                papeis=_papeis_da_rota(ctx.dependant), escopo_objeto=escopo, tenant_de=tenant, params_caminho=params_caminho,
                params_tenant_do_cliente=do_cliente + [f"corpo:{c}" for c in corpo if PARAMS_TENANT.search(c)],
            )
        )
    from app.main import app as _app
    for r in _app.routes:
        if type(r).__name__ == "APIRoute":
            resultado.append(Rota(metodos=sorted(r.methods), caminho=r.path, handler=f"{r.endpoint.__module__}.{r.endpoint.__name__}"))
    return sorted(resultado, key=lambda r: (r.caminho, r.metodos))


def _cobertura(codigos: list[int] | None) -> str:
    if not codigos:
        return "não exercitada"
    conjunto = set(codigos)
    if conjunto & set(range(200, 300)):
        return "executada (2xx), sem vazamento"
    if conjunto <= {401, 403}:
        return "negada por papel/autenticação"
    if 404 in conjunto and conjunto <= {401, 403, 404}:
        return "negada (404) com ids de outro tenant"
    if conjunto <= {422}:
        return "validação (422) — ver testes dirigidos"
    return "negada/validação (" + ",".join(map(str, sorted(conjunto))) + ")"


def markdown(rotas: list[Rota], cobertura: dict | None = None) -> str:
    cobertura = cobertura or {}
    linhas = ["| Método | Caminho | Autenticação | Papéis | Origem do tenant | Escopo de objeto | Tenant vindo do cliente | Resultado da varredura |", "|---|---|---|---|---|---|---|---|"]
    for r in rotas:
        chave = f"{r.metodos[0]} {r.caminho}" if len(r.metodos) == 1 else None
        codigos = None
        if chave:
            codigos = cobertura.get(chave)
        else:
            achados = [c for m in r.metodos for c in cobertura.get(f"{m} {r.caminho}", [])]
            codigos = achados or None
        linhas.append(
            f"| {'/'.join(r.metodos)} | `{r.caminho}` | {r.autenticacao} | {', '.join(r.papeis) or '—'} | {r.tenant_de} | "
            f"{', '.join(n.replace('exigir_escopo_', '').replace('_usuario', '') for n in r.escopo_objeto) or '—'} | "
            f"{', '.join(r.params_tenant_do_cliente) or '—'} | {_cobertura(codigos) if r.autenticacao == 'sessao' else 'fora do escopo da varredura (ver guarda de rotas públicas)'} |"
        )
    return "\n".join(linhas)


if __name__ == "__main__":
    rotas = carregar()
    if "--md" in sys.argv:
        arquivo = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--cobertura=")), None)
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8")).get("status_por_rota") if arquivo else None
        print(markdown(rotas, dados))
    elif "--json" in sys.argv:
        print(json.dumps([asdict(r) for r in rotas], ensure_ascii=False, indent=1))
    else:
        print(f"{len(rotas)} rotas")
        por = {}
        for r in rotas:
            por[r.autenticacao] = por.get(r.autenticacao, 0) + 1
        print(por)
