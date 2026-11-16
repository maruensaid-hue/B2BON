from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auditoria import AuditLog
from app.models.bloqueio_contato import BloqueioContato
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.mensagem import Mensagem
from app.models.pausa_canal import PausaCanal
from app.models.registro_reputacao_canal import RegistroReputacaoCanal
from app.models.tenant import Tenant
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

_JANELA_DIAS = 7
_TIPOS_VALIDOS = {"enviado", "bounce", "spam_report", "recusa_spam"}
# Prefixo do motivo da pausa causada por recusas de spam: essa pausa só o super admin desfaz à mão, e ela se desfaz sozinha quando a taxa cai.
MOTIVO_PAUSA_SPAM = "recusas_spam"
# Mesmo valor de `bloqueio_contato_service.ORIGEM_EMAIL_RECUSADO_SPAM` (aquele módulo não é importado aqui para não criar ciclo).
_ORIGEM_RECUSADO_SPAM = "email_recusado_spam"


def _obter_ou_criar_registro_do_dia(db: Session, tenant_id: str, canal: str, dia: str) -> RegistroReputacaoCanal:
    registro = (
        db.query(RegistroReputacaoCanal).filter_by(tenant_id=tenant_id, canal=canal, data=dia).one_or_none()
    )
    if registro is None:
        registro = RegistroReputacaoCanal(tenant_id=tenant_id, canal=canal, data=dia)
        db.add(registro)
        db.flush()
    return registro


def _agregado_janela(db: Session, tenant_id: str, canal: str) -> tuple[int, int, int]:
    limite = (date.today() - timedelta(days=_JANELA_DIAS)).isoformat()
    registros = (
        db.query(RegistroReputacaoCanal)
        .filter(
            RegistroReputacaoCanal.tenant_id == tenant_id,
            RegistroReputacaoCanal.canal == canal,
            RegistroReputacaoCanal.data >= limite,
        )
        .all()
    )
    enviados = sum(r.enviados for r in registros)
    bounces = sum(r.bounces for r in registros)
    spam_reports = sum(r.spam_reports for r in registros)
    return enviados, bounces, spam_reports


def canal_pausado(db: Session, tenant_id: str, canal: str) -> bool:
    pausa = db.query(PausaCanal).filter_by(tenant_id=tenant_id, canal=canal, ativa=True).one_or_none()
    return pausa is not None


def _corte_recusas(db: Session, tenant_id: str) -> datetime:
    """Início da janela das recusas por spam: 7 dias atrás ou a última reativação manual do canal, o que for mais recente (depois de o super admin revisar
    e reativar, as recusas de antes não pausam o canal de novo)."""
    corte = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=_JANELA_DIAS)
    reativacao = (
        db.query(AuditLog.criado_em)
        .filter(AuditLog.tenant_id == tenant_id, AuditLog.evento_tipo == "canal_reativado_manualmente")
        .order_by(AuditLog.id.desc())
        .first()
    )
    if reativacao is not None and reativacao[0] is not None:
        momento = reativacao[0].astimezone(UTC).replace(tzinfo=None) if reativacao[0].tzinfo else reativacao[0]
        corte = max(corte, momento)
    return corte


def _emails_que_sairam(db: Session, tenant_id: str, corte: datetime) -> int:
    """E-mails de cadência e campanha que de fato saíram desde o corte, contados nos próprios envios: com conta de e-mail própria o provedor não devolve
    "entregue", e o contador agregado ficaria em zero."""
    de_cadencias = (
        db.query(Mensagem)
        .filter(Mensagem.tenant_id == tenant_id, Mensagem.canal == "email", Mensagem.status == "enviado", Mensagem.enviado_em >= corte)
        .count()
    )
    campanhas_com_email = [c.id for c in db.query(Campanha.id, Campanha.canais).filter(Campanha.tenant_id == tenant_id).all() if "email" in (c.canais or [])]
    if not campanhas_com_email:
        return de_cadencias
    de_campanhas = (
        db.query(CampanhaDestinatario)
        .filter(
            CampanhaDestinatario.tenant_id == tenant_id,
            CampanhaDestinatario.campanha_id.in_(campanhas_com_email),
            CampanhaDestinatario.status == "enviado",
            CampanhaDestinatario.email.isnot(None),
            CampanhaDestinatario.enviado_em >= corte,
        )
        .count()
    )
    return de_cadencias + de_campanhas


