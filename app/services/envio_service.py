import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.integrations import contract as integracoes
from app.contexts.predator import contract as predator_contract
from app.core.config import settings
from app.models.conta import Conta
from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.decisor import Decisor
from app.models.aprovacao import Aprovacao
from app.models.mensagem import Mensagem
from app.models.tarefa_linkedin import TarefaLinkedin
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.email_validation.base import EmailVerificationProvider
from app.services import (
    aprovacao_service,
    atividade_service,
    auditoria_service,
    bloqueio_contato_service,
    campanha_personalizacao,
    optout_service,
    portao_envio_service,
    rampa_service,
    rastreamento_service,
    reputacao_service,
    whatsapp_service,
)
from app.services.errors import RegraNegocioViolada

_VARIAVEL = re.compile(r"\{\{\s*(nome|empresa|cargo)\s*\}\}", re.IGNORECASE)


def _renderizar_variaveis(texto: str | None, decisor: Decisor, empresa: str | None) -> str | None:
    """`{{nome}}` (primeiro nome), `{{empresa}}` e `{{cargo}}` — as variáveis que a edição na fila de aprovação aceita — trocadas pelos
    dados do decisor na hora do envio. Antes disto elas saíam literais na cadência."""
    if not texto or "{{" not in texto:
        return texto
    valores = {"nome": campanha_personalizacao.primeiro_nome(decisor.nome), "empresa": (empresa or "").strip() or campanha_personalizacao.EMPRESA_PADRAO,
               "cargo": (decisor.cargo or "").strip()}
    return _VARIAVEL.sub(lambda m: valores[m.group(1).lower()], texto)


def _devolver_para_revisao(db: Session, tenant_id: str, mensagem: Mensagem, motivo: str) -> None:
    """Mensagem com erro que nenhuma aprovação conserta sozinha (campo não preenchido, corpo vazio): volta para a fila de aprovação com
    o motivo, em vez de sair ou de ser descartada em silêncio."""
    mensagem.status = "aguardando_aprovacao"
    mensagem.motivo_falha = motivo
    aprovacao = db.query(Aprovacao).filter_by(tenant_id=tenant_id, mensagem_id=mensagem.id).order_by(Aprovacao.id.desc()).first()
    if aprovacao is not None:
        aprovacao.status, aprovacao.decidido_em = "pendente", None
    auditoria_service.registrar(db, tenant_id, "envio_devolvido_para_revisao", "mensagem", mensagem.id, None, {"motivo": motivo},
                                canal=mensagem.canal)

MAX_TENTATIVAS_ENVIO = 3
JANELA_LIVRE_WHATSAPP_HORAS = 24


def _dentro_da_janela_dias_uteis_e_horario(config: ConfiguracaoEnvio | None) -> bool:
    agora = datetime.now(UTC)
    if agora.weekday() >= 5:  # sábado/domingo — E3-H3
        return False
    if config is None:
        return True
    return config.horario_inicio <= agora.time() <= config.horario_fim


def _variavel_botao_whatsapp(db: Session, decisor: Decisor) -> str | None:
    """Número de WhatsApp pessoal do vendedor responsável pela conta do
    decisor — raio-X 2026-09-15, preenche a URL dinâmica do botão de
    redirecionamento do template ("https://wa.me/{{1}}"), cadastrado pelo
    próprio vendedor em "Meu Perfil". `None` se a conta não tiver
    vendedor atribuído ou ele não tiver cadastrado o número — o envio do
    template segue normalmente, só sem preencher o botão."""
    conta = db.query(Conta).filter_by(id=decisor.conta_id).one_or_none()
    if conta is None or conta.vendedor_usuario_id is None:
        return None
    vendedor = db.query(Usuario).filter_by(id=conta.vendedor_usuario_id).one_or_none()
    return vendedor.whatsapp_pessoal if vendedor else None


def _processar_whatsapp(
    db: Session, mensagem: Mensagem, decisor: Decisor, provider: WhatsAppProvider
) -> ResultadoEnvio | None:
    if mensagem.template_id is None:
        ultima = decisor.ultima_interacao_em
        if ultima is not None and ultima.tzinfo is None:
            # A coluna é `timestamp` sem fuso (gravada em UTC): lida do banco vem "ingênua", e subtrair de um horário com fuso estourava
            # TypeError, derrubando o envio de WhatsApp do tenant inteiro justamente para quem já tinha respondido.
            ultima = ultima.replace(tzinfo=UTC)
        fora_da_janela = ultima is None or (datetime.now(UTC) - ultima).total_seconds() > JANELA_LIVRE_WHATSAPP_HORAS * 3600
        if not fora_da_janela:
            return provider.enviar_texto_livre(decisor.telefone, mensagem.conteudo)
        if mensagem.whatsapp_modo != "direct_send":
            # Mensagem livre fora da janela de 24h: exige template — adia,
            # não trata como falha (E3-H2).
            return None
        # Janela fechada e mensagem marcada para sair sem template (Direct Send, categoria utilidade), com as travas.
        promocionais = predator_contract.portao_envio.termos_promocionais(mensagem.conteudo)
        if promocionais:
            _devolver_para_revisao(
                db, mensagem.tenant_id, mensagem,
                f"Texto promocional (\"{promocionais[0]}\") não pode sair pelo WhatsApp sem template: a Meta trata como marketing e pune "
                "o número. Tire a promoção ou use um template aprovado.",
            )
            return None
        resultado = whatsapp_service.enviar_direct_send(db, mensagem.tenant_id, provider, decisor.telefone, mensagem.conteudo)
        if resultado is None:
            mensagem.motivo_falha = "WhatsApp sem template indisponível para esta conta (desligado ou recusado pela Meta): aguardando."
        return resultado
    variavel_botao = _variavel_botao_whatsapp(db, decisor)
    return provider.enviar_template(decisor.telefone, mensagem.template_id, {}, variavel_botao)


