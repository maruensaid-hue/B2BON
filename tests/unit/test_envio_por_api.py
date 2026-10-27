import httpx
import pytest

from app.api.deps import resolver_email_provider
from app.core.config import settings
from app.models.configuracao_email_api import ConfiguracaoEmailApi
from app.models.configuracao_email_smtp import ConfiguracaoEmailSmtp
from app.models.tenant import Tenant
from app.providers.channels.email.base import montar_html_com_pixel
from app.providers.channels.email.sendgrid import SendGridEmailProvider
from app.providers.channels.email.smtp import SmtpEmailProvider

TENANT_ID = "tenant-envio-api"


class _Resposta:
    def __init__(self, status_code: int = 202, texto: str = "") -> None:
        self.status_code = status_code
        self.headers = {"X-Message-Id": "msg-1"}
        self.text = texto


@pytest.fixture(autouse=True)
def _config_da_plataforma(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sendgrid_api_key", "SG.da-plataforma")
    monkeypatch.setattr(settings, "sendgrid_remetente_email", "contato@plataforma.com.br")


def test_provedor_com_chave_e_remetente_do_cliente_usa_a_conta_dele(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict = {}

    def falso(url, json, headers, timeout):
        capturado.update(json=json, headers=headers)
        return _Resposta(202)

    monkeypatch.setattr(httpx, "post", falso)

    resultado = SendGridEmailProvider(api_key="SG.do-cliente", remetente_email="vendas@cliente.com", remetente_nome="Maria | Cliente").enviar(
        "dest@x.com", "Assunto", "Corpo", "B2B ON", "sistema@plataforma.com.br", TENANT_ID,
        pixel_url="https://api/pixel.png", campanha_destinatario_id=7,
    )

    assert resultado.sucesso is True
    assert capturado["headers"]["Authorization"] == "Bearer SG.do-cliente"
    corpo = capturado["json"]
    assert corpo["from"] == {"email": "vendas@cliente.com", "name": "Maria | Cliente"}
    assert corpo["reply_to"] == {"email": "vendas@cliente.com"}
    assert corpo["personalizations"][0]["custom_args"] == {"tenant_id": TENANT_ID, "campanha_destinatario_id": "7"}  # volta no aviso de entrega
    assert any(parte["type"] == "text/html" and "pixel.png" in parte["value"] for parte in corpo["content"])


def test_provedor_sem_argumentos_continua_usando_a_conta_da_plataforma(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict = {}
    monkeypatch.setattr(httpx, "post", lambda url, json, headers, timeout: capturado.update(json=json, headers=headers) or _Resposta(202))

    SendGridEmailProvider().enviar("dest@x.com", "A", "C", "Equipe", "reply@x.com", TENANT_ID)

    assert capturado["headers"]["Authorization"] == "Bearer SG.da-plataforma"
    assert capturado["json"]["from"] == {"email": "contato@plataforma.com.br", "name": "Equipe"}


def test_erro_do_servico_nao_mostra_o_nome_do_fornecedor(monkeypatch: pytest.MonkeyPatch) -> None:
    texto = '{"errors":[{"message":"The from address does not match a verified Sender Identity. See https://sendgrid.com/docs/sender-identity"}]}'
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resposta(403, texto))

    resultado = SendGridEmailProvider(api_key="SG.x", remetente_email="a@b.com").enviar("d@x.com", "A", "C", "N", "a@b.com", TENANT_ID)

    assert resultado.sucesso is False and resultado.transitoria is False
    assert "sendgrid" not in resultado.motivo_falha.lower()
    assert "verified Sender Identity" in resultado.motivo_falha and "serviço de envio" in resultado.motivo_falha


def _tenant(db_session) -> None:
    db_session.add(Tenant(id=TENANT_ID, razao_social="Cliente do envio por API"))
    db_session.commit()


def test_envio_por_api_do_cliente_tem_prioridade_sobre_a_conta_smtp(db_session) -> None:
    _tenant(db_session)
    db_session.add(ConfiguracaoEmailSmtp(tenant_id=TENANT_ID, host="smtp.gmail.com", porta=587, usuario="eu@x.com", senha="s", usar_tls=True))
    db_session.commit()
    assert isinstance(resolver_email_provider(TENANT_ID, db_session), SmtpEmailProvider)

    db_session.add(ConfiguracaoEmailApi(tenant_id=TENANT_ID, chave_api="SG.do-cliente", remetente_email="vendas@cliente.com", remetente_nome="Cliente"))
    db_session.commit()

    provedor = resolver_email_provider(TENANT_ID, db_session)
    assert isinstance(provedor, SendGridEmailProvider)
    assert (provedor.api_key, provedor.remetente_email, provedor.remetente_nome) == ("SG.do-cliente", "vendas@cliente.com", "Cliente")


def test_a_chave_do_cliente_fica_cifrada_no_banco(db_session) -> None:
    from sqlalchemy import text

    _tenant(db_session)
    db_session.add(ConfiguracaoEmailApi(tenant_id=TENANT_ID, chave_api="SG.segredo-do-cliente", remetente_email="v@c.com", chave_webhook="chave-publica"))
    db_session.commit()

    linha = db_session.execute(text("select chave_api, chave_webhook from configuracao_email_api")).one()

    assert "segredo-do-cliente" not in linha[0] and "chave-publica" not in linha[1]  # só o token cifrado fica em repouso
    assert db_session.query(ConfiguracaoEmailApi).one().chave_api == "SG.segredo-do-cliente"


def test_html_do_e_mail_transforma_enderecos_em_link_sem_quebrar_aspas() -> None:
    html = montar_html_com_pixel('Veja "http://x.com/a?b=1&c=2"\nSair: https://api.exemplo.com/opt-out/campanha/t:1:abc', "https://api/p.png")

    assert '<a href="http://x.com/a?b=1&amp;c=2">http://x.com/a?b=1&amp;c=2</a>&quot;' in html  # a aspa de fora não entra no link
    assert '<a href="https://api.exemplo.com/opt-out/campanha/t:1:abc">' in html
    assert '<img src="https://api/p.png"' in html
