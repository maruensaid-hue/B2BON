from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_tenant_id
from app.llm.base import LLMProvider
from app.models.icp import ICP
from app.models.oferta import Oferta
from app.schemas.comunicacao import (
    AmostraResponseSchema,
    ConfiguracaoComunicacaoSchema,
    ConfiguracaoComunicacaoUpsertSchema,
    ValidarTextoRequestSchema,
    ValidarTextoResponseSchema,
)
from app.services import comunicacao_service
from app.services.errors import RegraNegocioViolada

router = APIRouter(prefix="/comunicacao", tags=["comunicacao"])


@router.get("", response_model=ConfiguracaoComunicacaoSchema | None)
def obter_comunicacao(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoComunicacaoSchema | None:
    return comunicacao_service.obter(db, tenant_id)


@router.put("", response_model=ConfiguracaoComunicacaoSchema)
def salvar_comunicacao(
    dados: ConfiguracaoComunicacaoUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoComunicacaoSchema:
    return comunicacao_service.salvar(db, tenant_id, ator_id, dados)


@router.post("/validar-texto", response_model=ValidarTextoResponseSchema)
def validar_texto(
    dados: ValidarTextoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ValidarTextoResponseSchema:
    config = comunicacao_service.obter(db, tenant_id)
    restricoes = config.restricoes if config else []
    violacoes = comunicacao_service.validar_texto(dados.texto, restricoes)
    return ValidarTextoResponseSchema(valido=not violacoes, violacoes=violacoes)


@router.post("/amostra", response_model=AmostraResponseSchema)
def gerar_amostra(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> AmostraResponseSchema:
    config = comunicacao_service.obter(db, tenant_id)
    if config is None:
        raise RegraNegocioViolada("Configure tom e restrições de comunicação antes de gerar amostra.")

    icp = db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).first()
    if icp is None:
        raise RegraNegocioViolada("Sem ICP ativo, o motor não inicia prospecção.")

    oferta = db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).first()
    if oferta is None:
        raise RegraNegocioViolada("Cadastre ao menos uma oferta antes de gerar amostra.")

    mensagens = comunicacao_service.gerar_amostra(db, tenant_id, llm, icp, oferta, config)
    return AmostraResponseSchema(mensagens=mensagens)
