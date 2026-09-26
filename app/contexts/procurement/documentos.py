"""Document Intelligence — buy side (§48), sobre os engines compartilhados de
documento e de requisitos (`sourcing`, S1).

Documento com hash, fonte, classificação (padrão CONFIDENTIAL) e texto por
página. Análise por IA (`procurement.analise_documento`, C3, uso interno do
órgão) com o mesmo grounding do Bid Intelligence: só entra achado com
trecho literal, página calculada. RESTRICTED nunca vai para a IA (§58).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.intelligence.contract import ContextoIA
from app.contexts.procurement.tipos import CLASSIFICACOES
from app.contexts.sourcing import contract as sourcing
from app.core.observability import correlation_id_atual
from app.llm.base import LLMProvider
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


def perfil() -> sourcing.requisitos.PerfilExtracao:
    """Perfil `documento_compras` do Requirement Engine (lido na hora, como no Bids)."""
    return sourcing.requisitos.PerfilExtracao(nome="documento_compras", sistema=_SISTEMA, categorias=CATEGORIAS, max_tokens=6000,
                                              maximo_blocos=MAXIMO_BLOCOS)


def registrar(
    db: Session, tenant_id: str, tipo: str, nome_arquivo: str, tipo_mime: str, conteudo: bytes, usuario_id: int | None,
    processo_id: int | None, contrato_id: int | None, classificacao: str = "CONFIDENTIAL", fonte_url: str | None = None,
) -> DocumentoCompras:
    arquivo = sourcing.documentos.preparar(conteudo, tipo_mime)
    if classificacao not in CLASSIFICACOES:
        raise ValidacaoFalhou(f"Classificação inválida: {classificacao}")
    duplicado = db.query(DocumentoCompras.id).filter_by(
        tenant_id=tenant_id, processo_id=processo_id, contrato_id=contrato_id, sha256=arquivo.sha256).first()
    if duplicado is not None:
        raise RegraNegocioViolada("Este arquivo já foi enviado.")
    documento = DocumentoCompras(
        tenant_id=tenant_id, processo_id=processo_id, contrato_id=contrato_id, tipo=tipo, nome_arquivo=nome_arquivo[:255],
        tipo_mime=tipo_mime, tamanho_bytes=arquivo.tamanho_bytes, sha256=arquivo.sha256, conteudo=conteudo,
        paginas_texto=arquivo.paginas, paginas=len(arquivo.paginas), fonte="URL" if fonte_url else "UPLOAD", fonte_url=fonte_url,
        classificacao=classificacao, achados=[], status_analise=arquivo.status_inicial, enviado_por_usuario_id=usuario_id,
    )
    db.add(documento)
    db.flush()
    return documento


def analisar(db: Session, llm: LLMProvider, tenant_id: str, usuario_id: int | None, documento: DocumentoCompras,
             confirmado: bool = False) -> dict:
    sourcing.documentos.exigir_analisavel(documento.status_analise, documento.classificacao,
                                          "Documento sem texto extraível; sem OCR, a análise não é feita.")
    paginas: list[str] = documento.paginas_texto or []
    base = ContextoIA(tenant_id=tenant_id, feature=FEATURE, usuario_id=usuario_id, entidade_tipo="documento_compras",
                      entidade_id=documento.id)
    # Documento inteiro = uma execução (crédito variável por página, estimado e
    # confirmado antes; ações determinísticas de compras não usam IA).
    extracao = sourcing.requisitos.extrair(db, llm, base, paginas, perfil(), f"{documento.tipo} {documento.nome_arquivo}",
                                           confirmado)
    documento.achados = [
        {"categoria": item.categoria, "descricao": item.descricao, "evidencia": item.evidencia, "pagina": item.pagina,
         "clausula": item.clausula, "status": "sugerido", "correlation_id": correlation_id_atual()}
        for item in extracao.itens
    ]
    documento.status_analise = "ANALISADO"
    db.flush()
    return {"documento_id": documento.id, "achados": len(documento.achados), "descartados_sem_evidencia": extracao.sem_evidencia,
            "analise_parcial": extracao.parcial, "analisado_em": datetime.now(UTC)}


def como_dict(documento: DocumentoCompras) -> dict:
    return {
        "id": documento.id, "processo_id": documento.processo_id, "contrato_id": documento.contrato_id, "tipo": documento.tipo,
        "nome_arquivo": documento.nome_arquivo, "sha256": documento.sha256, "paginas": documento.paginas,
        "fonte": documento.fonte, "fonte_url": documento.fonte_url, "classificacao": documento.classificacao,
        "status_analise": documento.status_analise, "achados": documento.achados or [], "criado_em": documento.criado_em,
    }
