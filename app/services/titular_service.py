import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.notificacao_vendedor import NotificacaoVendedor
from app.models.qualificacao import QualificacaoScore
from app.models.registro_supressao_permanente import RegistroSupressaoPermanente
from app.models.reuniao import Reuniao
from app.models.turno_conversa import TurnoConversa
from app.services import auditoria_service
from app.services.errors import NaoEncontrado


def _normalizar(identificador: str) -> str:
    return identificador.strip().lower()


def _hash_identificador(identificador: str) -> str:
    return hashlib.sha256(_normalizar(identificador).encode()).hexdigest()


def _buscar_decisor(db: Session, tenant_id: str, identificador: str) -> Decisor | None:
    normalizado = _normalizar(identificador)
    return (
        db.query(Decisor)
        .filter(
            Decisor.tenant_id == tenant_id,
            (Decisor.email == normalizado) | (Decisor.telefone == normalizado),
        )
        .first()
    )


def buscar(db: Session, tenant_id: str, identificador: str) -> dict:
    """Busca de titular por identificadores (E9-H3)."""
    decisor = _buscar_decisor(db, tenant_id, identificador)
    if decisor is None:
        return {"encontrado": False}
    return {"encontrado": True, "decisor_id": decisor.id, "conta_id": decisor.conta_id, "nome": decisor.nome}


def exportar(db: Session, tenant_id: str, identificador: str) -> dict:
    """Exportação dos dados tratados sobre o titular (E9-H3)."""
    decisor = _buscar_decisor(db, tenant_id, identificador)
    if decisor is None:
        raise NaoEncontrado("Titular não encontrado para o identificador informado.")

    conta = db.query(Conta).filter_by(id=decisor.conta_id).one()
    conversas = db.query(ConversaQualificacao).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).all()
    turnos: list[TurnoConversa] = []
    for conversa in conversas:
        turnos.extend(db.query(TurnoConversa).filter_by(conversa_id=conversa.id).all())
    mensagens = db.query(Mensagem).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).all()
    reunioes = db.query(Reuniao).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).all()
    qualificacoes = db.query(QualificacaoScore).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).all()

    return {
        "decisor": {
            "id": decisor.id,
            "nome": decisor.nome,
            "cargo": decisor.cargo,
            "email": decisor.email,
            "telefone": decisor.telefone,
            "linkedin_url": decisor.linkedin_url,
        },
        "conta": {"id": conta.id, "nome": conta.nome},
        "turnos_conversa": [
            {"direcao": turno.direcao, "conteudo": turno.conteudo, "criado_em": turno.criado_em.isoformat()}
            for turno in turnos
        ],
        "mensagens": [
            {"canal": mensagem.canal, "conteudo": mensagem.conteudo, "status": mensagem.status}
            for mensagem in mensagens
        ],
        "reunioes": [
            {"id": reuniao.id, "status": reuniao.status, "data_hora": reuniao.data_hora.isoformat()}
            for reuniao in reunioes
        ],
        "qualificacoes": [
            {"score_total": qs.score_total, "criterios": qs.criterios} for qs in qualificacoes
        ],
    }


def _eliminar_decisor(
    db: Session, tenant_id: str, ator_id: str | None, decisor: Decisor, identificador_hash: str, evento: str
) -> None:
    """Núcleo comum de eliminação (E9-H3) — apaga os dados pessoais
    associados e grava só o hash do identificador, para impedir recontato
    futuro do mesmo titular. Usado tanto pelo pedido explícito
    (`eliminar`) quanto pela retenção automática (`expirar_inativos`)."""
    conversas = db.query(ConversaQualificacao).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).all()
    conversa_ids = [conversa.id for conversa in conversas]

    if conversa_ids:
        db.query(TurnoConversa).filter(TurnoConversa.conversa_id.in_(conversa_ids)).delete(
            synchronize_session=False
        )
        db.query(NotificacaoVendedor).filter(NotificacaoVendedor.conversa_id.in_(conversa_ids)).delete(
            synchronize_session=False
        )

    db.query(QualificacaoScore).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).delete(
        synchronize_session=False
    )
    for conversa in conversas:
        db.delete(conversa)

    db.query(Mensagem).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).delete(synchronize_session=False)
    db.query(Reuniao).filter_by(tenant_id=tenant_id, decisor_id=decisor.id).delete(synchronize_session=False)

    decisor_id = decisor.id
    db.delete(decisor)

    db.add(RegistroSupressaoPermanente(tenant_id=tenant_id, identificador_hash=identificador_hash))

    auditoria_service.registrar(
        db, tenant_id, evento, "decisor", decisor_id, ator_id, {"identificador_hash": identificador_hash}
    )


def eliminar(db: Session, tenant_id: str, ator_id: str | None, identificador: str) -> dict:
    """Eliminação por pedido explícito do titular (E9-H3)."""
    decisor = _buscar_decisor(db, tenant_id, identificador)
    if decisor is None:
        raise NaoEncontrado("Titular não encontrado para o identificador informado.")

    identificador_hash = _hash_identificador(identificador)
    _eliminar_decisor(db, tenant_id, ator_id, decisor, identificador_hash, "titular_eliminado")
    db.commit()

    return {"eliminado": True, "identificador_hash": identificador_hash}


def expirar_inativos(db: Session, tenant_id: str, dias: int) -> dict:
    """Retenção automática (raio-X de produção / LGPD): decisores
    prospectados sem nenhuma interação há `dias` são anonimizados sozinhos,
    mesmo sem pedido explícito — sem isto, uma base que cresce via geração
    de listas acumula dado pessoal por tempo indefinido. Nunca expira quem
    virou cliente de fato (`Conta.cliente_desde` setado) — ali a retenção
    tem base legal de execução de contrato, não só legítimo interesse de
    prospecção."""
    # Naive de propósito: as colunas de data do modelo são `DateTime` sem
    # timezone, e o SQLite devolve naive na releitura mesmo quando se
    # grava um valor aware — comparar aware contra o atributo já lido de
    # volta do banco lança TypeError.
    limite = (datetime.now(UTC) - timedelta(days=dias)).replace(tzinfo=None)

    candidatos = (
        db.query(Decisor)
        .join(Conta, Decisor.conta_id == Conta.id)
        .filter(
            Decisor.tenant_id == tenant_id,
            Decisor.criado_em < limite,
            Conta.cliente_desde.is_(None),
        )
        .all()
    )

    expirados = 0
    for decisor in candidatos:
        ultima_interacao = decisor.ultima_interacao_em
        if ultima_interacao is not None and ultima_interacao >= limite:
            continue
        identificador = decisor.email or decisor.telefone or f"decisor-{decisor.id}"
        identificador_hash = _hash_identificador(identificador)
        _eliminar_decisor(db, tenant_id, None, decisor, identificador_hash, "titular_expirado_por_retencao")
        expirados += 1

    db.commit()
    return {"decisores_expirados": expirados}
