"""Supplier 360 e Supplier Intelligence (§42).

Cada bloco diz a natureza do dado: OFFICIAL (fontes oficiais registradas),
INTERNAL (contratos, fiscalizações e avaliações do próprio órgão) e
SELF_DECLARED (perfil público do fornecedor na Business Network, só se ele
estiver visível no diretório). Nada do comprador vai para o fornecedor.
"""

from sqlalchemy.orm import Session

from app.contexts.network.contract import perfil_publico_por_cnpj
from app.contexts.procurement import contratos as contratos_intel
from app.models.contrato_compra import ContratoCompra
from app.models.evento_contrato_compra import EventoContratoCompra
from app.models.fornecedor_compras import FornecedorCompras


def visao_360(db: Session, tenant_id: str, fornecedor: FornecedorCompras) -> dict:
    contratos = db.query(ContratoCompra).filter_by(tenant_id=tenant_id, fornecedor_id=fornecedor.id).order_by(ContratoCompra.id).all()
    intel = [contratos_intel.inteligencia(db, tenant_id, c) for c in contratos]
    ocorrencias_avulsas = db.query(EventoContratoCompra).filter_by(
        tenant_id=tenant_id, fornecedor_id=fornecedor.id, contrato_id=None).all()
    notas = [i["nota_media"] for i in intel if i["nota_media"] is not None]
    return {
        "identidade": {"id": fornecedor.id, "cnpj": fornecedor.cnpj, "razao_social": fornecedor.razao_social,
                       "categorias": fornecedor.categorias or []},
        "OFFICIAL": fornecedor.dados_oficiais or None,
        "INTERNAL": {
            "contratos_vigentes": [{"id": c.id, "objeto": c.objeto, "valor_atual": c.valor_atual, "vigencia_fim": c.vigencia_fim}
                                   for c in contratos if c.status == "VIGENTE"],
            "contratos_historicos": [{"id": c.id, "objeto": c.objeto, "status": c.status} for c in contratos if c.status != "VIGENTE"],
            "valor_contratado_total": sum(c.valor_atual or 0 for c in contratos),
            "nota_media_fiscalizacao": round(sum(notas) / len(notas), 2) if notas else None,
            "ocorrencias": sum(i["ocorrencias"] for i in intel) + sum(1 for e in ocorrencias_avulsas if e.tipo == "OCORRENCIA"),
            "avaliacoes_internas": fornecedor.dados_internos or None,
        },
        "SELF_DECLARED": perfil_publico_por_cnpj(db, fornecedor.cnpj),
    }


def ranking_por_categoria(db: Session, tenant_id: str, categoria: str) -> list[dict]:
    contratos = db.query(ContratoCompra).filter_by(tenant_id=tenant_id, categoria=categoria).all()
    por_fornecedor: dict[int, dict] = {}
    for c in contratos:
        intel = contratos_intel.inteligencia(db, tenant_id, c)
        item = por_fornecedor.setdefault(c.fornecedor_id, {"fornecedor_id": c.fornecedor_id, "contratos": 0, "valor": 0.0,
                                                           "notas": [], "ocorrencias": 0})
        item["contratos"] += 1
        item["valor"] += c.valor_atual or 0
        item["ocorrencias"] += intel["ocorrencias"]
        if intel["nota_media"] is not None:
            item["notas"].append(intel["nota_media"])
    total = sum(i["valor"] for i in por_fornecedor.values())
    resultado = []
    for item in por_fornecedor.values():
        notas = item.pop("notas")
        item["nota_media"] = round(sum(notas) / len(notas), 2) if notas else None
        item["participacao"] = round(item["valor"] / total, 3) if total else None
        resultado.append(item)
    return sorted(resultado, key=lambda i: -i["valor"])
