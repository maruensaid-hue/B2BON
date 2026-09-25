"""Varredura de isolamento (Fase 17): tenant × tenant e Buy × Sell.

Em vez de confiar em testes rota a rota, o tenant A grava um marcador
único em dados PRIVADOS de vários módulos (conta, contato, negócio,
oferta, ICP, licitação, processo de compra, fornecedor...). Depois, TODA
rota GET do OpenAPI é chamada:

- como tenant B, trocando cada parâmetro de caminho por ids existentes:
  o marcador de A nunca pode aparecer (IDOR / vazamento entre tenants);
- como o próprio tenant A, fora de `/procurement`: o marcador do lado
  comprador nunca pode aparecer (barreira Buy/Sell).

Nenhuma rota pode responder 5xx nessa varredura (erro não tratado com
id inexistente ou de outro tenant).
"""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.main import app

MARCADOR_A = "MARCADOR-PRIVADO-TENANT-A"
MARCADOR_COMPRA = "MARCADOR-SIGILO-COMPRADOR"
IDS = ("1", "2", "3")
# Rotas que disparam processamento pesado ou externo e não leem dados por id.
IGNORAR = re.compile(r"^/(health|metrics)|/stream|/sse|/download-app")
TEXTO_POR_PARAM = {"tenant_id": "tenant-teste", "sistema": "b2bon_crm", "entidade": "accounts", "recurso": "orgaos",
                   "token": "x", "slug": "x", "cnpj": "11222333000181", "periodo": "2026-01"}


def _semear_tenant_a(client) -> None:
    conta = client.post("/api/v1/leads/contas", json={"nome": f"Conta {MARCADOR_A}"}).json()
    decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": f"Decisor {MARCADOR_A}"}).json()
    negocio = client.post("/api/v1/crm/negocios", json={"conta_id": conta["id"], "decisor_id": decisor["id"],
                                                        "nome": f"Negócio {MARCADOR_A}", "valor": 1000}).json()
    client.post(f"/api/v1/crm/negocios/{negocio['id']}/atividades", json={"tipo": "nota", "descricao": f"Nota {MARCADOR_A}"})
    client.post("/api/v1/ofertas", json={"nome": f"Oferta {MARCADOR_A}", "descricao": MARCADOR_A})
    client.post("/api/v1/icp", json={"nome": f"ICP {MARCADOR_A}", "segmento": "x", "porte": "grande", "regiao": "sudeste"})
    client.post("/api/v1/bids/licitacoes", json={"titulo": f"Licitação {MARCADOR_A}",
                                                  "prazo_proposta": (datetime.now(UTC) + timedelta(days=9)).isoformat()})
    orgao = client.post("/api/v1/procurement/orgaos", json={"nome": f"Órgão {MARCADOR_COMPRA} {MARCADOR_A}"}).json()
    client.post("/api/v1/procurement/processos", json={"orgao_id": orgao["id"], "objeto": f"Objeto {MARCADOR_COMPRA} {MARCADOR_A}"})
    client.post("/api/v1/procurement/fornecedores", json={"razao_social": f"Fornecedor {MARCADOR_COMPRA} {MARCADOR_A}"})


def _rotas_get() -> list[str]:
    caminhos = app.openapi()["paths"]
    return sorted(p for p, metodos in caminhos.items() if "get" in metodos and not IGNORAR.search(p))


def _instancias(caminho: str) -> list[str]:
    parametros = re.findall(r"{(\w+)}", caminho)
    if not parametros:
        return [caminho]
    resultado = []
    for valor in IDS:
        concreto = caminho
        for nome in parametros:
            substituto = TEXTO_POR_PARAM.get(nome, valor if nome.endswith("id") or nome == "id" else valor)
            concreto = concreto.replace("{" + nome + "}", substituto, 1)
        resultado.append(concreto)
    return sorted(set(resultado))


@pytest.fixture()
def dados_a(client):
    _semear_tenant_a(client)
    corpo = client.get("/api/v1/crm/negocios").text + client.get("/api/v1/procurement/fornecedores").text
    assert MARCADOR_A in corpo and MARCADOR_COMPRA in corpo, "semeadura falhou"


def test_nenhuma_rota_get_devolve_dado_privado_de_outro_tenant(client, dados_a, criar_usuario_autenticado):
    tenant_b = criar_usuario_autenticado("tenant-b-varredura", papel="admin", email="admin@b-varredura.com")
    vazamentos, erros = [], []
    chamadas = 0
    for caminho in _rotas_get():
        for concreto in _instancias(caminho):
            resposta = client.get(concreto, headers=tenant_b)
            chamadas += 1
            if resposta.status_code >= 500:
                erros.append(f"{concreto} → {resposta.status_code}")
            elif MARCADOR_A in resposta.text:
                vazamentos.append(concreto)
    assert chamadas > 200
    # controle positivo: os mesmos ids, como tenant A, chegam de fato aos dados marcados
    positivos = [c for caminho in _rotas_get() if "{" in caminho for c in _instancias(caminho) if MARCADOR_A in client.get(c).text]
    assert len(positivos) >= 5, positivos
    assert vazamentos == [], f"dado do tenant A visível ao tenant B em: {vazamentos}"
    assert erros == [], "\n".join(erros)


def test_nenhuma_rota_fora_de_procurement_expoe_dado_do_comprador(client, dados_a):
    vazamentos, erros = [], []
    for caminho in _rotas_get():
        if caminho.startswith("/api/v1/procurement"):
            continue
        for concreto in _instancias(caminho):
            resposta = client.get(concreto)
            if resposta.status_code >= 500:
                erros.append(f"{concreto} → {resposta.status_code}")
            elif MARCADOR_COMPRA in resposta.text:
                vazamentos.append(concreto)
    assert vazamentos == [], f"dado do lado comprador fora de /procurement em: {vazamentos}"
    assert erros == [], "\n".join(erros)
