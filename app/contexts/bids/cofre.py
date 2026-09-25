"""Bid Document Vault (§36): validade, emissor, escopo, status e alertas."""

import hashlib
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.documento_cofre import DocumentoCofre

DIAS_ALERTA = 30


def status(documento: DocumentoCofre, referencia: date | None = None) -> str:
    """VALIDO | VENCENDO (≤30 dias) | VENCIDO | SEM_VALIDADE (sem data informada)."""
    hoje = referencia or date.today()
    if documento.valido_ate is None:
        return "SEM_VALIDADE"
    if documento.valido_ate < hoje:
        return "VENCIDO"
    if documento.valido_ate <= hoje + timedelta(days=DIAS_ALERTA):
        return "VENCENDO"
    return "VALIDO"


def valido_em(documento: DocumentoCofre, data: date) -> bool | None:
    """True/False quando há validade; None quando o documento não informa."""
    if documento.valido_ate is None:
        return None
    return (documento.valido_desde is None or documento.valido_desde <= data) and documento.valido_ate >= data


def hash_de(conteudo: bytes | None) -> str | None:
    return hashlib.sha256(conteudo).hexdigest() if conteudo else None


def listar(db: Session, tenant_id: str, incluir_inativos: bool = False) -> list[DocumentoCofre]:
    consulta = db.query(DocumentoCofre).filter_by(tenant_id=tenant_id)
    if not incluir_inativos:
        consulta = consulta.filter(DocumentoCofre.ativo.is_(True))
    return consulta.order_by(DocumentoCofre.valido_ate.is_(None), DocumentoCofre.valido_ate, DocumentoCofre.id).all()


def alertas(db: Session, tenant_id: str, referencia: date | None = None) -> list[dict]:
    return [
        {**como_dict(d, referencia), "alerta": status(d, referencia)}
        for d in listar(db, tenant_id)
        if status(d, referencia) in ("VENCENDO", "VENCIDO")
    ]


def como_dict(documento: DocumentoCofre, referencia: date | None = None) -> dict:
    return {
        "id": documento.id,
        "tipo": documento.tipo,
        "nome": documento.nome,
        "emissor": documento.emissor,
        "escopo": documento.escopo,
        "palavras_chave": documento.palavras_chave or [],
        "valido_desde": documento.valido_desde,
        "valido_ate": documento.valido_ate,
        "status": status(documento, referencia),
        "nome_arquivo": documento.nome_arquivo,
        "sha256": documento.sha256,
        "tem_arquivo": documento.conteudo is not None,
        "ativo": documento.ativo,
        "criado_em": documento.criado_em,
    }
