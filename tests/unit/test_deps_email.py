import pytest

from app.api.deps import get_email_provider
from app.core.config import settings
from app.providers.channels.email.desativado import EmailDesativadoProvider
from app.providers.channels.email.smtp import SmtpEmailProvider
from app.providers.channels.email.stub import StubEmailProvider


def test_com_smtp_configurado_usa_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "smtp.exemplo.com.br")

    provider = get_email_provider()

    assert isinstance(provider, SmtpEmailProvider)


def test_sem_smtp_em_producao_nao_finge_que_enviou(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trava a correção do raio-X: StubEmailProvider sempre reportava
    sucesso mesmo sem SMTP configurado — vazando pra produção, isso fazia
    o convite de empresa parecer enviado quando não saía nada de verdade
    (ver EmailDesativadoProvider)."""
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@host/db")

    provider = get_email_provider()

    assert isinstance(provider, EmailDesativadoProvider)
    resultado = provider.enviar("x@teste.com.br", "assunto", "corpo", "B2B ON", "no-reply@predator.local")
    assert resultado.sucesso is False


def test_sem_smtp_fora_de_producao_usa_stub_de_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "database_url", "sqlite:///./predator.db")

    provider = get_email_provider()

    assert isinstance(provider, StubEmailProvider)
