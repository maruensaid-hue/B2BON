"""Orçamento de desempenho (plano unificado §36): mede e compara com a baseline.

Não roda na suíte normal. Uso:

    B2BON_MEDIR=docs/b2bon/perf/fase_a.json \
    B2BON_BASELINE=docs/b2bon/perf/baseline.json \
    python -m pytest -q tests/desempenho

Mede, em processo (SQLite em memória, mesmos fixtures da suíte):
- latência p50/p95 e consultas ao banco por rota: painel principal, CRM,
  vendedor (licitações) e comprador (processos, riscos);
- fluxos críticos de sourcing de ponta a ponta (latência e consultas);
- tempo de inicialização (`import app.main` em processo novo) e pico de memória.
O tamanho do bundle vem do build do frontend (`frontend/dist`), se existir.

Com `B2BON_BASELINE`, compara: consulta a mais em rota é regressão; latência
p95 acima de 1,5x a baseline (e de 20 ms absolutos) também.
"""

import json
import os
import resource
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import event

from scripts.carga.carga_api import _percentil

pytestmark = pytest.mark.skipif(not os.environ.get("B2BON_MEDIR"), reason="medição sob demanda (B2BON_MEDIR)")

RAIZ = Path(__file__).resolve().parents[2]
B, P = "/api/v1/bids", "/api/v1/procurement"
REPETICOES = 25
VOLUME = 40  # por entidade semeada


class _Consultas:
    def __init__(self, engine) -> None:
        self.total, self._engine = 0, engine

    def __enter__(self):
        event.listen(self._engine, "before_cursor_execute", self._contar)
        return self

    def __exit__(self, *exc):
        event.remove(self._engine, "before_cursor_execute", self._contar)

    def _contar(self, *args):
        self.total += 1


def _semear(client) -> dict:
    ids: dict = {}
    for i in range(VOLUME):
        conta = client.post("/api/v1/leads/contas", json={"nome": f"Conta {i}"}).json()
        decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": f"Decisor {i}"}).json()
        client.post("/api/v1/crm/negocios", json={"conta_id": conta["id"], "decisor_id": decisor["id"], "nome": f"Negócio {i}",
                                                  "valor": 1000 + i})
        lic = client.post(f"{B}/licitacoes", json={"titulo": f"Edital {i}", "objeto": "Notebooks e licenças",
                                                   "orgao_nome": "Prefeitura", "modalidade": "PRIVATE_RFP" if i % 4 == 0 else "PUBLIC_TENDER"}).json()
        client.post(f"{B}/licitacoes/{lic['id']}/documentos", data={"tipo": "EDITAL"},
                    files={"arquivo": ("e.txt", b"5.1 Apresentar certidao negativa. " * 50, "text/plain")})
        client.post(f"{B}/licitacoes/{lic['id']}/requisitos", json={"categoria": "HABILITACAO", "descricao": "Certidão negativa"})
        ids.setdefault("licitacao", lic["id"])
    orgao = client.post(f"{P}/orgaos", json={"nome": "Prefeitura"}).json()
    for i in range(VOLUME):
        proc = client.post(f"{P}/processos", json={"orgao_id": orgao["id"], "objeto": f"Limpeza predial {i}", "valor_estimado": 90000}).json()
        client.patch(f"{P}/processos/{proc['id']}", json={"status": "PESQUISA_PRECOS"})
        ids.setdefault("processo", proc["id"])
    # Phase E: RFP privado com 10 participantes e propostas avaliadas
    S = "/api/v1/sourcing"
    rfp = client.post(f"{S}/processos", json={"tipo_processo": "RFP", "titulo": "Notebooks corporativos"}).json()
    requisitos = [client.post(f"{S}/processos/{rfp['id']}/requisitos", json={"categoria": "REQUISITO_TECNICO", "texto": f"Critério {i}",
                                                                           "obrigatorio": i == 0, "peso": 1 + i}).json() for i in range(5)]
    participantes = [client.post(f"{S}/processos/{rfp['id']}/participantes", json={"nome": f"Fornecedor {i}"}).json() for i in range(10)]
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        client.post(f"{S}/processos/{rfp['id']}/status", json={"status": status})
    for i, participante in enumerate(participantes):
        proposta = client.post(f"{S}/processos/{rfp['id']}/propostas", json={"participante_id": participante["id"],
                                                                            "valor_total": 1000 + i}).json()
        for requisito in requisitos:
            client.put(f"{S}/propostas/{proposta['id']}/avaliacoes", json={"requisito_id": requisito["id"], "status": "COMPLIANT",
                                                                          "nota": 7})
    ids["sourcing"] = rfp["id"]
    return ids


