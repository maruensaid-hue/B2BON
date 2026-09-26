"""Tender Analyzer e TR Analyzer (Fase 9, §33-§34), via AI Gateway —
perfil `edital_tr` do Requirement Engine compartilhado (`sourcing.requisitos`, S1).

Proveniência (GATE): a IA propõe requisitos com a citação literal; o
sistema só grava o que encontra no texto do documento, calcula a página
a partir do próprio texto (não confia no número que a IA disser) e só
mantém a cláusula se ela aparecer na página. Cada requisito aponta para
documento (hash, fonte, URL) + página + cláusula + trecho.

Documento longo é analisado em blocos de páginas; cada bloco é uma chamada
medida. Acima do teto de blocos, a análise é parcial e isso é declarado.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.bids.tipos import CATEGORIAS_REQUISITO
from app.contexts.intelligence.contract import ContextoIA, aprendizado
from app.contexts.shared import texto
from app.contexts.sourcing import contract as sourcing
from app.core.observability import correlation_id_atual
from app.llm.base import LLMProvider
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.requisito_licitacao import RequisitoLicitacao

FEATURE_EDITAL = "bids.analise_edital"
FEATURE_TR = "bids.analise_tr"
CARACTERES_POR_BLOCO = 40_000
MAXIMO_BLOCOS = 8
MAXIMO_ITENS_POR_BLOCO = 60

_SISTEMA = (
    "Você analisa editais e termos de referência de licitações e RFPs para uma empresa que pretende "
    "participar. Responda SOMENTE com um array JSON. Cada item: "
    '{"categoria": uma de ' + ", ".join(CATEGORIAS_REQUISITO) + ', "descricao": frase curta em português, '
    '"citacao": trecho COPIADO LITERALMENTE do documento que comprova o item, "clausula": número do item/'
    'cláusula como aparece no documento (ex.: "5.2.1") ou null}. Não invente: sem trecho literal, não inclua. '
    "Não resuma o documento; extraia requisitos, prazos, garantias, penalidades, critérios, lotes/itens, "
    "obrigações e riscos. Se não houver nada, responda []."
)


def perfil() -> sourcing.requisitos.PerfilExtracao:
    """Perfil `edital_tr` do Requirement Engine (lido na hora: os limites do módulo são ajustáveis)."""
    return sourcing.requisitos.PerfilExtracao(
        nome="edital_tr", sistema=_SISTEMA, categorias=CATEGORIAS_REQUISITO, max_tokens=8000,
        caracteres_por_bloco=CARACTERES_POR_BLOCO, maximo_blocos=MAXIMO_BLOCOS, maximo_itens_por_bloco=MAXIMO_ITENS_POR_BLOCO,
    )


def analisar(db: Session, llm: LLMProvider, tenant_id: str, usuario_id: int | None, documento: DocumentoLicitacao,
             confirmado: bool = False) -> dict:
    sourcing.documentos.exigir_analisavel(documento.status_analise)
    paginas: list[str] = documento.paginas_texto or []
    feature = FEATURE_TR if documento.tipo == "TR" else FEATURE_EDITAL
    existentes = {
        texto.normalizar(r.descricao)
        for r in db.query(RequisitoLicitacao).filter_by(tenant_id=tenant_id, documento_id=documento.id).all()
    }
    base = ContextoIA(tenant_id=tenant_id, feature=feature, usuario_id=usuario_id, entidade_tipo="documento_licitacao",
                      entidade_id=documento.id)
    extracao = sourcing.requisitos.extrair(db, llm, base, paginas, perfil(), f"{documento.tipo} {documento.nome_arquivo}",
                                           confirmado)
    criados: list[RequisitoLicitacao] = []
    for item in extracao.itens:
        chave = texto.normalizar(item.descricao)
        if chave in existentes:
            continue
        existentes.add(chave)
        requisito = RequisitoLicitacao(
            tenant_id=tenant_id, licitacao_id=documento.licitacao_id, documento_id=documento.id,
            categoria=item.categoria, descricao=item.descricao, evidencia=item.evidencia, pagina=item.pagina,
            clausula=item.clausula, obrigatorio=item.obrigatorio, origem="ia", status="sugerido", correlation_id=correlation_id_atual(),
        )
        db.add(requisito)
        criados.append(requisito)

    documento.status_analise = "ANALISADO"
    documento.analisado_em = datetime.now(UTC)
    db.flush()
    if criados:
        aprendizado.registrar(
            db, tenant_id, feature, "GERADO", entidade_tipo="documento_licitacao", entidade_id=documento.id,
            usuario_id=usuario_id, dados={"sugeridos": len(criados), "sem_evidencia": extracao.sem_evidencia},
        )
    return {
        "documento_id": documento.id,
        "sugeridos": len(criados),
        "descartados_sem_evidencia": extracao.sem_evidencia,
        "blocos_analisados": extracao.blocos_analisados,
        "paginas_analisadas": extracao.paginas_analisadas,
        "paginas_total": extracao.paginas_total,
        "analise_parcial": extracao.parcial,
    }
