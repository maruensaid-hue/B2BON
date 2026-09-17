from datetime import datetime

from sqlalchemy.orm import Session

from app.models.intent import Intent
from app.models.perfil_empresa import PerfilEmpresa
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado
from app.services.rede_social_service import status_conexao_com


def _serializar(db: Session, intent: Intent) -> dict:
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=intent.tenant_id).one_or_none()
    return {
        "id": intent.id,
        "tenant_id": intent.tenant_id,
        "empresa_nome": perfil.nome_exibicao if perfil is not None else intent.tenant_id,
        "categoria": intent.categoria,
        "titulo": intent.titulo,
        "descricao": intent.descricao,
        "requisitos": intent.requisitos,
        "faixa_orcamento": intent.faixa_orcamento,
        "localizacao": intent.localizacao,
        "prazo": intent.prazo,
        "perfil_fornecedor_desejado": intent.perfil_fornecedor_desejado,
        "visibilidade": intent.visibilidade,
        "status": intent.status,
        "criado_em": intent.criado_em,
        "expira_em": intent.expira_em,
    }


def criar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    categoria: str,
    titulo: str,
    descricao: str,
    requisitos: list[str] | None,
    faixa_orcamento: str | None,
    localizacao: str | None,
    prazo: datetime | None,
    perfil_fornecedor_desejado: str | None,
    visibilidade: str,
) -> dict:
    intent = Intent(
        tenant_id=tenant_id,
        categoria=categoria,
        titulo=titulo,
        descricao=descricao,
        requisitos=requisitos or [],
        faixa_orcamento=faixa_orcamento,
        localizacao=localizacao,
        prazo=prazo,
        perfil_fornecedor_desejado=perfil_fornecedor_desejado,
        visibilidade=visibilidade if visibilidade in ("publica", "conexoes") else "publica",
    )
    db.add(intent)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "intent_criada", "intent", intent.id, ator_id, {})
    db.commit()
    db.refresh(intent)
    return _serializar(db, intent)


def _obter(db: Session, intent_id: int) -> Intent:
    intent = db.query(Intent).filter_by(id=intent_id).one_or_none()
    if intent is None:
        raise NaoEncontrado(f"Intent {intent_id} não encontrada")
    return intent


def _visivel_para(db: Session, tenant_id_atual: str, intent: Intent) -> bool:
    if intent.tenant_id == tenant_id_atual:
        return True
    if intent.visibilidade == "publica":
        return True
    return status_conexao_com(db, tenant_id_atual, intent.tenant_id) == "aceita"


def obter_visivel(db: Session, tenant_id_atual: str, intent_id: int) -> dict:
    intent = _obter(db, intent_id)
    if not _visivel_para(db, tenant_id_atual, intent):
        raise NaoEncontrado(f"Intent {intent_id} não encontrada")
    return _serializar(db, intent)


def listar(db: Session, tenant_id_atual: str) -> list[dict]:
    """Necessidades da rede (master prompt §46-47, Fase 3A) — próprias +
    de outros tenants respeitando `visibilidade` (`conexoes` só é
    visível pra quem já tem conexão aceita com o autor)."""
    intents = db.query(Intent).order_by(Intent.criado_em.desc(), Intent.id.desc()).all()
    visiveis = [intent for intent in intents if _visivel_para(db, tenant_id_atual, intent)]
    return [_serializar(db, intent) for intent in visiveis]


def _exigir_autor(tenant_id: str, intent: Intent) -> None:
    if intent.tenant_id != tenant_id:
        raise NaoAutorizado("Só a própria empresa autora pode alterar esta necessidade.")


def encerrar(db: Session, tenant_id: str, ator_id: str | None, intent_id: int) -> dict:
    intent = _obter(db, intent_id)
    _exigir_autor(tenant_id, intent)
    intent.status = "cancelada"
    auditoria_service.registrar(db, tenant_id, "intent_encerrada", "intent", intent.id, ator_id, {})
    db.commit()
    db.refresh(intent)
    return _serializar(db, intent)


def marcar_atendida(db: Session, tenant_id: str, ator_id: str | None, intent_id: int) -> dict:
    intent = _obter(db, intent_id)
    _exigir_autor(tenant_id, intent)
    intent.status = "atendida"
    auditoria_service.registrar(db, tenant_id, "intent_atendida", "intent", intent.id, ator_id, {})
    db.commit()
    db.refresh(intent)
    return _serializar(db, intent)
