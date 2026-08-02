import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import LLMProvider
from app.models.alerta_detrator import AlertaDetrator
from app.models.configuracao_notificacao import ConfiguracaoNotificacao
from app.models.configuracao_nps import ConfiguracaoNps
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.pesquisa_nps import PesquisaNps
from app.models.reuniao import Reuniao
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.services import auditoria_service, indicacao_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

_SEPARADOR = ":"

# Definição internacional do Net Promoter Score — não é decisão comercial
# configurável (mesmo raciocínio de `scoring_service.ETAPAS`).
NPS_PROMOTOR_MINIMO = 9
NPS_DETRATOR_MAXIMO = 6


def gerar_token(tenant_id: str, pesquisa_id: int) -> str:
    payload = f"{tenant_id}{_SEPARADOR}{pesquisa_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR}{assinatura}"


def _validar_token(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de pesquisa NPS inválido.")
    tenant_id, pesquisa_id_str, assinatura = partes
    try:
        pesquisa_id = int(pesquisa_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de pesquisa NPS inválido.") from erro

    esperado = gerar_token(tenant_id, pesquisa_id).rsplit(_SEPARADOR, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de pesquisa NPS inválido.")
    return tenant_id, pesquisa_id


def obter_configuracao(db: Session, tenant_id: str) -> ConfiguracaoNps:
    config = db.query(ConfiguracaoNps).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        return ConfiguracaoNps(tenant_id=tenant_id, dias_apos_reuniao_realizada=settings.nps_dias_apos_reuniao_padrao)
    return config


def definir_configuracao(db: Session, tenant_id: str, dias_apos_reuniao_realizada: int) -> ConfiguracaoNps:
    config = db.query(ConfiguracaoNps).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        config = ConfiguracaoNps(tenant_id=tenant_id, dias_apos_reuniao_realizada=dias_apos_reuniao_realizada)
        db.add(config)
    else:
        config.dias_apos_reuniao_realizada = dias_apos_reuniao_realizada
    db.commit()
    db.refresh(config)
    return config


def _enviar_pesquisa(db: Session, tenant_id: str, pesquisa: PesquisaNps, decisor: Decisor, whatsapp, email) -> None:
    link = f"Responda de 0 a 10: qual a probabilidade de você nos indicar? {gerar_token(tenant_id, pesquisa.id)}"
    if decisor.telefone:
        whatsapp.enviar_texto_livre(decisor.telefone, link)
    elif decisor.email:
        email.enviar(decisor.email, "Sua opinião é muito importante", link, "PREDATOR", "no-reply@predator.local")


def disparar_pendentes(db: Session, tenant_id: str, whatsapp: WhatsAppProvider, email: EmailProvider) -> dict:
    """Disparo de NPS configurável por marco — dias após a reunião ser
    realizada (E11-H1). Dispatcher explícito, mesmo padrão de
    `envio_service.processar_pendentes`/`reuniao_service.processar_lembretes`."""
    config = obter_configuracao(db, tenant_id)
    limite = datetime.now(UTC) - timedelta(days=config.dias_apos_reuniao_realizada)

    reunioes = db.query(Reuniao).filter_by(tenant_id=tenant_id, status="realizada").all()
    disparadas = 0
    for reuniao in reunioes:
        if reuniao.criado_em.replace(tzinfo=UTC) > limite:
            continue
        ja_existe = (
            db.query(PesquisaNps)
            .filter_by(tenant_id=tenant_id, conta_id=reuniao.conta_id, decisor_id=reuniao.decisor_id, marco="dias_apos_reuniao")
            .one_or_none()
        )
        if ja_existe is not None:
            continue

        decisor = db.query(Decisor).filter_by(id=reuniao.decisor_id).one()
        pesquisa = PesquisaNps(
            tenant_id=tenant_id, conta_id=reuniao.conta_id, decisor_id=reuniao.decisor_id, marco="dias_apos_reuniao"
        )
        db.add(pesquisa)
        db.flush()
        _enviar_pesquisa(db, tenant_id, pesquisa, decisor, whatsapp, email)
        auditoria_service.registrar(
            db, tenant_id, "nps_disparado", "pesquisa_nps", pesquisa.id, None, {"marco": "dias_apos_reuniao"}, conta_id=reuniao.conta_id
        )
        disparadas += 1

    db.commit()
    return {"pesquisas_disparadas": disparadas}


def marcar_entrega_concluida(
    db: Session, tenant_id: str, ator_id: str | None, decisor_id: int, whatsapp: WhatsAppProvider, email: EmailProvider
) -> PesquisaNps:
    """Segundo marco do E11-H1 — gatilho manual de "entrega concluída"."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    pesquisa = PesquisaNps(
        tenant_id=tenant_id, conta_id=decisor.conta_id, decisor_id=decisor.id, marco="entrega_concluida"
    )
    db.add(pesquisa)
    db.flush()
    _enviar_pesquisa(db, tenant_id, pesquisa, decisor, whatsapp, email)
    auditoria_service.registrar(
        db, tenant_id, "nps_disparado", "pesquisa_nps", pesquisa.id, ator_id, {"marco": "entrega_concluida"}, conta_id=decisor.conta_id
    )
    db.commit()
    db.refresh(pesquisa)
    return pesquisa


def _classificar(nota: int) -> str:
    if nota >= NPS_PROMOTOR_MINIMO:
        return "promotor"
    if nota <= NPS_DETRATOR_MAXIMO:
        return "detrator"
    return "neutro"


def _sugestao_acao(nota: int) -> str:
    if nota <= 3:
        return "Contato imediato do Gestor Comercial em até 24h — risco alto de cancelamento."
    return "Agendar ligação de recuperação e revisar as pendências recentes do cliente."


def _gerar_alerta_detrator(db: Session, tenant_id: str, pesquisa: PesquisaNps, whatsapp: WhatsAppProvider) -> AlertaDetrator:
    sugestao = _sugestao_acao(pesquisa.nota)
    alerta = AlertaDetrator(
        tenant_id=tenant_id,
        pesquisa_nps_id=pesquisa.id,
        conta_id=pesquisa.conta_id,
        decisor_id=pesquisa.decisor_id,
        nota=pesquisa.nota,
        sugestao_acao=sugestao,
    )
    db.add(alerta)
    db.flush()

    config = db.query(ConfiguracaoNotificacao).filter_by(tenant_id=tenant_id).one_or_none()
    if config and config.vendedor_telefone:
        whatsapp.enviar_texto_livre(
            config.vendedor_telefone, f"Detrator identificado (nota {pesquisa.nota}). {sugestao}"
        )

    auditoria_service.registrar(
        db, tenant_id, "alerta_detrator_criado", "alerta_detrator", alerta.id, None, {"nota": pesquisa.nota}, conta_id=pesquisa.conta_id
    )
    return alerta


def obter_por_token(db: Session, token: str) -> PesquisaNps:
    tenant_id, pesquisa_id = _validar_token(token)
    pesquisa = db.query(PesquisaNps).filter_by(id=pesquisa_id, tenant_id=tenant_id).one_or_none()
    if pesquisa is None:
        raise NaoEncontrado(f"Pesquisa NPS {pesquisa_id} não encontrada")
    return pesquisa


def responder(db: Session, token: str, nota: int, whatsapp: WhatsAppProvider, llm: LLMProvider) -> PesquisaNps:
    """Resposta pública à pesquisa (link/token, endpoint sem X-Tenant-Id).

    Classificação promotor/neutro/detrator é registrada na pesquisa e na
    conta (E11-H1). Detrator gera alerta imediato; promotor (nota >= 9)
    dispara o pedido de indicação (E11-H2) — nunca para quem não está
    encantado.
    """
    tenant_id, pesquisa_id = _validar_token(token)
    if not (0 <= nota <= 10):
        raise ValidacaoFalhou("Nota de NPS deve estar entre 0 e 10.")

    pesquisa = db.query(PesquisaNps).filter_by(id=pesquisa_id, tenant_id=tenant_id).one_or_none()
    if pesquisa is None:
        raise NaoEncontrado(f"Pesquisa NPS {pesquisa_id} não encontrada")

    pesquisa.nota = nota
    pesquisa.classificacao = _classificar(nota)
    pesquisa.respondida_em = datetime.now(UTC)

    conta = db.query(Conta).filter_by(id=pesquisa.conta_id).one()
    conta.nps_nota = nota
    conta.nps_classificacao = pesquisa.classificacao

    auditoria_service.registrar(
        db, tenant_id, "nps_respondida", "pesquisa_nps", pesquisa.id, None, {"nota": nota, "classificacao": pesquisa.classificacao}, conta_id=conta.id
    )

    if pesquisa.classificacao == "detrator":
        _gerar_alerta_detrator(db, tenant_id, pesquisa, whatsapp)
    elif pesquisa.classificacao == "promotor":
        indicacao_service.solicitar(db, tenant_id, pesquisa, llm)

    db.commit()
    db.refresh(pesquisa)
    return pesquisa
