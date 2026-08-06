from sqlalchemy.orm import Session

from app.models.material_oferta import MaterialOferta
from app.models.oferta import Oferta
from app.schemas.oferta import OfertaCreateSchema
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TIPOS_MATERIAL_PERMITIDOS = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Blob vai direto no Postgres/SQLite (raio-X de produção) — teto evita que
# um upload gigante esgote banco/memória (nenhum limite existia antes).
TAMANHO_MAXIMO_MATERIAL_BYTES = 15 * 1024 * 1024


def listar(db: Session, tenant_id: str) -> list[Oferta]:
    return db.query(Oferta).filter_by(tenant_id=tenant_id).all()


def existe_oferta_ativa(db: Session, tenant_id: str) -> bool:
    return db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).first() is not None


def _obter(db: Session, tenant_id: str, oferta_id: int) -> Oferta:
    oferta = db.query(Oferta).filter_by(id=oferta_id, tenant_id=tenant_id).one_or_none()
    if oferta is None:
        raise NaoEncontrado(f"Oferta {oferta_id} não encontrada")
    return oferta


def criar(db: Session, tenant_id: str, ator_id: str | None, dados: OfertaCreateSchema) -> Oferta:
    oferta = Oferta(
        tenant_id=tenant_id,
        icp_id=dados.icp_id,
        nome=dados.nome,
        descricao=dados.descricao,
        diferenciais=dados.diferenciais,
        provas_sociais=dados.provas_sociais,
        faixa_preco_min=dados.faixa_preco_min,
        faixa_preco_max=dados.faixa_preco_max,
        ativo=True,
    )
    db.add(oferta)
    db.flush()
    # Só uma oferta ativa por tenant — mesma regra do ICP (nova versão
    # desativa as anteriores). Sem isto, "gerar cadência" ficava com
    # ativo=True duplicado e um `.first()` arbitrário decidindo qual
    # oferta realmente entrava no prompt (bug real de produção).
    db.query(Oferta).filter(Oferta.tenant_id == tenant_id, Oferta.id != oferta.id).update({"ativo": False})

    auditoria_service.registrar(db, tenant_id, "oferta_criada", "oferta", oferta.id, ator_id, {"nome": oferta.nome})
    db.commit()
    db.refresh(oferta)
    return oferta


def atualizar(db: Session, tenant_id: str, ator_id: str | None, oferta_id: int, dados: OfertaCreateSchema) -> Oferta:
    oferta = _obter(db, tenant_id, oferta_id)
    oferta.icp_id = dados.icp_id
    oferta.nome = dados.nome
    oferta.descricao = dados.descricao
    oferta.diferenciais = dados.diferenciais
    oferta.provas_sociais = dados.provas_sociais
    oferta.faixa_preco_min = dados.faixa_preco_min
    oferta.faixa_preco_max = dados.faixa_preco_max

    auditoria_service.registrar(db, tenant_id, "oferta_atualizada", "oferta", oferta.id, ator_id, {"nome": oferta.nome})
    db.commit()
    db.refresh(oferta)
    return oferta


def ativar(db: Session, tenant_id: str, ator_id: str | None, oferta_id: int) -> Oferta:
    oferta = _obter(db, tenant_id, oferta_id)
    db.query(Oferta).filter(Oferta.tenant_id == tenant_id, Oferta.id != oferta.id).update({"ativo": False})
    oferta.ativo = True

    auditoria_service.registrar(db, tenant_id, "oferta_ativada", "oferta", oferta.id, ator_id, {})
    db.commit()
    db.refresh(oferta)
    return oferta


def desativar(db: Session, tenant_id: str, ator_id: str | None, oferta_id: int) -> Oferta:
    oferta = _obter(db, tenant_id, oferta_id)
    oferta.ativo = False

    auditoria_service.registrar(db, tenant_id, "oferta_desativada", "oferta", oferta.id, ator_id, {})
    db.commit()
    db.refresh(oferta)
    return oferta


def excluir(db: Session, tenant_id: str, ator_id: str | None, oferta_id: int) -> None:
    oferta = _obter(db, tenant_id, oferta_id)
    db.query(MaterialOferta).filter_by(tenant_id=tenant_id, oferta_id=oferta_id).delete()

    auditoria_service.registrar(db, tenant_id, "oferta_excluida", "oferta", oferta.id, ator_id, {"nome": oferta.nome})
    db.delete(oferta)
    db.commit()


def salvar_material(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    oferta_id: int,
    nome_arquivo: str,
    tipo_mime: str,
    conteudo: bytes,
) -> MaterialOferta:
    oferta = db.query(Oferta).filter_by(id=oferta_id, tenant_id=tenant_id).one_or_none()
    if oferta is None:
        raise NaoEncontrado(f"Oferta {oferta_id} não encontrada")

    if tipo_mime not in TIPOS_MATERIAL_PERMITIDOS:
        raise ValidacaoFalhou(f"Tipo de arquivo não suportado: {tipo_mime}. Envie PDF ou DOCX.")
    if len(conteudo) > TAMANHO_MAXIMO_MATERIAL_BYTES:
        limite_mb = TAMANHO_MAXIMO_MATERIAL_BYTES // (1024 * 1024)
        raise ValidacaoFalhou(f"Arquivo maior que o limite de {limite_mb}MB.")

    material = MaterialOferta(
        tenant_id=tenant_id,
        oferta_id=oferta_id,
        nome_arquivo=nome_arquivo,
        tipo_mime=tipo_mime,
        conteudo=conteudo,
        tamanho_bytes=len(conteudo),
    )
    db.add(material)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "material_enviado", "oferta", oferta_id, ator_id, {"nome_arquivo": nome_arquivo}
    )
    db.commit()
    db.refresh(material)
    return material


def obter_material(db: Session, tenant_id: str, oferta_id: int, material_id: int) -> MaterialOferta:
    material = db.query(MaterialOferta).filter_by(id=material_id, oferta_id=oferta_id, tenant_id=tenant_id).one_or_none()
    if material is None:
        raise NaoEncontrado(f"Material {material_id} não encontrado")
    return material
