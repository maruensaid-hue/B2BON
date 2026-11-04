"""Criar modelo de mensagem pela plataforma (permissão whatsapp_business_management): regras, chamada à Meta e cache local."""

import httpx
import pytest

from app.models.template_whatsapp import TemplateWhatsApp
from app.providers.channels.whatsapp.meta import MetaWhatsAppProvider
from app.services import whatsapp_service
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

TENANT = "tenant-templates"


class _Resposta:
    def __init__(self, status: int, corpo: dict):
        self.status_code, self._corpo = status, corpo

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._corpo


def _provider() -> MetaWhatsAppProvider:
    return MetaWhatsAppProvider("EAAtoken", "111", "222")


def test_cria_na_conta_do_tenant_com_nome_normalizado_e_guarda_o_status(db_session, monkeypatch):
    chamadas = []

    def post(url, json=None, headers=None, timeout=None):
        chamadas.append((url, json))
        return _Resposta(200, {"id": "987", "status": "PENDING", "category": "UTILITY"})

    monkeypatch.setattr(httpx, "post", post)

    template = whatsapp_service.criar_template(db_session, TENANT, "1", _provider(), "Retorno do Contato", "UTILITY",
                                               "Olá! Retornando o contato que você pediu.", "Responda SAIR para não receber mais")

    url, corpo = chamadas[0]
    assert url.endswith("/222/message_templates")
    assert corpo["name"] == "retorno_do_contato" and corpo["language"] == "pt_BR" and corpo["category"] == "UTILITY"
    assert corpo["components"] == [{"type": "BODY", "text": "Olá! Retornando o contato que você pediu."},
                                   {"type": "FOOTER", "text": "Responda SAIR para não receber mais"}]
    assert template.status == "pending"
    assert db_session.query(TemplateWhatsApp).filter_by(tenant_id=TENANT, nome="retorno_do_contato").count() == 1


@pytest.mark.parametrize(
    ("nome", "categoria", "corpo", "rodape"),
    [
        ("###", "UTILITY", "texto", None),  # nome sem letra nem número
        ("ok", "AUTHENTICATION", "texto", None),  # categoria não permitida aqui
        ("ok", "UTILITY", "Olá {{nome}}", None),  # variável não é preenchida no envio
        ("ok", "UTILITY", "", None),
        ("ok", "UTILITY", "texto", "x" * 61),
    ],
)
def test_recusa_antes_de_chamar_a_meta(db_session, monkeypatch, nome, categoria, corpo, rodape):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("não deveria chamar a Meta"))
    with pytest.raises(ValidacaoFalhou):
        whatsapp_service.criar_template(db_session, TENANT, "1", _provider(), nome, categoria, corpo, rodape)


def test_nome_repetido_e_erro_da_meta_viram_mensagem_clara(db_session, monkeypatch):
    db_session.add(TemplateWhatsApp(tenant_id=TENANT, nome="boas_vindas", corpo="x", status="approved"))
    db_session.commit()
    with pytest.raises(RegraNegocioViolada, match="Já existe"):
        whatsapp_service.criar_template(db_session, TENANT, "1", _provider(), "Boas-vindas", "UTILITY", "texto")

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resposta(400, {"error": {"code": 100, "message": "Invalid parameter",
                                                                                 "error_user_msg": "Conteúdo não permitido"}}))
    with pytest.raises(RegraNegocioViolada, match="Conteúdo não permitido"):
        whatsapp_service.criar_template(db_session, TENANT, "1", _provider(), "novo", "MARKETING", "texto")
    assert db_session.query(TemplateWhatsApp).filter_by(tenant_id=TENANT, nome="novo").count() == 0


def test_nome_de_template_segue_a_regra_da_meta():
    assert whatsapp_service.nome_de_template("  Promoção de Março!! ") == "promocao_de_marco"


def test_meta_sem_resposta_mostra_os_modelos_guardados_em_vez_de_lista_vazia(db_session, monkeypatch):
    db_session.add(TemplateWhatsApp(tenant_id=TENANT, nome="retorno_contato", corpo="Olá", status="pending"))
    db_session.commit()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resposta(400, {"error": {"code": 80008, "message": "rate limit"}}))

    lista = whatsapp_service.sincronizar_templates(db_session, TENANT, _provider())

    assert [t.nome for t in lista] == ["retorno_contato"]
