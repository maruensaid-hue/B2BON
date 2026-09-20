from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.rede_social import (
    AbrirSalaRequestSchema,
    AtualizarPerfilRequestSchema,
    CanalSalaSchema,
    ComentarioPostSchema,
    ConexaoEmpresaSchema,
    ContagemNaoLidasSchema,
    CriarCanalRequestSchema,
    CriarComentarioRequestSchema,
    CriarIntentRequestSchema,
    DeclararRelacionamentoRequestSchema,
    EmpresaDiretorioSchema,
    EnviarMensagemRequestSchema,
    EnviarMensagemSalaRequestSchema,
    IntentSchema,
    MensagemRedeSocialSchema,
    MensagemSalaSchema,
    NotificacaoRedeSocialSchema,
    PerfilEmpresaSchema,
    PostRedeSocialSchema,
    ReacaoPostSchema,
    RelacionamentoEmpresarialSchema,
    ResponderConexaoRequestSchema,
    SalaCompraSchema,
    SalaCorporativaSchema,
    SeguidorEmpresaSchema,
    SeguirRequestSchema,
    SolicitarConexaoRequestSchema,
    VincularNegocioRequestSchema,
)
from app.services import (
    intent_service,
    notificacao_rede_social_service,
    post_rede_social_service,
    rede_social_service,
    relacionamento_empresarial_service,
    sala_compra_service,
    sala_corporativa_service,
    seguidor_empresa_service,
)

router = APIRouter(prefix="/rede-social", tags=["rede-social"])


