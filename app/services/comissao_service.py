"""Base líquida das comissões de representantes (D-073), para todas as vendas (planos privados e Government).

A comissão é paga sobre o lucro líquido da CyberFort com o B2B ON naquele recebimento:

    base líquida = valor recebido − impostos − custo de infraestrutura
    comissão     = base líquida × taxa do representante/componente (× fração, se dividida)

Impostos e infraestrutura são alíquotas sobre o valor recebido, numa política versionada e auditada (`BASE_LIQUIDA`).
Enquanto alguma não estiver definida, a comissão nasce `pendente_parametros` (valor 0, nunca repassada) e é recalculada
quando o PO informar os valores — nenhuma alíquota é presumida.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.comissao_representante import ComissaoRepresentante
from app.models.contrato_governo import PoliticaComissao
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

CODIGO = "BASE_LIQUIDA"
DEDUCOES = ("impostos", "infraestrutura")
PENDENTE = "pendente_parametros"
CENTAVO = Decimal("0.01")


def vigente(db: Session) -> PoliticaComissao:
    politica = db.query(PoliticaComissao).filter_by(codigo=CODIGO, ativa=True).order_by(PoliticaComissao.versao.desc()).first()
    if politica is None:  # bancos criados sem a migração (testes, E2E): começa sem alíquotas, como em produção
        politica = PoliticaComissao(codigo=CODIGO, versao=1, regras=dict.fromkeys(DEDUCOES), ativa=True,
                                    motivo="Alíquotas a informar pelo PO (D-073)", criado_por="semente")
        db.add(politica)
        db.flush()
    return politica


def aliquotas(db: Session) -> dict:
    politica = vigente(db)
    return {**{d: politica.regras.get(d) for d in DEDUCOES}, "versao": politica.versao}


def base_liquida(bruto, deducoes: dict) -> Decimal | None:
    if any(deducoes.get(d) is None for d in DEDUCOES):
        return None
    fator = Decimal(1) - sum((Decimal(str(deducoes[d])) for d in DEDUCOES), Decimal(0))
    return (Decimal(str(bruto)) * fator).quantize(CENTAVO, ROUND_HALF_UP)


def calcular(db: Session, comissao: ComissaoRepresentante, bruto, taxa, fracao=1) -> ComissaoRepresentante:
    """Preenche base bruta, deduções, base líquida, valor e status da comissão."""
    deducoes = aliquotas(db)
    liquida = base_liquida(bruto, deducoes)
    comissao.base_bruta = float(Decimal(str(bruto)))
    comissao.deducoes = deducoes
    comissao.taxa = float(taxa)
    comissao.fracao_divisao = float(fracao)
    if liquida is None:
        comissao.base_calculo, comissao.valor_comissao, comissao.status = None, 0.0, PENDENTE
    else:
        comissao.base_calculo = float(liquida)
        comissao.valor_comissao = float((liquida * Decimal(str(taxa)) * Decimal(str(fracao))).quantize(CENTAVO, ROUND_HALF_UP))
        comissao.status = "calculada"
    return comissao


def definir(db: Session, impostos: float, infraestrutura: float, motivo: str, ator_id: str | None) -> dict:
    """Nova versão das alíquotas; recalcula as comissões que aguardavam. Comissões já calculadas não mudam."""
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo da mudança.")
    valores = {"impostos": impostos, "infraestrutura": infraestrutura}
    if any(v is None or not 0 <= v < 1 for v in valores.values()) or sum(valores.values()) >= 1:
        raise ValidacaoFalhou("Alíquotas entre 0 e 1 (ex.: 0,15 = 15%), somando menos de 100%.")
    anterior = vigente(db)
    anterior.ativa = False
    nova = PoliticaComissao(codigo=CODIGO, versao=anterior.versao + 1, regras=valores, ativa=True, motivo=motivo, criado_por=ator_id)
    db.add(nova)
    db.flush()
    recalculadas = 0
    for comissao in db.query(ComissaoRepresentante).filter_by(status=PENDENTE).all():
        calcular(db, comissao, comissao.base_bruta or 0, comissao.taxa or 0, comissao.fracao_divisao or 1)
        recalculadas += 1
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "base_liquida_comissao_alterada", "politica_comissao", nova.id,
                                ator_id, {"antes": anterior.regras, "depois": valores, "versao": nova.versao, "motivo": motivo,
                                          "comissoes_recalculadas": recalculadas, "origem": "admin"})
    db.commit()
    return {**aliquotas(db), "comissoes_recalculadas": recalculadas}
