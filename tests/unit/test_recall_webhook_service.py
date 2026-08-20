import hashlib
import hmac
from datetime import datetime

from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.reuniao import Reuniao
from app.services import recall_webhook_service
from tests.fakes import FakeLLMProvider

TENANT_ID = "tenant-teste"
SEGREDO = "segredo-de-teste-recall"


def _assinar(payload: bytes, segredo: str = SEGREDO) -> str:
    return hmac.new(segredo.encode(), payload, hashlib.sha256).hexdigest()


def test_verificar_assinatura_valida() -> None:
    payload = b'{"bot_id": "bot-1"}'
    assert recall_webhook_service.verificar_assinatura(payload, _assinar(payload), SEGREDO) is True


def test_verificar_assinatura_invalida() -> None:
    payload = b'{"bot_id": "bot-1"}'
    assert recall_webhook_service.verificar_assinatura(payload, "assinatura-forjada", SEGREDO) is False


def test_verificar_assinatura_sem_header_ou_segredo() -> None:
    payload = b'{"bot_id": "bot-1"}'
    assert recall_webhook_service.verificar_assinatura(payload, None, SEGREDO) is False
    assert recall_webhook_service.verificar_assinatura(payload, _assinar(payload), "") is False


def test_processar_evento_atualiza_reuniao_pelo_bot_id(db_session) -> None:
    conta = Conta(tenant_id=TENANT_ID, nome="Empresa Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    db_session.flush()
    reuniao = Reuniao(
        tenant_id=TENANT_ID, conta_id=conta.id, decisor_id=decisor.id, vendedor_id="1",
        data_hora=datetime(2026, 9, 1, 14, 0), status="agendada", bot_id="bot-123",
    )
    db_session.add(reuniao)
    db_session.commit()

    llm = FakeLLMProvider(["Resumo da reunião."])
    recall_webhook_service.processar_evento(db_session, llm, {"bot_id": "bot-123", "transcript": "texto bruto"})

    db_session.refresh(reuniao)
    assert reuniao.transcricao == "texto bruto"
    assert reuniao.status_transcricao == "concluida"
    assert db_session.query(Atividade).filter_by(conta_id=conta.id, tipo="reuniao").count() == 1


def test_processar_evento_ignora_bot_id_desconhecido(db_session) -> None:
    llm = FakeLLMProvider(["Resumo."])
    # Não deve levantar exceção mesmo sem nenhuma Reuniao com esse bot_id.
    recall_webhook_service.processar_evento(db_session, llm, {"bot_id": "bot-inexistente", "transcript": "texto"})


def test_processar_evento_ignora_payload_sem_transcricao(db_session) -> None:
    llm = FakeLLMProvider(["Resumo."])
    recall_webhook_service.processar_evento(db_session, llm, {"bot_id": "bot-123"})
    assert llm.chamadas == []
