"""Gestão da plataforma de API pelo próprio tenant (Fase 3): chaves de
API, webhooks de saída e conexões do Integration Hub. JWT, papel
admin/super_admin, sempre escopado ao tenant do usuário logado."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_usuario_atual
from app.contexts.integrations import contract as integracoes
from app.contexts.map import contract as map_contract
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
    credenciais: dict[str, str] = Field(default_factory=dict, description="Gravadas criptografadas; nunca devolvidas.")
    configuracao: dict[str, str] = Field(default_factory=dict)


class CredenciaisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credenciais: dict[str, str]


class ConexaoSchema(BaseModel):
    """Nunca expõe `credenciais`."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    sistema: str
    nome: str
    status: str
    configuracao: dict
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
    oauth = integracoes.obter_oauth()
    registry = integracoes.obter_registry()
    return [
        {**c.model_dump(mode="json"), "conectavel": registry.conectavel(c.sistema), "oauth": oauth.disponivel(c.sistema),
         "escrita": c.sistema in _SISTEMAS_COM_ESCRITA}
        for c in registry.listar_conectores()
    ]


_SISTEMAS_COM_ESCRITA = frozenset({"salesforce", "hubspot", "pipedrive", "rd_station"})  # = escrita.SISTEMAS_EXTERNOS
# Chaves que só o fluxo OAuth da B2B ON grava (nunca coladas pelo usuário).
_CHAVES_RESERVADAS = frozenset({"oauth_app", "_escrita"})


def _validar_conexao(sistema: str, credenciais: dict, configuracao: dict) -> None:
    try:
        integracoes.obter_registry().validar_conexao(sistema, credenciais, configuracao)
    except ValueError as erro:
        raise ValidacaoFalhou(str(erro)) from erro


def _conexao_do_tenant(db: Session, tenant_id: str, conexao_id: int) -> ConexaoIntegracao:
    conexao = db.query(ConexaoIntegracao).filter_by(id=conexao_id, tenant_id=tenant_id).one_or_none()
    if conexao is None:
        raise NaoEncontrado(f"Conexão {conexao_id} não encontrada")
    return conexao


