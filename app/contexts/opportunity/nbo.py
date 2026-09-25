"""Next Best Offer (§21): o que vender, com fit, motivo e evidência.

Cruza, de forma determinística: necessidades do negócio (confirmadas
pesam mais que sugeridas) × Offer Intelligence (problemas resolvidos,
dores, casos de uso, requisitos), segmento da conta × indústrias da
oferta, cargos dos decisores × personas, ICP, histórico (o que a conta já
comprou) e MAP (churn alto suprime cross-sell/upsell, §26).

Não cruza ainda: Corporate Brain (texto livre, sem embeddings, D-017) e
Business Graph (Fase 7). Isso é declarado na resposta, não escondido.
"""

from app.contexts.opportunity import texto
from app.contexts.opportunity.dados import DadosOportunidade
from app.contexts.opportunity.explicavel import (
    INSUFFICIENT_INFORMATION,
    Confianca,
    Evidencia,
    FonteEvidencia,
    Recomendacao,
    recomendacao,
)
from app.models.oferta import Oferta

FONTE = "opportunity.next_best_offer.v1"
PESO_NECESSIDADE_CONFIRMADA = 25
PESO_NECESSIDADE_SUGERIDA = 10
TETO_NECESSIDADES = 60
PESO_INDUSTRIA = 15
PESO_PERSONA = 10
PESO_ICP = 15
PENALIDADE_INCOMPATIBILIDADE = 30
CATEGORIAS_CASAVEIS = frozenset({"dor", "requisito", "objecao", "outro"})
NAO_CRUZADOS = ["Corporate Brain (sem busca semântica ainda, D-017)", "Business Graph (Fase 7)"]


def itens_oferta(oferta: Oferta) -> list[tuple[str, str]]:
    campos = ("problemas_resolvidos", "dores", "casos_uso", "requisitos")
    return [(campo, item) for campo in campos for item in (getattr(oferta, campo) or []) if item]


def tem_inteligencia(oferta: Oferta) -> bool:
    return bool(itens_oferta(oferta) or oferta.industrias or oferta.personas)


def churn_alto(dados: DadosOportunidade) -> bool:
    return dados.e_cliente and dados.risco_map is not None and dados.risco_map["classificacao"] == "critico"


def evidencia_churn(dados: DadosOportunidade) -> Evidencia:
    r = dados.risco_map or {}
    return Evidencia(
        "map", dados.conta.id,
        f"Risco de churn {r.get('classificacao')} (score {r.get('score')}; sinais: {', '.join(r.get('sinais') or []) or 'nenhum'})",
        FonteEvidencia.CALCULO,
    )


def _casa_lista(valor: str | None, lista: list | None) -> str | None:
    for item in lista or []:
        if item and texto.termos_em_comum(valor, item):
            return item
    return None


def avaliar(dados: DadosOportunidade, oferta: Oferta, necessidades) -> dict:
    """Fit de uma oferta. Devolve score, evidências, riscos e contagem."""
    evidencias: list[Evidencia] = []
    riscos: list[str] = []
    pontos_necessidade = 0
    necessidades_confirmadas_casadas = 0
    necessidades_casadas = 0

    for n in necessidades:
        if n.categoria not in CATEGORIAS_CASAVEIS:
            continue
        for campo, item in itens_oferta(oferta):
            comuns = texto.termos_em_comum(n.descricao, item) or texto.termos_em_comum(n.citacao, item)
            if not comuns:
                continue
            confirmada = n.status == "confirmada"
            pontos_necessidade += PESO_NECESSIDADE_CONFIRMADA if confirmada else PESO_NECESSIDADE_SUGERIDA
            necessidades_casadas += 1
            necessidades_confirmadas_casadas += int(confirmada)
            evidencias.append(
                Evidencia(
                    "necessidade", n.id,
                    f"\"{n.descricao}\" ↔ {campo.replace('_', ' ')}: \"{item}\"",
                    FonteEvidencia.CONFIRMADO_POR_HUMANO if confirmada else FonteEvidencia.SUGESTAO_IA,
                )
            )
            break
        incompat = _casa_lista(n.descricao, oferta.incompatibilidades)
        if incompat:
            riscos.append(f"Necessidade \"{n.descricao}\" esbarra na incompatibilidade \"{incompat}\".")

    score = min(pontos_necessidade, TETO_NECESSIDADES)
    firmografia = 0

    industria = _casa_lista(dados.conta.segmento, oferta.industrias)
    if industria:
        score += PESO_INDUSTRIA
        firmografia += 1
        evidencias.append(Evidencia("conta", dados.conta.id, f"Segmento \"{dados.conta.segmento}\" ↔ indústria \"{industria}\"", FonteEvidencia.CADASTRO))
    incompat_segmento = _casa_lista(dados.conta.segmento, oferta.incompatibilidades)
    if incompat_segmento:
        riscos.append(f"Segmento da conta esbarra na incompatibilidade \"{incompat_segmento}\".")

    for d in dados.decisores:
        persona = _casa_lista(d.cargo, oferta.personas)
        if persona:
            score += PESO_PERSONA
            firmografia += 1
            evidencias.append(Evidencia("decisor", d.id, f"{d.nome} ({d.cargo}) ↔ persona \"{persona}\"", FonteEvidencia.CADASTRO))
            break

    if oferta.icp_id is not None and oferta.icp_id == dados.conta.icp_id:
        score += PESO_ICP
        firmografia += 1
        evidencias.append(Evidencia("conta", dados.conta.id, f"Conta está no ICP {oferta.icp_id}, o mesmo da oferta", FonteEvidencia.CADASTRO))

    if riscos:
        score -= PENALIDADE_INCOMPATIBILIDADE
    score = max(0, min(100, score))

    if necessidades_confirmadas_casadas and firmografia:
        confianca = Confianca.ALTA
    elif necessidades_confirmadas_casadas or (necessidades_casadas and firmografia):
        confianca = Confianca.MEDIA
    else:
        confianca = Confianca.BAIXA

    return {
        "score": score,
        "evidencias": evidencias,
        "riscos": riscos,
        "confianca": confianca,
        "necessidades_casadas": necessidades_casadas,
    }


