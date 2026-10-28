import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cadencia import Cadencia
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.configuracao_email_api import ConfiguracaoEmailApi
from app.models.configuracao_email_smtp import ConfiguracaoEmailSmtp
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.services import auditoria_service, panel_service, reputacao_service
from app.services.errors import ValidacaoFalhou

# Só e-mail tem um sinal real de entrega/bounce hoje (webhook do
# SendGrid) — WhatsApp/LinkedIn não têm confirmação de entrega/leitura
# rastreada (raio-X 2026-09-16), então o relatório não finge medir isso.
_LIMITE_CONTATOS_COM_BOUNCE = 200

# Raio-X 2026-09-17: o KPI "enviados" de `reputacao_service.status_saude`
# só conta eventos "delivered" que o SendGrid já confirmou via webhook —
# sub-representa o real quando a confirmação ainda não chegou (o cliente
# via só "2" após ativar cadências com dezenas de destinatários). Esta
# visão granular classifica cada mensagem/destinatário de e-mail
# individualmente, sem depender só do webhook.
_STATUS_MENSAGEM_PENDENTE = {"rascunho", "aguardando_aprovacao", "aprovado"}
_STATUS_FILTROS_VALIDOS = {"todos", "erro", "enviado", "entregue", "aberto", "pendente", "nao_enviado", "cancelado"}
_JANELA_RESUMO_DIAS = 7

_EMAIL_NO_TEXTO = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_MAXIMO_BOUNCES_POR_VEZ = 500
MOTIVO_BOUNCE_MANUAL = "Informado manualmente: o e-mail voltou como não entregue."
_LIMITE_MAXIMO_ENVIOS = 200


def _contatos_com_bounce_de_mensagens(db: Session, tenant_id: str) -> list[dict]:
    linhas = (
        db.query(Mensagem, Decisor, Conta)
        .join(Decisor, Mensagem.decisor_id == Decisor.id)
        .join(Conta, Decisor.conta_id == Conta.id)
        .filter(Mensagem.tenant_id == tenant_id, Mensagem.bounce_em.isnot(None))
        .order_by(Mensagem.bounce_em.desc())
        .all()
    )
    return [
        {
            "decisor_id": decisor.id,
            "conta_id": conta.id,
            "nome": decisor.nome,
            "email": decisor.email,
            "conta_nome": conta.nome_fantasia or conta.nome,
            "canal": "email",
            "motivo_bounce": mensagem.motivo_bounce,
            "bounce_em": mensagem.bounce_em,
        }
        for mensagem, decisor, conta in linhas
    ]


def _contatos_com_bounce_de_campanhas(db: Session, tenant_id: str) -> list[dict]:
    destinatarios = (
        db.query(CampanhaDestinatario)
        .filter(CampanhaDestinatario.tenant_id == tenant_id, CampanhaDestinatario.bounce_em.isnot(None))
        .order_by(CampanhaDestinatario.bounce_em.desc())
        .all()
    )
    resultado = []
    for destinatario in destinatarios:
        conta_nome = None
        conta_id = None
        if destinatario.decisor_id is not None:
            decisor = db.query(Decisor).filter_by(id=destinatario.decisor_id).one_or_none()
            if decisor is not None:
                conta = db.query(Conta).filter_by(id=decisor.conta_id).one_or_none()
                conta_id = decisor.conta_id
                conta_nome = (conta.nome_fantasia or conta.nome) if conta is not None else None
        resultado.append(
            {
                "decisor_id": destinatario.decisor_id,
                "conta_id": conta_id,
                "nome": destinatario.nome,
                "email": destinatario.email,
                "conta_nome": conta_nome,
                "canal": "campanha",
                "motivo_bounce": destinatario.motivo_bounce,
                "bounce_em": destinatario.bounce_em,
            }
        )
    return resultado


def _listar_contatos_com_bounce(db: Session, tenant_id: str) -> list[dict]:
    """Dedupe por decisor (mantém só o bounce mais recente) — contato sem
    `decisor_id` (destinatário avulso de campanha) nunca é agrupado, cada
    ocorrência aparece."""
    todos = _contatos_com_bounce_de_mensagens(db, tenant_id) + _contatos_com_bounce_de_campanhas(db, tenant_id)
    todos.sort(key=lambda item: item["bounce_em"], reverse=True)

    vistos: set[int] = set()
    deduplicados = []
    for item in todos:
        if item["decisor_id"] is not None:
            if item["decisor_id"] in vistos:
                continue
            vistos.add(item["decisor_id"])
        deduplicados.append(item)
        if len(deduplicados) >= _LIMITE_CONTATOS_COM_BOUNCE:
            break
    return deduplicados


