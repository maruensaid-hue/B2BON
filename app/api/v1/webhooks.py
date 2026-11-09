import hashlib
import hmac
import json
import logging
import re

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    get_email_provider,
    get_fiscal_provider,
    get_llm_provider,
    get_payment_provider,
    get_plan_limits_provider,
    resolver_email_provider,
    resolver_whatsapp_provider,
)
from app.contexts.enriquecimento import contract as enriquecimento
from app.contexts.finops import contract as finops
from app.core.config import settings
from app.db import rls
from app.llm.base import LLMProvider
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp, hash_phone_number_id
from app.models.decisor import Decisor
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.channels.whatsapp.meta import telefone_para_meta
from app.providers.fiscal.base import FiscalProvider
from app.providers.payment.base import PaymentProvider
from app.schemas.reputacao import RegistrarEventoReputacaoRequestSchema, SaudeCanalSchema
from app.schemas.whatsapp import WebhookEmailRequestSchema, WebhookWhatsAppRequestSchema
from app.services import (
    conversa_comercial_service,
    email_direto_service,
    optout_service,
    pagamento_licenca_service,
    qualificacao_service,
    rastreamento_service,
    recall_webhook_service,
    reputacao_service,
    resposta_service,
    sendgrid_webhook_service,
)
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _exigir_segredo_interno(x_webhook_secret: str | None = Header(None)) -> None:
    """Endpoints internos (o `tenant_id` vem do corpo e nenhum provedor os chama): sem segredo configurado ou com segredo
    errado ficam inacessíveis. Antes estavam abertos — qualquer pessoa com um `tenant_id` podia forjar resposta/opt-out de um
    decisor, disparar IA e mensagens de WhatsApp do tenant ou empurrar a pausa automática de um canal."""
    esperado = settings.webhook_interno_secret
    if not esperado or not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, esperado):
        raise NaoAutorizado("Segredo de webhook interno ausente ou inválido.")


def assinatura_meta_valida(corpo: bytes, cabecalho: str | None, app_secret: str) -> bool:
    """`X-Hub-Signature-256: sha256=<hmac-sha256 hex do corpo bruto com o App Secret>`. Sem segredo ou sem cabeçalho: inválida."""
    if not app_secret or not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(cabecalho[len("sha256="):], esperado)

_PALAVRAS_OPTOUT = {"sair", "parar", "stop", "cancelar"}


def _whatsapp_provider_do_webhook_whatsapp(
    dados: WebhookWhatsAppRequestSchema, db: Session = Depends(get_db)
) -> WhatsAppProvider:
    """Wrapper testável (`app.dependency_overrides`) em torno de
    `resolver_whatsapp_provider` — webhook público (Meta chamando, sem
    JWT), então o tenant vem do próprio corpo da requisição, não de
    `Depends(get_tenant_id)` (que exigiria usuário autenticado)."""
    rls.definir_tenant(db, dados.tenant_id)  # rota interna: o segredo já foi conferido (dependência da rota); o tenant vem do chamador interno
    return resolver_whatsapp_provider(dados.tenant_id, db)


def _whatsapp_provider_do_webhook_email(
    dados: WebhookEmailRequestSchema, db: Session = Depends(get_db)
) -> WhatsAppProvider:
    rls.definir_tenant(db, dados.tenant_id)
    return resolver_whatsapp_provider(dados.tenant_id, db)


def _texto_da_mensagem(mensagem: dict) -> str | None:
    """Texto digitado, ou o rótulo do botão tocado (resposta rápida de um modelo ou mensagem interativa)."""
    return (
        (mensagem.get("text") or {}).get("body")
        or (mensagem.get("button") or {}).get("text")
        or ((mensagem.get("interactive") or {}).get("button_reply") or {}).get("title")
    )


