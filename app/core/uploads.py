"""Leitura de arquivos enviados com teto de tamanho aplicado ANTES de o conteúdo ir para a memória.

`await arquivo.read()` sem argumento carrega o arquivo inteiro: um upload de gigabytes (ou muitos arquivos) consumiria a memória do serviço antes de qualquer
validação de tamanho nos serviços. O servidor de multipart já descarrega o corpo grande em disco; o risco está em trazê-lo de volta inteiro para a memória. Aqui se lê no
máximo `limite + 1` bytes: o byte a mais basta para o serviço (que mantém a sua própria checagem e a sua mensagem) recusar o arquivo grande, sem nunca alocá-lo.
"""

from fastapi import UploadFile

from app.services.errors import ValidacaoFalhou

TAMANHO_MAXIMO_DOCUMENTO_BYTES = 15 * 1024 * 1024
# Teto da soma dos anexos de uma mesma requisição (o maior vídeo individual já é 80 MB).
TAMANHO_MAXIMO_REQUISICAO_BYTES = 100 * 1024 * 1024


async def ler_limitado(arquivo: UploadFile, limite_bytes: int = TAMANHO_MAXIMO_DOCUMENTO_BYTES) -> bytes:
    """Lê no máximo `limite_bytes + 1` bytes; se vier mais que o limite, o conteúdo devolvido tem `limite_bytes + 1` e o serviço o recusa pelo tamanho."""
    return await arquivo.read(limite_bytes + 1)


async def ler_varios_limitados(arquivos: list[UploadFile], limite_por_arquivo, limite_total_bytes: int = TAMANHO_MAXIMO_REQUISICAO_BYTES) -> list[bytes]:
    """Lê vários anexos com teto por arquivo (`limite_por_arquivo(arquivo)` devolve o limite daquele tipo) e teto da soma: ao estourar a soma, recusa sem ler o resto."""
    conteudos: list[bytes] = []
    total = 0
    for arquivo in arquivos:
        conteudo = await ler_limitado(arquivo, limite_por_arquivo(arquivo))
        total += len(conteudo)
        if total > limite_total_bytes:
            limite_mb = limite_total_bytes // (1024 * 1024)
            raise ValidacaoFalhou(f"Os arquivos enviados somam mais que o limite de {limite_mb} MB por envio.")
        conteudos.append(conteudo)
    return conteudos