@router.post("/hub-integracoes/conexoes", response_model=ConexaoSchema, status_code=201)
def criar_conexao(dados: CriarConexaoRequest, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> ConexaoSchema:
    registry = integracoes.obter_registry()
    if registry.obter_conector(dados.sistema) is None:
        raise ValidacaoFalhou(f"Conector desconhecido: {dados.sistema}")
    if not registry.conectavel(dados.sistema):
        raise ValidacaoFalhou(f"O conector {dados.sistema} ainda não está disponível.")
    if _CHAVES_RESERVADAS & set(dados.credenciais):
        raise ValidacaoFalhou("Credenciais de app OAuth da B2B ON só entram pelo botão Conectar.")
    _validar_conexao(dados.sistema, dados.credenciais, dados.configuracao)
    conexao = ConexaoIntegracao(
        tenant_id=usuario.tenant_id, sistema=dados.sistema, nome=dados.nome, status="ativa", configuracao=dados.configuracao,
        credenciais=json.dumps(dados.credenciais) if dados.credenciais else None,
    )
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
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    if not integracoes.obter_registry().conectavel(conexao.sistema):
        raise ValidacaoFalhou(f"O conector {conexao.sistema} está desabilitado.")
    sync = integracoes.obter_sync()
    if entidade not in sync.ENTIDADES:
        raise ValidacaoFalhou(f"Entidade inválida. Válidas: {sorted(sync.ENTIDADES)}")
    return sync.sincronizar(db, conexao, entidade)


@router.put("/hub-integracoes/conexoes/{conexao_id}/credenciais", response_model=ConexaoSchema)
def trocar_credenciais(conexao_id: int, dados: CredenciaisRequest, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> ConexaoSchema:
    """Reconectar (token expirado/revogado). A credencial antiga é
    substituída, não mesclada: nada de segredo velho sobrevivendo."""
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    if _CHAVES_RESERVADAS & set(dados.credenciais):
        raise ValidacaoFalhou("Credenciais de app OAuth da B2B ON só entram pelo botão Conectar.")
    _validar_conexao(conexao.sistema, dados.credenciais, conexao.configuracao or {})
    conexao.credenciais = json.dumps(dados.credenciais)
    conexao.status = "ativa"
    conexao.ultimo_erro = None
    auditoria_service.registrar(db, usuario.tenant_id, "conexao_integracao_credenciais", "conexao_integracao", conexao.id, ator_id, {"sistema": conexao.sistema})
    db.commit()
    db.refresh(conexao)
    return conexao


# --- Escrita no CRM do cliente (D-087) ----------------------------------------------
class EscritaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predator: bool | None = None
    map: bool | None = None
    deduplicar: bool | None = None
    pipeline_id: str | None = Field(default=None, max_length=120)
    estagio_id: str | None = Field(default=None, max_length=120)
    prazo_fechamento_dias: int | None = None
    donos: dict[str, str] | None = None
    campos: dict[str, str | None] | None = None


class StatusConexaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(ativa|pausada)$")


class EnvioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conexao_id: int
    operacao: str
    status: str
    tentativas: int
    resultado: str | None
    ultimo_erro: str | None
    criado_em: datetime | None
    enviado_em: datetime | None
    proxima_tentativa_em: datetime | None


def _escrita(conexao: ConexaoIntegracao) -> dict:
    escrita = integracoes.obter_escrita()
    return {**escrita.config(conexao), "webhook_entrada_ativo": bool(conexao.webhook_token_hash), "sistema": conexao.sistema}


@router.get("/hub-integracoes/conexoes/{conexao_id}/escrita")
def obter_escrita(conexao_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return _escrita(_conexao_do_tenant(db, usuario.tenant_id, conexao_id))


@router.put("/hub-integracoes/conexoes/{conexao_id}/escrita")
def configurar_escrita(conexao_id: int, dados: EscritaRequest, usuario: Usuario = Depends(get_usuario_atual),
                       ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Opt-in explícito por capacidade (PREDATOR → CRM, MAP → CRM) e
    parâmetros da escrita. Desligar vale na hora para os envios pendentes."""
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    if conexao.sistema not in _SISTEMAS_COM_ESCRITA:
        raise ValidacaoFalhou("Este conector não escreve no CRM.")
    escrita = integracoes.obter_escrita()
    novo = {**escrita.config(conexao), **dados.model_dump(exclude_none=True)}
    try:
        novo = escrita.validar_config(conexao.sistema, novo)
    except ValueError as erro:
        raise ValidacaoFalhou(str(erro)) from erro
    conexao.escrita = novo
    auditoria_service.registrar(db, usuario.tenant_id, "conexao_integracao_escrita", "conexao_integracao", conexao.id, ator_id,
                                {k: novo.get(k) for k in ("predator", "map", "deduplicar", "pipeline_id", "estagio_id", "prazo_fechamento_dias")})
    db.commit()
    db.refresh(conexao)
    return _escrita(conexao)


@router.put("/hub-integracoes/conexoes/{conexao_id}/status", response_model=ConexaoSchema)
def alterar_status_conexao(conexao_id: int, dados: StatusConexaoRequest, usuario: Usuario = Depends(get_usuario_atual),
                           ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> ConexaoSchema:
    """Pausar = kill-switch da conexão: nada é lido nem escrito até retomar
    (os envios pendentes esperam, não se perdem)."""
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    conexao.status = dados.status
    if dados.status == "ativa":
        conexao.ultimo_erro = None
    auditoria_service.registrar(db, usuario.tenant_id, "conexao_integracao_status", "conexao_integracao", conexao.id, ator_id, {"status": dados.status})
    db.commit()
    db.refresh(conexao)
    return conexao


def _adapter_da_conexao(db: Session, conexao: ConexaoIntegracao):
    registry = integracoes.obter_registry()
    if conexao.status == "pausada" or not registry.conectavel(conexao.sistema):
        raise ValidacaoFalhou("Conexão pausada ou conector desabilitado.")
    return registry.obter_adapter(db, conexao)


def _ler_crm(chamada):
    """Erros do CRM viram mensagem segura (nunca token nem corpo de resposta)."""
    try:
        return chamada()
    except integracoes.OperacaoNaoSuportada as erro:
        raise ValidacaoFalhou(str(erro)) from erro
    except integracoes.ErroCredencial as erro:
        raise ValidacaoFalhou("O CRM recusou a credencial. Reconecte a integração.") from erro
    except Exception as erro:  # noqa: BLE001
        raise ValidacaoFalhou(f"Não foi possível falar com o CRM agora ({type(erro).__name__}). Tente de novo.") from erro


@router.get("/hub-integracoes/conexoes/{conexao_id}/funis")
def listar_funis(conexao_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    """Funis e estágios do CRM (para escolher onde o PREDATOR cria o negócio)."""
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    adapter = _adapter_da_conexao(db, conexao)

    def _externo(canonico: str) -> str:
        return canonico.split(":", 2)[-1]

    def _listar():
        estagios = adapter.list_stages(conexao.tenant_id)
        return [
            {"id": _externo(p.id), "nome": p.name,
             "estagios": [{"id": _externo(e.id), "nome": e.name} for e in sorted(estagios, key=lambda e: e.order) if e.pipeline_id == p.id and e.stage_type == "OPEN"]}
            for p in adapter.list_pipelines(conexao.tenant_id)
        ]

    return _ler_crm(_listar)


@router.post("/hub-integracoes/conexoes/{conexao_id}/preparar-campos")
def preparar_campos(conexao_id: int, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id),
                    db: Session = Depends(get_db)) -> dict:
    """Cria no CRM os campos próprios da B2B ON (HubSpot, Pipedrive) e grava
    as chaves na conexão. Salesforce/RD Station: o admin cria e informa."""
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    adapter = _adapter_da_conexao(db, conexao)
    campos = _ler_crm(lambda: adapter.preparar_campos(conexao.tenant_id))
    escrita = integracoes.obter_escrita()
    atual = escrita.config(conexao)
    conexao.escrita = {**atual, "campos": {**(atual.get("campos") or {}), **campos.model_dump(exclude_none=True)}}
    auditoria_service.registrar(db, usuario.tenant_id, "conexao_integracao_campos_preparados", "conexao_integracao", conexao.id, ator_id,
                                {"campos": campos.model_dump(exclude_none=True)})
    db.commit()
    return _escrita(conexao)


@router.post("/hub-integracoes/conexoes/{conexao_id}/indice")
def atualizar_indice(conexao_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    """Relê o CRM agora para a deduplicação do PREDATOR (cliente, negócio aberto, opt-out)."""
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    adapter = _adapter_da_conexao(db, conexao)
    return _ler_crm(lambda: integracoes.obter_escrita().atualizar_indice(db, conexao, adapter))


@router.post("/hub-integracoes/conexoes/{conexao_id}/sinais-map")
def publicar_sinais_map(conexao_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    """Calcula o risco das contas-cliente do CRM e enfileira a gravação dos sinais agora."""
    sinais_crm = map_contract.obter_sinais_crm()
    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    if not integracoes.obter_escrita().config(conexao).get("map"):
        raise ValidacaoFalhou("Ligue MAP → CRM nesta conexão primeiro.")
    adapter = _adapter_da_conexao(db, conexao)
    return _ler_crm(lambda: sinais_crm.publicar(db, conexao, adapter))


@router.post("/hub-integracoes/conexoes/{conexao_id}/webhook-entrada")
def gerar_webhook_entrada(conexao_id: int, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id),
                          db: Session = Depends(get_db)) -> dict:
    """URL secreta para o CRM avisar mudanças. Mostrada UMA vez; gerar de
    novo invalida a anterior."""
    from app.core.config import settings

    conexao = _conexao_do_tenant(db, usuario.tenant_id, conexao_id)
    token = integracoes.obter_entrada().gerar_token(db, conexao, ator_id)
    return {"url": f"{settings.url_base_api.rstrip('/')}/hub-integracoes/webhook/{token}"}


@router.delete("/hub-integracoes/conexoes/{conexao_id}/webhook-entrada", status_code=204)
def revogar_webhook_entrada(conexao_id: int, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id),
                            db: Session = Depends(get_db)) -> Response:
    integracoes.obter_entrada().revogar_token(db, _conexao_do_tenant(db, usuario.tenant_id, conexao_id), ator_id)
    return Response(status_code=204)


@router.get("/hub-integracoes/envios", response_model=list[EnvioSchema])
def listar_envios(conexao_id: int | None = None, status: str | None = None, usuario: Usuario = Depends(get_usuario_atual),
                  db: Session = Depends(get_db)) -> list[EnvioSchema]:
    from app.models.integracao_crm import EnvioCrm

    consulta = db.query(EnvioCrm).filter_by(tenant_id=usuario.tenant_id)
    if conexao_id is not None:
        consulta = consulta.filter_by(conexao_id=conexao_id)
    if status:
        consulta = consulta.filter_by(status=status)
    return consulta.order_by(EnvioCrm.id.desc()).limit(100).all()


@router.post("/hub-integracoes/envios/{envio_id}/reprocessar", response_model=EnvioSchema)
def reprocessar_envio(envio_id: int, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id),
                      db: Session = Depends(get_db)) -> EnvioSchema:
    try:
        return integracoes.obter_escrita().reprocessar(db, usuario.tenant_id, envio_id, ator_id)
    except LookupError as erro:
        raise NaoEncontrado(str(erro)) from erro
    except ValueError as erro:
        raise ValidacaoFalhou(str(erro)) from erro


# --- Conectar com 1 clique (OAuth, D-087) -------------------------------------------
class IniciarOauthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1, max_length=100)
    escrita: bool = False
    sandbox: bool = False


class ConcluirOauthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    referencia: str = Field(min_length=20, max_length=100)


@router.post("/hub-integracoes/oauth/{sistema}/iniciar")
def iniciar_oauth(sistema: str, dados: IniciarOauthRequest, usuario: Usuario = Depends(get_usuario_atual)) -> dict:
    oauth = integracoes.obter_oauth()
    if not integracoes.obter_registry().conectavel(sistema):
        raise ValidacaoFalhou(f"O conector {sistema} ainda não está disponível.")
    try:
        return {"url": oauth.iniciar(usuario.tenant_id, usuario.id, sistema, dados.nome, dados.escrita, dados.sandbox)}
    except oauth.ErroOauth as erro:
        raise ValidacaoFalhou(str(erro)) from erro


@router.post("/hub-integracoes/oauth/concluir", response_model=ConexaoSchema, status_code=201)
def concluir_oauth(dados: ConcluirOauthRequest, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id),
                   db: Session = Depends(get_db)) -> ConexaoSchema:
    """Cria a conexão a partir da autorização pendente — só para o MESMO
    usuário que iniciou (anti-CSRF; ver `integrations/oauth.py`)."""
    oauth = integracoes.obter_oauth()
    try:
        sistema, nome, credenciais, escrita = oauth.consumir(db, dados.referencia, usuario.tenant_id, usuario.id)
    except oauth.ErroOauth as erro:
        db.rollback()
        raise ValidacaoFalhou(str(erro)) from erro
    if not integracoes.obter_registry().conectavel(sistema):
        db.rollback()
        raise ValidacaoFalhou(f"O conector {sistema} ainda não está disponível.")
    _validar_conexao(sistema, credenciais, {})
    conexao = ConexaoIntegracao(tenant_id=usuario.tenant_id, sistema=sistema, nome=nome, status="ativa", configuracao={},
                                credenciais=json.dumps(credenciais))
    db.add(conexao)
    db.flush()
    auditoria_service.registrar(db, usuario.tenant_id, "conexao_integracao_criada", "conexao_integracao", conexao.id, ator_id,
                                {"sistema": sistema, "via": "oauth", "escopo_escrita": escrita})
    db.commit()
    db.refresh(conexao)
    return conexao
