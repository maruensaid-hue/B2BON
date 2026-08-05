from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_llm_provider, get_whatsapp_provider
from app.llm.base import LLMProvider
from app.models.decisor import Decisor
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.schemas.reputacao import RegistrarEventoReputacaoRequestSchema, SaudeCanalSchema
from app.schemas.whatsapp import WebhookEmailRequestSchema, WebhookWhatsAppRequestSchema
from app.services import optout_service, qualificacao_service, rastreamento_service, reputacao_service, resposta_service
from app.services.errors import NaoEncontrado

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_PALAVRAS_OPTOUT = {"sair", "parar", "stop", "cancelar"}


@router.post("/whatsapp")
def webhook_whatsapp(
    dados: WebhookWhatsAppRequestSchema,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
) -> dict:
    """Mensagem recebida do prospect: opt-out por palavra-chave (E9-H2),
    resposta que interrompe a cadência (E3-H3) e alimenta a conversa de
    qualificação S.H.A.R.K. (E5-H1)."""
    decisor = db.query(Decisor).filter_by(tenant_id=dados.tenant_id, telefone=dados.telefone).first()
    if decisor is None:
        raise NaoEncontrado("Decisor não encontrado para este telefone.")

    if dados.texto.strip().lower() in _PALAVRAS_OPTOUT:
        return optout_service.processar(db, dados.tenant_id, decisor.id, origem="whatsapp")

    resultado_resposta = resposta_service.marcar_resposta(db, dados.tenant_id, decisor.id)
    resultado_qualificacao = qualificacao_service.processar_mensagem_recebida(
        db, dados.tenant_id, decisor.id, "whatsapp", dados.texto, llm, whatsapp
    )
    return {**resultado_resposta, **resultado_qualificacao}


@router.post("/email")
def webhook_email(
    dados: WebhookEmailRequestSchema,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
) -> dict:
    """Integração de inbound-parse do ESP — resposta de e-mail interrompe a
    cadência em todos os canais (E3-H3) e alimenta a qualificação (E5-H1)."""
    decisor = db.query(Decisor).filter_by(tenant_id=dados.tenant_id, email=dados.email).first()
    if decisor is None:
        raise NaoEncontrado("Decisor não encontrado para este e-mail.")

    resultado_resposta = resposta_service.marcar_resposta(db, dados.tenant_id, decisor.id)
    resultado_qualificacao = qualificacao_service.processar_mensagem_recebida(
        db, dados.tenant_id, decisor.id, "email", dados.texto, llm, whatsapp
    )
    return {**resultado_resposta, **resultado_qualificacao}


@router.get("/email/aberto/{token}.png")
def registrar_abertura_email(token: str, db: Session = Depends(get_db)) -> Response:
    """Pixel de rastreio de abertura (Onda I) — carregado pelo cliente de
    e-mail do destinatário, nunca por uma pessoa. Token inválido/expirado
    não derruba a imagem, só não registra nada (ver rastreamento_service)."""
    rastreamento_service.registrar_abertura(db, token)
    return Response(content=rastreamento_service.PIXEL_PNG_1X1, media_type="image/png")


@router.post("/reputacao", response_model=SaudeCanalSchema)
def webhook_reputacao(dados: RegistrarEventoReputacaoRequestSchema, db: Session = Depends(get_db)) -> SaudeCanalSchema:
    """Callback do ESP/Meta com eventos de entregabilidade — dispara pausa
    automática de canal ao cruzar o limiar crítico (E10-H2)."""
    return SaudeCanalSchema(
        **reputacao_service.registrar_evento(db, dados.tenant_id, dados.canal, dados.tipo_evento, dados.quantidade)
    )