def _classificar_mensagem(mensagem: Mensagem) -> tuple[str, str | None]:
    if mensagem.bounce_em is not None:
        return "erro", mensagem.motivo_bounce
    if mensagem.status == "falhou":
        return "erro", mensagem.motivo_falha
    if mensagem.status == "cancelado":
        return "cancelado", None
    if mensagem.status in _STATUS_MENSAGEM_PENDENTE:
        return "pendente", None
    if mensagem.status == "enviado":
        if mensagem.aberto_em is not None:
            return "aberto", None
        return ("entregue" if mensagem.entregue_em is not None else "enviado"), None
    return mensagem.status, None


def _classificar_destinatario_campanha(destinatario: CampanhaDestinatario) -> tuple[str, str | None]:
    if destinatario.bounce_em is not None:
        return "erro", destinatario.motivo_bounce
    if destinatario.status == "falhou":
        return "erro", destinatario.motivo_falha
    if destinatario.status == "nao_enviado":  # sem destino válido (ex.: link no lugar do e-mail): nunca houve tentativa, então não é erro nem enviado
        return "nao_enviado", destinatario.motivo_falha
    if destinatario.status == "optout":
        return "cancelado", destinatario.motivo_falha  # "informado manualmente: não quer receber"; pelo link do e-mail não há motivo
    if destinatario.status == "pendente":
        return "pendente", destinatario.motivo_falha  # traz o aviso de envio adiado, se houver
    if destinatario.status == "retido":  # fora de uma rodada de envio parcial: aguarda o próximo envio
        return "pendente", "Aguardando o próximo envio da campanha"
    if destinatario.status == "enviado":
        if destinatario.aberto_em is not None:
            return "aberto", None
        return ("entregue" if destinatario.entregue_em is not None else "enviado"), None
    return destinatario.status, None


def _envios_email_de_mensagens(db: Session, tenant_id: str) -> list[dict]:
    linhas = (
        db.query(Mensagem, Decisor, Conta, Cadencia, ICP)
        .join(Decisor, Mensagem.decisor_id == Decisor.id)
        .join(Conta, Decisor.conta_id == Conta.id)
        .outerjoin(Cadencia, Mensagem.cadencia_id == Cadencia.id)
        .outerjoin(ICP, Cadencia.icp_id == ICP.id)
        .filter(Mensagem.tenant_id == tenant_id, Mensagem.canal == "email")
        .order_by(Mensagem.criado_em.desc())
        .all()
    )
    resultado = []
    for mensagem, decisor, conta, cadencia, icp in linhas:
        status, detalhe = _classificar_mensagem(mensagem)
        if icp is not None:
            origem_nome = f"Cadência · {icp.nome}"
        elif cadencia is not None:
            origem_nome = f"Cadência #{cadencia.id}"
        else:
            origem_nome = "Envio avulso"
        resultado.append(
            {
                "origem": "cadencia",
                "origem_nome": origem_nome,
                "decisor_id": decisor.id,
                "conta_id": conta.id,
                "nome": decisor.nome,
                "email": decisor.email,
                "conta_nome": conta.nome_fantasia or conta.nome,
                "status": status,
                "detalhe": detalhe,
                "enviado_em": mensagem.enviado_em,
                "criado_em": mensagem.criado_em,
            }
        )
    return resultado