def saude_recusas_spam(db: Session, tenant_id: str) -> dict:
    """Recusas por spam/reputação dos últimos 7 dias: as informadas pelo usuário (aviso de falha colado no Relatório de Entrega) e as que o envio por API
    devolve ("blocked"), sobre os e-mails que saíram no mesmo período."""
    corte = _corte_recusas(db, tenant_id)
    enviados = _emails_que_sairam(db, tenant_id, corte)
    manuais = (
        db.query(BloqueioContato)
        .filter(BloqueioContato.tenant_id == tenant_id, BloqueioContato.origem == _ORIGEM_RECUSADO_SPAM, BloqueioContato.criado_em >= corte)
        .count()
    )
    do_provedor = sum(
        r.recusas_spam or 0
        for r in db.query(RegistroReputacaoCanal).filter(
            RegistroReputacaoCanal.tenant_id == tenant_id,
            RegistroReputacaoCanal.canal == "email",
            RegistroReputacaoCanal.data >= corte.date().isoformat(),
        )
    )
    recusas = manuais + do_provedor
    taxa = min(recusas / enviados, 1.0) if enviados else (1.0 if recusas else 0.0)
    if recusas and enviados >= settings.amostra_minima_reputacao and taxa >= settings.limiar_recusa_spam_pausa:
        nivel = "critico"
    elif recusas and taxa >= settings.limiar_recusa_spam_alerta:
        nivel = "alerta"
    else:
        nivel = "ok"
    tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    return {
        "recusas_spam": recusas,
        "enviados_recusas": enviados,
        "taxa_recusa_spam": taxa,
        "limiar_recusa_spam_alerta": settings.limiar_recusa_spam_alerta,
        "limiar_recusa_spam_pausa": settings.limiar_recusa_spam_pausa,
        "nivel_recusa_spam": nivel,
        "isento_pausa_spam": bool(tenant is not None and tenant.isento_pausa_spam),
    }


def definir_isencao_pausa_spam(db: Session, tenant_id: str, ator_id: str | None, isento: bool) -> Tenant:
    """Liga ou desliga a isenção da pausa por recusas de spam (só o super admin chega aqui). Isento, o tenant continua vendo as recusas no relatório, mas o
    canal não pausa por elas; uma pausa por spam já ativa é desfeita na hora."""
    tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    if tenant is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")
    tenant.isento_pausa_spam = isento
    auditoria_service.registrar(db, tenant_id, "isencao_pausa_spam_alterada", "tenant", 0, ator_id, {"isento": isento}, canal="email")
    db.commit()
    avaliar_recusas_spam(db, tenant_id)
    db.refresh(tenant)
    return tenant


def pausado_por_spam(db: Session, tenant_id: str) -> bool:
    pausa = db.query(PausaCanal).filter_by(tenant_id=tenant_id, canal="email", ativa=True).one_or_none()
    return pausa is not None and (pausa.motivo or "").startswith(MOTIVO_PAUSA_SPAM)


