from datetime import UTC, datetime, time

from app.models.configuracao_envio import ConfiguracaoEnvio
from app.services import envio_service


def _config(inicio: time, fim: time) -> ConfiguracaoEnvio:
    return ConfiguracaoEnvio(
        tenant_id="tenant-teste",
        remetente_nome="X",
        remetente_email="x@x.com",
        assinatura="",
        horario_inicio=inicio,
        horario_fim=fim,
    )


def _fixar_relogio(monkeypatch, agora: datetime) -> None:
    class _RelogioFixo:
        @staticmethod
        def now(tz=None):
            return agora

    monkeypatch.setattr(envio_service, "datetime", _RelogioFixo)


def test_bloqueia_envio_de_email_no_fim_de_semana(monkeypatch):
    """E3-H3: agendamento respeita dias úteis."""
    sabado = datetime(2024, 1, 6, 10, 0, tzinfo=UTC)
    _fixar_relogio(monkeypatch, sabado)

    assert envio_service._dentro_da_janela_dias_uteis_e_horario(_config(time(9, 0), time(18, 0))) is False


def test_bloqueia_envio_de_email_fora_do_horario_configurado(monkeypatch):
    """E3-H3: agendamento respeita janela de horário configurável."""
    segunda_de_madrugada = datetime(2024, 1, 8, 3, 0, tzinfo=UTC)
    _fixar_relogio(monkeypatch, segunda_de_madrugada)

    assert envio_service._dentro_da_janela_dias_uteis_e_horario(_config(time(9, 0), time(18, 0))) is False


def test_permite_envio_de_email_em_dia_util_dentro_do_horario(monkeypatch):
    segunda_de_tarde = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)
    _fixar_relogio(monkeypatch, segunda_de_tarde)

    assert envio_service._dentro_da_janela_dias_uteis_e_horario(_config(time(9, 0), time(18, 0))) is True
