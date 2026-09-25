"""Extração de texto por página e hash de arquivo — Shared Kernel.

Usado por Bid Intelligence (Fase 9) e Public Procurement (Fase 10): cada
lado guarda os próprios documentos; só a técnica é compartilhada.
"""

import hashlib
import io

from app.services.errors import ValidacaoFalhou

TAMANHO_MAXIMO = 15 * 1024 * 1024
TIPOS_MIME = {"application/pdf": "pdf", "text/plain": "txt"}


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def validar(conteudo: bytes, tipo_mime: str) -> None:
    if len(conteudo) == 0:
        raise ValidacaoFalhou("Arquivo vazio.")
    if len(conteudo) > TAMANHO_MAXIMO:
        raise ValidacaoFalhou("Arquivo acima de 15 MB.")
    if tipo_mime not in TIPOS_MIME:
        raise ValidacaoFalhou("Formato não suportado. Envie PDF ou texto.")


def extrair_paginas(conteudo: bytes, tipo_mime: str) -> list[str]:
    if tipo_mime == "text/plain":
        # Form feed separa páginas em texto exportado; sem ele, 1 página.
        return conteudo.decode("utf-8", errors="replace").split("\f")
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
