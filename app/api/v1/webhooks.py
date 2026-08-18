from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_llm_provider, get_payment_provider, resolver_whatsapp_provider
from app.core.config import settings
from app.llm.base import LLMProvider
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.models.decisor import Decisor
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.payment.base import PaymentProvider
from app.schemas.reputacao import RegistrarEventoReputacaoRequestSchema, SaudeCanalSchema
from app.schemas.whatsapp import WebhookEmailRequestSchema, WebhookWhatsAppRequestSchema
from app.services import (
    optout_service,
    pagamento_licenca_service,
    qualificacao_service,
    rastreamento_service,
    reputacao_service,
    resposta_service,
)
from app.services.errors import NaoAutorizado, NaoEncontrado

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_PALAVRAS_OPTOUT = {"sair", "parar", "stop", "cancelar"}


def _whatsapp_provider_do_webhook_whatsapp(
    dados: WebhookWhatsAppRequestSchema, db: Session = Depends(get_db)
) -> WhatsAppProvider:
    """Wrapper testável (`app.dependency_overrides`) em torno de
    `resolver_whatsapp_provider` — webhook público (Meta chamando, sem
    JWT), então o tenant vem do próprio corpo da requisição, não de
    `Depends(get_tenant_id)` (que exigiria usuário autenticado)."""
    return resolver_whatsapp_provider(dados.tenant_id, db)


def _whatsapp_provider_do_webhook_email(
    dados: WebhookEmailRequestSchema, db: Session = Depends(get_db)
) -> WhatsAppProvider:
    return resolver_whatsapp_provider(dados.tenant_id, db)


def _processar_mensagem_whatsapp(
    db: Session,
    llm: LLMProvider,
    whatsapp: WhatsAppProvider,
    tenant_id: str,
    telefone: str,
    texto: str,
) -> dict:
    """Núcleo comum aos dois formatos de entrada de webhook (schema
    simplificado dos testes e payload nativo da Meta): opt-out por
    palavra-chave (E9-H2), resposta que interrompe a cadência (E3-H3) e
    alimenta a conversa de qualificação S.H.A.R.K. (E5-H1)."""
    decisor = db.query(Decisor).filter_by(tenant_id=tenant_id, telefone=telefone).first()
    if decisor is None:
        raise NaoEncontrado("Decisor não encontrado para este telefone.")

    if texto.strip().lower() in _PALAVRAS_OPTOUT:
        return optout_service.processar(db, tenant_id, decisor.id, origem="whatsapp")

    resultado_resposta = resposta_service.marcar_resposta(db, tenant_id, decisor.id)
    resultado_qualificacao = qualificacao_service.processar_mensagem_recebida(
        db, tenant_id, decisor.id, "whatsapp", texto, llm, whatsapp
    )
    return {**resultado_resposta, **resultado_qualificacao}


@router.post("/whatsapp")
def webhook_whatsapp(
    dados: WebhookWhatsAppRequestSchema,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    whatsapp: WhatsAppProvider = Depends(_whatsapp_provider_do_webhook_whatsapp),
) -> dict:
    """Schema simplificado (`tenant_id` explícito) usado pela suíte de
    testes e por chamadas internas — a Meta nunca chama esta rota
    diretamente, ver `/whatsapp/meta` abaixo para o formato real."""
    return _processar_mensagem_whatsapp(db, llm, whatsapp, dados.tenant_id, dados.telefone, dados.texto)


@router.get("/whatsapp/meta")
def verificar_webhook_whatsapp_meta(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> Response:
    """Handshake que a Meta dispara uma única vez ao salvar a Callback URL
    em Step 2 (Production setup) — precisa ecoar `hub.challenge` em texto
    puro se `hub.verify_token` bater com o configurado, senão 403."""
    if hub_mode != "subscribe" or not settings.whatsapp_webhook_verify_token:
        raise NaoAutorizado("Verify token inválido.")
    if hub_verify_token != settings.whatsapp_webhook_verify_token:
        raise NaoAutorizado("Verify token inválido.")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/whatsapp/meta")
async def receber_webhook_whatsapp_meta(
    request: Request,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> dict:
    """Payload real do WhatsApp Cloud API (`entry[].changes[].value`) —
    bem diferente do schema simplificado de `/whatsapp` acima. O tenant é
    resolvido pelo `phone_number_id` que recebeu a mensagem
    (`ConfiguracaoWhatsApp`), já que o payload nativo da Meta não carrega
    `tenant_id`. Mensagens chegando no número compartilhado legado (sem
    linha própria em `ConfiguracaoWhatsApp`) são ignoradas — não dá pra
    saber de qual tenant é sem ambiguidade. Remetente desconhecido
    (não é um `Decisor` rastreado) também é ignorado, não é erro: gente
    de fora do CRM pode mandar mensagem pro número a qualquer momento."""
    corpo = await request.json()
    for entrada in corpo.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            phone_number_id = valor.get("metadata", {}).get("phone_number_id")
            if not phone_number_id:
                continue
            config = db.query(ConfiguracaoWhatsApp).filter_by(phone_number_id=phone_number_id).one_or_none()
            if config is None:
                continue
            whatsapp = resolver_whatsapp_provider(config.tenant_id, db)
            for mensagem in valor.get("messages", []):
                telefone = mensagem.get("from")
                texto = mensagem.get("text", {}).get("body")
                if not telefone or not texto:
                    continue
                try:
                    _processar_mensagem_whatsapp(db, llm, whatsapp, config.tenant_id, telefone, texto)
                except NaoEncontrado:
                    continue
    return {"recebido": True}


@router.post("/email")
def webhook_email(
    dados: WebhookEmailRequestSchema,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    whatsapp: WhatsAppProvider = Depends(_whatsapp_provider_do_webhook_email),
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


@router.post("/mercadopago")
def webhook_mercadopago(
    request: Request,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    x_signature: str | None = Header(None, alias="x-signature"),
    x_request_id: str | None = Header(None, alias="x-request-id"),
) -> dict:
    """Callback do Mercado Pago confirmando (ou não) o pagamento de uma
    licença (cadastro self-service com escolha de plano, raio-X de
    produção). A assinatura é validada **antes** de qualquer
    processamento — sem isso, qualquer um poderia forjar um "aprovado" e
    ganhar licença de graça (ver
    `pagamento_licenca_service.verificar_assinatura_webhook`)."""
    payment_id = request.query_params.get("data.id") or request.query_params.get("id")
    if not pagamento_licenca_service.verificar_assinatura_webhook(
        x_signature, x_request_id, payment_id, settings.mercadopago_webhook_secret
    ):
        raise NaoAutorizado("Assinatura do webhook inválida.")

    if payment_id:
        pagamento_licenca_service.confirmar_via_webhook(db, payment_provider, payment_id)
    return {"recebido": True}
