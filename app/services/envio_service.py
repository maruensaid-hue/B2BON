from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.tarefa_linkedin import TarefaLinkedin
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.email_validation.base import EmailVerificationProvider
from app.services import (
    aprovacao_service,
    atividade_service,
    auditoria_service,
    optout_service,
    rampa_service,
    rastreamento_service,
    reputacao_service,
)
from app.services.errors import RegraNegocioViolada

MAX_TENTATIVAS_ENVIO = 3
JANELA_LIVRE_WHATSAPP_HORAS = 24


def _dentro_da_janela_dias_uteis_e_horario(config: ConfiguracaoEnvio | None) -> bool:
    agora = datetime.now(UTC)
    if agora.weekday() >= 5:  # sábado/domingo — E3-H3
        return False
    if config is None:
        return True
    return config.horario_inicio <= agora.time() <= config.horario_fim


def _processar_whatsapp(mensagem: Mensagem, decisor: Decisor, provider: WhatsAppProvider) -> ResultadoEnvio | None:
    if mensagem.template_id is None:
        fora_da_janela = (
            decisor.ultima_interacao_em is None
            or (datetime.now(UTC) - decisor.ultima_interacao_em).total_seconds()
            > JANELA_LIVRE_WHATSAPP_HORAS * 3600
        )
        if fora_da_janela:
            # Mensagem livre fora da janela de 24h: exige template — adia,
            # não trata como falha (E3-H2).
            return None
        return provider.enviar_texto_livre(decisor.telefone, mensagem.conteudo)
    return provider.enviar_template(decisor.telefone, mensagem.template_id, {})


def _processar_email(
    mensagem: Mensagem, decisor: Decisor, config: ConfiguracaoEnvio | None, provider: EmailProvider
) -> ResultadoEnvio:
    remetente_nome = config.remetente_nome if config else "PREDATOR"
    remetente_email = config.remetente_email if config else "no-reply@predator.local"
    corpo = f"{mensagem.conteudo}\n\n{config.assinatura}" if config else mensagem.conteudo
    pixel_url = rastreamento_service.url_pixel(mensagem.tenant_id, mensagem.id)
    return provider.enviar(decisor.email, "Contato", corpo, remetente_nome, remetente_email, pixel_url)


def processar_pendentes(
    db: Session,
    tenant_id: str,
    whatsapp: WhatsAppProvider,
    email: EmailProvider,
    email_validation: EmailVerificationProvider,
) -> dict:
    """Dispatcher explícito, chamado por cron externo — a arquitetura de
    referência não define fila de jobs; manter isto síncrono e idempotente
    é o que garante determinismo em teste (E3-H2, E3-H3, E10-H1).

    LinkedIn nunca é enviado automaticamente aqui: vira `TarefaLinkedin`
    para execução humana (E3-H4).
    """
    agora = datetime.now(UTC)
    config = db.query(ConfiguracaoEnvio).filter_by(tenant_id=tenant_id).one_or_none()

    candidatas = (
        db.query(Mensagem)
        .filter(
            Mensagem.tenant_id == tenant_id,
            Mensagem.status.in_(["aprovado", "falhou"]),
            Mensagem.tentativas_envio < MAX_TENTATIVAS_ENVIO,
            Mensagem.agendado_para.isnot(None),
            Mensagem.agendado_para <= agora,
        )
        .order_by(Mensagem.agendado_para)
        .all()
    )

    resultado = {
        "enviadas": 0,
        "falhas": 0,
        "adiadas": 0,
        "tarefas_linkedin_criadas": 0,
        "descartadas_email_invalido": 0,
    }

    for mensagem in candidatas:
        decisor = db.query(Decisor).filter_by(id=mensagem.decisor_id).one()

        if optout_service.existe_supressao(db, decisor.id):
            mensagem.status = "cancelado"
            continue

        if mensagem.canal == "linkedin":
            existente = db.query(TarefaLinkedin).filter_by(mensagem_id=mensagem.id).one_or_none()
            if existente is None:
                db.add(
                    TarefaLinkedin(
                        tenant_id=tenant_id,
                        mensagem_id=mensagem.id,
                        decisor_id=decisor.id,
                        texto=mensagem.conteudo,
                        link_perfil=decisor.linkedin_url,
                    )
                )
                resultado["tarefas_linkedin_criadas"] += 1
            continue

        if mensagem.canal == "email" and not _dentro_da_janela_dias_uteis_e_horario(config):
            resultado["adiadas"] += 1
            continue

        if mensagem.canal == "email":
            # Verificação prévia de existência do e-mail — descarte
            # definitivo, não falha/retry nem adiamento (E10-H3).
            verificacao = email_validation.verificar(decisor.email)
            if not verificacao.valido:
                mensagem.status = "cancelado"
                mensagem.motivo_falha = verificacao.motivo
                auditoria_service.registrar(
                    db,
                    tenant_id,
                    "email_invalido_descartado",
                    "mensagem",
                    mensagem.id,
                    None,
                    {"motivo": verificacao.motivo},
                    conta_id=decisor.conta_id,
                    canal=mensagem.canal,
                )
                resultado["descartadas_email_invalido"] += 1
                continue

        if reputacao_service.canal_pausado(db, tenant_id, mensagem.canal):
            # Pausa automática por degradação de reputação (E10-H2) — adia,
            # não falha; cadências já ativas retomam quando o canal reabre.
            resultado["adiadas"] += 1
            continue

        try:
            rampa_service.verificar_e_registrar(db, tenant_id, mensagem.canal)
        except RegraNegocioViolada:
            resultado["adiadas"] += 1
            continue

        if mensagem.canal == "whatsapp":
            envio = _processar_whatsapp(mensagem, decisor, whatsapp)
            if envio is None:
                resultado["adiadas"] += 1
                continue
        else:
            envio = _processar_email(mensagem, decisor, config, email)

        if envio.sucesso:
            aprovacao_service.marcar_enviada(db, tenant_id, mensagem.id)
            atividade_service.registrar(
                db, tenant_id, conta_id=decisor.conta_id, tipo=mensagem.canal,
                descricao=f"Mensagem de cadência enviada ({mensagem.canal})",
            )
            resultado["enviadas"] += 1
        else:
            mensagem.motivo_falha = envio.motivo_falha
            mensagem.tentativas_envio += 1
            mensagem.status = "falhou"
            auditoria_service.registrar(
                db,
                tenant_id,
                "envio_falhou",
                "mensagem",
                mensagem.id,
                None,
                {"motivo": envio.motivo_falha, "tentativas": mensagem.tentativas_envio},
                conta_id=decisor.conta_id,
                canal=mensagem.canal,
            )
            resultado["falhas"] += 1

    db.commit()
    return resultado
