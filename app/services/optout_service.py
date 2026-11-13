import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.integrations import contract as integracoes
from app.core.config import settings
from app.db import rls
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import atividade_service, auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

_SEPARADOR = ":"


def gerar_token(tenant_id: str, decisor_id: int) -> str:
    """Token de opt-out assinado (HMAC) — sem tabela própria, verificável
    de forma stateless a partir de `settings.secret_key`."""
    payload = f"{tenant_id}{_SEPARADOR}{decisor_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR}{assinatura}"


def url_descadastro(tenant_id: str, decisor_id: int) -> str:
    """Link de descadastro do e-mail: abre a página de confirmação (GET); quem descadastra é o POST do botão ou do cliente de e-mail."""
    return f"{settings.url_base_api}/opt-out/email/{gerar_token(tenant_id, decisor_id)}"


def validar_token(token: str) -> None:
    """Só confere a assinatura — a página de confirmação (GET) não muda nada."""
    _validar_token(token)


def _validar_token(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de opt-out inválido.")
    tenant_id, decisor_id_str, assinatura = partes
    try:
        decisor_id = int(decisor_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de opt-out inválido.") from erro

    esperado = gerar_token(tenant_id, decisor_id).rsplit(_SEPARADOR, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de opt-out inválido.")
    return tenant_id, decisor_id


def _cancelar_mensagens_pendentes(db: Session, decisor_id: int) -> int:
    pendentes = (
        db.query(Mensagem)
        .filter(Mensagem.decisor_id == decisor_id, Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]))
        .all()
    )
    for mensagem in pendentes:
        mensagem.status = "cancelado"
    return len(pendentes)


def processar_por_token(db: Session, token: str) -> dict:
    """Opt-out via link do e-mail — endpoint público, sem X-Tenant-Id (E9-H2)."""
    tenant_id, decisor_id = _validar_token(token)
    rls.definir_tenant(db, tenant_id)  # o tenant vem do token assinado (HMAC), não da requisição
    return processar(db, tenant_id, decisor_id, origem="email")


def processar(db: Session, tenant_id: str, decisor_id: int, origem: str) -> dict:
    """Efeito imediato em todos os canais e cadências do assinante,
    supressão permanente (E9-H2)."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")
    resultado = aplicar(db, tenant_id, decisor, origem)
    db.commit()
    return resultado


def aplicar(db: Session, tenant_id: str, decisor: Decisor, origem: str) -> dict:
    """Mesmo efeito de `processar`, sem commit (quem chama decide). D-087:
    o opt-out também vai para o CRM do cliente que tiver PREDATOR → CRM
    ligado — exceto quando veio do próprio CRM (já está lá)."""
    ja_estava = decisor.suprimido_em is not None
    if decisor.suprimido_em is None:
        decisor.suprimido_em = datetime.now(UTC)

    canceladas = _cancelar_mensagens_pendentes(db, decisor.id)
    # Visível na linha do tempo da conta (antes o "SAIR" só ia para a auditoria e nada na tela mostrava o descadastro, visto em
    # produção em 09/11/2026). A resposta escrita ("me tire da lista") já registra a própria atividade com o trecho citado.
    if not ja_estava and not origem.startswith("resposta_"):
        canal = {"whatsapp": "WhatsApp", "email": "e-mail"}.get(origem, origem.replace("_", " "))
        atividade_service.registrar(
            db, tenant_id, conta_id=decisor.conta_id, tipo="sistema",
            descricao=f"{decisor.nome} pediu para não receber mais mensagens ({canal}): descadastrado, nada mais sai para este contato.",
        )

    auditoria_service.registrar(
        db,
        tenant_id,
        "optout_registrado",
        "decisor",
        decisor.id,
        None,
        {"origem": origem, "mensagens_canceladas": canceladas},
        conta_id=decisor.conta_id,
    )
    if origem != "crm_externo":
        integracoes.obter_escrita().enfileirar(db, tenant_id, "optout", decisor.id)
    return {"decisor_id": decisor.id, "suprimido": True, "mensagens_canceladas": canceladas}


def desfazer(db: Session, tenant_id: str, ator_id: str | None, decisor_id: int, motivo: str) -> Decisor:
    """Volta a liberar envios para quem foi descadastrado por engano — ex.: o filtro de segurança de e-mail corporativo abriu o
    link e o descadastro antigo valia só por abrir (visto em 13/11/2026). Só admin, com motivo, e fica na auditoria e na linha do
    tempo. As mensagens canceladas pelo descadastro não voltam: quem desfaz gera de novo o que quiser enviar."""
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise ValidacaoFalhou("Explique o motivo (mínimo de 10 caracteres): desfazer um descadastro fica registrado na auditoria.")
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")
    if decisor.suprimido_em is None:
        raise ValidacaoFalhou("Este contato não está descadastrado.")
    suprimido_em = decisor.suprimido_em
    decisor.suprimido_em = None
    atividade_service.registrar(
        db, tenant_id, conta_id=decisor.conta_id, tipo="sistema",
        descricao=f"Descadastro de {decisor.nome} desfeito por um administrador. Motivo: {motivo[:300]}",
    )
    auditoria_service.registrar(
        db, tenant_id, "optout_desfeito", "decisor", decisor.id, ator_id,
        {"motivo": motivo[:500], "suprimido_em": suprimido_em.isoformat()}, conta_id=decisor.conta_id,
    )
    db.commit()
    db.refresh(decisor)
    return decisor


def existe_supressao(db: Session, decisor_id: int) -> bool:
    """Lista de supressão consultada antes de qualquer novo envio (E9-H2)."""
    decisor = db.query(Decisor).filter_by(id=decisor_id).one_or_none()
    return decisor is not None and decisor.suprimido_em is not None