def _decisor_pelo_telefone(db: Session, tenant_id: str, telefone: str) -> Decisor | None:
    """A Meta manda o remetente só com dígitos e com o código do país ("5511993495349"); o contato pode estar cadastrado de qualquer jeito
    ("11993495349", "(11) 99349-5349", "+55 11 99349-5349"). A comparação exata nunca achava ninguém (visto em produção em 09/11/2026).
    Compara pela mesma forma que o envio usa (`telefone_para_meta`), filtrando antes pelos últimos 4 dígitos para não ler a base toda."""
    alvo = telefone_para_meta(telefone)
    if len(alvo) < 8:
        return None
    candidatos = (
        db.query(Decisor)
        .filter(Decisor.tenant_id == tenant_id, Decisor.telefone.isnot(None), Decisor.telefone.like(f"%{alvo[-4:]}"))
        .order_by(Decisor.id)
        .all()
    )
    for candidato in candidatos:
        if telefone_para_meta(candidato.telefone) == alvo:
            return candidato
    # Celular brasileiro: a Meta às vezes entrega o remetente sem o nono dígito (55 + DDD + 8 dígitos).
    if alvo.startswith("55") and len(alvo) == 12:
        com_nove = f"{alvo[:4]}9{alvo[4:]}"
        for candidato in candidatos:
            if telefone_para_meta(candidato.telefone) == com_nove:
                return candidato
    return None


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
    decisor = _decisor_pelo_telefone(db, tenant_id, telefone)
    if decisor is None:
        raise NaoEncontrado("Decisor não encontrado para este telefone.")

    if texto.strip().lower() in _PALAVRAS_OPTOUT:
        return optout_service.processar(db, tenant_id, decisor.id, origem="whatsapp")
    lida = resposta_service.ler_resposta(db, tenant_id, decisor, texto, "whatsapp")
    if lida is not None:  # descadastro escrito ou reclamação: sem resposta automática
        return lida

    resultado_resposta = resposta_service.marcar_resposta(db, tenant_id, decisor.id)
    resultado_qualificacao = qualificacao_service.processar_mensagem_recebida(
        db, tenant_id, decisor.id, "whatsapp", texto, llm, whatsapp
    )
    conversa = conversa_comercial_service.apos_resposta(db, tenant_id, decisor, texto, "whatsapp", llm, get_plan_limits_provider(db))
    return {**resultado_resposta, **resultado_qualificacao, "conversa_comercial": conversa}


@router.post("/whatsapp", dependencies=[Depends(_exigir_segredo_interno)])
def webhook_whatsapp(
    dados: WebhookWhatsAppRequestSchema,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    whatsapp: WhatsAppProvider = Depends(_whatsapp_provider_do_webhook_whatsapp),
) -> dict:
    """Schema simplificado (`tenant_id` explícito) usado pela suíte de
    testes e por chamadas internas — a Meta nunca chama esta rota
    diretamente, ver `/whatsapp/meta` abaixo para o formato real."""
    rls.definir_tenant(db, dados.tenant_id)  # rota interna (segredo conferido pela dependência da rota); repete aqui porque os testes substituem o provider
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
    corpo_bruto = await request.body()
    if not assinatura_meta_valida(corpo_bruto, request.headers.get("x-hub-signature-256"), settings.whatsapp_app_secret):
        raise NaoAutorizado("Assinatura do webhook inválida.")
    corpo = json.loads(corpo_bruto or b"{}")
    for entrada in corpo.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            phone_number_id = valor.get("metadata", {}).get("phone_number_id")
            if not phone_number_id:
                continue
            chave_numero = hash_phone_number_id(str(phone_number_id))
            with rls.contexto_busca(db, rls.ESCOPO_WHATSAPP_NUMERO, chave_numero):  # o número que recebeu a mensagem diz de qual tenant ela é
                config = db.query(ConfiguracaoWhatsApp).filter_by(phone_number_id_hash=chave_numero).one_or_none()
            mensagens = valor.get("messages", [])
            # Sem telefone nem texto no log (dado pessoal): só o suficiente para saber o que chegou e o que foi feito.
            logger.warning(
                "WEBHOOK_WHATSAPP campo=%s tenant=%s mensagens=%s tipos=%s status=%s",
                mudanca.get("field"), config.tenant_id if config else "desconhecido", len(mensagens),
                ",".join(sorted({str(m.get("type")) for m in mensagens})) or "-",
                ",".join(sorted({str(st.get("status")) for st in valor.get("statuses", [])})) or "-",
            )
            if config is None:
                continue
            rls.definir_tenant(db, config.tenant_id)
            whatsapp = resolver_whatsapp_provider(config.tenant_id, db)
            for mensagem in mensagens:
                telefone = mensagem.get("from")
                texto = _texto_da_mensagem(mensagem)
                if not telefone or not texto:
                    logger.warning("WEBHOOK_WHATSAPP_IGNORADA tenant=%s tipo=%s (sem texto)", config.tenant_id, mensagem.get("type"))
                    continue
                try:
                    resultado = _processar_mensagem_whatsapp(db, llm, whatsapp, config.tenant_id, telefone, texto)
                except NaoEncontrado:
                    logger.warning("WEBHOOK_WHATSAPP_REMETENTE_DESCONHECIDO tenant=%s (telefone não bate com nenhum contato)", config.tenant_id)
                    continue
                logger.warning("WEBHOOK_WHATSAPP_TRATADA tenant=%s resultado=%s", config.tenant_id, sorted((resultado or {}).keys()))
    return {"recebido": True}


