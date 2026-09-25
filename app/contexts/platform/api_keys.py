"""Chaves de API de produto por tenant (Fase 3, §11/§64).

Formato: `b2bk_<43 chars url-safe>`. Grava só SHA-256. Escopos por
módulo e operação; o acesso efetivo exige, além do escopo, licença ativa
e o módulo contratado (entitlement no backend, §74).
"""

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.chave_api_tenant import ChaveApiTenant
from app.services import auditoria_service
from app.services.errors import NaoAutenticado, NaoEncontrado, ValidacaoFalhou

PREFIXO = "b2bk_"
ESCOPOS = frozenset({"map:read", "predator:read", "predator:write"})
MAX_CHAVES_ATIVAS = 20


def _hash(segredo: str) -> str:
    return hashlib.sha256(segredo.encode()).hexdigest()


def criar(db: Session, tenant_id: str, usuario_id: int | None, nome: str, escopos: list[str]) -> tuple[ChaveApiTenant, str]:
    escopos_invalidos = set(escopos) - ESCOPOS
    if not escopos or escopos_invalidos:
        raise ValidacaoFalhou(f"Escopos inválidos: {sorted(escopos_invalidos) or 'nenhum informado'}. Válidos: {sorted(ESCOPOS)}")
    ativas = db.query(ChaveApiTenant).filter_by(tenant_id=tenant_id, revogada_em=None).count()
    if ativas >= MAX_CHAVES_ATIVAS:
        raise ValidacaoFalhou(f"Limite de {MAX_CHAVES_ATIVAS} chaves ativas por tenant atingido. Revogue uma antes.")
    segredo = PREFIXO + secrets.token_urlsafe(32)
    chave = ChaveApiTenant(
        tenant_id=tenant_id,
        nome=nome.strip()[:100] or "Chave",
        prefixo=segredo[: len(PREFIXO) + 6],
        chave_hash=_hash(segredo),
        escopos=sorted(set(escopos)),
        criado_por_usuario_id=usuario_id,
    )
    db.add(chave)
    db.flush()
    auditoria_service.registrar(
        db, tenant_id, "chave_api_criada", "chave_api_tenant", chave.id,
        str(usuario_id) if usuario_id else None, {"escopos": chave.escopos},
    )
    db.commit()
    db.refresh(chave)
    return chave, segredo


def listar(db: Session, tenant_id: str) -> list[ChaveApiTenant]:
    return db.query(ChaveApiTenant).filter_by(tenant_id=tenant_id).order_by(ChaveApiTenant.id.desc()).all()


def revogar(db: Session, tenant_id: str, usuario_id: int | None, chave_id: int) -> ChaveApiTenant:
    chave = db.query(ChaveApiTenant).filter_by(id=chave_id, tenant_id=tenant_id).one_or_none()
    if chave is None:
        raise NaoEncontrado(f"Chave {chave_id} não encontrada")
    if chave.revogada_em is None:
        chave.revogada_em = datetime.now(UTC)
        auditoria_service.registrar(
            db, tenant_id, "chave_api_revogada", "chave_api_tenant", chave.id, str(usuario_id) if usuario_id else None, {}
        )
        db.commit()
    return chave


def autenticar(db: Session, segredo: str | None) -> ChaveApiTenant:
    if not segredo or not segredo.startswith(PREFIXO):
        raise NaoAutenticado("Informe uma chave de API válida (header X-API-Key ou Authorization: Bearer b2bk_...).")
    chave = db.query(ChaveApiTenant).filter_by(chave_hash=_hash(segredo)).one_or_none()
    if chave is None or chave.revogada_em is not None:
        raise NaoAutenticado("Chave de API inválida ou revogada.")
    chave.ultimo_uso_em = datetime.now(UTC)
    db.commit()
    return chave
