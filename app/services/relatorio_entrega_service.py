from sqlalchemy.orm import Session

from app.models.cadencia import Cadencia
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.services import panel_service, reputacao_service

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
_STATUS_FILTROS_VALIDOS = {"todos", "erro", "enviado", "aberto", "pendente", "cancelado"}
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
        return ("aberto" if mensagem.aberto_em is not None else "enviado"), None
    return mensagem.status, None


def _classificar_destinatario_campanha(destinatario: CampanhaDestinatario) -> tuple[str, str | None]:
    if destinatario.bounce_em is not None:
        return "erro", destinatario.motivo_bounce
    if destinatario.status == "falhou":
        return "erro", destinatario.motivo_falha
    if destinatario.status == "optout":
        return "cancelado", None
    if destinatario.status == "pendente":
        return "pendente", None
    return "enviado", None


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
        if destinatario.decisor_id is not None:
            decisor = db.query(Decisor).filter_by(id=destinatario.decisor_id).one_or_none()
            if decisor is not None:
                conta_id = decisor.conta_id
                conta = db.query(Conta).filter_by(id=decisor.conta_id).one_or_none()
                conta_nome = (conta.nome_fantasia or conta.nome) if conta is not None else None
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


def obter(db: Session, tenant_id: str) -> dict:
    saude_email = reputacao_service.status_saude(db, tenant_id, "email")
    energia = panel_service.indicadores_energia(db, tenant_id, None, None)
    return {
        "saude_email": saude_email,
        "taxa_abertura_email": energia["taxa_abertura_email"],
        "taxa_resposta_por_canal": energia["taxa_resposta_por_canal"],
        "contatos_com_bounce": _listar_contatos_com_bounce(db, tenant_id),
    }