@router.post("/email", dependencies=[Depends(_exigir_segredo_interno)])
def webhook_email(
    dados: WebhookEmailRequestSchema,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    whatsapp: WhatsAppProvider = Depends(_whatsapp_provider_do_webhook_email),
) -> dict:
    """Integração de inbound-parse do ESP — resposta de e-mail interrompe a
    cadência em todos os canais (E3-H3) e alimenta a qualificação (E5-H1)."""
    rls.definir_tenant(db, dados.tenant_id)  # rota interna (segredo conferido pela dependência da rota)
    decisor = db.query(Decisor).filter_by(tenant_id=dados.tenant_id, email=dados.email).first()
    if decisor is None:
        raise NaoEncontrado("Decisor não encontrado para este e-mail.")
    lida = resposta_service.ler_resposta(db, dados.tenant_id, decisor, dados.texto, "email")
    if lida is not None:  # descadastro escrito ou reclamação: sem resposta automática
        return lida

    resultado_resposta = resposta_service.marcar_resposta(db, dados.tenant_id, decisor.id)
    resultado_qualificacao = qualificacao_service.processar_mensagem_recebida(
        db, dados.tenant_id, decisor.id, "email", dados.texto, llm, whatsapp
    )
    conversa = conversa_comercial_service.apos_resposta(db, dados.tenant_id, decisor, dados.texto, "email", llm, get_plan_limits_provider(db))
    return {**resultado_resposta, **resultado_qualificacao, "conversa_comercial": conversa}


_PADRAO_TOKEN_RESPOSTA = re.compile(r"resp\+([^@]+)@")
_PADRAO_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _extrair_token_resposta(campo_to: str) -> str | None:
    """`to` do Inbound Parse pode vir como `"resp+TOKEN@dominio"` ou
    `"Nome <resp+TOKEN@dominio>"` — extrai só o token do local-part."""
    correspondencia = _PADRAO_TOKEN_RESPOSTA.search(campo_to)
    return correspondencia.group(1) if correspondencia else None


def _extrair_email(campo_from: str) -> str:
    """`from` do Inbound Parse pode vir como `"Fulano <fulano@x.com>"` —
    extrai só o endereço; sem match, devolve o campo bruto (nunca quebra
    por causa de um formato inesperado)."""
    correspondencia = _PADRAO_EMAIL.search(campo_from)
    return correspondencia.group(0) if correspondencia else campo_from


@router.post("/email/inbound")
async def webhook_email_inbound(request: Request, db: Session = Depends(get_db)) -> dict:
    """SendGrid Inbound Parse (raio-X 2026-09-24, Webmail — caixa de
    entrada) — resposta de um cliente a um `EmailDireto` cujo reply-to
    foi trocado pro endereço de resposta nosso (`resposta_service.
    gerar_token_resposta`, ativo só quando `settings.dominio_respostas`
    está configurado). Sempre responde 200 mesmo com token
    inválido/expirado — o SendGrid re-tenta indefinidamente em erro, e
    um token velho (ex.: decisor já excluído) não é motivo pra isso."""
    formulario = await request.form()
    token = _extrair_token_resposta(str(formulario.get("to", "")))
    if token is None:
        return {"recebido": True, "processado": False}
    try:
        tenant_id, decisor_id = resposta_service.validar_token_resposta(token)
    except ValidacaoFalhou:
        return {"recebido": True, "processado": False}

    rls.definir_tenant(db, tenant_id)  # o tenant vem do token assinado (HMAC) do endereço de resposta
    remetente_email = _extrair_email(str(formulario.get("from", "")))
    assunto = str(formulario.get("subject", ""))
    corpo = str(formulario.get("text", ""))

    email_provider = resolver_email_provider(tenant_id, db)
    email_direto_service.processar_recebido(
        db, tenant_id, decisor_id, remetente_email, assunto, corpo, email_provider,
        llm=get_llm_provider(db), plan_limits=get_plan_limits_provider(db),
    )
    return {"recebido": True, "processado": True}


