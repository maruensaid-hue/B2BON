from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.conexao_empresa import ConexaoEmpresa
from app.models.mensagem_rede_social import MensagemRedeSocial
from app.models.oferta import Oferta
from app.models.perfil_empresa import PerfilEmpresa
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

_STATUS_CONEXAO_VALIDOS = {"pendente", "aceita", "recusada"}


def garantir_perfil(db: Session, tenant_id: str) -> PerfilEmpresa:
    """Cria um perfil padrão na primeira vez que falta um — mesmo padrão
    de `crm_service.garantir_estagios_padrao` (Onda B). Deixa o sistema
    robusto independente de como o tenant nasceu (script, endpoint
    admin, ou direto em teste)."""
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    if perfil is not None:
        return perfil
    perfil = PerfilEmpresa(tenant_id=tenant_id, nome_exibicao=tenant_id)
    db.add(perfil)
    db.commit()
    db.refresh(perfil)
    return perfil


def criar_perfil_inicial(db: Session, tenant_id: str, razao_social: str) -> PerfilEmpresa:
    """Chamado por `tenant_service.criar_tenant_inicial` — perfil nasce
    com o nome real da empresa, não o slug (Onda C)."""
    perfil = PerfilEmpresa(tenant_id=tenant_id, nome_exibicao=razao_social)
    db.add(perfil)
    db.flush()
    return perfil


def obter_perfil(db: Session, tenant_id: str) -> PerfilEmpresa:
    return garantir_perfil(db, tenant_id)


def atualizar_perfil(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    nome_exibicao: str | None = None,
    descricao: str | None = None,
    setor: str | None = None,
    site: str | None = None,
) -> PerfilEmpresa:
    perfil = garantir_perfil(db, tenant_id)
    if nome_exibicao is not None:
        perfil.nome_exibicao = nome_exibicao
    if descricao is not None:
        perfil.descricao = descricao
    if setor is not None:
        perfil.setor = setor
    if site is not None:
        perfil.site = site

    auditoria_service.registrar(db, tenant_id, "perfil_empresa_atualizado", "perfil_empresa", perfil.id, ator_id, {})
    db.commit()
    db.refresh(perfil)
    return perfil


def _status_conexao_com(db: Session, tenant_id_atual: str, tenant_id_outro: str) -> str:
    conexao = (
        db.query(ConexaoEmpresa)
        .filter(
            (
                (ConexaoEmpresa.tenant_id_origem == tenant_id_atual)
                & (ConexaoEmpresa.tenant_id_destino == tenant_id_outro)
            )
            | (
                (ConexaoEmpresa.tenant_id_origem == tenant_id_outro)
                & (ConexaoEmpresa.tenant_id_destino == tenant_id_atual)
            )
        )
        .one_or_none()
    )
    if conexao is None:
        return "nenhuma"
    if conexao.status == "aceita":
        return "aceita"
    if conexao.status == "pendente":
        return "pendente_enviada" if conexao.tenant_id_origem == tenant_id_atual else "pendente_recebida"
    return "nenhuma"  # recusada volta a poder ser solicitada


def listar_empresas(db: Session, tenant_id_atual: str) -> list[dict]:
    """Diretório/vitrine da Rede Social B2B (Onda C) — todos os perfis
    exceto o do próprio tenant, com status de conexão e oferta principal
    (reaproveitada do PREDATOR, E1-H2, sem duplicar dado)."""
    garantir_perfil(db, tenant_id_atual)
    perfis = db.query(PerfilEmpresa).filter(PerfilEmpresa.tenant_id != tenant_id_atual).all()

    resultado = []
    for perfil in perfis:
        oferta = (
            db.query(Oferta).filter_by(tenant_id=perfil.tenant_id, ativo=True).order_by(Oferta.id).first()
        )
        resultado.append(
            {
                "perfil": perfil,
                "status_conexao": _status_conexao_com(db, tenant_id_atual, perfil.tenant_id),
                "oferta_principal": {"nome": oferta.nome, "descricao": oferta.descricao} if oferta else None,
            }
        )
    return resultado


def solicitar_conexao(db: Session, tenant_id_origem: str, ator_id: str | None, tenant_id_destino: str) -> ConexaoEmpresa:
    if tenant_id_origem == tenant_id_destino:
        raise ValidacaoFalhou("Não é possível conectar com o próprio tenant.")

    existente = (
        db.query(ConexaoEmpresa)
        .filter(
            (
                (ConexaoEmpresa.tenant_id_origem == tenant_id_origem)
                & (ConexaoEmpresa.tenant_id_destino == tenant_id_destino)
            )
            | (
                (ConexaoEmpresa.tenant_id_origem == tenant_id_destino)
                & (ConexaoEmpresa.tenant_id_destino == tenant_id_origem)
            )
        )
        .one_or_none()
    )
    if existente is not None and existente.status in ("pendente", "aceita"):
        raise RegraNegocioViolada("Já existe uma conexão pendente ou aceita com este tenant.")

    if existente is not None:  # estava "recusada" — reabre a solicitação
        existente.tenant_id_origem = tenant_id_origem
        existente.tenant_id_destino = tenant_id_destino
        existente.status = "pendente"
        existente.respondida_em = None
        conexao = existente
    else:
        conexao = ConexaoEmpresa(tenant_id_origem=tenant_id_origem, tenant_id_destino=tenant_id_destino, status="pendente")
        db.add(conexao)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id_origem, "conexao_solicitada", "conexao_empresa", conexao.id, ator_id, {"tenant_id_destino": tenant_id_destino}
    )
    db.commit()
    db.refresh(conexao)
    return conexao