def _rotas(ids: dict) -> dict[str, str]:
    periodo = datetime.now(UTC).strftime("%Y-%m")
    return {
        "painel · métrica norte": "/api/v1/painel/metrica-norte",
        "painel · funil": "/api/v1/crm/dashboard/funil",
        "painel · economia": f"/api/v1/crm/dashboard/economia?periodo={periodo}",
        "crm · negócios": "/api/v1/crm/negocios",
        "crm · contas": "/api/v1/leads/contas",
        "vendedor · licitações": f"{B}/licitacoes",
        "vendedor · workspace": f"{B}/licitacoes/{ids['licitacao']}/workspace",
        "vendedor · go/no-go": f"{B}/licitacoes/{ids['licitacao']}/go-no-go",
        "comprador · processos": f"{P}/processos",
        "comprador · workspace": f"{P}/processos/{ids['processo']}/workspace",
        "comprador · riscos": f"{P}/riscos",
        "comprador privado · workspace": f"/api/v1/sourcing/processos/{ids['sourcing']}/workspace",
        "comprador privado · comparação": f"/api/v1/sourcing/processos/{ids['sourcing']}/comparacao",
    }


def _medir(client, engine, chamada) -> dict:
    latencias, consultas = [], []
    for _ in range(REPETICOES):
        with _Consultas(engine) as contador:
            inicio = time.perf_counter()
            resposta = chamada()
            latencias.append((time.perf_counter() - inicio) * 1000)
        assert resposta.status_code < 400, resposta.text[:300]
        consultas.append(contador.total)
    return {"p50_ms": round(statistics.median(latencias), 1), "p95_ms": round(_percentil(latencias, 95), 1),
            "consultas": max(consultas)}


def _fluxo_vendedor(client):
    lic = client.post(f"{B}/licitacoes", json={"titulo": "Fluxo vendedor", "orgao_nome": "Órgão", "modalidade": "PUBLIC_TENDER"}).json()
    client.post(f"{B}/licitacoes/{lic['id']}/requisitos", json={"categoria": "HABILITACAO", "descricao": "Certidão"})
    client.post(f"{B}/licitacoes/{lic['id']}/status", json={"status": "EM_ANALISE"})
    return client.post(f"{B}/licitacoes/{lic['id']}/go-no-go", json={"decisao": "NO_GO", "justificativa": "Sem equipe"})


def _fluxo_comprador(client, orgao_id):
    proc = client.post(f"{P}/processos", json={"orgao_id": orgao_id, "objeto": "Fluxo comprador", "valor_estimado": 1000}).json()
    for status in ("ESTUDOS_TECNICOS", "TERMO_REFERENCIA", "PUBLICADO"):
        client.patch(f"{P}/processos/{proc['id']}", json={"status": status})
    return client.get(f"{P}/processos/{proc['id']}/workspace")


def _inicializacao_ms() -> float:
    codigo = "import time; t = time.perf_counter(); import app.main; print((time.perf_counter() - t) * 1000)"
    medidas = [float(subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, check=True).stdout)
               for _ in range(3)]
    return round(statistics.median(medidas), 1)


def _bundle() -> dict | None:
    dist = RAIZ / "frontend" / "dist" / "assets"
    if not dist.exists():
        return None
    arquivos = list(dist.glob("*.js")) + list(dist.glob("*.css"))
    maior = max(arquivos, key=lambda a: a.stat().st_size)
    return {"total_kb": round(sum(a.stat().st_size for a in arquivos) / 1024, 1), "arquivos": len(arquivos),
            "maior_kb": round(maior.stat().st_size / 1024, 1)}


def _comparar(atual: dict, base: dict) -> list[str]:
    regressoes = []
    for grupo in ("rotas", "fluxos"):
        for nome, medida in atual[grupo].items():
            anterior = base.get(grupo, {}).get(nome)
            if anterior is None:
                continue
            if medida["consultas"] > anterior["consultas"]:
                regressoes.append(f"{nome}: consultas {anterior['consultas']} → {medida['consultas']}")
            if medida["p95_ms"] > max(anterior["p95_ms"] * 1.5, anterior["p95_ms"] + 20):
                regressoes.append(f"{nome}: p95 {anterior['p95_ms']} → {medida['p95_ms']} ms")
    return regressoes


def test_medir_orcamento_de_desempenho(client, db_session):
    engine = db_session.get_bind()
    ids = _semear(client)
    orgao_id = client.get(f"{P}/orgaos").json()[0]["id"]
    resultado = {
        "medido_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "volume_por_entidade": VOLUME, "repeticoes": REPETICOES,
        "rotas": {nome: _medir(client, engine, lambda c=caminho: client.get(c)) for nome, caminho in _rotas(ids).items()},
        "fluxos": {
            "vendedor · criar → requisito → status → go/no-go": _medir(client, engine, lambda: _fluxo_vendedor(client)),
            "comprador · criar → 3 etapas → workspace": _medir(client, engine, lambda: _fluxo_comprador(client, orgao_id)),
        },
        "inicializacao_ms": _inicializacao_ms(),
        "memoria_pico_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "bundle": _bundle(),
    }
    destino = RAIZ / os.environ["B2BON_MEDIR"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.environ.get("B2BON_BASELINE"):
        regressoes = _comparar(resultado, json.loads((RAIZ / os.environ["B2BON_BASELINE"]).read_text(encoding="utf-8")))
        assert regressoes == [], "Regressão de desempenho:\n" + "\n".join(regressoes)
