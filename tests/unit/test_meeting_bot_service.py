from datetime import UTC, datetime

from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.reuniao import Reuniao
from app.providers.meeting_bot.stub import StubMeetingBotProvider
from app.services import meeting_bot_service
from tests.fakes import FakeLLMProvider

TENANT_ID = "tenant-teste"


def _criar_reuniao(db_session, link_reuniao: str | None, origem_crm_id: str | None = None) -> Reuniao:
    conta = Conta(tenant_id=TENANT_ID, nome="Empresa Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    db_session.flush()
    reuniao = Reuniao(
        tenant_id=TENANT_ID, conta_id=conta.id, decisor_id=decisor.id, vendedor_id="1",
        data_hora=datetime(2026, 9, 1, 14, 0), status="agendada",
        horario_confirmado=datetime(2026, 9, 1, 14, 0), link_reuniao=link_reuniao,
        origem_crm_id=origem_crm_id,
    )
    db_session.add(reuniao)
    db_session.commit()
    return reuniao


def test_agendar_transcricao_pula_link_de_stub(db_session) -> None:
    reuniao = _criar_reuniao(db_session, "https://meet.stub/stub-evento-1")
    provider = StubMeetingBotProvider()

    meeting_bot_service.agendar_transcricao_pos_confirmacao(db_session, reuniao, provider)

    assert provider.bots_agendados == []
    assert reuniao.bot_id is None


def test_agendar_transcricao_pula_sem_link(db_session) -> None:
    reuniao = _criar_reuniao(db_session, None)
    provider = StubMeetingBotProvider()

    meeting_bot_service.agendar_transcricao_pos_confirmacao(db_session, reuniao, provider)

    assert provider.bots_agendados == []


def test_agendar_transcricao_com_link_real_grava_bot_id(db_session) -> None:
    reuniao = _criar_reuniao(db_session, "https://meet.google.com/abc-defg-hij")
    provider = StubMeetingBotProvider()

    meeting_bot_service.agendar_transcricao_pos_confirmacao(db_session, reuniao, provider)

    assert len(provider.bots_agendados) == 1
    assert provider.bots_agendados[0]["link_reuniao"] == "https://meet.google.com/abc-defg-hij"
    assert reuniao.bot_id == "stub-bot-1"
    assert reuniao.status_transcricao == "agendado"


def test_agendar_transcricao_nao_propaga_erro_do_provider(db_session) -> None:
    reuniao = _criar_reuniao(db_session, "https://meet.google.com/abc-defg-hij")

    class ProviderComFalha:
        def agendar_bot(self, link_reuniao, horario_inicio, webhook_url):
            raise RuntimeError("fornecedor fora do ar")

    # Não deve levantar exceção — bot de transcrição é melhor-esforço.
    meeting_bot_service.agendar_transcricao_pos_confirmacao(db_session, reuniao, ProviderComFalha())

    assert reuniao.bot_id is None


def test_processar_transcricao_cria_atividade_com_conta_e_negocio(db_session) -> None:
    reuniao = _criar_reuniao(db_session, "https://meet.google.com/abc-defg-hij", origem_crm_id="42")
    llm = FakeLLMProvider(["Pontos discutidos: preço e prazo. Próximo passo: enviar proposta."])

    meeting_bot_service.processar_transcricao(db_session, reuniao, llm, "transcrição bruta da reunião...")

    assert reuniao.transcricao == "transcrição bruta da reunião..."
    assert "preço e prazo" in reuniao.resumo_ia
    assert reuniao.status_transcricao == "concluida"

    atividade = db_session.query(Atividade).filter_by(tenant_id=TENANT_ID, tipo="reuniao").one()
    assert atividade.conta_id == reuniao.conta_id
    assert atividade.negocio_id == 42
    assert "preço e prazo" in atividade.descricao
    assert atividade.usuario_id is None


def test_processar_transcricao_tolera_origem_crm_id_nao_numerico(db_session) -> None:
    reuniao = _criar_reuniao(db_session, "https://meet.google.com/abc-defg-hij", origem_crm_id="stub-negocio-abc")
    llm = FakeLLMProvider(["Resumo qualquer."])

    meeting_bot_service.processar_transcricao(db_session, reuniao, llm, "transcrição bruta...")

    atividade = db_session.query(Atividade).filter_by(tenant_id=TENANT_ID, tipo="reuniao").one()
    assert atividade.negocio_id is None
    assert atividade.conta_id == reuniao.conta_id
