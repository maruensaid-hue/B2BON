import hashlib
import hmac

from sqlalchemy.orm import Session

from app.db import rls
from app.llm.base import LLMProvider
from app.models.reuniao import Reuniao
from app.services import meeting_bot_service


def verificar_assinatura(payload: bytes, assinatura: str | None, segredo: str) -> bool:
    """HMAC-SHA256 sobre o corpo bruto, com o segredo compartilhado
    (`settings.recall_webhook_secret`) — mesmo raciocínio do webhook do
    Mercado Pago: sem isso, qualquer um poderia forjar uma "transcrição"
    falsa e escrever lixo na conta/oportunidade de um tenant. Raio-X: o
    header exato e o algoritmo precisam ser conferidos contra a doc real
    do fornecedor escolhido — HMAC-SHA256 é o padrão mais comum pra esse
    tipo de callback, mas ainda não foi validado contra uma conta real."""
    if not assinatura or not segredo:
        return False
    esperado = hmac.new(segredo.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura)


def processar_evento(db: Session, llm: LLMProvider, payload: dict) -> None:
    """Raio-X: o formato exato do payload (nome dos campos de `bot_id` e do
    texto da transcrição) precisa ser conferido contra a doc real do
    fornecedor — aqui assume `bot_id` e `transcript` no nível raiz, os
    nomes mais prováveis pra esse tipo de callback. Evento sem `bot_id`
    reconhecido (reunião não encontrada) é ignorado, não é erro — pode ser
    um evento de um bot de outro ambiente/teste."""
    bot_id = payload.get("bot_id")
    texto_transcricao = payload.get("transcript")
    if not bot_id or not texto_transcricao:
        return

    with rls.contexto_busca(db, rls.ESCOPO_RECALL_BOT, str(bot_id)):
        reuniao = db.query(Reuniao).filter_by(bot_id=bot_id).one_or_none()
    if reuniao is None:
        return
    rls.definir_tenant(db, reuniao.tenant_id)  # a reunião diz de qual tenant é a transcrição (assinatura do webhook já conferida)

    meeting_bot_service.processar_transcricao(db, reuniao, llm, texto_transcricao)
