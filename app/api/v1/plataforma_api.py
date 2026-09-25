"""Gestão da plataforma de API pelo próprio tenant (Fase 3): chaves de
API, webhooks de saída e conexões do Integration Hub. JWT, papel
admin/super_admin, sempre escopado ao tenant do usuário logado."""

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_usuario_atual
from app.contexts.integrations import contract as integracoes
from app.contexts.platform.contract import api_keys, webhooks
from app.models.conexao_integracao import ConexaoIntegracao
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

router = APIRouter(tags=["plataforma-api"], dependencies=[Depends(exigir_papel("admin", "super_admin"))])


# --- Chaves de API ---------------------------------------------------------------
class CriarChaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1, max_length=100)
    escopos: list[str]


class ChaveSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    prefixo: str
    escopos: list[str]
    criado_em: datetime | None
    ultimo_uso_em: datetime | None
    revogada_em: datetime | None


class ChaveCriadaSchema(ChaveSchema):
    segredo: str = Field(description="Mostrado uma única vez. Guarde agora.")


@router.get("/chaves-api/escopos")
def escopos_disponiveis() -> list[str]:
    return sorted(api_keys.ESCOPOS)


@router.post("/chaves-api", response_model=ChaveCriadaSchema, status_code=201)
def criar_chave(dados: CriarChaveRequest, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> ChaveCriadaSchema:
    chave, segredo = api_keys.criar(db, usuario.tenant_id, usuario.id, dados.nome, dados.escopos)
    return ChaveCriadaSchema(**ChaveSchema.model_validate(chave).model_dump(), segredo=segredo)


@router.get("/chaves-api", response_model=list[ChaveSchema])
def listar_chaves(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[ChaveSchema]:
    return api_keys.listar(db, usuario.tenant_id)


@router.delete("/chaves-api/{chave_id}", status_code=204)
def revogar_chave(chave_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> Response:
    api_keys.revogar(db, usuario.tenant_id, usuario.id, chave_id)
    return Response(status_code=204)


# --- Webhooks de saída -------------------------------------------------------------
class CriarWebhookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2000)
    eventos: list[str]


class WebhookSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str
    eventos: list[str]
    ativa: bool
    criado_em: datetime | None


class WebhookCriadoSchema(WebhookSchema):
    segredo: str = Field(description="Usado para verificar X-B2BON-Signature. Mostrado uma única vez.")


class EntregaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    evento_id: str
    tipo: str
    status: str
    tentativas: int
    ultimo_status_http: int | None
    ultimo_erro: str | None
    criado_em: datetime | None
    entregue_em: datetime | None


@router.get("/webhooks-saida/eventos")
def eventos_disponiveis() -> list[str]:
    return sorted(webhooks.TIPOS_VALIDOS)


@router.post("/webhooks-saida", response_model=WebhookCriadoSchema, status_code=201)
def criar_webhook(dados: CriarWebhookRequest, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> WebhookCriadoSchema:
    assinatura, segredo = webhooks.criar_assinatura(db, usuario.tenant_id, ator_id, dados.url, dados.eventos)
    return WebhookCriadoSchema(**WebhookSchema.model_validate(assinatura).model_dump(), segredo=segredo)


@router.get("/webhooks-saida", response_model=list[WebhookSchema])
def listar_webhooks(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[WebhookSchema]:
    return webhooks.listar_assinaturas(db, usuario.tenant_id)


@router.delete("/webhooks-saida/{assinatura_id}", status_code=204)
def desativar_webhook(assinatura_id: int, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> Response:
    webhooks.desativar_assinatura(db, usuario.tenant_id, ator_id, assinatura_id)
    return Response(status_code=204)


@router.get("/webhooks-saida/{assinatura_id}/entregas", response_model=list[EntregaSchema])
def listar_entregas(assinatura_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[EntregaSchema]:
    return webhooks.listar_entregas(db, usuario.tenant_id, assinatura_id)


# --- Integration Hub -------------------------------------------------------------
class CriarConexaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sistema: str
    nome: str = Field(min_length=1, max_length=100)


class ConexaoSchema(BaseModel):
    """Nunca expõe `credenciais`."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    sistema: str
    nome: str
    status: str
    criado_em: datetime | None
    ultimo_sync_em: datetime | None
    ultimo_erro: str | None


class ExecucaoSyncSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entidade: str
    status: str
    itens_lidos: int
    paginas: int
    tentativas: int
    iniciado_em: datetime | None
    finalizado_em: datetime | None
    erro: str | None


@router.get("/hub-integracoes/conectores")
def listar_conectores() -> list[dict]:
    return [c.model_dump(mode="json") for c in integracoes.obter_registry().listar_conectores()]


@router.post("/hub-integracoes/conexoes", response_model=ConexaoSchema, status_code=201)
def criar_conexao(dados: CriarConexaoRequest, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> ConexaoSchema:
    registry = integracoes.obter_registry()
    if registry.obter_conector(dados.sistema) is None:
        raise ValidacaoFalhou(f"Conector desconhecido: {dados.sistema}")
    if not registry.conectavel(dados.sistema):
        raise ValidacaoFalhou(f"O conector {dados.sistema} ainda não está disponível.")
    conexao = ConexaoIntegracao(tenant_id=usuario.tenant_id, sistema=dados.sistema, nome=dados.nome, status="ativa", configuracao={})
    db.add(conexao)
    db.flush()
    auditoria_service.registrar(db, usuario.tenant_id, "conexao_integracao_criada", "conexao_integracao", conexao.id, ator_id, {"sistema": dados.sistema})
    db.commit()
    db.refresh(conexao)
    return conexao


@router.get("/hub-integracoes/conexoes", response_model=list[ConexaoSchema])
def listar_conexoes(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[ConexaoSchema]:
    return db.query(ConexaoIntegracao).filter_by(tenant_id=usuario.tenant_id).order_by(ConexaoIntegracao.id).all()


@router.post("/hub-integracoes/conexoes/{conexao_id}/sincronizar/{entidade}", response_model=ExecucaoSyncSchema)
def sincronizar(conexao_id: int, entidade: str, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> ExecucaoSyncSchema:
    conexao = db.query(ConexaoIntegracao).filter_by(id=conexao_id, tenant_id=usuario.tenant_id).one_or_none()
    if conexao is None:
        raise NaoEncontrado(f"Conexão {conexao_id} não encontrada")
    sync = integracoes.obter_sync()
    if entidade not in sync.ENTIDADES:
        raise ValidacaoFalhou(f"Entidade inválida. Válidas: {sorted(sync.ENTIDADES)}")
    return sync.sincronizar(db, conexao, entidade)