def _processar_email(
    mensagem: Mensagem, decisor: Decisor, config: ConfiguracaoEnvio | None, provider: EmailProvider
) -> ResultadoEnvio:
    remetente_nome = config.remetente_nome if config else "PREDATOR"
    remetente_email = config.remetente_email if config else settings.sendgrid_remetente_email
    corpo = f"{mensagem.conteudo}\n\n{config.assinatura}" if config else mensagem.conteudo
    pixel_url = rastreamento_service.url_pixel(mensagem.tenant_id, mensagem.id)
    return provider.enviar(
        decisor.email,
        "Contato",
        corpo,
        remetente_nome,
        remetente_email,
        mensagem.tenant_id,
        pixel_url,
        mensagem_id=mensagem.id,
    )


def _bloqueado_pelo_crm(db: Session, tenant_id: str, mensagem: Mensagem, decisor: Decisor, conexoes: list[int]) -> bool:
    """D-087: o CRM do cliente diz para não abordar (já é cliente, negócio
    aberto, opt-out lá) → a mensagem é cancelada e auditada. Opt-out no CRM
    vira opt-out aqui também (supressão bidirecional)."""
    conta = db.query(Conta).filter_by(id=decisor.conta_id, tenant_id=tenant_id).one_or_none()
    bloqueio = integracoes.obter_escrita().bloqueio_prospeccao(
        db, tenant_id, conta.cnpj if conta else None, conta.dominio if conta else None, decisor.email, conexoes)
    if bloqueio is None:
        return False
    motivo, codigo = bloqueio
    mensagem.status = "cancelado"
    mensagem.motivo_falha = motivo
    auditoria_service.registrar(db, tenant_id, "envio_bloqueado_crm", "mensagem", mensagem.id, None, {"motivo": codigo},
                                conta_id=decisor.conta_id, canal=mensagem.canal)
    if codigo == "optout":
        optout_service.aplicar(db, tenant_id, decisor, origem="crm_externo")
    return True


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
        "bloqueadas_crm": 0,
        "bloqueadas_email_inexistente": 0,
        "aguardando_confirmacao_email": 0,
        "devolvidas_para_revisao": 0,
    }
    # D-087: conexões de CRM com deduplicação ligada (uma consulta por rodada).
    escrita_crm = integracoes.obter_escrita()
    conexoes_dedup = [c.id for c in escrita_crm.conexoes_com(db, tenant_id, "deduplicar")]
    # E-mails registrados como inexistentes ou que já voltaram (uma consulta por rodada): não se tenta de novo, em nenhuma área da plataforma.
    inviaveis = bloqueio_contato_service.emails_inviaveis(db, tenant_id)

    for mensagem in candidatas:
        decisor = db.query(Decisor).filter_by(id=mensagem.decisor_id).one()

        if optout_service.existe_supressao(db, decisor.id):
            mensagem.status = "cancelado"
            continue

        if conexoes_dedup and _bloqueado_pelo_crm(db, tenant_id, mensagem, decisor, conexoes_dedup):
            resultado["bloqueadas_crm"] += 1
            continue

        if mensagem.canal == "email" and bloqueio_contato_service.email_esta_inviavel(decisor.email, inviaveis):
            mensagem.status = "cancelado"
            mensagem.motivo_falha = f"E-mail inexistente ou devolvido em envio anterior: {(decisor.email or '').strip()[:80]}"
            auditoria_service.registrar(db, tenant_id, "envio_bloqueado_email_inexistente", "mensagem", mensagem.id, None, {},
                                        conta_id=decisor.conta_id, canal=mensagem.canal)
            resultado["bloqueadas_email_inexistente"] += 1
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

        if mensagem.canal in ("email", "whatsapp"):
            empresa = db.query(Conta.nome).filter_by(id=decisor.conta_id, tenant_id=tenant_id).scalar()
            mensagem.conteudo = _renderizar_variaveis(mensagem.conteudo, decisor, empresa)
            mensagem.assunto = _renderizar_variaveis(mensagem.assunto, decisor, empresa)
            graves = [p for p in portao_envio_service.problemas(db, tenant_id, mensagem, decisor) if p.grave]
            if graves:
                _devolver_para_revisao(db, tenant_id, mensagem, "Devolvida para revisão: " + "; ".join(p.texto for p in graves))
                resultado["devolvidas_para_revisao"] += 1
                continue

        if mensagem.canal == "email" and decisor.email_status == "inferido":
            # E-mail montado pelo padrão da empresa: sem verificador de caixa contratado, um palpite não sai. Fica pendente, com o motivo à
            # vista, até alguém confirmar o e-mail no cadastro do decisor (aí o envio segue sozinho na próxima rodada).
            mensagem.motivo_falha = "E-mail deduzido pelo padrão do site: confirme o e-mail do decisor para liberar o envio."
            resultado["aguardando_confirmacao_email"] += 1
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
            envio = _processar_whatsapp(db, mensagem, decisor, whatsapp)
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
            escrita_crm.enfileirar(db, tenant_id, "atividade_mensagem", mensagem.id)  # D-087: histórico no CRM do cliente
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
