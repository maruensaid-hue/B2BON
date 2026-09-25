from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Body, Depends, File, Form, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_email_provider, get_tenant_id, get_usuario_atual
from app.contexts.network.contract import grafo, identidade, membership, salas
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.schemas.rede_social import (
    DeclararRelacionamentoPorCnpjSchema,
    VisibilidadeDiretorioSchema,
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
    ReagirRequestSchema,
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
    auditoria_service,
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
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> PerfilEmpresaSchema:
    membership.exigir(usuario, "editar_perfil")
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
    email: EmailProvider = Depends(get_email_provider),
) -> ConexaoEmpresaSchema:
    return rede_social_service.solicitar_conexao(db, tenant_id, ator_id, dados.tenant_id_destino, email)


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
    email: EmailProvider = Depends(get_email_provider),
) -> ConexaoEmpresaSchema:
    return rede_social_service.responder_conexao(db, tenant_id, ator_id, conexao_id, dados.aceitar, email)


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
    email: EmailProvider = Depends(get_email_provider),
) -> MensagemRedeSocialSchema:
    """Só entre empresas já conectadas (Onda C)."""
    return rede_social_service.enviar_mensagem(db, tenant_id, ator_id, dados.tenant_id_destinatario, dados.texto, email)


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
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> RelacionamentoEmpresarialSchema:
    """Business Graph foundation (master prompt §40, Fase 1D)."""
    membership.exigir(usuario, "gerenciar_relacionamentos")
    return relacionamento_empresarial_service.declarar(
        db, tenant_id, ator_id, dados.tenant_id_destino, dados.tipo, dados.visibilidade,
        dados.valido_desde, dados.valido_ate,
    )


