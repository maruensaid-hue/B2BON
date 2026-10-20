"""AI-independent core: com o provedor de IA fora do ar, o produto continua usável; só o que depende de IA sinaliza."""

import pytest

from app.api.deps import get_llm_provider
from app.llm.base import LLMFalhaDeProvedor
from app.main import app
from tests.fakes import FakeLLMProvider


class _IAForaDoAr(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__(["x"])
        self.tentativas = 0

    def generate(self, request):
        self.tentativas += 1
        raise LLMFalhaDeProvedor("provedor fora do ar")


@pytest.fixture()
def ia_fora_do_ar(monkeypatch):
    llm = _IAForaDoAr()
    monkeypatch.setitem(app.dependency_overrides, get_llm_provider, lambda: llm)
    return llm


def test_crm_e_kpis_deterministicos_funcionam_sem_ia(client, criar_conta_com_decisor, ia_fora_do_ar):
    conta, decisor = criar_conta_com_decisor()

    criado = client.post("/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio X", "valor": 5000.0})
    assert criado.status_code == 201

    assert any(n["nome"] == "Negócio X" for n in client.get("/api/v1/crm/negocios").json())
    assert client.get("/api/v1/crm/estagios").status_code == 200
    funil = client.get("/api/v1/crm/dashboard/funil")
    assert funil.status_code == 200 and sum(e["quantidade"] for e in funil.json()["estagios"]) == 1
    assert client.get("/api/v1/crm/dashboard/economia", params={"periodo": "2026-10"}).status_code == 200
    assert client.get("/api/v1/painel/metrica-norte").status_code == 200
    assert client.get("/api/v1/crm/dashboard/atividade").status_code == 200

    assert ia_fora_do_ar.tentativas == 0  # nada determinístico encostou na IA


def test_funcao_de_ia_sinaliza_indisponibilidade_sem_derrubar_o_servidor(client, criar_conta_com_decisor, ia_fora_do_ar):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post("/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "N", "valor": 1.0}).json()

    resposta = client.post(f"/api/v1/crm/negocios/{negocio['id']}/meeting-brief")

    assert resposta.status_code == 409
    assert "IA" in resposta.json()["detalhe"]
    assert "Traceback" not in resposta.text and "anthropic" not in resposta.text.lower()
    # o CRM segue de pé depois da falha de IA
    assert client.get("/api/v1/crm/negocios").status_code == 200
