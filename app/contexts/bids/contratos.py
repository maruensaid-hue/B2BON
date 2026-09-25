"""Contract Intelligence do lado vendedor (Fase 9): contratos ganhos e o
que eles pedem agora (renovação, nova licitação)."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.contrato_venda_publica import ContratoVendaPublica

DIAS_RENOVACAO = 120


def sinais(db: Session, tenant_id: str, hoje: date | None = None) -> list[dict]:
    hoje = hoje or date.today()
    resultado = []
    for c in db.query(ContratoVendaPublica).filter_by(tenant_id=tenant_id, status="VIGENTE").all():
        if c.vigencia_fim is None:
            resultado.append({"contrato_id": c.id, "acao": "INFORMAR_VIGENCIA",
                              "motivo": "Contrato sem data de fim: sem ela não há alerta de renovação."})
            continue
        dias = (c.vigencia_fim - hoje).days
        if dias < 0:
            resultado.append({"contrato_id": c.id, "acao": "ATUALIZAR_STATUS",
                              "motivo": f"Vigência terminou em {c.vigencia_fim:%d/%m/%Y} e o contrato ainda consta como vigente."})
        elif dias <= DIAS_RENOVACAO:
            acao = "PREPARAR_RENOVACAO" if c.renovavel else "MONITORAR_NOVA_LICITACAO"
            motivo = (f"Vence em {dias} dias e é renovável: preparar a renovação/aditivo." if c.renovavel
                      else f"Vence em {dias} dias sem renovação prevista: acompanhar a nova contratação do órgão.")
            resultado.append({"contrato_id": c.id, "acao": acao, "motivo": motivo, "vigencia_fim": c.vigencia_fim,
                              "janela_dias": DIAS_RENOVACAO})
    return resultado


def como_dict(c: ContratoVendaPublica) -> dict:
    return {
        "id": c.id, "licitacao_id": c.licitacao_id, "conta_id": c.conta_id, "orgao_nome": c.orgao_nome,
        "numero": c.numero, "objeto": c.objeto, "valor": c.valor, "vigencia_inicio": c.vigencia_inicio,
        "vigencia_fim": c.vigencia_fim, "renovavel": c.renovavel, "status": c.status, "criado_em": c.criado_em,
    }
