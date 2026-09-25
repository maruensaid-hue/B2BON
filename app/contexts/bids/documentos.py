"""Ingestão de documentos da licitação com proveniência (GATE da Fase 9).

Cada documento guarda fonte, URL (se houver), hash SHA-256 do arquivo e o
texto por página. O mesmo arquivo (mesmo hash) na mesma licitação não
entra duas vezes. PDF sem camada de texto (escaneado) fica SEM_TEXTO:
não há OCR, e isso é declarado em vez de analisado às cegas.
"""

import hashlib
import io

from sqlalchemy.orm import Session

from app.models.documento_licitacao import DocumentoLicitacao
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

TAMANHO_MAXIMO = 15 * 1024 * 1024
TIPOS_MIME = {"application/pdf": "pdf", "text/plain": "txt"}


def extrair_paginas(conteudo: bytes, tipo_mime: str) -> list[str]:
    if tipo_mime == "text/plain":
        texto = conteudo.decode("utf-8", errors="replace")
        # Form feed separa páginas em texto exportado; sem ele, 1 página.
        return [p for p in texto.split("\f")] or [""]
    if tipo_mime == "application/pdf":
        if not conteudo.startswith(b"%PDF"):
            raise ValidacaoFalhou("O arquivo não é um PDF válido.")
        from pypdf import PdfReader

        try:
            leitor = PdfReader(io.BytesIO(conteudo))
            return [(pagina.extract_text() or "") for pagina in leitor.pages]
        except Exception as erro:  # pypdf levanta vários tipos para PDF corrompido
            raise ValidacaoFalhou("Não foi possível ler o PDF.") from erro
    raise ValidacaoFalhou("Formato não suportado. Envie PDF ou texto.")


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
    if len(conteudo) == 0:
        raise ValidacaoFalhou("Arquivo vazio.")
    if len(conteudo) > TAMANHO_MAXIMO:
        raise ValidacaoFalhou("Arquivo acima de 15 MB.")
    if tipo_mime not in TIPOS_MIME:
        raise ValidacaoFalhou("Formato não suportado. Envie PDF ou texto.")
    sha256 = hashlib.sha256(conteudo).hexdigest()
    if db.query(DocumentoLicitacao).filter_by(licitacao_id=licitacao_id, sha256=sha256).first() is not None:
        raise RegraNegocioViolada("Este arquivo já foi enviado para esta licitação.")

    paginas = extrair_paginas(conteudo, tipo_mime)
    tem_texto = any(p.strip() for p in paginas)
    documento = DocumentoLicitacao(
        tenant_id=tenant_id, licitacao_id=licitacao_id, tipo=tipo, nome_arquivo=nome_arquivo[:255],
        tipo_mime=tipo_mime, tamanho_bytes=len(conteudo), sha256=sha256, conteudo=conteudo,
        paginas_texto=paginas, paginas=len(paginas), fonte=fonte, fonte_url=fonte_url,
        status_analise="PENDENTE" if tem_texto else "SEM_TEXTO", enviado_por_usuario_id=usuario_id,
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