def ofertas_por_nome(ofertas: list[Oferta], nomes: list | None, excluir: set[int]) -> list[dict]:
    alvos = {texto.normalizar(n) for n in nomes or [] if n}
    return [{"oferta_id": o.id, "nome": o.nome} for o in ofertas if texto.normalizar(o.nome) in alvos and o.id not in excluir]


def recomendar(dados: DadosOportunidade, limite: int = 3) -> dict:
    if not dados.ofertas:
        return {
            "status": INSUFFICIENT_INFORMATION,
            "faltando": ["Nenhuma oferta disponível para venda no portfólio (Configurações → Ofertas)."],
            "recomendacoes": [],
            "nao_cruzados": NAO_CRUZADOS,
        }
    necessidades = dados.necessidades or dados.necessidades_da_conta
    faltando: list[str] = []
    if not necessidades:
        faltando.append("Necessidades do cliente (extraia da reunião ou registre no negócio).")
    if not any(tem_inteligencia(o) for o in dados.ofertas):
        faltando.append("Offer Intelligence das ofertas (problemas resolvidos, dores, casos de uso, indústrias, personas).")

    suprimir_expansao = churn_alto(dados)
    candidatas: list[tuple[int, Recomendacao]] = []
    for oferta in dados.ofertas:
        if oferta.id in dados.ofertas_compradas_ids:
            continue
        avaliacao = avaliar(dados, oferta, necessidades)
        if avaliacao["score"] <= 0 or not avaliacao["evidencias"]:
            continue
        cross_sell = [] if suprimir_expansao else ofertas_por_nome(dados.ofertas, oferta.cross_sell, dados.ofertas_compradas_ids | {oferta.id})
        upsell = [] if suprimir_expansao else ofertas_por_nome(dados.ofertas, oferta.upsell, {oferta.id})
        riscos = list(avaliacao["riscos"])
        evidencias = list(avaliacao["evidencias"])
        if suprimir_expansao:
            riscos.append("Churn alto nesta conta: cross-sell e upsell suprimidos; priorize remediação (§26).")
            evidencias.append(evidencia_churn(dados))
        motivo = (
            f"Casa com {avaliacao['necessidades_casadas']} necessidade(s) do cliente"
            if avaliacao["necessidades_casadas"]
            else "Casa só pelo perfil da conta (segmento, persona ou ICP), sem necessidade registrada"
        )
        candidatas.append(
            (
                avaliacao["score"],
                recomendacao(
                    "next_best_offer", oferta.nome, motivo + ".", evidencias, avaliacao["confianca"], FONTE,
                    gerado_em=dados.agora,
                    dados={
                        "oferta_id": oferta.id,
                        "fit_score": avaliacao["score"],
                        "riscos": riscos,
                        "cross_sell": cross_sell,
                        "upsell": upsell,
                        "e_a_oferta_do_negocio": dados.negocio is not None and dados.negocio.oferta_id == oferta.id,
                        "prerequisitos": oferta.prerequisitos or [],
                        "objecoes_conhecidas": oferta.objecoes or [],
                    },
                ),
            )
        )
    candidatas.sort(key=lambda par: (-par[0], par[1].titulo))
    recomendacoes = [r for _, r in candidatas[:limite]]
    if not recomendacoes and not faltando:
        faltando.append("Nenhuma oferta casou com as necessidades e o perfil desta conta.")
    return {
        "status": "OK" if recomendacoes else INSUFFICIENT_INFORMATION,
        "faltando": faltando,
        "recomendacoes": recomendacoes,
        "nao_cruzados": NAO_CRUZADOS,
    }
