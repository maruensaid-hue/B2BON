"""Next Best Action (§22): o que fazer agora neste negócio.

Regras determinísticas, cada uma com motivo e evidência, em ordem de
prioridade. A saída é sugestão para o vendedor: nenhuma ação é executada
sozinha.
"""

from app.contexts.opportunity.dados import DadosOportunidade
from app.contexts.opportunity.discovery import PAPEIS_AUTORIDADE
from app.contexts.opportunity.explicavel import Confianca, Evidencia, FonteEvidencia, Recomendacao, recomendacao
from app.contexts.opportunity.nbo import churn_alto, evidencia_churn

FONTE = "opportunity.next_best_action.v1"
DIAS_PARADO = 14
PROBABILIDADE_FASE_PROPOSTA = 60


class Acao:
    PRIORIZAR_REMEDIACAO = "PRIORIZAR_REMEDIACAO"
    ENVOLVER_DECISOR = "ENVOLVER_DECISOR"
    DISCOVERY_ADICIONAL = "DISCOVERY_ADICIONAL"
    VALIDAR_ORCAMENTO = "VALIDAR_ORCAMENTO"
    NAO_ENVIAR_PROPOSTA_AINDA = "NAO_ENVIAR_PROPOSTA_AINDA"
    AGENDAR_REUNIAO = "AGENDAR_REUNIAO"
    DEFINIR_PROXIMO_PASSO = "DEFINIR_PROXIMO_PASSO"
    VALIDAR_PREREQUISITOS = "VALIDAR_PREREQUISITOS"
    DEMONSTRACAO = "DEMONSTRACAO"
    PREPARAR_PROPOSTA = "PREPARAR_PROPOSTA"


def _acao(acao: str, titulo: str, motivo: str, evidencias: list[Evidencia], confianca: Confianca, dados: DadosOportunidade, **extra) -> Recomendacao:
    return recomendacao("next_best_action", titulo, motivo, evidencias, confianca, FONTE, gerado_em=dados.agora, dados={"acao": acao, **extra})