def avaliar_recusas_spam(db: Session, tenant_id: str) -> dict:
    """Pausa o canal de e-mail quando as recusas por spam passam do limite (salvo tenant isento) e o reabre sozinho quando a taxa volta para baixo dele.
    Só mexe na pausa causada por spam; a de bounce continua com as regras dela. Faz commit só quando muda alguma coisa."""
    saude = saude_recusas_spam(db, tenant_id)
    pausa = db.query(PausaCanal).filter_by(tenant_id=tenant_id, canal="email").one_or_none()
    pausada_por_spam = pausa is not None and pausa.ativa and (pausa.motivo or "").startswith(MOTIVO_PAUSA_SPAM)
    detalhes = {"recusas": saude["recusas_spam"], "enviados": saude["enviados_recusas"], "taxa": round(saude["taxa_recusa_spam"], 4)}
    if saude["nivel_recusa_spam"] == "critico" and not saude["isento_pausa_spam"]:
        if pausa is None or not pausa.ativa:
            if pausa is None:
                pausa = PausaCanal(tenant_id=tenant_id, canal="email")
                db.add(pausa)
            pausa.ativa = True
            pausa.motivo = (
                f"{MOTIVO_PAUSA_SPAM} taxa={saude['taxa_recusa_spam']:.4f} recusas={saude['recusas_spam']} enviados={saude['enviados_recusas']}"
            )
            pausa.pausado_em = datetime.now(UTC)
            auditoria_service.registrar(db, tenant_id, "canal_pausado_por_spam", "canal", 0, None, detalhes, canal="email")
            db.commit()
    elif pausada_por_spam:
        pausa.ativa = False
        auditoria_service.registrar(db, tenant_id, "canal_reaberto_taxa_spam_normalizada", "canal", 0, None, detalhes, canal="email")
        db.commit()
    return saude


def exigir_canal_nao_pausado(db: Session, tenant_id: str, canal: str) -> None:
    """Bloqueia a ativação de uma nova cadência/campanha nesse canal
    (raio-X 2026-09-16: Relatório de Entrega) — distinto de
    `canal_pausado`, usado em `envio_service`/`campanha_service` só pra
    *adiar* envios já agendados. Aqui a intenção é impedir de colocar
    ainda mais e-mail na fila enquanto o canal está degradado; rascunho/
    geração de conteúdo pela IA continuam liberados, só a ativação (que
    de fato programa envio) é que trava."""
    if canal == "email":
        avaliar_recusas_spam(db, tenant_id)
        if pausado_por_spam(db, tenant_id):
            raise RegraNegocioViolada(
                "Canal de e-mail pausado: os servidores dos destinatários recusaram como spam mais de "
                f"{settings.limiar_recusa_spam_pausa:.0%} dos seus e-mails nos últimos 7 dias. Veja no Relatório de Entrega o que fazer para "
                "melhorar a reputação; o canal volta sozinho quando a taxa cair abaixo do limite."
            )
    if canal_pausado(db, tenant_id, canal):
        raise RegraNegocioViolada(
            f"Canal {canal} pausado por alta taxa de bounce/spam — corrija ou remova os contatos "
            "problemáticos no Relatório de Entrega e reative o canal antes de continuar."
        )


def _verificar_e_pausar(db: Session, tenant_id: str, canal: str) -> None:
    enviados, bounces, spam_reports = _agregado_janela(db, tenant_id, canal)
    if enviados == 0:
        return

    # `enviados` só conta "delivered"; bounce/dropped/blocked não entram
    # nele — a amostra real de tentativas é a soma dos dois.
    if enviados + bounces < settings.amostra_minima_reputacao:
        return

    taxa_bounce = bounces / enviados
    taxa_spam = spam_reports / enviados
    if taxa_bounce < settings.limiar_bounce_padrao and taxa_spam < settings.limiar_spam_padrao:
        return
    if canal_pausado(db, tenant_id, canal):
        return

    motivo = f"taxa_bounce={taxa_bounce:.4f} taxa_spam={taxa_spam:.4f}"
    pausa = db.query(PausaCanal).filter_by(tenant_id=tenant_id, canal=canal).one_or_none()
    if pausa is None:
        pausa = PausaCanal(tenant_id=tenant_id, canal=canal)
        db.add(pausa)
    pausa.ativa = True
    pausa.motivo = motivo
    pausa.pausado_em = datetime.now(UTC)

    auditoria_service.registrar(
        db, tenant_id, "canal_pausado_automaticamente", "canal", 0, None, {"canal": canal, "motivo": motivo}, canal=canal
    )


