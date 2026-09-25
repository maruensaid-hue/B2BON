"""Tender Analyzer e TR Analyzer (Fase 9, §33-§34), via AI Gateway.

Proveniência (GATE): a IA propõe requisitos com a citação literal; o
sistema só grava o que encontra no texto do documento, calcula a página
a partir do próprio texto (não confia no número que a IA disser) e só
mantém a cláusula se ela aparecer na página. Cada requisito aponta para
documento (hash, fonte, URL) + página + cláusula + trecho.

Documento longo é analisado em blocos de páginas; cada bloco é uma chamada
medida. Acima do teto de blocos, a análise é parcial e isso é declarado.
"""

import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.bids.tipos import CATEGORIAS_REQUISITO
from app.contexts.intelligence.contract import ContextoIA, aprendizado, gerar, prompt_seguro
from app.contexts.shared import texto
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


def _blocos(paginas: list[str]) -> list[list[int]]:
    blocos: list[list[int]] = []
    atual: list[int] = []
    tamanho = 0
    for indice, pagina in enumerate(paginas):
        if atual and tamanho + len(pagina) > CARACTERES_POR_BLOCO:
            blocos.append(atual)
            atual, tamanho = [], 0
        atual.append(indice)
        tamanho += len(pagina)
    if atual:
        blocos.append(atual)
    return blocos


def _itens(conteudo: str) -> list[dict]:
    achado = re.search(r"\[.*\]", conteudo, re.DOTALL)
    if achado is None:
        return []
    try:
        itens = json.loads(achado.group(0))
    except json.JSONDecodeError:
        return []
    return [i for i in itens if isinstance(i, dict)] if isinstance(itens, list) else []


def _clausula_valida(clausula: object, pagina_texto: str) -> str | None:
    if not isinstance(clausula, str):
        return None
    clausula = clausula.strip()[:40]
    if not clausula or not re.search(r"\w", clausula):
        return None
    return clausula if clausula.lower() in pagina_texto.lower() else None


def analisar(db: Session, llm: LLMProvider, tenant_id: str, usuario_id: int | None, documento: DocumentoLicitacao) -> dict:
    if documento.status_analise == "SEM_TEXTO":
        raise RegraNegocioViolada(
            "Este documento não tem texto extraível (provavelmente digitalizado). Sem OCR, a análise não é feita."
        )
    paginas: list[str] = documento.paginas_texto or []
    feature = FEATURE_TR if documento.tipo == "TR" else FEATURE_EDITAL
    blocos = _blocos(paginas)
    parcial = len(blocos) > MAXIMO_BLOCOS
    blocos = blocos[:MAXIMO_BLOCOS]

    existentes = {
        texto.normalizar(r.descricao)
        for r in db.query(RequisitoLicitacao).filter_by(tenant_id=tenant_id, documento_id=documento.id).all()
    }
    criados: list[RequisitoLicitacao] = []
    sem_evidencia = 0
    for bloco in blocos:
        corpo = "\n".join(f"[[página {i + 1}]]\n{paginas[i]}" for i in bloco)
        resposta = gerar(
            db, llm,
            ContextoIA(tenant_id=tenant_id, feature=feature, usuario_id=usuario_id,
                       entidade_tipo="documento_licitacao", entidade_id=documento.id),
            LLMRequest(
                system=_SISTEMA,
                prompt=prompt_seguro.bloco_dados_externos(f"{documento.tipo} {documento.nome_arquivo}", corpo),
                max_tokens=8000,
            ),
        )
        paginas_do_bloco = [paginas[i] for i in bloco]
        for item in _itens(resposta.content)[:MAXIMO_ITENS_POR_BLOCO]:
            descricao = str(item.get("descricao") or "").strip()[:500]
            citacao = str(item.get("citacao") or "").strip()[:2000]
            categoria = str(item.get("categoria") or "").strip().upper()
            if not descricao or categoria not in CATEGORIAS_REQUISITO:
                continue
            pagina_relativa = texto.localizar_pagina(paginas_do_bloco, citacao) if citacao else None
            if pagina_relativa is None:
                sem_evidencia += 1
                continue
            pagina = bloco[pagina_relativa - 1] + 1
            chave = texto.normalizar(descricao)
            if chave in existentes:
                continue
            existentes.add(chave)
            requisito = RequisitoLicitacao(
                tenant_id=tenant_id, licitacao_id=documento.licitacao_id, documento_id=documento.id,
                categoria=categoria, descricao=descricao, evidencia=citacao, pagina=pagina,
                clausula=_clausula_valida(item.get("clausula"), paginas[pagina - 1]),
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
