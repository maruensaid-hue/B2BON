"""Document Intelligence — buy side (§48).

Documento com hash, fonte, classificação (padrão CONFIDENTIAL) e texto por
página. Análise por IA (`procurement.analise_documento`, C3, uso interno do
órgão) com o mesmo grounding do Bid Intelligence: só entra achado com
trecho literal, página calculada. RESTRICTED nunca vai para a IA (§58).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.intelligence.contract import ContextoIA, execucao, gerar, prompt_seguro
from app.contexts.procurement.tipos import CLASSIFICACOES
from app.contexts.shared import grounding
from app.contexts.shared.documentos import extrair_paginas, sha256, validar
from app.core.observability import correlation_id_atual
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.documento_compras import DocumentoCompras
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

FEATURE = "procurement.analise_documento"
MAXIMO_BLOCOS = 8
CATEGORIAS = ("OBRIGACAO", "PRAZO", "VALOR", "GARANTIA", "PENALIDADE", "SLA", "REQUISITO", "RISCO", "OUTRO")
_SISTEMA = (
    "Você apoia a equipe de compras de um órgão (uso interno). Extraia do documento obrigações, prazos, valores, "
    "garantias, penalidades, SLAs, requisitos e riscos. Responda SOMENTE com um array JSON de itens "
    '{"categoria": uma de ' + ", ".join(CATEGORIAS) + ', "descricao": frase curta, "citacao": trecho COPIADO '
    'LITERALMENTE do documento, "clausula": número da cláusula ou null}. Sem trecho literal, não inclua. '
    "Não emita juízo jurídico. Se não houver nada, responda []."
)


def registrar(
    db: Session, tenant_id: str, tipo: str, nome_arquivo: str, tipo_mime: str, conteudo: bytes, usuario_id: int | None,
    processo_id: int | None, contrato_id: int | None, classificacao: str = "CONFIDENTIAL", fonte_url: str | None = None,
) -> DocumentoCompras:
    validar(conteudo, tipo_mime)
    if classificacao not in CLASSIFICACOES:
        raise ValidacaoFalhou(f"Classificação inválida: {classificacao}")
    hash_arquivo = sha256(conteudo)
    duplicado = db.query(DocumentoCompras).filter_by(
        tenant_id=tenant_id, processo_id=processo_id, contrato_id=contrato_id, sha256=hash_arquivo).first()
    if duplicado is not None:
        raise RegraNegocioViolada("Este arquivo já foi enviado.")
    paginas = extrair_paginas(conteudo, tipo_mime)
    documento = DocumentoCompras(
        tenant_id=tenant_id, processo_id=processo_id, contrato_id=contrato_id, tipo=tipo, nome_arquivo=nome_arquivo[:255],
        tipo_mime=tipo_mime, tamanho_bytes=len(conteudo), sha256=hash_arquivo, conteudo=conteudo, paginas_texto=paginas,
        paginas=len(paginas), fonte="URL" if fonte_url else "UPLOAD", fonte_url=fonte_url, classificacao=classificacao,
        achados=[], status_analise="PENDENTE" if any(p.strip() for p in paginas) else "SEM_TEXTO",
        enviado_por_usuario_id=usuario_id,
    )
    db.add(documento)
    db.flush()
    return documento


def analisar(db: Session, llm: LLMProvider, tenant_id: str, usuario_id: int | None, documento: DocumentoCompras,
             confirmado: bool = False) -> dict:
    if documento.classificacao == "RESTRICTED":
        raise RegraNegocioViolada("Documento RESTRICTED não é enviado para IA.")
    if documento.status_analise == "SEM_TEXTO":
        raise RegraNegocioViolada("Documento sem texto extraível; sem OCR, a análise não é feita.")
    paginas: list[str] = documento.paginas_texto or []
    todos = grounding.blocos(paginas)
    blocos = todos[:MAXIMO_BLOCOS]
    achados: list[dict] = []
    sem_evidencia = 0
    base = ContextoIA(tenant_id=tenant_id, feature=FEATURE, usuario_id=usuario_id, entidade_tipo="documento_compras",
                      entidade_id=documento.id)
    # Fase 15: documento inteiro = uma execução (crédito variável por página,
    # estimado e confirmado antes; ações determinísticas de compras não usam IA).
    with execucao(db, base, parametros={"paginas": len(paginas)}, confirmado=confirmado) as ctx:
        respostas = [
            (bloco, gerar(db, llm, ctx, LLMRequest(system=_SISTEMA, prompt=prompt_seguro.bloco_dados_externos(
                f"{documento.tipo} {documento.nome_arquivo}", grounding.corpo_do_bloco(paginas, bloco)), max_tokens=6000)))
            for bloco in blocos
        ]
    for bloco, resposta in respostas:
        for item in grounding.itens_json(resposta.content)[:60]:
            categoria = str(item.get("categoria") or "").upper()
            descricao = str(item.get("descricao") or "").strip()[:500]
            citacao = str(item.get("citacao") or "").strip()[:2000]
            if categoria not in CATEGORIAS or not descricao:
                continue
            pagina = grounding.ancorar(paginas, bloco, citacao)
            if pagina is None:
                sem_evidencia += 1
                continue
            achados.append({
                "categoria": categoria, "descricao": descricao, "evidencia": citacao, "pagina": pagina,
                "clausula": grounding.clausula_valida(item.get("clausula"), paginas[pagina - 1]),
                "status": "sugerido", "correlation_id": correlation_id_atual(),
            })
    documento.achados = achados
    documento.status_analise = "ANALISADO"
    db.flush()
    return {"documento_id": documento.id, "achados": len(achados), "descartados_sem_evidencia": sem_evidencia,
            "analise_parcial": len(todos) > MAXIMO_BLOCOS, "analisado_em": datetime.now(UTC)}


def como_dict(documento: DocumentoCompras) -> dict:
    return {
        "id": documento.id, "processo_id": documento.processo_id, "contrato_id": documento.contrato_id, "tipo": documento.tipo,
        "nome_arquivo": documento.nome_arquivo, "sha256": documento.sha256, "paginas": documento.paginas,
        "fonte": documento.fonte, "fonte_url": documento.fonte_url, "classificacao": documento.classificacao,
        "status_analise": documento.status_analise, "achados": documento.achados or [], "criado_em": documento.criado_em,
    }
