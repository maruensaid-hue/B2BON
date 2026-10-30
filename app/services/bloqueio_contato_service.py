import re
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bloqueio_contato import BloqueioContato
from app.models.campanha import CampanhaDestinatario
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import auditoria_service
from app.services.errors import NaoEncontrado

# Telefones são comparados pelos 10 últimos dígitos: "+55 (11) 99999-0000" e "11999990000" são a mesma pessoa.
_DIGITOS_DO_TELEFONE = 10
_MINIMO_DE_DIGITOS = 8

# Endereço que voltou como inexistente: bloqueia só o e-mail (o telefone da mesma pessoa continua valendo) e vale em toda a plataforma.
ORIGEM_EMAIL_INEXISTENTE = "email_inexistente"
MOTIVO_BOUNCE_MANUAL = "Informado manualmente: o e-mail voltou como não entregue."


def normalizar_email(email: str | None) -> str | None:
    """E-mail em minúsculas e sem espaços nas pontas; vazio vira `None`."""
    texto = (email or "").strip().lower()
    return texto or None


def normalizar_telefone(telefone: str | None) -> str | None:
    """Só os dígitos; com menos de 8 dígitos não é telefone (`None`)."""
    digitos = re.sub(r"\D", "", telefone or "")
    return digitos if len(digitos) >= _MINIMO_DE_DIGITOS else None


@dataclass
class Bloqueados:
    """Conjuntos já normalizados, consultados a cada destinatário sem voltar ao banco."""

    emails: set[str] = field(default_factory=set)
    telefones: set[str] = field(default_factory=set)
    emails_inexistentes: set[str] = field(default_factory=set)  # voltaram como não entregues: não recebem e-mail, mas o telefone não é bloqueado

    def contem(self, email: str | None, telefone: str | None) -> bool:
        """True se o e-mail, ou o telefone (pelos 10 últimos dígitos), está na lista."""
        email_normalizado = normalizar_email(email)
        telefone_normalizado = normalizar_telefone(telefone)
        return (email_normalizado is not None and email_normalizado in self.emails) or (
            telefone_normalizado is not None and telefone_normalizado[-_DIGITOS_DO_TELEFONE:] in self.telefones
        )


def carregar(db: Session, tenant_id: str) -> Bloqueados:
    """Carrega a lista do tenant em conjuntos normalizados, uma vez por rodada de envio."""
    bloqueados = Bloqueados()
    for bloqueio in db.query(BloqueioContato).filter_by(tenant_id=tenant_id).all():
        if bloqueio.origem == ORIGEM_EMAIL_INEXISTENTE:
            if bloqueio.email:
                bloqueados.emails_inexistentes.add(bloqueio.email)
            continue
        if bloqueio.email:
            bloqueados.emails.add(bloqueio.email)
        telefone = normalizar_telefone(bloqueio.telefone)
        if telefone:
            bloqueados.telefones.add(telefone[-_DIGITOS_DO_TELEFONE:])
    return bloqueados


def emails_devolvidos(db: Session, tenant_id: str) -> set[str]:
    """Endereços que já voltaram como não entregues (aviso do provedor ou registro manual) em campanhas ou cadências do tenant, em minúsculas."""
    de_campanhas = db.query(func.lower(func.trim(CampanhaDestinatario.email))).filter(
        CampanhaDestinatario.tenant_id == tenant_id, CampanhaDestinatario.bounce_em.isnot(None), CampanhaDestinatario.email.isnot(None)
    )
    de_cadencias = (
        db.query(func.lower(func.trim(Decisor.email)))
        .join(Mensagem, Mensagem.decisor_id == Decisor.id)
        .filter(Mensagem.tenant_id == tenant_id, Mensagem.bounce_em.isnot(None), Decisor.email.isnot(None))
    )
    return {email for (email,) in [*de_campanhas.all(), *de_cadencias.all()]}


def emails_inviaveis(db: Session, tenant_id: str) -> set[str]:
    """Todos os e-mails para os quais não se deve enviar nada: os registrados como inexistentes e os que já voltaram como não entregues. É a consulta única
    de campanhas, cadências, webmail, lembretes e NPS: um endereço que voltou não é tentado de novo em lugar nenhum da plataforma."""
    return carregar(db, tenant_id).emails_inexistentes | emails_devolvidos(db, tenant_id)


def email_esta_inviavel(email: str | None, inviaveis: set[str]) -> bool:
    """True se o endereço (comparado em minúsculas e sem espaços) está no conjunto devolvido por `emails_inviaveis`."""
    normalizado = normalizar_email(email)
    return normalizado is not None and normalizado in inviaveis