@router.get("/perfil", response_model=PerfilEmpresaSchema)
def obter_perfil(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> PerfilEmpresaSchema:
    return rede_social_service.obter_perfil(db, tenant_id)


@router.put("/perfil", response_model=PerfilEmpresaSchema)
def atualizar_perfil(
    dados: AtualizarPerfilRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PerfilEmpresaSchema:
    return rede_social_service.atualizar_perfil(
        db,
        tenant_id,
        ator_id,
        nome_exibicao=dados.nome_exibicao,
        descricao=dados.descricao,
        setor=dados.setor,
        site=dados.site,
        logo_url=dados.logo_url,
        capa_url=dados.capa_url,
        cnae_principal=dados.cnae_principal,
        porte=dados.porte,
        sede_cidade=dados.sede_cidade,
        sede_uf=dados.sede_uf,
        mercados=dados.mercados,
        produtos_servicos=dados.produtos_servicos,
        tecnologias=dados.tecnologias,
        certificacoes=dados.certificacoes,
        redes_sociais=dados.redes_sociais,
    )


@router.get("/empresas", response_model=list[EmpresaDiretorioSchema])
def listar_empresas(
    setor: str | None = None,
    porte: str | None = None,
    mercado: str | None = None,
    apenas_verificadas: bool = False,
    busca: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[EmpresaDiretorioSchema]:
    """Diretório/vitrine — descobrir empresas para conectar (Onda C). Filtros
    opcionais (master prompt §59 Company Search, Fase 1C)."""
    return rede_social_service.listar_empresas(db, tenant_id, setor, porte, mercado, apenas_verificadas, busca)


@router.post("/conexoes", response_model=ConexaoEmpresaSchema, status_code=201)
def solicitar_conexao(
    dados: SolicitarConexaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConexaoEmpresaSchema:
    return rede_social_service.solicitar_conexao(db, tenant_id, ator_id, dados.tenant_id_destino)


@router.get("/conexoes", response_model=list[ConexaoEmpresaSchema])
def listar_conexoes(
    status: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ConexaoEmpresaSchema]:
    return rede_social_service.listar_conexoes(db, tenant_id, status)


@router.put("/conexoes/{conexao_id}", response_model=ConexaoEmpresaSchema)
def responder_conexao(
    conexao_id: int,
    dados: ResponderConexaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConexaoEmpresaSchema:
    return rede_social_service.responder_conexao(db, tenant_id, ator_id, conexao_id, dados.aceitar)


@router.post("/conexoes/{conexao_id}/desconectar", response_model=ConexaoEmpresaSchema)
def desconectar(
    conexao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConexaoEmpresaSchema:
    """DISCONNECTED (master prompt §43, Fase 2A)."""
    return rede_social_service.desconectar(db, tenant_id, ator_id, conexao_id)


@router.post("/bloquear/{tenant_id_outro}", response_model=ConexaoEmpresaSchema)
def bloquear(
    tenant_id_outro: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConexaoEmpresaSchema:
    """BLOCKED (master prompt §43, Fase 2A)."""
    return rede_social_service.bloquear(db, tenant_id, ator_id, tenant_id_outro)


@router.post("/conexoes/{conexao_id}/desbloquear", response_model=ConexaoEmpresaSchema)
def desbloquear(
    conexao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConexaoEmpresaSchema:
    return rede_social_service.desbloquear(db, tenant_id, ator_id, conexao_id)


@router.post("/seguir", response_model=SeguidorEmpresaSchema, status_code=201)
def seguir(
    dados: SeguirRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> SeguidorEmpresaSchema:
    """FOLLOWING (master prompt §43, Fase 2A) — independente do status
    de conexão."""
    return seguidor_empresa_service.seguir(db, tenant_id, ator_id, dados.tenant_id_seguido)


@router.delete("/seguir/{tenant_id_seguido}", status_code=204)
def deixar_de_seguir(
    tenant_id_seguido: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    seguidor_empresa_service.deixar_de_seguir(db, tenant_id, ator_id, tenant_id_seguido)


@router.post("/mensagens", response_model=MensagemRedeSocialSchema, status_code=201)
def enviar_mensagem(
    dados: EnviarMensagemRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> MensagemRedeSocialSchema:
    """Só entre empresas já conectadas (Onda C)."""
    return rede_social_service.enviar_mensagem(db, tenant_id, ator_id, dados.tenant_id_destinatario, dados.texto)


@router.get("/mensagens/{com_tenant_id}", response_model=list[MensagemRedeSocialSchema])
def listar_conversa(
    com_tenant_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[MensagemRedeSocialSchema]:
    return rede_social_service.listar_conversa(db, tenant_id, com_tenant_id)


@router.post("/mensagens/{mensagem_id}/marcar-lida", response_model=MensagemRedeSocialSchema)
def marcar_lida(
    mensagem_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> MensagemRedeSocialSchema:
    return rede_social_service.marcar_lida(db, tenant_id, mensagem_id)


@router.post("/relacionamentos", response_model=RelacionamentoEmpresarialSchema, status_code=201)
def declarar_relacionamento(
    dados: DeclararRelacionamentoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RelacionamentoEmpresarialSchema:
    """Business Graph foundation (master prompt §40, Fase 1D)."""
    return relacionamento_empresarial_service.declarar(
        db, tenant_id, ator_id, dados.tenant_id_destino, dados.tipo, dados.visibilidade
    )


@router.get("/relacionamentos/{tenant_id_alvo}", response_model=list[RelacionamentoEmpresarialSchema])
def listar_relacionamentos(
    tenant_id_alvo: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[RelacionamentoEmpresarialSchema]:
    return relacionamento_empresarial_service.listar_da_empresa(db, tenant_id, tenant_id_alvo)


@router.post("/relacionamentos/{relacionamento_id}/confirmar", response_model=RelacionamentoEmpresarialSchema)
def confirmar_relacionamento(
    relacionamento_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RelacionamentoEmpresarialSchema:
    return relacionamento_empresarial_service.confirmar(db, tenant_id, ator_id, relacionamento_id)


@router.delete("/relacionamentos/{relacionamento_id}", status_code=204)
def remover_relacionamento(
    relacionamento_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    relacionamento_empresarial_service.remover(db, tenant_id, ator_id, relacionamento_id)


@router.post("/posts", response_model=PostRedeSocialSchema, status_code=201)
async def criar_post(
    texto: str = Form(...),
    link_url: str | None = Form(None),
    arquivo: UploadFile | None = File(None),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PostRedeSocialSchema:
    """Business Feed (master prompt §44-45, Fase 2B) — anexo real de
    foto/vídeo (2026-09-20) via multipart, em vez de URL colada."""
    midia_conteudo = await arquivo.read() if arquivo is not None else None
    midia_tipo_mime = arquivo.content_type if arquivo is not None else None
    return post_rede_social_service.criar(
        db,
        tenant_id,
        ator_id,
        texto,
        None,
        link_url,
        midia_conteudo=midia_conteudo,
        midia_tipo_mime=midia_tipo_mime,
    )


@router.get("/posts", response_model=list[PostRedeSocialSchema])
def listar_feed(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[PostRedeSocialSchema]:
    return post_rede_social_service.listar_feed(db, tenant_id_atual=tenant_id)


@router.get("/posts/{post_id}/midia")
def baixar_midia_post(
    post_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Serve a foto/vídeo anexado (blob comprimido por `midia_service`)
    — sem exigência de tenant específico, mesmo padrão de acesso de
    `listar_comentarios` abaixo: o post já é visível pra toda a rede
    via `listar_feed`, então a mídia dele não é mais restrita que o
    post em si."""
    post = post_rede_social_service.obter_midia(db, post_id)
    return Response(content=post.midia_conteudo, media_type=post.midia_tipo_mime)


@router.delete("/posts/{post_id}", status_code=204)
def excluir_post(
    post_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    post_rede_social_service.excluir(db, tenant_id, ator_id, post_id)


@router.post("/posts/{post_id}/comentarios", response_model=ComentarioPostSchema, status_code=201)
def comentar_post(
    post_id: int,
    dados: CriarComentarioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ComentarioPostSchema:
    """Comentários em post (master prompt §45, Fase 2C)."""
    return post_rede_social_service.comentar(db, tenant_id, ator_id, post_id, dados.texto)


@router.get("/posts/{post_id}/comentarios", response_model=list[ComentarioPostSchema])
def listar_comentarios(
    post_id: int,
    db: Session = Depends(get_db),
) -> list[ComentarioPostSchema]:
    return post_rede_social_service.listar_comentarios(db, post_id)


@router.post("/posts/{post_id}/reagir", response_model=ReacaoPostSchema)
def reagir_post(
    post_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ReacaoPostSchema:
    """Reação toggle em post (master prompt §45, Fase 2C)."""
    return post_rede_social_service.reagir(db, tenant_id, ator_id, post_id)


@router.get("/notificacoes", response_model=list[NotificacaoRedeSocialSchema])
def listar_notificacoes(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[NotificacaoRedeSocialSchema]:
    """Notificações da Rede Social (master prompt §65, Fase 2D)."""
    return notificacao_rede_social_service.listar(db, tenant_id)


@router.get("/notificacoes/contagem-nao-lidas", response_model=ContagemNaoLidasSchema)
def contar_notificacoes_nao_lidas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ContagemNaoLidasSchema:
    return {"total": notificacao_rede_social_service.contar_nao_lidas(db, tenant_id)}


@router.post("/notificacoes/{notificacao_id}/marcar-lida", status_code=204)
def marcar_notificacao_lida(
    notificacao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> None:
    notificacao_rede_social_service.marcar_lida(db, tenant_id, notificacao_id)


@router.post("/notificacoes/marcar-todas-lidas", status_code=204)
def marcar_todas_notificacoes_lidas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> None:
    notificacao_rede_social_service.marcar_todas_lidas(db, tenant_id)


@router.post("/intents", response_model=IntentSchema, status_code=201)
def criar_intent(
    dados: CriarIntentRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> IntentSchema:
    """Business Intent (master prompt §46-47, Fase 3A)."""
    return intent_service.criar(
        db,
        tenant_id,
        ator_id,
        dados.categoria,
        dados.titulo,
        dados.descricao,
        dados.requisitos,
        dados.faixa_orcamento,
        dados.localizacao,
        dados.prazo,
        dados.perfil_fornecedor_desejado,
        dados.visibilidade,
    )


@router.get("/intents", response_model=list[IntentSchema])
def listar_intents(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[IntentSchema]:
    return intent_service.listar(db, tenant_id)


@router.get("/intents/{intent_id}", response_model=IntentSchema)
def obter_intent(
    intent_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> IntentSchema:
    return intent_service.obter_visivel(db, tenant_id, intent_id)


@router.post("/intents/{intent_id}/encerrar", response_model=IntentSchema)
def encerrar_intent(
    intent_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> IntentSchema:
    return intent_service.encerrar(db, tenant_id, ator_id, intent_id)


@router.post("/intents/{intent_id}/atender", response_model=IntentSchema)
def marcar_intent_atendida(
    intent_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> IntentSchema:
    return intent_service.marcar_atendida(db, tenant_id, ator_id, intent_id)


@router.post("/salas", response_model=SalaCorporativaSchema, status_code=201)
def abrir_sala(
    dados: AbrirSalaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> SalaCorporativaSchema:
    """Corporate Room (master prompt §52, Fase 4A)."""
    return sala_corporativa_service.abrir_ou_obter_sala(db, tenant_id, ator_id, dados.tenant_id_alvo)


@router.get("/salas", response_model=list[SalaCorporativaSchema])
def listar_salas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[SalaCorporativaSchema]:
    return sala_corporativa_service.listar_salas(db, tenant_id)


@router.get("/salas/{sala_id}/canais", response_model=list[CanalSalaSchema])
def listar_canais_sala(
    sala_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[CanalSalaSchema]:
    return sala_corporativa_service.listar_canais(db, tenant_id, sala_id)


@router.post("/salas/{sala_id}/canais", response_model=CanalSalaSchema, status_code=201)
def criar_canal_sala(
    sala_id: int,
    dados: CriarCanalRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CanalSalaSchema:
    return sala_corporativa_service.criar_canal(db, tenant_id, ator_id, sala_id, dados.tipo, dados.nome, dados.escopo)


@router.get("/salas/canais/{canal_id}/mensagens", response_model=list[MensagemSalaSchema])
def listar_mensagens_canal(
    canal_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[MensagemSalaSchema]:
    return sala_corporativa_service.listar_mensagens(db, tenant_id, canal_id)


@router.post("/salas/canais/{canal_id}/mensagens", response_model=MensagemSalaSchema, status_code=201)
def enviar_mensagem_canal(
    canal_id: int,
    dados: EnviarMensagemSalaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> MensagemSalaSchema:
    return sala_corporativa_service.enviar_mensagem_sala(
        db, tenant_id, ator_id, canal_id, dados.texto, dados.documento_url
    )


@router.post("/salas/{sala_id}/negocio", response_model=SalaCompraSchema, status_code=201)
def vincular_negocio_sala(
    sala_id: int,
    dados: VincularNegocioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> SalaCompraSchema:
    """Buying Room (master prompt §55, Fase 5A)."""
    return sala_compra_service.vincular_negocio(
        db, tenant_id, ator_id, sala_id, dados.negocio_id, dados.visivel_para_comprador
    )


@router.get("/salas/{sala_id}/negocio", response_model=SalaCompraSchema | None)
def obter_negocio_sala(
    sala_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> SalaCompraSchema | None:
    return sala_compra_service.obter_para_sala(db, tenant_id, sala_id)
