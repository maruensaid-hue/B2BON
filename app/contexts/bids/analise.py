"""Tender Analyzer e TR Analyzer (Fase 9, §33-§34), via AI Gateway.

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
from app.contexts.intelligence.contract import ContextoIA, aprendizado, execucao, gerar, prompt_seguro
from app.contexts.shared import grounding, texto
from app.core.observability import correlation_id_atual
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.requisito_licitacao import RequisitoLicitacao
from app.services.errors import RegraNegocioViolada

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


def analisar(db: Session, llm: LLMProvider, tenant_id: str, usuario_id: int | None, documento: DocumentoLicitacao,
             confirmado: bool = False) -> dict:
    if documento.status_analise == "SEM_TEXTO":
        raise RegraNegocioViolada(
            "Este documento não tem texto extraível (provavelmente digitalizado). Sem OCR, a análise não é feita."
        )
    paginas: list[str] = documento.paginas_texto or []
    feature = FEATURE_TR if documento.tipo == "TR" else FEATURE_EDITAL
    blocos = grounding.blocos(paginas, CARACTERES_POR_BLOCO)
    parcial = len(blocos) > MAXIMO_BLOCOS
    blocos = blocos[:MAXIMO_BLOCOS]

    existentes = {
        texto.normalizar(r.descricao)
        for r in db.query(RequisitoLicitacao).filter_by(tenant_id=tenant_id, documento_id=documento.id).all()
    }
    criados: list[RequisitoLicitacao] = []
    sem_evidencia = 0
    base = ContextoIA(tenant_id=tenant_id, feature=feature, usuario_id=usuario_id, entidade_tipo="documento_licitacao",
                      entidade_id=documento.id)
    # Fase 15: um documento = uma execução de crédito, por mais blocos que tenha.
    with execucao(db, base, parametros={"paginas": len(paginas)}, confirmado=confirmado) as ctx:
        respostas = [
            (bloco, gerar(
                db, llm, ctx,
                LLMRequest(
                    system=_SISTEMA,
                    prompt=prompt_seguro.bloco_dados_externos(f"{documento.tipo} {documento.nome_arquivo}",
                                                              grounding.corpo_do_bloco(paginas, bloco)),
                    max_tokens=8000,
                ),
            ))
            for bloco in blocos
        ]
    for bloco, resposta in respostas:
        for item in grounding.itens_json(resposta.content)[:MAXIMO_ITENS_POR_BLOCO]:
            descricao = str(item.get("descricao") or "").strip()[:500]
            citacao = str(item.get("citacao") or "").strip()[:2000]
            categoria = str(item.get("categoria") or "").strip().upper()
            if not descricao or categoria not in CATEGORIAS_REQUISITO:
                continue
            pagina = grounding.ancorar(paginas, bloco, citacao)
            if pagina is None:
                sem_evidencia += 1
                continue
            chave = texto.normalizar(descricao)
            if chave in existentes:
                continue
            existentes.add(chave)
            requisito = RequisitoLicitacao(
                tenant_id=tenant_id, licitacao_id=documento.licitacao_id, documento_id=documento.id,
                categoria=categoria, descricao=descricao, evidencia=citacao, pagina=pagina,
                clausula=grounding.clausula_valida(item.get("clausula"), paginas[pagina - 1]),
                origem="ia", status="sugerido", correlation_id=correlation_id_atual(),
            )
            db.add(requisito)
            criados.append(requisito)

    documento.status_analise = "ANALISADO"
    documento.analisado_em = datetime.now(UTC)
    db.flush()
    if criados:
        aprendizado.registrar(
            db, tenant_id, feature, "GERADO", entidade_tipo="documento_licitacao", entidade_id=documento.id,
            usuario_id=usuario_id, dados={"sugeridos": len(criados), "sem_evidencia": sem_evidencia},
        )
    return {
        "documento_id": documento.id,
        "sugeridos": len(criados),
        "descartados_sem_evidencia": sem_evidencia,
        "blocos_analisados": len(blocos),
        "paginas_analisadas": sum(len(b) for b in blocos),
        "paginas_total": len(paginas),
        "analise_parcial": parcial,
    }
