"""Opportunity Intelligence Card (Fase 6): tudo do §20 num lugar só.

Deal Intelligence, Meeting Intelligence, Next Best Offer, Next Best
Action, Discovery Gaps, Cross-Sell, Upsell, White Space, Buying Signals,
Risks e Missing Stakeholders. Cada item recomendável sai no formato de
`explicavel.Recomendacao` (motivo, evidências, confiança, fonte, data).
Montar o card não chama IA: custo zero, reprodutível.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.contexts.opportunity import dados as dados_mod
from app.contexts.opportunity import discovery, nba, nbo, texto, white_space
from app.contexts.opportunity.explicavel import METODOLOGIA, Confianca, Evidencia, FonteEvidencia, Recomendacao, recomendacao
from app.contexts.opportunity.necessidades import como_dict
from app.models.oferta import Oferta
from app.services.conta_service import sugerir_papel_comite_compra

FONTE_SINAIS = "opportunity.buying_signals.v1"
FONTE_RISCOS = "opportunity.risks.v1"
FONTE_STAKEHOLDERS = "opportunity.stakeholders.v1"
PAPEIS_ESPERADOS = {
    "DECISION_MAKER": "Quem decide",
    "ECONOMIC_BUYER": "Quem libera o orçamento",
    "CHAMPION": "Defensor interno",
    "TECHNICAL_EVALUATOR": "Avaliador técnico",
}
JANELA_SINAIS_DIAS = 30


def _sinais_compra(d: dados_mod.DadosOportunidade) -> list[Recomendacao]:
    sinais = []
    for n in d.necessidades:
        if n.status == "confirmada" and n.categoria in ("prazo", "orcamento"):
            sinais.append(recomendacao(
                "sinal_compra", "Prazo definido" if n.categoria == "prazo" else "Orçamento mencionado",
                "Cliente declarou " + ("prazo" if n.categoria == "prazo" else "orçamento") + ", informação confirmada pelo vendedor.",
                [Evidencia("necessidade", n.id, n.citacao or n.descricao, FonteEvidencia.CONFIRMADO_POR_HUMANO)],
                Confianca.ALTA, FONTE_SINAIS, gerado_em=d.agora,
            ))
    limite = d.agora - timedelta(days=JANELA_SINAIS_DIAS)
    positivos = [i for i in d.interacoes if i.tipo == "feedback_positivo" and i.criado_em.replace(tzinfo=limite.tzinfo) >= limite]
    if positivos:
        sinais.append(recomendacao(
            "sinal_compra", "Feedback positivo recente",
            f"{len(positivos)} feedback(s) positivo(s) registrados nos últimos {JANELA_SINAIS_DIAS} dias.",
            [Evidencia("interacao", i.id, i.descricao or "feedback positivo", FonteEvidencia.CONFIRMADO_POR_HUMANO) for i in positivos[:3]],
            Confianca.MEDIA, FONTE_SINAIS, gerado_em=d.agora,
        ))
    decisores = [x for x in d.decisores if x.papel_confirmado in discovery.PAPEIS_AUTORIDADE]
    reunioes_com_decisor = [r for r in d.reunioes if r.decisor_id in {x.id for x in decisores}]
    if reunioes_com_decisor:
        r = reunioes_com_decisor[0]
        sinais.append(recomendacao(
            "sinal_compra", "Decisor em reunião",
            "Houve reunião com um contato confirmado como decisor.",
            [Evidencia("reuniao", r.id, f"Reunião em {r.data_hora:%d/%m/%Y} (status {r.status})", FonteEvidencia.CADASTRO)],
            Confianca.MEDIA, FONTE_SINAIS, gerado_em=d.agora,
        ))
    return sinais


def _riscos(d: dados_mod.DadosOportunidade, resultado_nbo: dict) -> list[Recomendacao]:
    riscos = []
    if nbo.churn_alto(d):
        riscos.append(recomendacao(
            "risco", "Churn crítico na conta", "O MAP classifica esta conta cliente com risco crítico de churn.",
            [nbo.evidencia_churn(d)], Confianca.ALTA, FONTE_RISCOS, gerado_em=d.agora,
        ))
    if d.negocio is not None and d.dias_sem_atividade > nba.DIAS_PARADO:
        riscos.append(recomendacao(
            "risco", "Negócio parado", f"{d.dias_sem_atividade} dias sem atividade registrada no negócio.",
            [Evidencia("negocio", d.negocio.id, f"{d.dias_sem_atividade} dias sem atividade", FonteEvidencia.CALCULO)],
            Confianca.ALTA, FONTE_RISCOS, gerado_em=d.agora,
        ))
    if d.conta.proximo_passo and d.conta.proximo_passo_em and d.conta.proximo_passo_em.replace(tzinfo=d.agora.tzinfo) < d.agora:
        riscos.append(recomendacao(
            "risco", "Próximo passo atrasado", f"\"{d.conta.proximo_passo}\" estava previsto para {d.conta.proximo_passo_em:%d/%m/%Y}.",
            [Evidencia("conta", d.conta.id, d.conta.proximo_passo, FonteEvidencia.CADASTRO)],
            Confianca.ALTA, FONTE_RISCOS, gerado_em=d.agora,
        ))
    objecoes = [n for n in d.necessidades if n.categoria == "objecao" and n.status == "confirmada"]
    if objecoes:
        riscos.append(recomendacao(
            "risco", "Objeções abertas", f"{len(objecoes)} objeção(ões) confirmada(s) do cliente.",
            [Evidencia("necessidade", n.id, n.citacao or n.descricao, FonteEvidencia.CONFIRMADO_POR_HUMANO) for n in objecoes],
            Confianca.MEDIA, FONTE_RISCOS, gerado_em=d.agora,
        ))
    for r in resultado_nbo["recomendacoes"]:
        for texto_risco in r.dados.get("riscos", []):
            if "incompatibilidade" in texto_risco:
                riscos.append(recomendacao(
                    "risco", f"Incompatibilidade em \"{r.titulo}\"", texto_risco,
                    [Evidencia("oferta", r.dados["oferta_id"], texto_risco, FonteEvidencia.CADASTRO)],
                    Confianca.MEDIA, FONTE_RISCOS, gerado_em=d.agora,
                ))
    return riscos


def _stakeholders_faltantes(d: dados_mod.DadosOportunidade, resultado_nbo: dict) -> list[Recomendacao]:
    confirmados = {x.papel_confirmado for x in d.decisores if x.papel_confirmado}
    sugeridos = {sugerir_papel_comite_compra(x.cargo): x for x in d.decisores if not x.papel_confirmado}
    faltantes = []
    for papel, rotulo in PAPEIS_ESPERADOS.items():
        if papel in confirmados:
            continue
        candidato = sugeridos.get(papel)
        evid = (
            [Evidencia("decisor", candidato.id, f"{candidato.nome} ({candidato.cargo}) pode ser {papel} pelo cargo — confirmar", FonteEvidencia.SUGESTAO_IA)]
            if candidato
            else [Evidencia("lacuna", papel, f"Nenhum contato confirmado como {papel}", FonteEvidencia.AUSENCIA)]
        )
        faltantes.append(recomendacao(
            "stakeholder_faltante", rotulo, f"Papel {papel} não confirmado no comitê de compra.", evid,
            Confianca.MEDIA if candidato else Confianca.ALTA, FONTE_STAKEHOLDERS, gerado_em=d.agora,
            dados={"papel": papel, "candidato_decisor_id": candidato.id if candidato else None},
        ))
    melhor = resultado_nbo["recomendacoes"][0] if resultado_nbo["recomendacoes"] else None
    if melhor is not None:
        oferta = next((o for o in d.ofertas if o.id == melhor.dados["oferta_id"]), None)
        for persona in (oferta.personas or []) if oferta else []:
            if not any(texto.termos_em_comum(x.cargo, persona) for x in d.decisores):
                faltantes.append(recomendacao(
                    "stakeholder_faltante", f"Persona \"{persona}\"",
                    f"A oferta \"{oferta.nome}\" é vendida para esta persona e nenhum contato da conta tem esse perfil.",
                    [Evidencia("oferta", oferta.id, f"Persona cadastrada: {persona}", FonteEvidencia.CADASTRO)],
                    Confianca.MEDIA, FONTE_STAKEHOLDERS, gerado_em=d.agora, dados={"persona": persona},
                ))
    return faltantes


def _serializar(valor):
    if isinstance(valor, Recomendacao):
        return valor.como_dict()
    if isinstance(valor, dict):
        return {k: _serializar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_serializar(v) for v in valor]
    return valor


def montar(db: Session, tenant_id: str, negocio_id: int) -> dict:
    d = dados_mod.carregar(db, tenant_id, negocio_id)
    oferta_do_negocio = next((o for o in d.ofertas if o.id == d.negocio.oferta_id), None)
    if oferta_do_negocio is None and d.negocio.oferta_id is not None:
        oferta_do_negocio = db.query(Oferta).filter_by(id=d.negocio.oferta_id, tenant_id=tenant_id).one_or_none()
    resultado_discovery = discovery.analisar(d, oferta_do_negocio.perguntas_descoberta if oferta_do_negocio else None)
    resultado_nbo = nbo.recomendar(d)
    resultado_nba = nba.recomendar(d, resultado_discovery, resultado_nbo)
    resultado_ws = white_space.analisar(d)
    melhor = resultado_nbo["recomendacoes"][0] if resultado_nbo["recomendacoes"] else None

    card = {
        "negocio_id": d.negocio.id,
        "conta_id": d.conta.id,
        "gerado_em": d.agora,
        "metodologia": METODOLOGIA,
        "deal_intelligence": {
            "nome": d.negocio.nome,
            "valor": d.negocio.valor,
            "probabilidade": d.negocio.probabilidade,
            "estagio": d.estagio.nome,
            "estagio_tipo": d.estagio.tipo,
            "dias_sem_atividade": d.dias_sem_atividade,
            "oferta_do_negocio": {"oferta_id": oferta_do_negocio.id, "nome": oferta_do_negocio.nome} if oferta_do_negocio else None,
            "risco_map": d.risco_map,
            "conta_e_cliente": d.e_cliente,
        },
        "meeting_intelligence": {
            "reunioes": [
                {
                    "id": r.id, "data_hora": r.data_hora, "status": r.status,
                    "tem_transcricao": bool(r.transcricao), "resumo_ia": (r.resumo_ia or None) and r.resumo_ia[:800],
                }
                for r in d.reunioes
            ],
            "necessidades": [como_dict(n) for n in d.necessidades],
        },
        "next_best_offer": resultado_nbo,
        "next_best_action": resultado_nba,
        "discovery_gaps": resultado_discovery,
        "cross_sell": melhor.dados["cross_sell"] if melhor else resultado_ws["cross_sell"],
        "upsell": melhor.dados["upsell"] if melhor else resultado_ws["upsell"],
        "white_space": resultado_ws,
        "buying_signals": _sinais_compra(d),
        "riscos": _riscos(d, resultado_nbo),
        "stakeholders_faltantes": _stakeholders_faltantes(d, resultado_nbo),
    }
    return _serializar(card)


def white_space_da_conta(db: Session, tenant_id: str, conta_id: int) -> dict:
    return _serializar(white_space.analisar(dados_mod.carregar_conta(db, tenant_id, conta_id)))
