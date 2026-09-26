"""Document Engine (S1): preparação do arquivo e regras de análise, iguais
para os dois lados. Cada lado grava na própria tabela (até a S3) e checa
duplicidade no próprio escopo; o que é comum mora aqui."""

from dataclasses import dataclass

from app.contexts.shared.documentos import TAMANHO_MAXIMO, extrair_paginas, sha256, validar
from app.services.errors import RegraNegocioViolada

__all__ = ["TAMANHO_MAXIMO", "ArquivoPreparado", "exigir_analisavel", "preparar"]

MENSAGEM_SEM_TEXTO = "Este documento não tem texto extraível (provavelmente digitalizado). Sem OCR, a análise não é feita."


@dataclass(frozen=True)
class ArquivoPreparado:
    sha256: str
    paginas: list[str]
    tamanho_bytes: int

    @property
    def status_inicial(self) -> str:
        """PENDENTE se há texto para analisar; SEM_TEXTO (sem OCR, declarado) se não."""
        return "PENDENTE" if any(p.strip() for p in self.paginas) else "SEM_TEXTO"


def preparar(conteudo: bytes, tipo_mime: str) -> ArquivoPreparado:
    """Valida tipo e tamanho, calcula o hash e extrai o texto por página."""
    validar(conteudo, tipo_mime)
    return ArquivoPreparado(sha256(conteudo), extrair_paginas(conteudo, tipo_mime), len(conteudo))


def exigir_analisavel(status_analise: str, classificacao: str | None = None, mensagem_sem_texto: str = MENSAGEM_SEM_TEXTO) -> None:
    """RESTRICTED nunca vai para IA (§58); sem texto, não há o que ancorar."""
    if classificacao == "RESTRICTED":
        raise RegraNegocioViolada("Documento RESTRICTED não é enviado para IA.")
    if status_analise == "SEM_TEXTO":
        raise RegraNegocioViolada(mensagem_sem_texto)
