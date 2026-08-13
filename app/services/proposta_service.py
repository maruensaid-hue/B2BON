from sqlalchemy.orm import Session

from app.models.negocio import Negocio
from app.models.proposta_negocio import PropostaNegocio
from app.services import atividade_service, auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TIPOS_PERMITIDOS = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Mesmo teto de MaterialOferta — blob vai direto no banco, sem limite o
# upload de um arquivo gigante esgotaria banco/memória.
TAMANHO_MAXIMO_BYTES = 15 * 1024 * 1024


def _obter_negocio(db: Session, tenant_id: str, negocio_id: int) -> Negocio:
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")
    return negocio


def anexar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    negocio_id: int,
    nome_arquivo: str,
    tipo_mime: str,
    conteudo: bytes,
    gerada_automaticamente: bool = False,
) -> PropostaNegocio:
    negocio = _obter_negocio(db, tenant_id, negocio_id)

    if tipo_mime not in TIPOS_PERMITIDOS:
        raise ValidacaoFalhou(f"Tipo de arquivo não suportado: {tipo_mime}. Envie PDF ou DOCX.")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        limite_mb = TAMANHO_MAXIMO_BYTES // (1024 * 1024)
        raise ValidacaoFalhou(f"Arquivo maior que o limite de {limite_mb}MB.")

    maior_versao = (
        db.query(PropostaNegocio.versao)
        .filter_by(tenant_id=tenant_id, negocio_id=negocio_id)
        .order_by(PropostaNegocio.versao.desc())
        .first()
    )
    versao = (maior_versao[0] + 1) if maior_versao else 1

    proposta = PropostaNegocio(
        tenant_id=tenant_id,
        negocio_id=negocio_id,
        versao=versao,
        nome_arquivo=nome_arquivo,
        tipo_mime=tipo_mime,
        conteudo=conteudo,
        tamanho_bytes=len(conteudo),
        gerada_automaticamente=gerada_automaticamente,
        enviada_por_usuario_id=None if gerada_automaticamente else (int(ator_id) if ator_id else None),
    )
    db.add(proposta)
    db.flush()

    atividade_service.registrar(
        db,
        tenant_id,
        conta_id=negocio.conta_id,
        negocio_id=negocio_id,
        tipo="sistema",
        descricao=f"Proposta enviada (v{versao}): {nome_arquivo}",
        ator_id=None if gerada_automaticamente else ator_id,
    )
    auditoria_service.registrar(
        db, tenant_id, "proposta_anexada", "negocio", negocio_id, ator_id, {"versao": versao, "nome_arquivo": nome_arquivo}
    )
    db.commit()
    db.refresh(proposta)
    return proposta


def listar(db: Session, tenant_id: str, negocio_id: int) -> list[PropostaNegocio]:
    return (
        db.query(PropostaNegocio)
        .filter_by(tenant_id=tenant_id, negocio_id=negocio_id)
        .order_by(PropostaNegocio.versao.desc())
        .all()
    )


def obter(db: Session, tenant_id: str, negocio_id: int, proposta_id: int) -> PropostaNegocio:
    proposta = (
        db.query(PropostaNegocio)
        .filter_by(id=proposta_id, negocio_id=negocio_id, tenant_id=tenant_id)
        .one_or_none()
    )
    if proposta is None:
        raise NaoEncontrado(f"Proposta {proposta_id} não encontrada")
    return proposta