@router.get("/email/aberto/{token}.png")
def registrar_abertura_email(token: str, db: Session = Depends(get_db)) -> Response:
    """Pixel de rastreio de abertura (Onda I) — carregado pelo cliente de
    e-mail do destinatário, nunca por uma pessoa. Token inválido/expirado
    não derruba a imagem, só não registra nada (ver rastreamento_service)."""
    rastreamento_service.registrar_abertura(db, token)
    return Response(content=rastreamento_service.PIXEL_PNG_1X1, media_type="image/png")


@router.post("/reputacao", response_model=SaudeCanalSchema, dependencies=[Depends(_exigir_segredo_interno)])
def webhook_reputacao(dados: RegistrarEventoReputacaoRequestSchema, db: Session = Depends(get_db)) -> SaudeCanalSchema:
    """Callback do ESP/Meta com eventos de entregabilidade — dispara pausa
    automática de canal ao cruzar o limiar crítico (E10-H2)."""
    rls.definir_tenant(db, dados.tenant_id)  # rota interna (segredo conferido); o tenant vem do chamador interno
    return SaudeCanalSchema(
        **reputacao_service.registrar_evento(db, dados.tenant_id, dados.canal, dados.tipo_evento, dados.quantidade)
    )


@router.post("/envio/eventos")  # mesmo tratamento sob um endereço sem o nome do fornecedor, o que o cliente cola no serviço de envio dele
@router.post("/sendgrid/eventos")
async def webhook_sendgrid_eventos(request: Request, db: Session = Depends(get_db)) -> dict:
    """Event Webhook do SendGrid (delivered/bounce/dropped/spamreport)
    alimentando `reputacao_service` de verdade (raio-X de produção — antes
    só chegava evento via `/reputacao` chamado manualmente em teste).
    Assinatura verificada **antes** de processar qualquer coisa, mesmo
    raciocínio do webhook do Mercado Pago: sem isso, qualquer um poderia
    forjar bounce/spam em massa e pausar o canal de e-mail de um tenant."""
    corpo = await request.body()
    processado = sendgrid_webhook_service.autenticar_e_processar(
        db,
        corpo,
        request.headers.get("x-twilio-email-event-webhook-signature"),
        request.headers.get("x-twilio-email-event-webhook-timestamp"),
        settings.sendgrid_webhook_verification_key,
    )
    if not processado:
        raise NaoAutorizado("Assinatura do webhook inválida.")
    return {"recebido": True}


@router.post("/recall/eventos")
async def webhook_recall_eventos(
    request: Request, db: Session = Depends(get_db), llm: LLMProvider = Depends(get_llm_provider)
) -> dict:
    """Callback do bot de reunião/transcrição de terceiro (raio-X: vídeo +
    transcrição — tipo Recall.ai) quando a transcrição fica pronta. Mesmo
    raciocínio dos outros webhooks assinados deste arquivo: assinatura
    verificada **antes** de tocar no corpo, senão qualquer um poderia
    forjar uma transcrição falsa pra uma reunião."""
    corpo = await request.body()
    assinatura_valida = recall_webhook_service.verificar_assinatura(
        corpo, request.headers.get("x-recall-signature"), settings.recall_webhook_secret
    )
    if not assinatura_valida:
        raise NaoAutorizado("Assinatura do webhook inválida.")

    recall_webhook_service.processar_evento(db, llm, json.loads(corpo))
    return {"recebido": True}


@router.post("/mercadopago")
def webhook_mercadopago(
    request: Request,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    email: EmailProvider = Depends(get_email_provider),
    fiscal: FiscalProvider = Depends(get_fiscal_provider),
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
        pagamento_licenca_service.confirmar_via_webhook(db, payment_provider, payment_id, email)
        finops.compras.confirmar_via_webhook(db, payment_provider, payment_id)  # top-up de AI Credits
        enriquecimento.pacotes.confirmar_via_webhook(db, payment_provider, payment_id, fiscal=fiscal)  # pacote adicional de créditos de enriquecimento
    return {"recebido": True}
