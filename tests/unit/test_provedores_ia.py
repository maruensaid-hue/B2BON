"""Provedores adicionais de IA: contrato dos adapters (simulado), erros, fallback controlado e travas de custo/privacidade.

Nenhum teste aqui fala com a rede nem usa credencial real: o transporte é `httpx.MockTransport`."""

import json

import httpx
import pytest

from app.core.config import settings
from app.llm import fallback, provedores
from app.llm.base import LLMFalhaDeProvedor, LLMIndisponivel, LLMProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.schemas import LLMRequest, LLMResponse

CHAVE = "chave-de-teste-nao-vazar"
REQ = LLMRequest(prompt="Pergunta", system="Seja breve", max_tokens=300, temperature=0.2, model="claude-sonnet-5")


def _mock(resposta):
    """(transport, capturas). `resposta`: httpx.Response, exceção ou função(request)."""
    capturas: list[httpx.Request] = []

    def tratar(request):
        capturas.append(request)
        item = resposta(request) if callable(resposta) else resposta
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.MockTransport(tratar), capturas


def _corpo(captura: httpx.Request) -> dict:
    return json.loads(captura.content)


OPENAI_OK = httpx.Response(200, json={"model": "m-real", "choices": [{"message": {"content": "Olá"}, "finish_reason": "stop"}],
                                      "usage": {"prompt_tokens": 11, "completion_tokens": 7}})


# --- Groq / OpenRouter (OpenAI compatível) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fabrica", "url", "provedor"),
    [(provedores.groq, "https://api.groq.com/openai/v1/chat/completions", "groq"),
     (provedores.openrouter, "https://openrouter.ai/api/v1/chat/completions", "openrouter")],
)
def test_openai_compativel_contrato(fabrica, url, provedor):
    transporte, capturas = _mock(OPENAI_OK)
    resposta = fabrica(chave=CHAVE, modelo="modelo-x", transport=transporte).generate(REQ)

    assert (resposta.content, resposta.provider, resposta.input_tokens, resposta.output_tokens, resposta.model) == ("Olá", provedor, 11, 7, "m-real")
    [captura] = capturas
    assert str(captura.url) == url and captura.headers["authorization"] == f"Bearer {CHAVE}"
    corpo = _corpo(captura)
    assert corpo["model"] == "modelo-x"  # nunca o id Claude do request
    assert corpo["messages"] == [{"role": "system", "content": "Seja breve"}, {"role": "user", "content": "Pergunta"}]
    assert (corpo["max_tokens"], corpo["temperature"]) == (300, 0.2)


def test_temperature_e_system_so_vao_quando_informados():
    transporte, capturas = _mock(OPENAI_OK)
    provedores.groq(chave=CHAVE, modelo="m", transport=transporte).generate(LLMRequest(prompt="oi"))
    corpo = _corpo(capturas[0])
    assert "temperature" not in corpo and [m["role"] for m in corpo["messages"]] == ["user"]


# --- Cloudflare Workers AI -----------------------------------------------------------------------------------------


def test_cloudflare_contrato():
    transporte, capturas = _mock(httpx.Response(200, json={"success": True, "errors": [], "result": {"response": "Oi!"}}))
    provedor = provedores.CloudflareWorkersAI(account_id="conta123", chave=CHAVE, modelo="@cf/meta/modelo", transport=transporte)

    resposta = provedor.generate(REQ)

    assert (resposta.content, resposta.provider, resposta.model, resposta.input_tokens) == ("Oi!", "cloudflare", "@cf/meta/modelo", 0)
    [captura] = capturas
    assert str(captura.url) == "https://api.cloudflare.com/client/v4/accounts/conta123/ai/run/@cf/meta/modelo"
    assert captura.headers["authorization"] == f"Bearer {CHAVE}"
    assert _corpo(captura)["messages"][-1] == {"role": "user", "content": "Pergunta"}


def test_cloudflare_success_false_e_falha_do_provedor():
    transporte, _ = _mock(httpx.Response(200, json={"success": False, "errors": [{"message": "x"}], "result": None}))
    with pytest.raises(LLMFalhaDeProvedor):
        provedores.CloudflareWorkersAI(account_id="c", chave=CHAVE, modelo="m", transport=transporte).generate(REQ)


# --- Gemini --------------------------------------------------------------------------------------------------------


