from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.decisor import Decisor
from app.models.qualificacao import QualificacaoScore
from app.models.reuniao import Reuniao
from app.models.turno_conversa import TurnoConversa
from app.providers.crm.base import CrmProvider
from app.services.errors import NaoEncontrado

_PROXIMA_ACAO_POR_ETAPA = {
    "dores": "Explorar as dores e o contexto do decisor.",
    "contexto": "Aprofundar contexto e identificar orçamento disponível.",
    "orcamento": "Confirmar orçamento e mapear autoridade de decisão.",
    "autoridade": "Validar autoridade de decisão e alinhar timing.",
    "timing": "Fechar o roteiro de qualificação e propor reunião.",
    "concluida": "Avançar para proposta — roteiro de qualificação concluído.",
}


def montar(db: Session, tenant_id: str, reuniao_id: int) -> dict:
    """Dossiê com dores/respostas, score decomposto, histórico e próxima
    ação recomendada (E7-H1) — leitura rápida, formato compacto para mobile."""
    reuniao = db.query(Reuniao).filter_by(id=reuniao_id, tenant_id=tenant_id).one_or_none()
    if reuniao is None:
        raise NaoEncontrado(f"Reunião {reuniao_id} não encontrada")

    decisor = db.query(Decisor).filter_by(id=reuniao.decisor_id).one()
    conta = db.query(Conta).filter_by(id=reuniao.conta_id).one()

    conversa = (
        db.query(ConversaQualificacao)
        .filter_by(tenant_id=tenant_id, decisor_id=decisor.id)
        .order_by(ConversaQualificacao.id.desc())
        .first()
    )

    turnos: list[TurnoConversa] = []
    score = None
    proxima_acao = "Iniciar qualificação."
    if conversa is not None:
        turnos = (
            db.query(TurnoConversa).filter_by(conversa_id=conversa.id).order_by(TurnoConversa.criado_em).all()
        )
        score = (
            db.query(QualificacaoScore)
            .filter_by(conversa_id=conversa.id)
            .order_by(QualificacaoScore.id.desc())
            .first()
        )
        proxima_acao = _PROXIMA_ACAO_POR_ETAPA.get(conversa.etapa_atual, "Seguir roteiro S.H.A.R.K.")

    dores = [turno.conteudo for turno in turnos if turno.direcao == "entrada"]
    respostas = [
        {"direcao": turno.direcao, "conteudo": turno.conteudo, "criado_em": turno.criado_em.isoformat()}
        for turno in turnos
    ]

    return {
        "decisor_nome": decisor.nome,
        "conta_nome": conta.nome,
        "dores": dores,
        "respostas": respostas,
        "score_total": score.score_total if score else None,
        "score_criterios": score.criterios if score else {},
        "proxima_acao_recomendada": proxima_acao,
        "oportunidade_crm_id": reuniao.origem_crm_id,
    }


def montar_e_anexar(db: Session, tenant_id: str, reuniao_id: int, crm: CrmProvider) -> dict:
    """Dossiê gerado automaticamente e anexado à oportunidade no CRM (E7-H1)."""
    dossie = montar(db, tenant_id, reuniao_id)
    if dossie["oportunidade_crm_id"]:
        texto = (
            f"Dossiê de handoff — {dossie['decisor_nome']} ({dossie['conta_nome']})\n"
            f"Score: {dossie['score_total']} — {dossie['score_criterios']}\n"
            f"Próxima ação: {dossie['proxima_acao_recomendada']}"
        )
        crm.anexar_nota(tenant_id, dossie["oportunidade_crm_id"], texto)
    return dossie
