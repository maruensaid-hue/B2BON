import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.decisor import Decisor
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.schemas.campanha import DestinatarioAvulsoSchema
from app.services import atividade_service, auditoria_service, optout_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

_SEPARADOR = ":"

_REMETENTE_NOME = "B2B ON"


def _validar_canais(canais: list[str], assunto: str | None, conteudo_email: str | None, template_whatsapp_id: str | None) -> None:
    if not canais:
        raise ValidacaoFalhou("Selecione ao menos um canal (e-mail e/ou WhatsApp).")
    if "email" in canais and not (assunto and conteudo_email):
        raise ValidacaoFalhou("Campanhas com canal e-mail exigem assunto e conteúdo.")
    if "whatsapp" in canais and not template_whatsapp_id:
        raise ValidacaoFalhou("Campanhas com canal WhatsApp exigem um template aprovado pela Meta.")


def criar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    nome: str,
    tipo: str,
    canais: list[str],
    assunto: str | None,
    conteudo_email: str | None,
    template_whatsapp_id: str | None,
) -> Campanha:
    _validar_canais(canais, assunto, conteudo_email, template_whatsapp_id)
    campanha = Campanha(
        tenant_id=tenant_id,
        nome=nome,
        tipo=tipo,
        canais=canais,
        assunto=assunto,
        conteudo_email=conteudo_email,
        template_whatsapp_id=template_whatsapp_id,
        status="rascunho",
    )
    db.add(campanha)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "campanha_criada", "campanha", campanha.id, ator_id, {"nome": nome})
    db.commit()
    db.refresh(campanha)
    return campanha


def obter(db: Session, tenant_id: str, campanha_id: int) -> Campanha:
    campanha = db.query(Campanha).filter_by(id=campanha_id, tenant_id=tenant_id).one_or_none()
    if campanha is None:
        raise NaoEncontrado(f"Campanha {campanha_id} não encontrada")
    return campanha


def listar(db: Session, tenant_id: str) -> list[Campanha]:
    return db.query(Campanha).filter_by(tenant_id=tenant_id).order_by(Campanha.criado_em.desc()).all()


def _exigir_rascunho(campanha: Campanha) -> None:
    if campanha.status != "rascunho":
        raise RegraNegocioViolada("Essa ação só é permitida enquanto a campanha está em rascunho.")


def atualizar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    campanha_id: int,
    nome: str,
    tipo: str,
    canais: list[str],
    assunto: str | None,
    conteudo_email: str | None,
    template_whatsapp_id: str | None,
) -> Campanha:
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    _validar_canais(canais, assunto, conteudo_email, template_whatsapp_id)
    campanha.nome = nome
    campanha.tipo = tipo
    campanha.canais = canais
    campanha.assunto = assunto
    campanha.conteudo_email = conteudo_email
    campanha.template_whatsapp_id = template_whatsapp_id
    auditoria_service.registrar(db, tenant_id, "campanha_atualizada", "campanha", campanha.id, ator_id, {})
    db.commit()
    db.refresh(campanha)
    return campanha


def excluir(db: Session, tenant_id: str, ator_id: str | None, campanha_id: int) -> None:
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).delete()
    db.delete(campanha)
    auditoria_service.registrar(db, tenant_id, "campanha_excluida", "campanha", campanha_id, ator_id, {})
    db.commit()


def listar_destinatarios(db: Session, tenant_id: str, campanha_id: int) -> list[CampanhaDestinatario]:
    obter(db, tenant_id, campanha_id)
    return (
        db.query(CampanhaDestinatario)
        .filter_by(campanha_id=campanha_id)
        .order_by(CampanhaDestinatario.id)
        .all()
    )


def metricas(db: Session, tenant_id: str, campanha_id: int) -> dict[str, int]:
    destinatarios = listar_destinatarios(db, tenant_id, campanha_id)
    contagem = {"total": len(destinatarios), "pendente": 0, "enviado": 0, "falhou": 0, "optout": 0}
    for destinatario in destinatarios:
        contagem[destinatario.status] = contagem.get(destinatario.status, 0) + 1
    return contagem