def registrar_evento(db: Session, tenant_id: str, canal: str, tipo_evento: str, quantidade: int = 1) -> dict:
    """Registra bounce/spam/envio e dispara a pausa automática ao cruzar o
    limiar crítico de entregabilidade (E10-H2)."""
    if tipo_evento not in _TIPOS_VALIDOS:
        raise ValueError(f"tipo_evento inválido: {tipo_evento}")

    hoje = date.today().isoformat()
    registro = _obter_ou_criar_registro_do_dia(db, tenant_id, canal, hoje)
    if tipo_evento == "enviado":
        registro.enviados += quantidade
    elif tipo_evento == "bounce":
        registro.bounces += quantidade
    elif tipo_evento == "recusa_spam":
        registro.recusas_spam = (registro.recusas_spam or 0) + quantidade
    else:
        registro.spam_reports += quantidade

    _verificar_e_pausar(db, tenant_id, canal)
    if tipo_evento == "recusa_spam" and canal == "email":
        db.flush()
        avaliar_recusas_spam(db, tenant_id)

    db.commit()
    return status_saude(db, tenant_id, canal)


def status_saude(db: Session, tenant_id: str, canal: str) -> dict:
    """Painel de saúde por canal e assinante com limiares de alerta (E10-H2)."""
    enviados, bounces, spam_reports = _agregado_janela(db, tenant_id, canal)
    return {
        "canal": canal,
        "enviados": enviados,
        "bounces": bounces,
        "spam_reports": spam_reports,
        "taxa_bounce": bounces / enviados if enviados else 0.0,
        "taxa_spam": spam_reports / enviados if enviados else 0.0,
        "pausado": canal_pausado(db, tenant_id, canal),
        "limiar_bounce": settings.limiar_bounce_padrao,
        "limiar_spam": settings.limiar_spam_padrao,
        "amostra_minima": settings.amostra_minima_reputacao,
    }


def reativar(db: Session, tenant_id: str, ator_id: str | None, canal: str, super_admin: bool = False) -> dict:
    """Reativação manual do canal pelo Admin B2B ON, após correção (E10-H2).

    Zera bounce/spam da janela de 7 dias: sem isso, os mesmos eventos que
    causaram a pausa continuam contando e o próximo evento qualquer
    re-pausa o canal na hora, mesmo depois do usuário corrigir os contatos.
    O que foi zerado fica no log de auditoria."""
    pausa = db.query(PausaCanal).filter_by(tenant_id=tenant_id, canal=canal).one_or_none()
    if pausa is not None and pausa.ativa and (pausa.motivo or "").startswith(MOTIVO_PAUSA_SPAM) and not super_admin:
        # Pausa por spam não se desfaz pelo próprio cliente: volta sozinha quando a taxa cai, ou pelo administrador da plataforma depois de revisar.
        raise RegraNegocioViolada(
            "Esta pausa foi causada por recusas de spam e não pode ser desfeita por aqui: o canal volta sozinho quando a taxa dos últimos 7 dias "
            "cair abaixo do limite, ou pelo administrador da plataforma depois de revisar."
        )
    if pausa is not None:
        pausa.ativa = False

    _, bounces_anteriores, spam_anteriores = _agregado_janela(db, tenant_id, canal)
    limite = (date.today() - timedelta(days=_JANELA_DIAS)).isoformat()
    for registro in (
        db.query(RegistroReputacaoCanal)
        .filter(
            RegistroReputacaoCanal.tenant_id == tenant_id,
            RegistroReputacaoCanal.canal == canal,
            RegistroReputacaoCanal.data >= limite,
        )
        .all()
    ):
        registro.bounces = 0
        registro.spam_reports = 0
        registro.recusas_spam = 0

    auditoria_service.registrar(
        db,
        tenant_id,
        "canal_reativado_manualmente",
        "canal",
        0,
        ator_id,
        {"canal": canal, "bounces_zerados": bounces_anteriores, "spam_reports_zerados": spam_anteriores},
        canal=canal,
    )
    db.commit()
    return status_saude(db, tenant_id, canal)