def _envios_email_de_campanhas(db: Session, tenant_id: str) -> list[dict]:
    linhas = (
        db.query(CampanhaDestinatario, Campanha)
        .join(Campanha, CampanhaDestinatario.campanha_id == Campanha.id)
        .filter(CampanhaDestinatario.tenant_id == tenant_id, CampanhaDestinatario.email.isnot(None))
        .order_by(CampanhaDestinatario.criado_em.desc())
        .all()
    )
    # Contatos e empresas de uma vez só (a campanha pode ter centenas de destinatários: uma consulta por linha deixava a tela lenta).
    ids_decisores = {destinatario.decisor_id for destinatario, _ in linhas if destinatario.decisor_id is not None}
    decisores = {d.id: d for d in db.query(Decisor).filter(Decisor.id.in_(ids_decisores)).all()} if ids_decisores else {}
    ids_contas = {d.conta_id for d in decisores.values()}
    contas = {c.id: c for c in db.query(Conta).filter(Conta.id.in_(ids_contas)).all()} if ids_contas else {}
    resultado = []
    for destinatario, campanha in linhas:
        # `CampanhaDestinatario.status` é combinado entre os canais da
        # campanha (e-mail e/ou WhatsApp, `campanha_service._disparar_
        # destinatario`) — só entra aqui quem tem e-mail cadastrado E cuja
        # campanha de fato inclui o canal e-mail, senão herdaria status de
        # um envio de WhatsApp que nunca tentou e-mail nenhum.
        if "email" not in (campanha.canais or []):
            continue
        status, detalhe = _classificar_destinatario_campanha(destinatario)
        conta_nome = None
        conta_id = None
        decisor = decisores.get(destinatario.decisor_id) if destinatario.decisor_id is not None else None
        if decisor is not None:
            conta_id = decisor.conta_id
            conta = contas.get(decisor.conta_id)
            conta_nome = (conta.nome_fantasia or conta.nome) if conta is not None else None
        elif destinatario.empresa:
            conta_nome = destinatario.empresa  # destinatário de lista colada: a empresa digitada
        resultado.append(
            {
                "origem": "campanha",
                "origem_nome": campanha.nome,
                "decisor_id": destinatario.decisor_id,
                "conta_id": conta_id,
                "nome": destinatario.nome,
                "email": destinatario.email,
                "conta_nome": conta_nome,
                "status": status,
                "detalhe": detalhe,
                "enviado_em": destinatario.enviado_em,
                "criado_em": destinatario.criado_em,
            }
        )
    return resultado


def listar_envios_email(db: Session, tenant_id: str, status: str = "todos", limite: int = 50, offset: int = 0) -> dict:
    """Visão granular por destinatário — cada mensagem/destinatário de
    e-mail (cadência ou campanha), individualmente, com o motivo real
    quando deu erro. `contagem_por_status` sempre reflete o total (sem o
    filtro), pra alimentar os KPIs mesmo com uma aba/status específico
    selecionado na lista."""
    limite = min(max(limite, 1), _LIMITE_MAXIMO_ENVIOS)
    offset = max(offset, 0)

    todos = _envios_email_de_mensagens(db, tenant_id) + _envios_email_de_campanhas(db, tenant_id)
    todos.sort(key=lambda item: item["criado_em"], reverse=True)

    # Pendente parado por pausa do canal parecia "fila normal" — o usuário
    # via 22 aprovados sem sair e nenhum motivo (incidente 2026-10-05).
    if reputacao_service.canal_pausado(db, tenant_id, "email"):
        for item in todos:
            if item["status"] == "pendente":
                item["detalhe"] = "Aguardando — canal de e-mail pausado"

    contagem: dict[str, int] = {}
    for item in todos:
        contagem[item["status"]] = contagem.get(item["status"], 0) + 1

    filtrados = todos if status not in _STATUS_FILTROS_VALIDOS or status == "todos" else [
        item for item in todos if item["status"] == status
    ]
    return {
        "itens": filtrados[offset : offset + limite],
        "total": len(filtrados),
        "contagem_por_status": contagem,
    }


def _resumo_envios(db: Session, tenant_id: str) -> dict:
    """Totais dos últimos 7 dias contados nos próprios envios (os mesmos da lista abaixo), não só nos retornos do provedor: sem o retorno do provedor
    (conta SMTP própria) o contador de reputação fica em zero mesmo com centenas de e-mails enviados."""
    corte = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=_JANELA_RESUMO_DIAS)
    resumo = {"enviados": 0, "entregues": 0, "abertos": 0, "erros": 0, "nao_enviados": 0, "pendentes": 0}
    for item in _envios_email_de_mensagens(db, tenant_id) + _envios_email_de_campanhas(db, tenant_id):
        momento = item["enviado_em"] or item["criado_em"]
        if momento is not None and momento.tzinfo is not None:
            momento = momento.astimezone(UTC).replace(tzinfo=None)
        if momento is None or momento < corte:
            continue
        if item["status"] in ("enviado", "entregue", "aberto"):
            resumo["enviados"] += 1
            if item["status"] in ("entregue", "aberto"):
                resumo["entregues"] += 1  # aberto implica entregue
            if item["status"] == "aberto":
                resumo["abertos"] += 1
        elif item["status"] == "erro":
            resumo["erros"] += 1
        elif item["status"] == "nao_enviado":
            resumo["nao_enviados"] += 1
        elif item["status"] == "pendente":
            resumo["pendentes"] += 1
    return resumo