def adicionar_de_decisores(
    db: Session, tenant_id: str, ator_id: str | None, campanha_id: int, decisor_ids: list[int]
) -> list[CampanhaDestinatario]:
    """Snapshot de nome/e-mail/telefone no momento em que entra na
    campanha — pula quem já está suprimido (opt-out), reaproveitando a
    mesma lista de supressão que protege a cadência (E9-H2)."""
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)

    ja_adicionados = {
        destinatario.decisor_id
        for destinatario in db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).all()
        if destinatario.decisor_id is not None
    }

    adicionados: list[CampanhaDestinatario] = []
    for decisor_id in decisor_ids:
        if decisor_id in ja_adicionados:
            continue
        decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
        if decisor is None or optout_service.existe_supressao(db, decisor.id):
            continue
        destinatario = CampanhaDestinatario(
            tenant_id=tenant_id,
            campanha_id=campanha.id,
            decisor_id=decisor.id,
            nome=decisor.nome,
            email=decisor.email,
            telefone=decisor.telefone,
        )
        db.add(destinatario)
        adicionados.append(destinatario)
        ja_adicionados.add(decisor_id)

    db.flush()
    auditoria_service.registrar(
        db,
        tenant_id,
        "campanha_destinatarios_adicionados",
        "campanha",
        campanha.id,
        ator_id,
        {"quantidade": len(adicionados), "origem": "decisores"},
    )
    db.commit()
    for destinatario in adicionados:
        db.refresh(destinatario)
    return adicionados


def adicionar_avulsos(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    campanha_id: int,
    destinatarios: list[DestinatarioAvulsoSchema],
) -> list[CampanhaDestinatario]:
    """Lista colada/avulsa — sem Decisor de origem, então sem checagem
    contra a supressão do CRM (limitação documentada: um destinatário
    avulso que se descadastra só fica suprimido dentro desta campanha,
    não em campanhas futuras — não existe hoje uma lista de supressão
    por e-mail cruzando campanhas)."""
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)

    ja_existentes = {
        destinatario.email.strip().lower()
        for destinatario in db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).all()
        if destinatario.email
    }

    adicionados: list[CampanhaDestinatario] = []
    for item in destinatarios:
        nome = item.nome.strip()
        email = (item.email or "").strip() or None
        telefone = (item.telefone or "").strip() or None
        if not nome or not (email or telefone):
            continue
        if email and email.lower() in ja_existentes:
            continue
        destinatario = CampanhaDestinatario(
            tenant_id=tenant_id, campanha_id=campanha.id, decisor_id=None, nome=nome, email=email, telefone=telefone
        )
        db.add(destinatario)
        adicionados.append(destinatario)
        if email:
            ja_existentes.add(email.lower())

    db.flush()
    auditoria_service.registrar(
        db,
        tenant_id,
        "campanha_destinatarios_adicionados",
        "campanha",
        campanha.id,
        ator_id,
        {"quantidade": len(adicionados), "origem": "avulso"},
    )
    db.commit()
    for destinatario in adicionados:
        db.refresh(destinatario)
    return adicionados


def remover_destinatario(db: Session, tenant_id: str, ator_id: str | None, campanha_id: int, destinatario_id: int) -> None:
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    destinatario = (
        db.query(CampanhaDestinatario)
        .filter_by(id=destinatario_id, campanha_id=campanha.id, tenant_id=tenant_id)
        .one_or_none()
    )
    if destinatario is None:
        raise NaoEncontrado(f"Destinatário {destinatario_id} não encontrado")
    db.delete(destinatario)
    auditoria_service.registrar(
        db, tenant_id, "campanha_destinatario_removido", "campanha", campanha.id, ator_id, {"destinatario_id": destinatario_id}
    )
    db.commit()


def marcar_pronta(db: Session, tenant_id: str, ator_id: str | None, campanha_id: int) -> Campanha:
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    total = db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).count()
    if total == 0:
        raise ValidacaoFalhou("Adicione ao menos um destinatário antes de marcar a campanha como pronta.")
    _validar_canais(campanha.canais, campanha.assunto, campanha.conteudo_email, campanha.template_whatsapp_id)
    campanha.status = "pronta"
    auditoria_service.registrar(db, tenant_id, "campanha_marcada_pronta", "campanha", campanha.id, ator_id, {})
    db.commit()
    db.refresh(campanha)
    return campanha


