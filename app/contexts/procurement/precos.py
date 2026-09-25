"""Price Research foundation: estatística sobre preços coletados com fonte.
Nunca gera preço: sem coleta, não há referência."""

from statistics import mean, median, pstdev

from sqlalchemy.orm import Session

from app.contexts.shared.texto import normalizar
from app.models.pesquisa_preco import PesquisaPreco

DESVIO_ALERTA = 0.30  # cotação 30% acima/abaixo da mediana = sinal para revisão
MINIMO_AMOSTRAS = 3


def resumo(db: Session, tenant_id: str, processo_id: int) -> list[dict]:
    grupos: dict[str, list[PesquisaPreco]] = {}
    for p in db.query(PesquisaPreco).filter_by(tenant_id=tenant_id, processo_id=processo_id).order_by(PesquisaPreco.id):
        grupos.setdefault(normalizar(p.item_descricao), []).append(p)
    resultado = []
    for itens in grupos.values():
        precos = [i.preco_unitario for i in itens]
        med = median(precos)
        fora = [
            {"id": i.id, "preco": i.preco_unitario, "fonte": i.fonte_descricao, "desvio": round(i.preco_unitario / med - 1, 3)}
            for i in itens if med and abs(i.preco_unitario / med - 1) > DESVIO_ALERTA
        ]
        resultado.append({
            "item": itens[0].item_descricao,
            "unidade": itens[0].unidade,
            "amostras": len(precos),
            "suficiente": len(precos) >= MINIMO_AMOSTRAS,
            "mediana": med,
            "media": round(mean(precos), 2),
            "minimo": min(precos),
            "maximo": max(precos),
            "coeficiente_variacao": round(pstdev(precos) / mean(precos), 3) if len(precos) > 1 and mean(precos) else None,
            "fora_da_faixa": fora,
            "fontes": sorted({i.fonte_tipo for i in itens}),
        })
    return resultado
