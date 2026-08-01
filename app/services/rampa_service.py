from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.configuracao_canal import ConfiguracaoCanal
from app.models.registro_envio_diario import RegistroEnvioDiario
from app.services.errors import RegraNegocioViolada

CANAIS_COM_RAMPA = {"whatsapp", "email"}


def limite_diario(canal: str, dias_de_uso: int) -> int:
    """Limite diário para o canal conforme a idade de uso (E10-H1).

    Função pura — os degraus são parâmetro de entregabilidade configurável
    (`settings.rampa_degraus_*`), não uma curva comercial fechada. Lê
    `settings` a cada chamada (não em import) para respeitar overrides de
    configuração/teste.
    """
    degraus = settings.rampa_degraus_whatsapp if canal == "whatsapp" else settings.rampa_degraus_email
    for degrau in sorted(degraus, key=lambda d: d["dias"]):
        if dias_de_uso <= degrau["dias"]:
            return degrau["limite"]
    return degraus[-1]["limite"]


def _obter_ou_criar_configuracao_canal(db: Session, tenant_id: str, canal: str) -> ConfiguracaoCanal:
    config = db.query(ConfiguracaoCanal).filter_by(tenant_id=tenant_id, canal=canal).one_or_none()
    if config is None:
        config = ConfiguracaoCanal(tenant_id=tenant_id, canal=canal)
        db.add(config)
        db.flush()
    return config


def _dias_de_uso(config: ConfiguracaoCanal) -> int:
    iniciado_em = config.iniciado_em
    if iniciado_em.tzinfo is None:
        iniciado_em = iniciado_em.replace(tzinfo=UTC)
    return (datetime.now(UTC) - iniciado_em).days


def status_rampa(db: Session, tenant_id: str, canal: str) -> dict:
    config = _obter_ou_criar_configuracao_canal(db, tenant_id, canal)
    dias_de_uso = _dias_de_uso(config)
    limite = limite_diario(canal, dias_de_uso)

    hoje = date.today().isoformat()
    registro = (
        db.query(RegistroEnvioDiario).filter_by(tenant_id=tenant_id, canal=canal, data=hoje).one_or_none()
    )
    usado_hoje = registro.quantidade_enviada if registro else 0

    return {
        "canal": canal,
        "dias_de_uso": dias_de_uso,
        "limite_diario": limite,
        "usado_hoje": usado_hoje,
        "restante_hoje": max(limite - usado_hoje, 0),
    }


def verificar_e_registrar(db: Session, tenant_id: str, canal: str) -> None:
    """Bloqueio de burla (E10-H1): incrementa o contador do dia só se ainda
    houver espaço na rampa; senão, levanta erro. O enforcement acontece no
    momento do envio — o assinante não consegue exceder o teto disparando
    mais requisições."""
    status = status_rampa(db, tenant_id, canal)
    if status["usado_hoje"] >= status["limite_diario"]:
        raise RegraNegocioViolada(
            f"Limite diário de envio para {canal} atingido "
            f"({status['limite_diario']}/dia nesta fase de aquecimento)."
        )

    hoje = date.today().isoformat()
    registro = (
        db.query(RegistroEnvioDiario).filter_by(tenant_id=tenant_id, canal=canal, data=hoje).one_or_none()
    )
    if registro is None:
        registro = RegistroEnvioDiario(tenant_id=tenant_id, canal=canal, data=hoje, quantidade_enviada=0)
        db.add(registro)
        db.flush()
    registro.quantidade_enviada += 1
    db.commit()