def registrar_bounces_manuais(db: Session, tenant_id: str, ator_id: str | None, texto: str) -> dict:
    """Marca como bounce os e-mails que o usuário informou ter voltado como não entregues (aviso de falha na caixa de entrada). Com conta SMTP própria
    o provedor não devolve esse retorno ao sistema. Aceita texto livre (endereços separados por linha, vírgula, ponto e vírgula ou o próprio aviso colado):
    todo endereço encontrado é procurado nos e-mails de campanha e de cadência já enviados. Não mexe nos contadores de reputação do canal: sem o retorno
    do provedor eles não têm o total de envios, e uma taxa calculada em cima deles pausaria o canal por engano."""
    enderecos: list[str] = []
    for achado in _EMAIL_NO_TEXTO.findall(texto or ""):
        endereco = achado.lower()
        if endereco not in enderecos:
            enderecos.append(endereco)
    if not enderecos:
        raise ValidacaoFalhou("Cole ao menos um endereço de e-mail.")
    if len(enderecos) > _MAXIMO_BOUNCES_POR_VEZ:
        raise ValidacaoFalhou(f"Informe até {_MAXIMO_BOUNCES_POR_VEZ} endereços por vez.")

    de_campanhas: dict[str, list] = {}
    for destinatario in (
        db.query(CampanhaDestinatario)
        .filter(
            CampanhaDestinatario.tenant_id == tenant_id,
            CampanhaDestinatario.status == "enviado",
            func.lower(CampanhaDestinatario.email).in_(enderecos),
        )
        .all()
    ):
        de_campanhas.setdefault(destinatario.email.lower(), []).append(destinatario)
    de_cadencias: dict[str, list] = {}
    for mensagem, decisor in (
        db.query(Mensagem, Decisor)
        .join(Decisor, Mensagem.decisor_id == Decisor.id)
        .filter(
            Mensagem.tenant_id == tenant_id,
            Mensagem.canal == "email",
            Mensagem.status == "enviado",
            func.lower(Decisor.email).in_(enderecos),
        )
        .all()
    ):
        de_cadencias.setdefault(decisor.email.lower(), []).append(mensagem)

    agora = datetime.now(UTC)
    registrados: list[str] = []
    ja_registrados: list[str] = []
    nao_encontrados: list[str] = []
    for endereco in enderecos:
        itens = de_campanhas.get(endereco, []) + de_cadencias.get(endereco, [])
        if not itens:
            nao_encontrados.append(endereco)
            continue
        novos = [item for item in itens if item.bounce_em is None]
        if not novos:
            ja_registrados.append(endereco)
            continue
        for item in novos:
            item.bounce_em = agora
            item.motivo_bounce = MOTIVO_BOUNCE_MANUAL
        registrados.append(endereco)

    auditoria_service.registrar(
        db, tenant_id, "bounce_registrado_manualmente", "relatorio_entrega", 0, ator_id,
        {"registrados": len(registrados), "ja_registrados": len(ja_registrados), "nao_encontrados": len(nao_encontrados)},
    )
    db.commit()
    return {"registrados": registrados, "ja_registrados": ja_registrados, "nao_encontrados": nao_encontrados}


def obter(db: Session, tenant_id: str) -> dict:
    saude_email = reputacao_service.status_saude(db, tenant_id, "email")
    # Com conta SMTP própria o provedor não devolve entrega/bounce/spam: as taxas abaixo ficam em zero sem querer dizer "nenhum problema".
    tem_api = db.execute(select(ConfiguracaoEmailApi.id).where(ConfiguracaoEmailApi.tenant_id == tenant_id)).first() is not None
    tem_smtp = db.execute(select(ConfiguracaoEmailSmtp.id).where(ConfiguracaoEmailSmtp.tenant_id == tenant_id)).first() is not None
    saude_email["medido_pelo_provedor"] = tem_api or not tem_smtp  # o envio por API devolve entrega/bounce/spam; a conta SMTP não
    energia = panel_service.indicadores_energia(db, tenant_id, None, None)
    return {
        "resumo_envios": _resumo_envios(db, tenant_id),
        "saude_email": saude_email,
        "taxa_abertura_email": energia["taxa_abertura_email"],
        "taxa_resposta_por_canal": energia["taxa_resposta_por_canal"],
        "contatos_com_bounce": _listar_contatos_com_bounce(db, tenant_id),
    }
