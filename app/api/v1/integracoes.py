import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_admin_distribuidor, get_db
from app.models.assinatura_webhook_parceiro import AssinaturaWebhookParceiro
from app.models.chave_api_parceiro import ChaveApiParceiro
from app.models.usuario import Usuario
from app.schemas.parceiro import (
    AssinaturaWebhookCriadaSchema,
    AssinaturaWebhookRequestSchema,
    AssinaturaWebhookSchema,
    ChaveApiCriadaSchema,
    ChaveApiSchema,
    CriarChaveApiRequestSchema,
)
from app.services.errors import NaoEncontrado

router = APIRouter(prefix="/integracoes", tags=["integracoes"], dependencies=[Depends(exigir_admin_distribuidor)])


@router.post("/chaves-api", response_model=ChaveApiCriadaSchema, status_code=201)
def criar_chave_api(
    dados: CriarChaveApiRequestSchema, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_distribuidor)
) -> ChaveApiCriadaSchema:
    """Gera a chave que o sistema do Distribuidor usa em `/parceiros/*`
    (Fase 2 da hierarquia, raio-X). A chave completa só existe nesta
    resposta — o banco guarda só o hash."""
    chave_completa = f"b2bon_{secrets.token_urlsafe(32)}"
    registro = ChaveApiParceiro(
        tenant_id=usuario.tenant_id,
        nome=dados.nome,
        prefixo=chave_completa[:12],
        chave_hash=hashlib.sha256(chave_completa.encode()).hexdigest(),
        criado_por_usuario_id=usuario.id,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return ChaveApiCriadaSchema(
        id=registro.id, nome=registro.nome, prefixo=registro.prefixo, chave=chave_completa, criado_em=registro.criado_em
    )


@router.get("/chaves-api", response_model=list[ChaveApiSchema])
def listar_chaves_api(db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_distribuidor)) -> list[ChaveApiSchema]:
    return db.query(ChaveApiParceiro).filter_by(tenant_id=usuario.tenant_id).order_by(ChaveApiParceiro.criado_em.desc()).all()


@router.delete("/chaves-api/{chave_id}", response_model=ChaveApiSchema)
def revogar_chave_api(
    chave_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_distribuidor)
) -> ChaveApiSchema:
    chave = db.query(ChaveApiParceiro).filter_by(id=chave_id, tenant_id=usuario.tenant_id).one_or_none()
    if chave is None:
        raise NaoEncontrado(f"Chave {chave_id} não encontrada.")
    chave.revogada_em = datetime.now(UTC)
    db.commit()
    db.refresh(chave)
    return chave


@router.put("/webhook", response_model=AssinaturaWebhookCriadaSchema)
def configurar_webhook(
    dados: AssinaturaWebhookRequestSchema, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_distribuidor)
) -> AssinaturaWebhookCriadaSchema:
    """Registra (ou substitui) a assinatura de webhook do Distribuidor —
    gera um segredo novo a cada chamada, mostrado uma vez só aqui."""
    segredo = secrets.token_urlsafe(32)
    assinatura = db.query(AssinaturaWebhookParceiro).filter_by(tenant_id=usuario.tenant_id).one_or_none()
    if assinatura is None:
        assinatura = AssinaturaWebhookParceiro(tenant_id=usuario.tenant_id, url_callback=dados.url_callback, segredo=segredo)
        db.add(assinatura)
    else:
        assinatura.url_callback = dados.url_callback
        assinatura.segredo = segredo
        assinatura.ativa = True
    db.commit()
    db.refresh(assinatura)
    return AssinaturaWebhookCriadaSchema(url_callback=assinatura.url_callback, segredo=segredo, ativa=assinatura.ativa)


@router.get("/webhook", response_model=AssinaturaWebhookSchema)
def obter_webhook(db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_distribuidor)) -> AssinaturaWebhookSchema:
    assinatura = db.query(AssinaturaWebhookParceiro).filter_by(tenant_id=usuario.tenant_id).one_or_none()
    if assinatura is None:
        raise NaoEncontrado("Nenhum webhook configurado.")
    return assinatura


@router.delete("/webhook", response_model=AssinaturaWebhookSchema)
def desativar_webhook(db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin_distribuidor)) -> AssinaturaWebhookSchema:
    assinatura = db.query(AssinaturaWebhookParceiro).filter_by(tenant_id=usuario.tenant_id).one_or_none()
    if assinatura is None:
        raise NaoEncontrado("Nenhum webhook configurado.")
    assinatura.ativa = False
    db.commit()
    db.refresh(assinatura)
    return assinatura