def recomendar(dados: DadosOportunidade, discovery: dict, nbo: dict) -> dict:
    if dados.negocio is None or dados.estagio.tipo != "aberto":
        return {"status": "NEGOCIO_ENCERRADO", "recomendacoes": []}

    acoes: list[Recomendacao] = []
    negocio = dados.negocio
    dimensoes = discovery["dimensoes"]
    faltando = [c for c, d in dimensoes.items() if d["status"] != "CONFIRMADO"]
    evid_prob = Evidencia("negocio", negocio.id, f"Probabilidade {negocio.probabilidade}% no estágio \"{dados.estagio.nome}\"", FonteEvidencia.CADASTRO)

    if churn_alto(dados):
        acoes.append(_acao(
            Acao.PRIORIZAR_REMEDIACAO, "Priorizar remediação antes de expandir",
            "A conta já é cliente e o MAP indica risco de churn crítico: expansão agressiva agora tende a piorar a relação.",
            [evidencia_churn(dados)], Confianca.ALTA, dados,
        ))

    decisores_autoridade = [d for d in dados.decisores if d.papel_confirmado in PAPEIS_AUTORIDADE]
    if not decisores_autoridade:
        evid = [Evidencia("decisor", d.id, f"{d.nome} ({d.cargo or 'sem cargo'}): papel {d.papel_confirmado or 'não confirmado'}", FonteEvidencia.CADASTRO) for d in dados.decisores]
        acoes.append(_acao(
            Acao.ENVOLVER_DECISOR, "Envolver o decisor",
            "Nenhum contato desta conta está confirmado como DECISION_MAKER ou ECONOMIC_BUYER.",
            evid or [Evidencia("lacuna", "decisores", "Nenhum decisor cadastrado na conta", FonteEvidencia.AUSENCIA)],
            Confianca.ALTA if negocio.probabilidade >= 50 else Confianca.MEDIA, dados,
        ))

    if "necessidade" in faltando:
        acoes.append(_acao(
            Acao.DISCOVERY_ADICIONAL, "Fazer discovery adicional",
            "A necessidade do cliente ainda não está confirmada.",
            [Evidencia("lacuna", "necessidade", f"Dimensão necessidade: {dimensoes['necessidade']['status']}", FonteEvidencia.AUSENCIA)],
            Confianca.ALTA, dados, perguntas=discovery["perguntas_sugeridas"],
        ))
    if "orcamento" in faltando:
        acoes.append(_acao(
            Acao.VALIDAR_ORCAMENTO, "Validar orçamento",
            "Não há informação confirmada de orçamento.",
            [Evidencia("lacuna", "orcamento", f"Dimensão orçamento: {dimensoes['orcamento']['status']}", FonteEvidencia.AUSENCIA)],
            Confianca.ALTA, dados,
        ))
    if faltando and negocio.probabilidade >= PROBABILIDADE_FASE_PROPOSTA:
        acoes.append(_acao(
            Acao.NAO_ENVIAR_PROPOSTA_AINDA, "Não enviar proposta ainda",
            f"O negócio está com {negocio.probabilidade}% de probabilidade, mas faltam: {', '.join(discovery['faltando'])}.",
            [evid_prob, Evidencia("lacuna", "discovery", "; ".join(discovery["faltando"]), FonteEvidencia.AUSENCIA)],
            Confianca.MEDIA, dados,
        ))

    if dados.dias_sem_atividade > DIAS_PARADO:
        ref = f"última atividade há {dados.dias_sem_atividade} dias" if dados.ultima_atividade_em else f"nenhuma atividade desde a criação, há {dados.dias_sem_atividade} dias"
        acoes.append(_acao(
            Acao.AGENDAR_REUNIAO, "Retomar contato e agendar reunião",
            f"Negócio parado: {ref}.",
            [Evidencia("negocio", negocio.id, ref, FonteEvidencia.CALCULO)], Confianca.ALTA, dados,
        ))
    if not dados.conta.proximo_passo:
        acoes.append(_acao(
            Acao.DEFINIR_PROXIMO_PASSO, "Definir próximo passo com o cliente",
            "A conta não tem próximo passo registrado.",
            [Evidencia("lacuna", "proximo_passo", "Campo próximo passo vazio na conta", FonteEvidencia.AUSENCIA)],
            Confianca.MEDIA, dados,
        ))

    melhor = nbo["recomendacoes"][0] if nbo["recomendacoes"] else None
    if melhor is not None and melhor.dados.get("prerequisitos"):
        acoes.append(_acao(
            Acao.VALIDAR_PREREQUISITOS, f"Validar pré-requisitos de \"{melhor.titulo}\" (assessment)",
            "A oferta mais aderente tem pré-requisitos cadastrados que ainda não foram validados neste negócio.",
            [Evidencia("oferta", melhor.dados["oferta_id"], "; ".join(melhor.dados["prerequisitos"]), FonteEvidencia.CADASTRO)],
            Confianca.MEDIA, dados,
        ))
    if (
        melhor is not None
        and dimensoes["necessidade"]["status"] == "CONFIRMADO"
        and melhor.confianca != Confianca.BAIXA
        and faltando
    ):
        acoes.append(_acao(
            Acao.DEMONSTRACAO, f"Demonstrar \"{melhor.titulo}\" focando nas necessidades confirmadas",
            "A necessidade está confirmada e a oferta casa com ela, mas ainda faltam informações para proposta.",
            list(melhor.evidencias), Confianca.MEDIA, dados, oferta_id=melhor.dados["oferta_id"],
        ))
    if not faltando and decisores_autoridade and not churn_alto(dados):
        evid = [Evidencia("discovery", "completo", "Necessidade, autoridade, orçamento, prazo e concorrência confirmados", FonteEvidencia.CONFIRMADO_POR_HUMANO)]
        if melhor is not None:
            evid.extend(melhor.evidencias)
        acoes.append(_acao(
            Acao.PREPARAR_PROPOSTA, "Preparar proposta" + (f" de \"{melhor.titulo}\"" if melhor else ""),
            "Discovery completo e decisor confirmado.",
            evid, Confianca.ALTA if melhor is not None else Confianca.MEDIA, dados,
            oferta_id=melhor.dados["oferta_id"] if melhor else None,
        ))
    return {"status": "OK", "recomendacoes": acoes}
