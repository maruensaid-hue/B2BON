from sqlalchemy.orm import Session

from app.models.canal_sala import CanalSala
from app.models.mensagem_sala import MensagemSala
from app.models.perfil_empresa import PerfilEmpresa
from app.models.sala_corporativa import SalaCorporativa
from app.services import auditoria_service, notificacao_rede_social_service
from app.services.errors import NaoAutorizado, NaoEncontrado, RegraNegocioViolada
from app.services.rede_social_service import conexao_aceita_entre

_TIPOS_CANAL_VALIDOS = {
    "GENERAL", "COMMERCIAL", "TECHNICAL", "LEGAL", "PROCUREMENT", "FINANCIAL", "SUPPORT", "CUSTOM",
}


def _nome_empresa(db: Session, tenant_id: str) -> str:
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    return perfil.nome_exibicao if perfil is not None else tenant_id


def _outro_tenant(sala: SalaCorporativa, tenant_id: str) -> str:
    return sala.tenant_id_b if sala.tenant_id_a == tenant_id else sala.tenant_id_a


def _exigir_participante(sala: SalaCorporativa, tenant_id: str) -> None:
    if tenant_id not in (sala.tenant_id_a, sala.tenant_id_b):
        raise NaoAutorizado("Sua empresa não participa desta sala corporativa.")


def _obter_sala(db: Session, tenant_id: str, sala_id: int) -> SalaCorporativa:
    sala = db.query(SalaCorporativa).filter_by(id=sala_id).one_or_none()
    if sala is None:
        raise NaoEncontrado(f"Sala corporativa {sala_id} não encontrada")
    _exigir_participante(sala, tenant_id)
    return sala


def _serializar_sala(db: Session, tenant_id: str, sala: SalaCorporativa) -> dict:
    outro = _outro_tenant(sala, tenant_id)
    return {
        "id": sala.id,
        "tenant_id_alvo": outro,
        "empresa_nome": _nome_empresa(db, outro),
        "criado_em": sala.criado_em,
    }


def abrir_ou_obter_sala(db: Session, tenant_id: str, ator_id: str | None, tenant_id_alvo: str) -> dict:
    """Corporate Room (master prompt §52, Fase 4A) — get-or-create
    normalizado por par (ordem lexicográfica), só entre tenants com
    conexão aceita (mesma precondição da DM). Cria o canal GENERAL
    automaticamente na primeira vez."""
    if tenant_id == tenant_id_alvo:
        raise RegraNegocioViolada("Não é possível abrir uma sala corporativa com a própria empresa.")
    if not conexao_aceita_entre(db, tenant_id, tenant_id_alvo):
        raise RegraNegocioViolada("É preciso ter uma conexão aceita com este tenant antes de abrir uma sala corporativa.")

    tenant_a, tenant_b = sorted((tenant_id, tenant_id_alvo))
    sala = db.query(SalaCorporativa).filter_by(tenant_id_a=tenant_a, tenant_id_b=tenant_b).one_or_none()
    if sala is None:
        sala = SalaCorporativa(tenant_id_a=tenant_a, tenant_id_b=tenant_b)
        db.add(sala)
        db.flush()
        db.add(CanalSala(sala_id=sala.id, tipo="GENERAL", criado_por=tenant_id))
        auditoria_service.registrar(db, tenant_id, "sala_corporativa_criada", "sala_corporativa", sala.id, ator_id, {})
        db.commit()
        db.refresh(sala)
    return _serializar_sala(db, tenant_id, sala)


def listar_salas(db: Session, tenant_id: str) -> list[dict]:
    salas = (
        db.query(SalaCorporativa)
        .filter((SalaCorporativa.tenant_id_a == tenant_id) | (SalaCorporativa.tenant_id_b == tenant_id))
        .order_by(SalaCorporativa.criado_em.desc())
        .all()
    )
    return [_serializar_sala(db, tenant_id, sala) for sala in salas]


def _serializar_canal(canal: CanalSala) -> dict:
    return {
        "id": canal.id,
        "sala_id": canal.sala_id,
        "tipo": canal.tipo,
        "nome": canal.nome,
        "criado_em": canal.criado_em,
    }


def listar_canais(db: Session, tenant_id: str, sala_id: int) -> list[dict]:
    _obter_sala(db, tenant_id, sala_id)
    canais = db.query(CanalSala).filter_by(sala_id=sala_id).order_by(CanalSala.criado_em).all()
    return [_serializar_canal(canal) for canal in canais]


def criar_canal(db: Session, tenant_id: str, ator_id: str | None, sala_id: int, tipo: str, nome: str | None) -> dict:
    _obter_sala(db, tenant_id, sala_id)
    if tipo not in _TIPOS_CANAL_VALIDOS:
        raise RegraNegocioViolada(f"Tipo de canal inválido: {tipo}")
    if tipo == "CUSTOM" and not nome:
        raise RegraNegocioViolada("Um canal CUSTOM precisa de um nome.")

    canal = CanalSala(sala_id=sala_id, tipo=tipo, nome=nome if tipo == "CUSTOM" else None, criado_por=tenant_id)
    db.add(canal)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "canal_sala_criado", "canal_sala", canal.id, ator_id, {"tipo": tipo})
    db.commit()
    db.refresh(canal)
    return _serializar_canal(canal)


def _obter_canal(db: Session, tenant_id: str, canal_id: int) -> tuple[CanalSala, SalaCorporativa]:
    canal = db.query(CanalSala).filter_by(id=canal_id).one_or_none()
    if canal is None:
        raise NaoEncontrado(f"Canal {canal_id} não encontrado")
    sala = _obter_sala(db, tenant_id, canal.sala_id)
    return canal, sala


def _serializar_mensagem(db: Session, mensagem: MensagemSala) -> dict:
    return {
        "id": mensagem.id,
        "canal_id": mensagem.canal_id,
        "tenant_id_remetente": mensagem.tenant_id_remetente,
        "empresa_nome": _nome_empresa(db, mensagem.tenant_id_remetente),
        "texto": mensagem.texto,
        "documento_url": mensagem.documento_url,
        "criado_em": mensagem.criado_em,
    }


def enviar_mensagem_sala(
    db: Session, tenant_id: str, ator_id: str | None, canal_id: int, texto: str, documento_url: str | None
) -> dict:
    canal, sala = _obter_canal(db, tenant_id, canal_id)
    mensagem = MensagemSala(
        canal_id=canal.id,
        tenant_id_remetente=tenant_id,
        usuario_id=int(ator_id) if ator_id else None,
        texto=texto,
        documento_url=documento_url,
    )
    db.add(mensagem)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "mensagem_sala_enviada", "mensagem_sala", mensagem.id, ator_id, {})
    outro = _outro_tenant(sala, tenant_id)
    rotulo_canal = canal.nome if canal.tipo == "CUSTOM" and canal.nome else canal.tipo
    notificacao_rede_social_service.criar(
        db, outro, "sala_mensagem", "mensagem_sala", mensagem.id,
        f"Nova mensagem de {_nome_empresa(db, tenant_id)} na sala corporativa (canal {rotulo_canal}).",
    )
    db.commit()
    db.refresh(mensagem)
    return _serializar_mensagem(db, mensagem)


def listar_mensagens(db: Session, tenant_id: str, canal_id: int) -> list[dict]:
    canal, _sala = _obter_canal(db, tenant_id, canal_id)
    mensagens = (
        db.query(MensagemSala)
        .filter_by(canal_id=canal.id)
        .order_by(MensagemSala.criado_em, MensagemSala.id)
        .all()
    )
    return [_serializar_mensagem(db, mensagem) for mensagem in mensagens]