@router.post("/relacionamentos/por-cnpj", response_model=RelacionamentoEmpresarialSchema, status_code=201)
def declarar_relacionamento_por_cnpj(
    dados: DeclararRelacionamentoPorCnpjSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> RelacionamentoEmpresarialSchema:
    """Company Claim (Fase 7): a empresa citada pode ainda não estar na rede."""
    membership.exigir(usuario, "gerenciar_relacionamentos")
    return relacionamento_empresarial_service.declarar_por_cnpj(
        db, tenant_id, ator_id, dados.cnpj, dados.nome, dados.tipo, dados.visibilidade,
        dados.valido_desde, dados.valido_ate,
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
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> RelacionamentoEmpresarialSchema:
    membership.exigir(usuario, "gerenciar_relacionamentos")
    return relacionamento_empresarial_service.confirmar(db, tenant_id, ator_id, relacionamento_id)


@router.delete("/relacionamentos/{relacionamento_id}", status_code=204)
def remover_relacionamento(
    relacionamento_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> None:
    membership.exigir(usuario, "gerenciar_relacionamentos")
    relacionamento_empresarial_service.remover(db, tenant_id, ator_id, relacionamento_id)


@router.get("/identidade")
def minha_identidade(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    """Company Identity do tenant e identidades não reivindicadas com o mesmo CNPJ."""
    propria = identidade.garantir_do_tenant(db, tenant_id)
    reivindicaveis = identidade.reivindicaveis(db, tenant_id)
    db.commit()
    return {
        "empresa": identidade.como_dict(propria),
        "reivindicaveis": [identidade.como_dict(e) for e in reivindicaveis],
    }


@router.post("/identidades/{empresa_id}/reivindicar")
def reivindicar_identidade(
    empresa_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    """Company Claim (Fase 7): só admin de empresa verificada com o mesmo CNPJ."""
    membership.exigir(usuario, "reivindicar")
    empresa = identidade.reivindicar(db, tenant_id, empresa_id)
    auditoria_service.registrar(db, tenant_id, "identidade_rede_reivindicada", "empresa_rede", empresa_id, ator_id, {})
    db.commit()
    return identidade.como_dict(empresa)


@router.get("/grafo/{empresa_id}")
def grafo_da_empresa(empresa_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    """Business Graph (Fase 7): arestas visíveis para quem consulta."""
    arestas = grafo.arestas_da_empresa(db, tenant_id, empresa_id)
    db.commit()
    return [a.model_dump(mode="json") for a in arestas]


@router.get("/membros")
def membros(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    """Membership (Fase 7): só os membros da própria empresa."""
    return membership.membros(db, tenant_id)


@router.put("/perfil/visibilidade", response_model=PerfilEmpresaSchema)
def alterar_visibilidade_diretorio(
    dados: VisibilidadeDiretorioSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> PerfilEmpresaSchema:
    membership.exigir(usuario, "visibilidade_diretorio")
    perfil = rede_social_service.garantir_perfil(db, tenant_id)
    perfil.visivel_no_diretorio = dados.visivel_no_diretorio
    auditoria_service.registrar(
        db, tenant_id, "perfil_visibilidade_diretorio", "perfil_empresa", perfil.id, ator_id,
        {"visivel_no_diretorio": dados.visivel_no_diretorio},
    )
    db.commit()
    db.refresh(perfil)
    return perfil


@router.post("/posts", response_model=PostRedeSocialSchema, status_code=201)
async def criar_post(
    texto: str = Form(...),
    link_url: str | None = Form(None),
    arquivos: list[UploadFile] = File([]),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PostRedeSocialSchema:
    """Business Feed (master prompt §44-45, Fase 2B) — anexo real de
    foto/vídeo via multipart, em vez de URL colada; várias fotos formam
    um carrossel (2026-09-20), vídeo sempre sozinho."""
    midias = [(await arquivo.read(), arquivo.content_type or "") for arquivo in arquivos]
    return post_rede_social_service.criar(
        db,
        tenant_id,
        ator_id,
        texto,
        None,
        link_url,
        midias=midias,
    )


@router.get("/posts", response_model=list[PostRedeSocialSchema])
def listar_feed(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[PostRedeSocialSchema]:
    return post_rede_social_service.listar_feed(db, tenant_id_atual=tenant_id)


@router.get("/posts/{post_id}/midia/{midia_id}")
def baixar_midia_post(
    post_id: int,
    midia_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Serve uma foto/vídeo do carrossel (blob comprimido por
    `midia_service`) — sem exigência de tenant específico, mesmo
    padrão de acesso de `listar_comentarios` abaixo: o post já é
    visível pra toda a rede via `listar_feed`, então a mídia dele não
    é mais restrita que o post em si."""
    midia = post_rede_social_service.obter_midia(db, post_id, midia_id)
    return Response(content=midia.conteudo, media_type=midia.tipo_mime)


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
    email: EmailProvider = Depends(get_email_provider),
) -> ComentarioPostSchema:
    """Comentários em post (master prompt §45, Fase 2C)."""
    return post_rede_social_service.comentar(db, tenant_id, ator_id, post_id, dados.texto, email)


@router.get("/posts/{post_id}/comentarios", response_model=list[ComentarioPostSchema])
def listar_comentarios(
    post_id: int,
    db: Session = Depends(get_db),
) -> list[ComentarioPostSchema]:
    return post_rede_social_service.listar_comentarios(db, post_id)


@router.post("/posts/{post_id}/reagir", response_model=ReacaoPostSchema)
def reagir_post(
    post_id: int,
    dados: ReagirRequestSchema = ReagirRequestSchema(),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> ReacaoPostSchema:
    """Reação em post (master prompt §45, Fase 2C; 9 tipos desde
    2026-09-20 — curtir + 8 emojis) — troca a reação existente do
    tenant, não soma."""
    return post_rede_social_service.reagir(db, tenant_id, ator_id, post_id, tipo=dados.tipo, email_provider=email)


@router.post("/posts/{post_id}/compartilhar", response_model=PostRedeSocialSchema, status_code=201)
def compartilhar_post(
    post_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> PostRedeSocialSchema:
    """Repost simples no feed do próprio tenant (2026-09-20) — sempre
    aponta pra raiz, um tenant só compartilha o mesmo post uma vez."""
    return post_rede_social_service.compartilhar(db, tenant_id, ator_id, post_id, email)


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
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[CanalSalaSchema]:
    salas.acesso(db, sala_id, usuario)
    return sala_corporativa_service.listar_canais(db, tenant_id, sala_id)


@router.post("/salas/{sala_id}/canais", response_model=CanalSalaSchema, status_code=201)
def criar_canal_sala(
    sala_id: int,
    dados: CriarCanalRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> CanalSalaSchema:
    salas.acesso(db, sala_id, usuario, escrita=True)
    return sala_corporativa_service.criar_canal(db, tenant_id, ator_id, sala_id, dados.tipo, dados.nome, dados.escopo)


@router.get("/salas/canais/{canal_id}/mensagens", response_model=list[MensagemSalaSchema])
def listar_mensagens_canal(
    canal_id: int,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[MensagemSalaSchema]:
    salas.acesso_pelo_canal(db, canal_id, usuario)
    return sala_corporativa_service.listar_mensagens(db, tenant_id, canal_id)


@router.post("/salas/canais/{canal_id}/mensagens", response_model=MensagemSalaSchema, status_code=201)
def enviar_mensagem_canal(
    canal_id: int,
    dados: EnviarMensagemSalaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> MensagemSalaSchema:
    salas.acesso_pelo_canal(db, canal_id, usuario, escrita=True)
    return sala_corporativa_service.enviar_mensagem_sala(
        db, tenant_id, ator_id, canal_id, dados.texto, dados.documento_url, email
    )


@router.post("/salas/{sala_id}/negocio", response_model=SalaCompraSchema, status_code=201)
def vincular_negocio_sala(
    sala_id: int,
    dados: VincularNegocioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> SalaCompraSchema:
    salas.acesso(db, sala_id, usuario, escrita=True)
    """Buying Room (master prompt §55, Fase 5A)."""
    return sala_compra_service.vincular_negocio(
        db, tenant_id, ator_id, sala_id, dados.negocio_id, dados.visivel_para_comprador
    )


@router.get("/salas/{sala_id}/negocio", response_model=SalaCompraSchema | None)
def obter_negocio_sala(
    sala_id: int,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> SalaCompraSchema | None:
    salas.acesso(db, sala_id, usuario)
    return sala_compra_service.obter_para_sala(db, tenant_id, sala_id)


# --- Corporate Rooms & Buying Rooms (Fase 11) -------------------------------------


class ParticipanteEntrada(BaseModel):
    usuario_id: int
    papel: Literal["EDITOR", "LEITOR"] = "EDITOR"


class TarefaEntrada(BaseModel):
    titulo: str = Field(min_length=2, max_length=300)
    descricao: str | None = None
    escopo: Literal["compartilhado", "interno"] = "compartilhado"
    responsavel_tenant_id: str | None = None
    responsavel_usuario_id: int | None = None
    prazo: date | None = None


class ReuniaoEntrada(BaseModel):
    titulo: str = Field(min_length=2, max_length=300)
    inicio: datetime
    fim: datetime | None = None
    link: str | None = None
    pauta: str | None = None
    escopo: Literal["compartilhado", "interno"] = "compartilhado"


class StakeholderEntrada(BaseModel):
    nome: str = Field(min_length=2)
    cargo: str | None = None
    lado: Literal["VENDEDOR", "COMPRADOR"]
    papel: str = "UNKNOWN"
    notas: str | None = None
    escopo: Literal["compartilhado", "interno"] = "interno"


class CompartilharNegocioEntrada(BaseModel):
    titulo_compartilhado: str | None = Field(default=None, max_length=200)
    fase_compartilhada: str | None = None


@router.get("/salas/{sala_id}/workspace")
def workspace_sala(sala_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    """Corporate/Buying Room (Fase 11): tudo que ESTA empresa pode ver na sala."""
    return salas.workspace(db, sala_id, usuario)


@router.get("/salas/{sala_id}/participantes")
def participantes_sala(sala_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    return salas.listar_participantes(db, sala_id, usuario)


@router.put("/salas/{sala_id}/participantes")
def definir_participantes_sala(sala_id: int, dados: list[ParticipanteEntrada], usuario: Usuario = Depends(get_usuario_atual),
                               db: Session = Depends(get_db)) -> list[dict]:
    return salas.definir_participantes(db, sala_id, usuario, [d.model_dump() for d in dados])


@router.post("/salas/{sala_id}/documentos", status_code=201)
async def enviar_documento_sala(
    sala_id: int,
    escopo: Literal["compartilhado", "interno"] = Form("compartilhado"),
    canal_id: int | None = Form(None),
    arquivo: UploadFile = File(...),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    documento = salas.adicionar_documento(db, sala_id, usuario, arquivo.filename or "documento", arquivo.content_type or "",
                                          await arquivo.read(), escopo, canal_id)
    return {"id": documento.id, "nome_arquivo": documento.nome_arquivo, "escopo": documento.escopo, "sha256": documento.sha256}


@router.get("/salas/documentos/{documento_id}/arquivo")
def baixar_documento_sala(documento_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> Response:
    documento = salas.obter_documento(db, documento_id, usuario)
    return Response(content=documento.conteudo, media_type=documento.tipo_mime,
                    headers={"Content-Disposition": f'attachment; filename="documento-{documento.id}"', "X-Content-SHA256": documento.sha256})


@router.post("/salas/{sala_id}/tarefas", status_code=201)
def criar_tarefa_sala(sala_id: int, dados: TarefaEntrada, usuario: Usuario = Depends(get_usuario_atual),
                      db: Session = Depends(get_db)) -> dict:
    tarefa = salas.criar_tarefa(db, sala_id, usuario, dados.model_dump())
    return {"id": tarefa.id, "titulo": tarefa.titulo, "escopo": tarefa.escopo, "status": tarefa.status}


@router.patch("/salas/tarefas/{tarefa_id}")
def atualizar_tarefa_sala(tarefa_id: int, status: Literal["ABERTA", "CONCLUIDA", "CANCELADA"] = Body(..., embed=True),
                          usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    tarefa = salas.atualizar_tarefa(db, tarefa_id, usuario, status)
    return {"id": tarefa.id, "status": tarefa.status}


@router.post("/salas/{sala_id}/reunioes", status_code=201)
def agendar_reuniao_sala(sala_id: int, dados: ReuniaoEntrada, usuario: Usuario = Depends(get_usuario_atual),
                         db: Session = Depends(get_db)) -> dict:
    reuniao = salas.agendar_reuniao(db, sala_id, usuario, dados.model_dump())
    return {"id": reuniao.id, "titulo": reuniao.titulo, "escopo": reuniao.escopo, "inicio": reuniao.inicio}


@router.post("/salas/{sala_id}/stakeholders", status_code=201)
def adicionar_stakeholder_sala(sala_id: int, dados: StakeholderEntrada, usuario: Usuario = Depends(get_usuario_atual),
                               db: Session = Depends(get_db)) -> dict:
    s = salas.adicionar_stakeholder(db, sala_id, usuario, dados.model_dump())
    return {"id": s.id, "nome": s.nome, "papel": s.papel, "lado": s.lado, "escopo": s.escopo}


@router.put("/salas/{sala_id}/negocio/compartilhado")
def compartilhar_negocio_sala(sala_id: int, dados: CompartilharNegocioEntrada, usuario: Usuario = Depends(get_usuario_atual),
                              db: Session = Depends(get_db)) -> dict | None:
    """Buying Room: o que o comprador vê (título e fase), separado do CRM."""
    return salas.compartilhar_negocio(db, sala_id, usuario, dados.titulo_compartilhado, dados.fase_compartilhada)
