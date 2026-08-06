import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.graph.client import Neo4jClient
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.indicacao import Indicacao
from app.models.reuniao import Reuniao
from app.providers.calendar.base import CalendarProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.crm.base import CrmProvider
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

_SEPARADOR = ":"
JANELA_PROPOSTA_HORAS = 72
DURACAO_PADRAO_MINUTOS = 30


def gerar_token_reagendamento(tenant_id: str, reuniao_id: int) -> str:
    payload = f"{tenant_id}{_SEPARADOR}{reuniao_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR}{assinatura}"


def _validar_token_reagendamento(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de reagendamento inválido.")
    tenant_id, reuniao_id_str, assinatura = partes
    try:
        reuniao_id = int(reuniao_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de reagendamento inválido.") from erro

    esperado = gerar_token_reagendamento(tenant_id, reuniao_id).rsplit(_SEPARADOR, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de reagendamento inválido.")
    return tenant_id, reuniao_id


def obter(db: Session, tenant_id: str, reuniao_id: int) -> Reuniao:
    reuniao = db.query(Reuniao).filter_by(id=reuniao_id, tenant_id=tenant_id).one_or_none()
    if reuniao is None:
        raise NaoEncontrado(f"Reunião {reuniao_id} não encontrada")
    return reuniao


def listar(
    db: Session, tenant_id: str, status: str | None = None, conta_id: int | None = None
) -> list[dict]:
    """Não existia rota de listagem — só ações por id (Onda J: faltava tela
    de Reuniões no frontend, esse é o endpoint que a alimenta). Nome de
    conta/decisor junto (mesmo padrão de `aprovacao_service.listar_fila`)
    — a tela não deveria mostrar só IDs crus."""
    query = (
        db.query(Reuniao, Conta, Decisor)
        .join(Conta, Reuniao.conta_id == Conta.id)
        .join(Decisor, Reuniao.decisor_id == Decisor.id)
        .filter(Reuniao.tenant_id == tenant_id)
    )
    if status is not None:
        query = query.filter(Reuniao.status == status)
    if conta_id is not None:
        query = query.filter(Reuniao.conta_id == conta_id)

    return [
        {
            "id": reuniao.id,
            "tenant_id": reuniao.tenant_id,
            "conta_id": reuniao.conta_id,
            "conta_nome": conta.nome,
            "decisor_id": reuniao.decisor_id,
            "decisor_nome": decisor.nome,
            "vendedor_id": reuniao.vendedor_id,
            "data_hora": reuniao.data_hora,
            "status": reuniao.status,
            "horarios_propostos": reuniao.horarios_propostos,
            "horario_confirmado": reuniao.horario_confirmado,
            "link_reuniao": reuniao.link_reuniao,
            "qualificada_confirmada": reuniao.qualificada_confirmada,
            "criado_em": reuniao.criado_em,
        }
        for reuniao, conta, decisor in query.order_by(Reuniao.data_hora.desc()).all()
    ]


def obter_por_token(db: Session, token: str) -> Reuniao:
    tenant_id, reuniao_id = _validar_token_reagendamento(token)
    return obter(db, tenant_id, reuniao_id)


def propor_horarios(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    decisor_id: int,
    vendedor_id: str,
    duracao_minutos: int,
    calendar: CalendarProvider,
) -> Reuniao:
    """Integração com a agenda do vendedor e proposta de 3 horários (E6-H1)."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    agora = datetime.now(UTC)
    horarios = calendar.propor_horarios(agora, agora + timedelta(hours=JANELA_PROPOSTA_HORAS), duracao_minutos)
    if len(horarios) < 3:
        raise RegraNegocioViolada("Não foi possível propor 3 horários disponíveis na agenda.")

    reuniao = Reuniao(
        tenant_id=tenant_id,
        conta_id=decisor.conta_id,
        decisor_id=decisor.id,
        vendedor_id=vendedor_id,
        data_hora=horarios[0],
        status="horarios_propostos",
        horarios_propostos=[horario.isoformat() for horario in horarios[:3]],
    )
    db.add(reuniao)
    db.flush()

    auditoria_service.registrar(
        db,
        tenant_id,
        "reuniao_horarios_propostos",
        "reuniao",
        reuniao.id,
        ator_id,
        {"horarios": reuniao.horarios_propostos},
        conta_id=decisor.conta_id,
    )
    db.commit()
    db.refresh(reuniao)
    return reuniao


def _confirmar_interno(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    reuniao: Reuniao,
    horario_escolhido: datetime,
    calendar: CalendarProvider,
    crm: CrmProvider,
    graph: Neo4jClient,
) -> Reuniao:
    conta = db.query(Conta).filter_by(id=reuniao.conta_id).one()
    decisor = db.query(Decisor).filter_by(id=reuniao.decisor_id).one()

    evento = calendar.criar_evento(
        titulo=f"Reunião com {conta.nome}",
        inicio=horario_escolhido,
        fim=horario_escolhido + timedelta(minutes=DURACAO_PADRAO_MINUTOS),
        participantes=[decisor.email] if decisor.email else [],
        descricao=f"Reunião qualificada — {conta.nome}",
    )

    # Nenhuma reunião do motor sem registro no CRM (E6-H2): se o CRM falhar,
    # a exceção propaga e a reunião NÃO é confirmada — guarda análoga ao
    # marcar_enviada (Onda 1) e ao consumir_para_ativacao (Onda 2).
    oportunidade_id = crm.criar_ou_atualizar_oportunidade(
        tenant_id,
        conta.id,
        {
            "origem": "predator",
            "decisor_id": decisor.id,
            "reuniao_id": reuniao.id,
            "data_hora": horario_escolhido.isoformat(),
        },
    )

    reuniao.status = "agendada"
    reuniao.data_hora = horario_escolhido
    reuniao.horario_confirmado = horario_escolhido
    reuniao.link_reuniao = evento.link_reuniao
    reuniao.origem_calendario_id = evento.id_externo
    reuniao.origem_crm_id = oportunidade_id

    # Fecha a cadeia promotor -> indicado -> oportunidade no grafo, se esta
    # conta veio de uma indicação (E11-H3) — gancho automático, sem ação
    # manual duplicada.
    indicacao = db.query(Indicacao).filter_by(tenant_id=tenant_id, conta_gerada_id=conta.id).one_or_none()
    if indicacao is not None:
        graph.registrar_indicacao(tenant_id, indicacao.promotor_decisor_id, conta.id, oportunidade_id=oportunidade_id)
        auditoria_service.registrar(
            db,
            tenant_id,
            "indicacao_vinculada_a_oportunidade",
            "indicacao",
            indicacao.id,
            ator_id,
            {"oportunidade_id": oportunidade_id},
            conta_id=conta.id,
        )

    auditoria_service.registrar(
        db,
        tenant_id,
        "reuniao_confirmada",
        "reuniao",
        reuniao.id,
        ator_id,
        {"horario": horario_escolhido.isoformat(), "oportunidade_crm_id": oportunidade_id},
        conta_id=conta.id,
    )
    db.commit()
    db.refresh(reuniao)
    return reuniao


def confirmar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    reuniao_id: int,
    horario_escolhido: datetime,
    calendar: CalendarProvider,
    crm: CrmProvider,
    graph: Neo4jClient,
) -> Reuniao:
    """Convite enviado com confirmação rastreada (E6-H1); oportunidade
    criada no ato do agendamento, sem ação humana (E6-H2)."""
    reuniao = obter(db, tenant_id, reuniao_id)
    if reuniao.status != "horarios_propostos":
        raise RegraNegocioViolada("Reunião não está aguardando confirmação de horário.")

    propostos = {datetime.fromisoformat(horario) for horario in reuniao.horarios_propostos}
    if horario_escolhido not in propostos:
        raise ValidacaoFalhou("Horário escolhido não está entre os propostos.")

    return _confirmar_interno(db, tenant_id, ator_id, reuniao, horario_escolhido, calendar, crm, graph)


def reagendar_por_token(
    db: Session, token: str, novo_horario: datetime, calendar: CalendarProvider, crm: CrmProvider, graph: Neo4jClient
) -> Reuniao:
    """Reagendamento pelo próprio lead (E6-H1) — endpoint público, o lead
    não é usuário autenticado (mesmo padrão do token de opt-out)."""
    tenant_id, reuniao_id = _validar_token_reagendamento(token)
    reuniao_antiga = obter(db, tenant_id, reuniao_id)

    if reuniao_antiga.origem_calendario_id:
        calendar.cancelar_evento(reuniao_antiga.origem_calendario_id)
    reuniao_antiga.status = "reagendada"
    db.flush()

    nova_reuniao = Reuniao(
        tenant_id=tenant_id,
        conta_id=reuniao_antiga.conta_id,
        decisor_id=reuniao_antiga.decisor_id,
        vendedor_id=reuniao_antiga.vendedor_id,
        data_hora=novo_horario,
        status="horarios_propostos",
        horarios_propostos=[novo_horario.isoformat()],
        reagendado_de_id=reuniao_antiga.id,
    )
    db.add(nova_reuniao)
    db.flush()

    nova_reuniao = _confirmar_interno(db, tenant_id, None, nova_reuniao, novo_horario, calendar, crm, graph)

    auditoria_service.registrar(
        db,
        tenant_id,
        "reuniao_reagendada",
        "reuniao",
        reuniao_antiga.id,
        None,
        {"nova_reuniao_id": nova_reuniao.id},
        conta_id=reuniao_antiga.conta_id,
    )
    db.commit()
    return nova_reuniao


def _enviar_lembrete(
    decisor: Decisor, reuniao: Reuniao, whatsapp: WhatsAppProvider, email: EmailProvider, texto_base: str
) -> None:
    texto = f"{texto_base} Link: {reuniao.link_reuniao or ''}"
    if decisor.telefone:
        whatsapp.enviar_texto_livre(decisor.telefone, texto)
    elif decisor.email:
        email.enviar(decisor.email, "Lembrete de reunião", texto, "PREDATOR", "no-reply@predator.local")


def processar_lembretes(
    db: Session, tenant_id: str, whatsapp: WhatsAppProvider, email: EmailProvider
) -> dict:
    """Lembretes automáticos em D-1 e H-2 para reduzir no-show (E6-H1).

    Dispatcher explícito (mesmo padrão do `envio_service.processar_pendentes`
    da Onda 2) — a arquitetura de referência não define fila de jobs.
    """
    agora = datetime.now(UTC)
    reunioes = db.query(Reuniao).filter_by(tenant_id=tenant_id, status="agendada").all()

    lembretes_d1 = 0
    lembretes_h2 = 0
    for reuniao in reunioes:
        if reuniao.horario_confirmado is None:
            continue
        faltam = reuniao.horario_confirmado - agora
        decisor = db.query(Decisor).filter_by(id=reuniao.decisor_id).one()

        if reuniao.lembrete_d1_enviado_em is None and timedelta(hours=20) <= faltam <= timedelta(hours=28):
            _enviar_lembrete(decisor, reuniao, whatsapp, email, "Lembrete: sua reunião é amanhã.")
            reuniao.lembrete_d1_enviado_em = agora
            lembretes_d1 += 1

        if reuniao.lembrete_h2_enviado_em is None and timedelta(hours=1) <= faltam <= timedelta(hours=3):
            _enviar_lembrete(decisor, reuniao, whatsapp, email, "Lembrete: sua reunião é em 2 horas.")
            reuniao.lembrete_h2_enviado_em = agora
            lembretes_h2 += 1

    db.commit()
    return {"lembretes_d1_enviados": lembretes_d1, "lembretes_h2_enviados": lembretes_h2}


def marcar_resultado(db: Session, tenant_id: str, ator_id: str | None, reuniao_id: int, status: str) -> Reuniao:
    """Status realizado/no-show capturado e refletido na métrica (E6-H2)."""
    if status not in ("realizada", "no_show"):
        raise ValidacaoFalhou("Status inválido — use 'realizada' ou 'no_show'.")

    reuniao = obter(db, tenant_id, reuniao_id)
    reuniao.status = status
    auditoria_service.registrar(
        db, tenant_id, "reuniao_resultado_marcado", "reuniao", reuniao.id, ator_id, {"status": status}, conta_id=reuniao.conta_id
    )
    db.commit()
    db.refresh(reuniao)
    return reuniao


def confirmar_qualificacao(
    db: Session, tenant_id: str, ator_id: str | None, reuniao_id: int, qualificada: bool, motivo: str | None
) -> Reuniao:
    """Prompt pós-reunião de 1 toque; feedback alimenta o refinamento do
    scoring (E6-H3) — grava o rótulo ligado ao score para análise futura."""
    reuniao = obter(db, tenant_id, reuniao_id)
    reuniao.qualificada_confirmada = qualificada
    reuniao.motivo_qualificacao = motivo
    auditoria_service.registrar(
        db,
        tenant_id,
        "reuniao_qualificacao_confirmada",
        "reuniao",
        reuniao.id,
        ator_id,
        {"qualificada": qualificada, "motivo": motivo},
        conta_id=reuniao.conta_id,
    )
    db.commit()
    db.refresh(reuniao)
    return reuniao