def registrar_email_inexistente(db: Session, tenant_id: str, ator_id: str | None, email: str, motivo: str) -> tuple[BloqueioContato, bool]:
    """Põe um e-mail na lista como inexistente (só o e-mail; o telefone não entra). Idempotente: devolve `(bloqueio, criado)`. Não faz commit."""
    email_normalizado = normalizar_email(email)
    existente = (
        db.query(BloqueioContato)
        .filter_by(tenant_id=tenant_id, email=email_normalizado, origem=ORIGEM_EMAIL_INEXISTENTE)
        .one_or_none()
    )
    if existente is not None:
        return existente, False
    bloqueio = BloqueioContato(
        tenant_id=tenant_id, email=email_normalizado, telefone=None, motivo=motivo, origem=ORIGEM_EMAIL_INEXISTENTE, criado_por=ator_id
    )
    db.add(bloqueio)
    db.flush()
    auditoria_service.registrar(
        db, tenant_id, "email_inexistente_registrado", "bloqueio_contato", bloqueio.id, ator_id, {"origem": ORIGEM_EMAIL_INEXISTENTE}
    )
    return bloqueio, True


def _limpar_bounces_manuais(db: Session, tenant_id: str, email: str) -> None:
    """Desfaz as marcas de bounce que o registro manual pôs nos envios deste e-mail (as do provedor ficam: aquele retorno foi real)."""
    for destinatario in db.query(CampanhaDestinatario).filter(
        CampanhaDestinatario.tenant_id == tenant_id,
        func.lower(func.trim(CampanhaDestinatario.email)) == email,
        CampanhaDestinatario.motivo_bounce == MOTIVO_BOUNCE_MANUAL,
    ):
        destinatario.bounce_em = None
        destinatario.motivo_bounce = None
    for mensagem in (
        db.query(Mensagem)
        .join(Decisor, Mensagem.decisor_id == Decisor.id)
        .filter(Mensagem.tenant_id == tenant_id, func.lower(func.trim(Decisor.email)) == email, Mensagem.motivo_bounce == MOTIVO_BOUNCE_MANUAL)
    ):
        mensagem.bounce_em = None
        mensagem.motivo_bounce = None


def registrar(
    db: Session, tenant_id: str, ator_id: str | None, *, email: str | None, telefone: str | None, motivo: str, origem: str
) -> BloqueioContato | None:
    """Põe o e-mail e/ou telefone na lista de bloqueio. Idempotente: se o mesmo e-mail ou telefone já está lá, devolve o que existe. Sem nenhum dos dois, não há o
    que bloquear (devolve `None`). Não faz commit (quem chama decide)."""
    email_normalizado = normalizar_email(email)
    telefone_normalizado = normalizar_telefone(telefone)
    if email_normalizado is None and telefone_normalizado is None:
        return None

    for existente in db.query(BloqueioContato).filter_by(tenant_id=tenant_id).all():
        mesmo_email = email_normalizado is not None and existente.email == email_normalizado
        telefone_existente = normalizar_telefone(existente.telefone)
        mesmo_telefone = (
            telefone_normalizado is not None
            and telefone_existente is not None
            and telefone_existente[-_DIGITOS_DO_TELEFONE:] == telefone_normalizado[-_DIGITOS_DO_TELEFONE:]
        )
        if mesmo_email or mesmo_telefone:
            return existente

    bloqueio = BloqueioContato(
        tenant_id=tenant_id,
        email=email_normalizado,
        telefone=telefone_normalizado,
        motivo=motivo,
        origem=origem,
        criado_por=ator_id,
    )
    db.add(bloqueio)
    db.flush()
    auditoria_service.registrar(
        db, tenant_id, "contato_bloqueado", "bloqueio_contato", bloqueio.id, ator_id, {"origem": origem, "tem_email": bool(email_normalizado), "tem_telefone": bool(telefone_normalizado)}
    )
    return bloqueio


def listar(db: Session, tenant_id: str) -> list[BloqueioContato]:
    """Bloqueios do tenant, do mais novo para o mais antigo."""
    return db.query(BloqueioContato).filter_by(tenant_id=tenant_id).order_by(BloqueioContato.criado_em.desc(), BloqueioContato.id.desc()).all()


def liberar(db: Session, tenant_id: str, ator_id: str | None, bloqueio_id: int) -> None:
    """Remove um bloqueio do tenant (desfaz um engano) e registra na auditoria."""
    bloqueio = db.query(BloqueioContato).filter_by(id=bloqueio_id, tenant_id=tenant_id).one_or_none()
    if bloqueio is None:
        raise NaoEncontrado(f"Bloqueio {bloqueio_id} não encontrado")
    if bloqueio.origem == ORIGEM_EMAIL_INEXISTENTE and bloqueio.email:
        _limpar_bounces_manuais(db, tenant_id, bloqueio.email)  # senão o e-mail continuaria barrado pelo bounce manual
    db.delete(bloqueio)
    auditoria_service.registrar(db, tenant_id, "contato_liberado", "bloqueio_contato", bloqueio_id, ator_id, {})
    db.commit()
