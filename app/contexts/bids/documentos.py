"""Ingestão de documentos da licitação com proveniência (GATE da Fase 9),
sobre o Document Engine compartilhado (`sourcing.documentos`, S1).

Cada documento guarda fonte, URL (se houver), hash SHA-256 do arquivo e o
texto por página. O mesmo arquivo (mesmo hash) na mesma licitação não
entra duas vezes. PDF sem camada de texto (escaneado) fica SEM_TEXTO:
não há OCR, e isso é declarado em vez de analisado às cegas.
"""

from sqlalchemy.orm import Session

from app.contexts.shared.documentos import TAMANHO_MAXIMO, extrair_paginas
from app.contexts.sourcing import contract as sourcing
from app.models.documento_licitacao import DocumentoLicitacao
from app.services.errors import RegraNegocioViolada

__all__ = ["TAMANHO_MAXIMO", "como_dict", "extrair_paginas", "registrar"]


def registrar(
    db: Session,
    tenant_id: str,
    licitacao_id: int,
    tipo: str,
    nome_arquivo: str,
    tipo_mime: str,
    conteudo: bytes,
    usuario_id: int | None,
    fonte: str = "UPLOAD",
    fonte_url: str | None = None,
) -> DocumentoLicitacao:
    arquivo = sourcing.documentos.preparar(conteudo, tipo_mime)
    if db.query(DocumentoLicitacao.id).filter_by(licitacao_id=licitacao_id, sha256=arquivo.sha256).first() is not None:
        raise RegraNegocioViolada("Este arquivo já foi enviado para esta licitação.")
    documento = DocumentoLicitacao(
        tenant_id=tenant_id, licitacao_id=licitacao_id, tipo=tipo, nome_arquivo=nome_arquivo[:255],
        tipo_mime=tipo_mime, tamanho_bytes=arquivo.tamanho_bytes, sha256=arquivo.sha256, conteudo=conteudo,
        paginas_texto=arquivo.paginas, paginas=len(arquivo.paginas), fonte=fonte, fonte_url=fonte_url,
        status_analise=arquivo.status_inicial, enviado_por_usuario_id=usuario_id,
    )
    db.add(documento)
    db.flush()
    return documento


def como_dict(documento: DocumentoLicitacao) -> dict:
    return {
        "id": documento.id,
        "licitacao_id": documento.licitacao_id,
        "tipo": documento.tipo,
        "nome_arquivo": documento.nome_arquivo,
        "tipo_mime": documento.tipo_mime,
        "tamanho_bytes": documento.tamanho_bytes,
        "sha256": documento.sha256,
        "paginas": documento.paginas,
        "fonte": documento.fonte,
        "fonte_url": documento.fonte_url,
        "status_analise": documento.status_analise,
        "analisado_em": documento.analisado_em,
        "criado_em": documento.criado_em,
    }
