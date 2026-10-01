"""Ofertas Government lidas do catálogo central (tabela `plano`) e proposta por template (D-072).

Página pública, Admin → Planos, proposta e contrato leem daqui: o preço existe num lugar só.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.governo import politicas
from app.contexts.governo.tipos import CHAVES_ENTITLEMENT, SEGMENTO_GOVERNO, ModeloCobranca
from app.models.plano import Plano
from app.services.errors import NaoEncontrado, RegraNegocioViolada

ZERO = Decimal(0)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def contratacao_inicial(licenca, implantacao, assinatura) -> Decimal:
    """Contratação inicial = Licença Institucional + Implantação + Subscrição Anual."""
    return _d(licenca) + _d(implantacao) + _d(assinatura)


def planos(db: Session) -> list[Plano]:
    return db.query(Plano).filter_by(segmento=SEGMENTO_GOVERNO).order_by(Plano.preco_assinatura_anual, Plano.id).all()


def obter_plano(db: Session, plano_id: int) -> Plano:
    plano = db.get(Plano, plano_id)
    if plano is None:
        raise NaoEncontrado(f"Plano {plano_id} não encontrado")
    if plano.segmento != SEGMENTO_GOVERNO:
        raise RegraNegocioViolada("Contrato governamental só com plano do segmento Government.")
    return plano


def oferta(plano: Plano) -> dict:
    """Componentes separados; nunca um valor mensal. Entitlement sem valor = "conforme contrato"."""
    entitlements = {chave: (plano.entitlements or {}).get(chave) for chave in CHAVES_ENTITLEMENT}
    licenca, implantacao, assinatura = _d(plano.preco_licenca), _d(plano.preco_implantacao), _d(plano.preco_assinatura_anual)
    return {
        "id": plano.id, "nome": plano.nome, "segmento": plano.segmento, "modelo_cobranca": plano.modelo_cobranca,
        "periodicidade": "ANUAL", "recomendado": plano.recomendado, "modulos": list(plano.modulos_contratados or []),
        "licenca": float(licenca), "implantacao": float(implantacao), "assinatura_anual": float(assinatura),
        "contratacao_inicial": float(contratacao_inicial(licenca, implantacao, assinatura)),
        "creditos_ia_anuais": plano.creditos_ia_anuais, "entitlements": entitlements,
    }


def catalogo_publico(db: Session) -> dict:
    """Seção "B2B ON Government" da página de preços. Subscription Only não tem preço público."""
    return {
        "id": "government", "nome": "B2B ON Government",
        "descricao": "Para órgãos e entidades públicas: licença institucional, implantação e subscrição anual.",
        "composicao": "Contratação inicial = Licença Institucional + Implantação + Subscrição Anual",
        "renovacao": "A partir do segundo período contratual, a renovação normal corresponde à subscrição anual, acrescida de "
                     "eventuais serviços, créditos adicionais e reajustes previstos contratualmente.",
        "adaptacao": "Condições podem ser adaptadas ao edital, ETP, Termo de Referência, modalidade de contratação e necessidades do órgão.",
        "so_assinatura": "Modelo de subscrição anual disponível conforme condições da contratação.",
        "modelos": [m.value for m in (ModeloCobranca.LICENCA_MAIS_ASSINATURA, ModeloCobranca.SO_ASSINATURA)],
        "planos": [oferta(p) for p in planos(db)],
    }


def _brl(valor: Decimal) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def proposta(db: Session, plano: Plano, entidade: str, referencia: str | None = None, valores: dict | None = None) -> dict:
    """Resumo comercial pelos componentes, no template vigente (não é texto jurídico)."""
    base = oferta(plano)
    valores = {**base, **(valores or {})}
    licenca, implantacao, assinatura = _d(valores["licenca"]), _d(valores["implantacao"]), _d(valores["assinatura_anual"])
    total = contratacao_inicial(licenca, implantacao, assinatura)
    template = politicas.template_vigente(db)
    texto = template.corpo.format(
        plano=plano.nome, entidade=entidade, referencia=referencia or "—", licenca=_brl(licenca), implantacao=_brl(implantacao),
        assinatura=_brl(assinatura), contratacao_inicial=_brl(total),
        creditos=f"{int(valores['creditos_ia_anuais'] or 0):,}".replace(",", "."),
    )
    return {"plano": plano.nome, "template_versao": template.versao, "texto": texto,
            "componentes": {"licenca": float(licenca), "implantacao": float(implantacao), "assinatura_anual": float(assinatura),
                            "contratacao_inicial": float(total), "creditos_ia_anuais": valores["creditos_ia_anuais"]}}
