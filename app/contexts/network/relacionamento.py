"""Relationship Intelligence (Fase 8): força da relação entre duas empresas.

Só com sinais que o consultante pode ver: conexão aceita (ele é parte),
arestas visíveis do Business Graph (confirmadas pesam mais) e a última
interação real (DM ou sala). Categórica e explicável: cada ponto tem motivo.
"""

from sqlalchemy.orm import Session

from app.contexts.network import grafo, privacidade
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial

FORTE, MODERADA, FRACA, NENHUMA = "FORTE", "MODERADA", "FRACA", "NENHUMA"


def forca(db: Session, consultante: str, alvo: str, dias_sem_interacao: int | None) -> dict:
    motivos: list[str] = []
    pontos = 0
    conectadas = alvo in privacidade.conectados(db, consultante)
    if conectadas:
        pontos += 2
        motivos.append("Conexão aceita na rede.")

    cache: dict = {}
    arestas = [
        a for a in db.query(RelacionamentoEmpresarial).filter(
            ((RelacionamentoEmpresarial.tenant_id_origem == consultante) & (RelacionamentoEmpresarial.tenant_id_destino == alvo))
            | ((RelacionamentoEmpresarial.tenant_id_origem == alvo) & (RelacionamentoEmpresarial.tenant_id_destino == consultante))
        ).all()
        if grafo.aresta_visivel(db, consultante, a, cache)
    ]
    confirmadas = [a for a in arestas if a.confianca == "confirmada_pela_contraparte"]
    if confirmadas:
        pontos += 2
        motivos.append("Relacionamento confirmado pelas duas empresas: " + ", ".join(sorted({a.tipo for a in confirmadas})) + ".")
    elif arestas:
        pontos += 1
        motivos.append("Relacionamento declarado (sem confirmação): " + ", ".join(sorted({a.tipo for a in arestas})) + ".")

    if dias_sem_interacao is not None and dias_sem_interacao <= 14:
        pontos += 2
        motivos.append(f"Interação há {dias_sem_interacao} dia(s).")
    elif dias_sem_interacao is not None and dias_sem_interacao <= 30:
        pontos += 1
        motivos.append(f"Última interação há {dias_sem_interacao} dias.")

    nivel = FORTE if pontos >= 5 else MODERADA if pontos >= 3 else FRACA if pontos >= 1 else NENHUMA
    return {
        "forca": nivel,
        "motivos": motivos or ["Nenhuma conexão, relacionamento ou interação registrada."],
        "conectadas": conectadas,
        "relacionamentos": [
            {"tipo": a.tipo, "verificacao": a.confianca, "confianca": grafo.confianca(a).value} for a in arestas
        ],
    }
