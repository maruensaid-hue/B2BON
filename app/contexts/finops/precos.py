"""Custo do provedor por chamada (Fase 5, §54).

    custo = entrada×P_in + saída×P_out + cache_escrita×P_cw + cache_leitura×P_cr   (USD, tokens/1e6)

`input_tokens` da Anthropic já exclui os tokens de cache, então os quatro
termos não se sobrepõem. Modelo sem preço cadastrado → custo `None`
(sinalizado no ledger e no dashboard), nunca zero.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.preco_modelo_ia import PrecoModeloIa

MILHAO = Decimal(1_000_000)

# Mesmos valores semeados pela migração f892ebf6e6f9 (teste garante que não divergem).
PRECOS_REFERENCIA = [
    ("claude-haiku-4-5", 1.0, 5.0, 1.25, 0.10),
    ("claude-sonnet-5", 2.0, 10.0, 2.50, 0.20),
    ("claude-sonnet-4-6", 3.0, 15.0, 3.75, 0.30),
    ("claude-opus-5", 5.0, 25.0, 6.25, 0.50),
    ("claude-opus-5-5", 4.0, 20.0, 5.00, 0.20),
    ("claude-opus-4-8", 5.0, 25.0, 6.25, 0.50),
]


def obter_preco(db: Session, modelo: str | None, provider: str = "anthropic", em: date | None = None) -> PrecoModeloIa | None:
    """Preço vigente para o modelo: match exato ou pelo maior prefixo
    (ex.: um id datado `claude-sonnet-5-2026...` cai em `claude-sonnet-5`)."""
    if not modelo:
        return None
    em = em or date.today()
    candidatos = (
        db.query(PrecoModeloIa)
        .filter(PrecoModeloIa.provider == provider, PrecoModeloIa.vigente_desde <= em)
        .order_by(PrecoModeloIa.vigente_desde.desc(), PrecoModeloIa.id.desc())
        .all()
    )
    melhor = None
    for preco in candidatos:
        if modelo == preco.modelo or modelo.startswith(preco.modelo + "-"):
            if melhor is None or len(preco.modelo) > len(melhor.modelo):
                melhor = preco
    return melhor


def calcular_custo(preco: PrecoModeloIa, entrada: int, saida: int, cache_escrita: int = 0, cache_leitura: int = 0) -> Decimal:
    total = (
        Decimal(entrada) * Decimal(str(preco.entrada_usd_mtok))
        + Decimal(saida) * Decimal(str(preco.saida_usd_mtok))
        + Decimal(cache_escrita) * Decimal(str(preco.cache_escrita_usd_mtok))
        + Decimal(cache_leitura) * Decimal(str(preco.cache_leitura_usd_mtok))
    )
    return (total / MILHAO).quantize(Decimal("0.00000001"))


def garantir_precos_referencia(db: Session) -> None:
    """Idempotente — para bancos criados por `create_all` (dev/testes),
    que não rodam a semente da migração."""
    if db.query(PrecoModeloIa).count():
        return
    for modelo, e, s, cw, cr in PRECOS_REFERENCIA:
        db.add(PrecoModeloIa(provider="anthropic", modelo=modelo, vigente_desde=date(2026, 6, 24), entrada_usd_mtok=e,
                             saida_usd_mtok=s, cache_escrita_usd_mtok=cw, cache_leitura_usd_mtok=cr, fonte="referência (semente)"))
    db.commit()
