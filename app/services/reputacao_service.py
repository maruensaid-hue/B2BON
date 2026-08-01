from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.pausa_canal import PausaCanal
from app.models.registro_reputacao_canal import RegistroReputacaoCanal
from app.services import auditoria_service

_JANELA_DIAS = 7
_TIPOS_VALIDOS = {"enviado", "bounce", "spam_report"}


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


def _verificar_e_pausar(db: Session, tenant_id: str, canal: str) -> None:
    enviados, bounces, spam_reports = _agregado_janela(db, tenant_id, canal)
    if enviados == 0:
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
    else:
        registro.spam_reports += quantidade

    _verificar_e_pausar(db, tenant_id, canal)

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
    }


def reativar(db: Session, tenant_id: str, ator_id: str | None, canal: str) -> dict:
    """Reativação manual do canal pelo Admin B2B ON, após correção (E10-H2)."""
    pausa = db.query(PausaCanal).filter_by(tenant_id=tenant_id, canal=canal).one_or_none()
    if pausa is not None:
        pausa.ativa = False

    auditoria_service.registrar(
        db, tenant_id, "canal_reativado_manualmente", "canal", 0, ator_id, {"canal": canal}, canal=canal
    )
    db.commit()
    return status_saude(db, tenant_id, canal)