def processar_pendentes(db: Session, tenant_id: str, email_provider: EmailProvider, whatsapp_provider: WhatsAppProvider) -> dict:
    """Dispatcher chamado por cron externo (mesmo padrão síncrono e
    idempotente de `envio_service.processar_pendentes`) — cada campanha
    `pronta` ou já `enviando` tem seus destinatários `pendente` disparados
    nesta chamada; ao esgotar, a campanha vira `concluida`."""
    resultado = {"enviadas": 0, "falhas": 0}

    campanhas = db.query(Campanha).filter(Campanha.tenant_id == tenant_id, Campanha.status.in_(["pronta", "enviando"])).all()
    for campanha in campanhas:
        campanha.status = "enviando"
        pendentes = (
            db.query(CampanhaDestinatario)
            .filter_by(campanha_id=campanha.id, tenant_id=tenant_id, status="pendente")
            .all()
        )
        for destinatario in pendentes:
            sucesso, motivo_falha = _disparar_destinatario(campanha, destinatario, email_provider, whatsapp_provider)
            if sucesso:
                destinatario.status = "enviado"
                destinatario.enviado_em = datetime.now(UTC)
                if destinatario.decisor_id is not None:
                    decisor = db.query(Decisor).filter_by(id=destinatario.decisor_id).one_or_none()
                    if decisor is not None:
                        atividade_service.registrar(
                            db, tenant_id, conta_id=decisor.conta_id, tipo="sistema",
                            descricao=f"Campanha '{campanha.nome}' enviada",
                        )
                resultado["enviadas"] += 1
            else:
                destinatario.status = "falhou"
                destinatario.motivo_falha = motivo_falha
                resultado["falhas"] += 1

        # `pendentes` já é a lista inteira de destinatários pendentes desta
        # campanha (sem lote/limite artificial) e todos foram atualizados
        # no laço acima — não sobra ninguém "pendente" depois disto, então
        # a campanha está concluída. (Reconsultar o banco aqui seria
        # arriscado: a sessão usa `autoflush=False`, então a query não
        # veria as mudanças de status ainda não commitadas.)
        campanha.status = "concluida"

    db.commit()
    return resultado


def _disparar_destinatario(
    campanha: Campanha, destinatario: CampanhaDestinatario, email_provider: EmailProvider, whatsapp_provider: WhatsAppProvider
) -> tuple[bool, str | None]:
    enviou_algum = False
    ultimo_motivo: str | None = None

    if "email" in campanha.canais and destinatario.email:
        corpo = f"{campanha.conteudo_email}\n\n{_link_optout(campanha.tenant_id, destinatario.id)}"
        resultado = email_provider.enviar(
            destinatario.email,
            campanha.assunto or "",
            corpo,
            _REMETENTE_NOME,
            settings.sendgrid_remetente_email,
            campanha.tenant_id,
        )
        if resultado.sucesso:
            enviou_algum = True
        else:
            ultimo_motivo = resultado.motivo_falha

    if "whatsapp" in campanha.canais and destinatario.telefone and campanha.template_whatsapp_id:
        resultado = whatsapp_provider.enviar_template(destinatario.telefone, campanha.template_whatsapp_id, {})
        if resultado.sucesso:
            enviou_algum = True
        else:
            ultimo_motivo = resultado.motivo_falha

    if not enviou_algum and ultimo_motivo is None:
        ultimo_motivo = "Destinatário sem e-mail/telefone compatível com os canais da campanha."
    return enviou_algum, ultimo_motivo


def _link_optout(tenant_id: str, destinatario_id: int) -> str:
    token = gerar_token_optout(tenant_id, destinatario_id)
    return f"Não quer mais receber esses e-mails? Descadastre-se: {settings.url_base_api}/opt-out/campanha/{token}"


def gerar_token_optout(tenant_id: str, destinatario_id: int) -> str:
    """Mesmo padrão stateless (HMAC) de `optout_service.gerar_token`,
    escopado a um destinatário de campanha em vez de um Decisor."""
    payload = f"{tenant_id}{_SEPARADOR}{destinatario_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR}{assinatura}"


def _validar_token_optout(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de opt-out inválido.")
    tenant_id, destinatario_id_str, assinatura = partes
    try:
        destinatario_id = int(destinatario_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de opt-out inválido.") from erro

    esperado = gerar_token_optout(tenant_id, destinatario_id).rsplit(_SEPARADOR, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de opt-out inválido.")
    return tenant_id, destinatario_id


def processar_optout_por_token(db: Session, token: str) -> dict:
    """Opt-out via link do e-mail da campanha — endpoint público. Quando o
    destinatário tem `decisor_id` (veio do CRM), propaga também para a
    supressão real (`optout_service.processar`), suprimindo cadências
    pro mesmo contato — destinatário avulso só fica suprimido aqui."""
    tenant_id, destinatario_id = _validar_token_optout(token)
    destinatario = db.query(CampanhaDestinatario).filter_by(id=destinatario_id, tenant_id=tenant_id).one_or_none()
    if destinatario is None:
        raise NaoEncontrado(f"Destinatário {destinatario_id} não encontrado")

    destinatario.status = "optout"
    if destinatario.decisor_id is not None:
        optout_service.processar(db, tenant_id, destinatario.decisor_id, origem="campanha")
    db.commit()
    return {"destinatario_id": destinatario.id, "suprimido": True}