def test_gemini_contrato_com_chave_no_cabecalho_e_nunca_na_url():
    transporte, capturas = _mock(httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "Olá "}, {"text": "mundo"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4}, "modelVersion": "gem-1"}))

    resposta = provedores.GoogleGemini(chave=CHAVE, modelo="gem", transport=transporte).generate(REQ)

    assert (resposta.content, resposta.provider, resposta.input_tokens, resposta.output_tokens) == ("Olá mundo", "gemini", 9, 4)
    [captura] = capturas
    assert str(captura.url) == "https://generativelanguage.googleapis.com/v1beta/models/gem:generateContent"
    assert CHAVE not in str(captura.url) and captura.headers["x-goog-api-key"] == CHAVE
    corpo = _corpo(captura)
    assert corpo["systemInstruction"] == {"parts": [{"text": "Seja breve"}]}
    assert corpo["generationConfig"] == {"maxOutputTokens": 300, "temperature": 0.2}


def test_gemini_sem_candidatos_e_resposta_sem_texto_nao_falha_de_provedor():
    transporte, _ = _mock(httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(LLMIndisponivel) as erro:
        provedores.GoogleGemini(chave=CHAVE, modelo="g", transport=transporte).generate(REQ)
    assert not isinstance(erro.value, LLMFalhaDeProvedor)


# --- Erros comuns a todos os adapters -------------------------------------------------------------------------------

ADAPTERS = [
    lambda t: provedores.groq(chave=CHAVE, modelo="m", transport=t),
    lambda t: provedores.openrouter(chave=CHAVE, modelo="m", transport=t),
    lambda t: provedores.CloudflareWorkersAI(account_id="c", chave=CHAVE, modelo="m", transport=t),
    lambda t: provedores.GoogleGemini(chave=CHAVE, modelo="m", transport=t),
]


@pytest.mark.parametrize("fabrica", ADAPTERS)
@pytest.mark.parametrize(
    "resposta",
    [httpx.Response(429), httpx.Response(500), httpx.Response(503), httpx.Response(401), httpx.Response(403), httpx.Response(404),
     httpx.Response(400), httpx.ConnectTimeout("lento"), httpx.ReadTimeout("lento"), httpx.ConnectError("recusado"),
     httpx.Response(200, content=b"<html>erro</html>"), httpx.Response(200, json=["nao-e-objeto"])],
)
def test_toda_falha_do_provedor_vira_llm_falha_de_provedor_sem_vazar_a_chave(fabrica, resposta):
    transporte, capturas = _mock(resposta)
    with pytest.raises(LLMFalhaDeProvedor) as erro:
        fabrica(transporte).generate(REQ)
    assert len(capturas) == 1  # o adapter não repete sozinho: retentativa/fallback é decisão da camada acima
    assert CHAVE not in str(erro.value) and CHAVE not in repr(erro.value)


@pytest.mark.parametrize("fabrica", ADAPTERS[:3])
def test_resposta_vazia_nao_e_falha_de_provedor(fabrica):
    corpos = {0: {"choices": [{"message": {"content": "  "}}]}, 1: {"choices": [{"message": {"content": ""}}]}, 2: {"success": True, "result": {"response": ""}}}
    for indice, corpo in corpos.items():
        if ADAPTERS[indice] is not fabrica:
            continue
        transporte, _ = _mock(httpx.Response(200, json=corpo))
        with pytest.raises(LLMIndisponivel) as erro:
            fabrica(transporte).generate(REQ)
        assert not isinstance(erro.value, LLMFalhaDeProvedor)


def test_resposta_cortada_por_limite_de_tokens_e_erro_de_conteudo():
    transporte, _ = _mock(httpx.Response(200, json={"choices": [{"message": {"content": "metade"}, "finish_reason": "length"}]}))
    with pytest.raises(LLMIndisponivel, match="cortada"):
        provedores.groq(chave=CHAVE, modelo="m", transport=transporte).generate(REQ)


# --- Fallback controlado -----------------------------------------------------------------------------------------


class Falso(LLMProvider):
    def __init__(self, nome: str, erro: Exception | None = None):
        self.nome, self.erro, self.pedidos = nome, erro, []

    def generate(self, request):
        self.pedidos.append(request)
        if self.erro:
            raise self.erro
        return LLMResponse(content=f"de-{self.nome}", model=self.nome, input_tokens=1, output_tokens=1, provider=self.nome)


def _cadeia(primario, *adicionais, contar=lambda pid: 0, limite=200):
    return fallback.ProvedorComFallback(primario, [(f.nome, f) for f in adicionais], contar, limite)


def test_principal_saudavel_nunca_aciona_fallback():
    principal, extra = Falso("anthropic"), Falso("groq")
    assert _cadeia(principal, extra).generate(REQ).content == "de-anthropic" and extra.pedidos == []


def test_falha_do_principal_usa_o_fallback_na_ordem_com_modelo_proprio():
    principal = Falso("anthropic", LLMFalhaDeProvedor("fora"))
    primeiro, segundo = Falso("groq", LLMFalhaDeProvedor("429")), Falso("gemini")

    resposta = _cadeia(principal, primeiro, segundo).generate(REQ)

    assert resposta.content == "de-gemini" and len(primeiro.pedidos) == 1 and len(segundo.pedidos) == 1
    assert segundo.pedidos[0].model is None and REQ.model == "claude-sonnet-5"  # o id Claude não vaza para outro fornecedor


def test_erro_de_conteudo_do_principal_nao_troca_de_fornecedor():
    principal, extra = Falso("anthropic", LLMIndisponivel("A IA não retornou texto na resposta.")), Falso("groq")
    with pytest.raises(LLMIndisponivel):
        _cadeia(principal, extra).generate(REQ)
    assert extra.pedidos == []


def test_todos_falhando_levanta_a_ultima_falha_sem_loop():
    cadeia = _cadeia(Falso("a", LLMFalhaDeProvedor("a")), Falso("b", LLMFalhaDeProvedor("b")), Falso("c", LLMFalhaDeProvedor("c")))
    with pytest.raises(LLMFalhaDeProvedor, match="c"):
        cadeia.generate(REQ)


def test_teto_diario_pula_o_provedor_em_vez_de_gastar_mais():
    extra = Falso("groq")
    cadeia = _cadeia(Falso("anthropic", LLMFalhaDeProvedor("fora")), extra, contar=lambda pid: 200, limite=200)
    with pytest.raises(LLMFalhaDeProvedor):
        cadeia.generate(REQ)
    assert extra.pedidos == []


def test_disjuntor_por_provedor_pula_o_que_esta_falhando(monkeypatch):
    monkeypatch.setattr(settings, "ai_disjuntor_falhas", 2)
    principal, ruim, bom = Falso("anthropic", LLMFalhaDeProvedor("fora")), Falso("groq", LLMFalhaDeProvedor("429")), Falso("gemini")
    cadeia = _cadeia(principal, ruim, bom)
    for _ in range(4):
        assert cadeia.generate(REQ).content == "de-gemini"
    assert len(principal.pedidos) == 2 and len(ruim.pedidos) == 2  # circuitos abertos após 2 falhas; o gemini atendeu as 4


# --- Habilitação: nada é chamado sem configuração, aprovação e trava de custo --------------------------------------


@pytest.fixture()
def limpo(monkeypatch):
    for campo in ("ai_provedores_fallback", "cloudflare_ai_account_id", "cloudflare_ai_api_token", "cloudflare_ai_modelo", "groq_api_key",
                  "groq_modelo", "openrouter_api_key", "openrouter_modelo", "gemini_api_key", "gemini_modelo"):
        monkeypatch.setattr(settings, campo, "")
    for campo in ("cloudflare_ai_aprovado_dados_reais", "groq_aprovado_dados_reais", "openrouter_aprovado_dados_reais",
                  "gemini_aprovado_dados_reais", "ai_fallback_permite_pago"):
        monkeypatch.setattr(settings, campo, False)
    for campo in ("cloudflare_ai_plano", "groq_plano", "openrouter_plano", "gemini_plano"):
        monkeypatch.setattr(settings, campo, "gratuito")


def _estados():
    return {p["id"]: p for p in fallback.status_provedores()}


def test_por_padrao_so_a_anthropic_e_nenhum_adicional_esta_ativo(db_session, limpo):
    assert isinstance(fallback.construir_provedor(db_session), ClaudeProvider)
    estados = _estados()
    assert {k: v["estado"] for k, v in estados.items() if k != "anthropic"} == dict.fromkeys(("cloudflare", "groq", "openrouter", "gemini"), "nao_configurado")
    assert all(v["adapter_implementado"] and v["teste_simulado"] and v["teste_real"] == "nao_realizado" for k, v in estados.items() if k != "anthropic")


def test_credencial_sem_estar_na_lista_fica_apenas_configurado_e_nunca_e_chamado(db_session, limpo, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", CHAVE)
    monkeypatch.setattr(settings, "groq_modelo", "m")
    monkeypatch.setattr(settings, "groq_aprovado_dados_reais", True)
    assert _estados()["groq"]["estado"] == "configurado"
    assert isinstance(fallback.construir_provedor(db_session), ClaudeProvider)


def test_listado_sem_aprovacao_de_privacidade_fica_bloqueado(db_session, limpo, monkeypatch):
    monkeypatch.setattr(settings, "ai_provedores_fallback", "groq")
    monkeypatch.setattr(settings, "groq_api_key", CHAVE)
    monkeypatch.setattr(settings, "groq_modelo", "m")
    assert _estados()["groq"]["estado"] == "bloqueado"
    assert any("sem_aprovacao_de_privacidade" in b for b in _estados()["groq"]["bloqueios"])
    assert isinstance(fallback.construir_provedor(db_session), ClaudeProvider)  # nenhum dado real sai


def test_plano_pago_exige_autorizacao_de_custo(db_session, limpo, monkeypatch):
    monkeypatch.setattr(settings, "ai_provedores_fallback", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", CHAVE)
    monkeypatch.setattr(settings, "gemini_modelo", "g")
    monkeypatch.setattr(settings, "gemini_aprovado_dados_reais", True)
    monkeypatch.setattr(settings, "gemini_plano", "pago")
    assert any("plano_pago_nao_permitido" in b for b in _estados()["gemini"]["bloqueios"])
    monkeypatch.setattr(settings, "ai_fallback_permite_pago", True)
    assert _estados()["gemini"]["estado"] == "ativo"


def test_plano_invalido_bloqueia(limpo, monkeypatch):
    monkeypatch.setattr(settings, "ai_provedores_fallback", "groq")
    monkeypatch.setattr(settings, "groq_api_key", CHAVE)
    monkeypatch.setattr(settings, "groq_modelo", "m")
    monkeypatch.setattr(settings, "groq_aprovado_dados_reais", True)
    monkeypatch.setattr(settings, "groq_plano", "talvez")
    assert any("plano_invalido" in b for b in _estados()["groq"]["bloqueios"])


def test_openrouter_gratuito_so_com_modelo_free(limpo, monkeypatch):
    monkeypatch.setattr(settings, "ai_provedores_fallback", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", CHAVE)
    monkeypatch.setattr(settings, "openrouter_aprovado_dados_reais", True)
    monkeypatch.setattr(settings, "openrouter_modelo", "vendor/modelo-pago")
    assert any("modelo_nao_gratuito" in b for b in _estados()["openrouter"]["bloqueios"])
    monkeypatch.setattr(settings, "openrouter_modelo", "vendor/modelo:free")
    assert _estados()["openrouter"]["estado"] == "ativo"


def test_ativo_entra_na_cadeia_so_apos_falha_da_anthropic_e_respeita_a_ordem(db_session, limpo, monkeypatch):
    monkeypatch.setattr(settings, "ai_provedores_fallback", "groq, gemini")
    for nome in ("groq", "gemini"):
        monkeypatch.setattr(settings, f"{nome}_api_key", CHAVE)
        monkeypatch.setattr(settings, f"{nome}_modelo", "m")
        monkeypatch.setattr(settings, f"{nome}_aprovado_dados_reais", True)
    transporte, capturas = _mock(OPENAI_OK)

    provedor = fallback.construir_provedor(db_session, transport=transporte)

    assert isinstance(provedor, fallback.ProvedorComFallback) and [i for i, _ in provedor._adicionais] == ["groq", "gemini"]
    assert capturas == []  # construir a cadeia não faz nenhuma chamada externa


def test_teto_diario_conta_so_sucessos_do_dia_no_ledger(db_session):
    from app.models.registro_uso_ia import RegistroUsoIa

    base = dict(tenant_id="t", agente="a", feature="f", tokens_entrada=0, tokens_saida=0, latencia_ms=1)
    for status, provider in [("sucesso", "groq"), ("sucesso", "groq"), ("falha", "groq"), ("sucesso", "gemini")]:
        db_session.add(RegistroUsoIa(status=status, provider=provider, **base))
    db_session.commit()
    assert (fallback.contar_sucessos_hoje(db_session, "groq"), fallback.contar_sucessos_hoje(db_session, "gemini")) == (2, 1)


def test_endpoint_de_status_e_so_super_admin_e_nao_vaza_credencial(client, criar_usuario_autenticado, limpo, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", CHAVE)
    monkeypatch.setattr(settings, "groq_modelo", "m")
    corpo = client.get("/api/v1/admin/provedores-ia")
    assert corpo.status_code == 200 and CHAVE not in corpo.text
    assert {p["id"] for p in corpo.json()} == {"anthropic", "cloudflare", "groq", "openrouter", "gemini"}
    admin = criar_usuario_autenticado("tenant-prov-ia", papel="admin", email="admin@prov-ia.com")
    assert client.get("/api/v1/admin/provedores-ia", headers=admin).status_code == 403


def test_gateway_registra_o_provedor_do_fallback_no_ledger(db_session):
    from app.contexts.intelligence.gateway import ContextoIA, gerar
    from app.models.registro_uso_ia import RegistroUsoIa

    cadeia = _cadeia(Falso("anthropic", LLMFalhaDeProvedor("fora")), Falso("groq"))
    resposta = gerar(db_session, cadeia, ContextoIA(tenant_id="t-fb", feature="plataforma.faq"), LLMRequest(prompt="p"))

    assert resposta.content == "de-groq"
    linha = db_session.query(RegistroUsoIa).filter_by(tenant_id="t-fb").one()
    assert (linha.provider, linha.status) == ("groq", "sucesso")