def responder_conexao(db: Session, tenant_id: str, ator_id: str | None, conexao_id: int, aceitar: bool) -> ConexaoEmpresa:
    conexao = db.query(ConexaoEmpresa).filter_by(id=conexao_id).one_or_none()
    if conexao is None or conexao.tenant_id_destino != tenant_id:
        raise NaoEncontrado(f"Conexão {conexao_id} não encontrada")
    if conexao.status != "pendente":
        raise RegraNegocioViolada("Só é possível responder conexões pendentes.")

    conexao.status = "aceita" if aceitar else "recusada"
    conexao.respondida_em = datetime.now(UTC)

    auditoria_service.registrar(
        db, tenant_id, "conexao_respondida", "conexao_empresa", conexao.id, ator_id, {"aceitar": aceitar}
    )
    db.commit()
    db.refresh(conexao)
    return conexao


def listar_conexoes(db: Session, tenant_id: str, status: str | None = None) -> list[ConexaoEmpresa]:
    query = db.query(ConexaoEmpresa).filter(
        (ConexaoEmpresa.tenant_id_origem == tenant_id) | (ConexaoEmpresa.tenant_id_destino == tenant_id)
    )
    if status is not None:
        if status not in _STATUS_CONEXAO_VALIDOS:
            raise ValidacaoFalhou(f"Status de conexão inválido: {status}")
        query = query.filter(ConexaoEmpresa.status == status)
    return query.order_by(ConexaoEmpresa.id.desc()).all()


def _conexao_aceita_entre(db: Session, tenant_a: str, tenant_b: str) -> bool:
    return (
        db.query(ConexaoEmpresa)
        .filter(
            ConexaoEmpresa.status == "aceita",
            (
                ((ConexaoEmpresa.tenant_id_origem == tenant_a) & (ConexaoEmpresa.tenant_id_destino == tenant_b))
                | ((ConexaoEmpresa.tenant_id_origem == tenant_b) & (ConexaoEmpresa.tenant_id_destino == tenant_a))
            ),
        )
        .one_or_none()
        is not None
    )


def enviar_mensagem(
    db: Session, tenant_id_remetente: str, ator_id: str | None, tenant_id_destinatario: str, texto: str
) -> MensagemRedeSocial:
    """Só é possível trocar mensagem entre empresas já conectadas — mesmo
    espírito do LinkedIn (Onda C)."""
    if not _conexao_aceita_entre(db, tenant_id_remetente, tenant_id_destinatario):
        raise RegraNegocioViolada("É preciso ter uma conexão aceita com este tenant antes de enviar mensagens.")

    mensagem = MensagemRedeSocial(
        tenant_id_remetente=tenant_id_remetente,
        tenant_id_destinatario=tenant_id_destinatario,
        usuario_remetente_id=int(ator_id) if ator_id else None,
        texto=texto,
    )
    db.add(mensagem)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id_remetente, "mensagem_rede_social_enviada", "mensagem_rede_social", mensagem.id, ator_id,
        {"tenant_id_destinatario": tenant_id_destinatario},
    )
    db.commit()
    db.refresh(mensagem)
    return mensagem


def listar_conversa(db: Session, tenant_id: str, com_tenant_id: str) -> list[MensagemRedeSocial]:
    return (
        db.query(MensagemRedeSocial)
        .filter(
            (
                (MensagemRedeSocial.tenant_id_remetente == tenant_id)
                & (MensagemRedeSocial.tenant_id_destinatario == com_tenant_id)
            )
            | (
                (MensagemRedeSocial.tenant_id_remetente == com_tenant_id)
                & (MensagemRedeSocial.tenant_id_destinatario == tenant_id)
            )
        )
        .order_by(MensagemRedeSocial.criado_em)
        .all()
    )


def marcar_lida(db: Session, tenant_id: str, mensagem_id: int) -> MensagemRedeSocial:
    mensagem = db.query(MensagemRedeSocial).filter_by(id=mensagem_id, tenant_id_destinatario=tenant_id).one_or_none()
    if mensagem is None:
        raise NaoEncontrado(f"Mensagem {mensagem_id} não encontrada")
    if mensagem.lida_em is None:
        mensagem.lida_em = datetime.now(UTC)
    db.commit()
    db.refresh(mensagem)
    return mensagem
