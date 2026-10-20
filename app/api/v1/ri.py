"""Documentos de RI de uma conta e seus indicadores (V5.2.1, Fase 5). Sem IA. Acesso pelo mesmo escopo de conta do restante do CRM."""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_escopo_conta_usuario, get_ator_id, get_db, get_tenant_id, limitar_pdf_por_tenant
from app.contexts.predator.contract import ri
from app.integrations import pdf_seguro

router = APIRouter(prefix="/contas/{conta_id}/ri", tags=["ri"], dependencies=[Depends(exigir_escopo_conta_usuario)])


def _usuario(ator_id: str | None) -> int | None:
    return int(ator_id) if ator_id and ator_id.isdigit() else None


class DocumentoPorUrl(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    tipo_documento: str = "outro"
    titulo: str | None = Field(default=None, max_length=200)
    data_publicacao: date | None = None


class ValidacaoIndicador(BaseModel):
    estado: str
    observacao: str | None = Field(default=None, max_length=200)


@router.get("/documentos")
def listar_documentos(conta_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return ri.listar(db, tenant_id, conta_id)


@router.post("/documentos", status_code=201, dependencies=[Depends(limitar_pdf_por_tenant())])
async def enviar_documento(conta_id: int, arquivo: UploadFile = File(...), tipo_documento: str = Form("outro"), titulo: str | None = Form(None),
                           data_publicacao: date | None = Form(None), tenant_id: str = Depends(get_tenant_id),
                           ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """O tipo e a extensão declarados não valem: o conteúdo precisa ser PDF de verdade. O arquivo NÃO é guardado."""
    conteudo = await arquivo.read(pdf_seguro.TAMANHO_MAXIMO_BYTES + 1)
    documento, reprocessado = ri.processar_pdf(db, tenant_id, conta_id, _usuario(ator_id), conteudo, nome_arquivo=arquivo.filename, origem="upload",
                                               tipo_documento=tipo_documento, titulo=titulo, data_publicacao=data_publicacao)
    return {**ri.detalhe(db, tenant_id, conta_id, documento.id), "reprocessado": reprocessado}


@router.post("/documentos/url", status_code=201, dependencies=[Depends(limitar_pdf_por_tenant())])
def enviar_documento_por_url(conta_id: int, dados: DocumentoPorUrl, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                             db: Session = Depends(get_db)) -> dict:
    documento, reprocessado = ri.processar_url(db, tenant_id, conta_id, _usuario(ator_id), dados.url, tipo_documento=dados.tipo_documento,
                                               titulo=dados.titulo, data_publicacao=dados.data_publicacao)
    return {**ri.detalhe(db, tenant_id, conta_id, documento.id), "reprocessado": reprocessado}


@router.get("/documentos/{documento_id}")
def detalhe_documento(conta_id: int, documento_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return ri.detalhe(db, tenant_id, conta_id, documento_id)


@router.post("/documentos/{documento_id}/reprocessar", dependencies=[Depends(limitar_pdf_por_tenant())])
def reprocessar_documento(conta_id: int, documento_id: int, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                          db: Session = Depends(get_db)) -> dict:
    documento, _ = ri.reprocessar(db, tenant_id, conta_id, _usuario(ator_id), documento_id)
    return {**ri.detalhe(db, tenant_id, conta_id, documento.id), "reprocessado": True}


@router.delete("/documentos/{documento_id}", status_code=204)
def excluir_documento(conta_id: int, documento_id: int, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                      db: Session = Depends(get_db)) -> None:
    ri.excluir(db, tenant_id, conta_id, _usuario(ator_id), documento_id)


@router.post("/documentos/{documento_id}/indicadores/{indicador_id}/validar")
def validar_indicador(conta_id: int, documento_id: int, indicador_id: int, dados: ValidacaoIndicador, tenant_id: str = Depends(get_tenant_id),
                      ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    indicador = ri.validar_indicador(db, tenant_id, conta_id, documento_id, indicador_id, dados.estado, _usuario(ator_id), dados.observacao)
    return ri.indicador_dict(indicador)


@router.get("/financeiro")
def financeiro(conta_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    """Indicadores do site e dos documentos de RI, lado a lado e rotulados pela origem, mais os sinais qualitativos."""
    return ri.financeiro_da_conta(db, tenant_id, conta_id)
