from sqlalchemy.orm import Session

from app.models.campanha import CampanhaDestinatario
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import panel_service, reputacao_service

# Só e-mail tem um sinal real de entrega/bounce hoje (webhook do
# SendGrid) — WhatsApp/LinkedIn não têm confirmação de entrega/leitura
# rastreada (raio-X 2026-09-16), então o relatório não finge medir isso.
_LIMITE_CONTATOS_COM_BOUNCE = 200


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


def obter(db: Session, tenant_id: str) -> dict:
    saude_email = reputacao_service.status_saude(db, tenant_id, "email")
    energia = panel_service.indicadores_energia(db, tenant_id, None, None)
    return {
        "saude_email": saude_email,
        "taxa_abertura_email": energia["taxa_abertura_email"],
        "taxa_resposta_por_canal": energia["taxa_resposta_por_canal"],
        "contatos_com_bounce": _listar_contatos_com_bounce(db, tenant_id),
    }
