import hashlib
import hmac
import json
from datetime import datetime

from app.core.config import settings
from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.reuniao import Reuniao

TENANT_ID = "tenant-teste"
SEGREDO = "segredo-de-teste-recall"


def _assinar(payload: bytes, segredo: str = SEGREDO) -> str:
    return hmac.new(segredo.encode(), payload, hashlib.sha256).hexdigest()


def _criar_reuniao_com_bot(db_session, bot_id: str = "bot-123") -> Reuniao:
    conta = Conta(tenant_id=TENANT_ID, nome="Empresa Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    db_session.flush()
    reuniao = Reuniao(
        tenant_id=TENANT_ID, conta_id=conta.id, decisor_id=decisor.id, vendedor_id="1",
        data_hora=datetime(2026, 9, 1, 14, 0), status="agendada", bot_id=bot_id, origem_crm_id="99",
    )
    db_session.add(reuniao)
    db_session.commit()
    return reuniao


def test_evento_com_assinatura_valida_alimenta_conta_e_negocio(client, db_session, monkeypatch, fake_llm) -> None:
    monkeypatch.setattr(settings, "recall_webhook_secret", SEGREDO)
    reuniao = _criar_reuniao_com_bot(db_session)
    fake_llm.definir_respostas(["Resumo: cliente confirmou interesse, próximo passo é enviar proposta."])

    payload = json.dumps({"bot_id": reuniao.bot_id, "transcript": "conteúdo bruto da transcrição"}).encode()
    resposta = client.post(
        "/api/v1/webhooks/recall/eventos",
        content=payload,
        headers={"content-type": "application/json", "x-recall-signature": _assinar(payload)},
    )

    assert resposta.status_code == 200
    db_session.refresh(reuniao)
    assert reuniao.status_transcricao == "concluida"

    atividade = db_session.query(Atividade).filter_by(tenant_id=TENANT_ID, tipo="reuniao").one()
    assert atividade.conta_id == reuniao.conta_id
    assert atividade.negocio_id == 99
    assert "próximo passo" in atividade.descricao


def test_assinatura_invalida_e_rejeitada_com_403(client, db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "recall_webhook_secret", SEGREDO)
    reuniao = _criar_reuniao_com_bot(db_session)

    resposta = client.post(
        "/api/v1/webhooks/recall/eventos",
        content=json.dumps({"bot_id": reuniao.bot_id, "transcript": "texto"}).encode(),
        headers={"content-type": "application/json", "x-recall-signature": "assinatura-forjada"},
    )

    assert resposta.status_code == 403


def test_sem_segredo_configurado_rejeita_qualquer_chamada(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "recall_webhook_secret", "")

    resposta = client.post(
        "/api/v1/webhooks/recall/eventos",
        content=b"{}",
        headers={"content-type": "application/json"},
    )

    assert resposta.status_code == 403
