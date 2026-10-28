"""Leitura de upload com teto antes de ir para a memória (auditoria de segurança A02)."""

import asyncio

import pytest

from app.core.uploads import ler_limitado, ler_varios_limitados
from app.services.errors import ValidacaoFalhou


class ArquivoEspiao:
    """Imita `UploadFile`: guarda o tamanho pedido em cada `read`, para provar que nunca se pede o arquivo inteiro."""

    def __init__(self, tamanho: int) -> None:
        self.tamanho = tamanho
        self.pedidos: list[int] = []

    async def read(self, tamanho: int = -1) -> bytes:
        self.pedidos.append(tamanho)
        entregue = self.tamanho if tamanho < 0 else min(tamanho, self.tamanho)
        return b"x" * entregue


def test_le_no_maximo_o_limite_mais_um_byte() -> None:
    arquivo = ArquivoEspiao(10_000)
    conteudo = asyncio.run(ler_limitado(arquivo, 100))
    assert arquivo.pedidos == [101]  # nunca `read()` sem teto
    assert len(conteudo) == 101  # um byte a mais basta para o serviço recusar o arquivo grande


def test_arquivo_dentro_do_limite_volta_inteiro() -> None:
    arquivo = ArquivoEspiao(50)
    assert len(asyncio.run(ler_limitado(arquivo, 100))) == 50


def test_soma_dos_anexos_estoura_o_teto_da_requisicao_e_para_de_ler() -> None:
    arquivos = [ArquivoEspiao(60), ArquivoEspiao(60), ArquivoEspiao(60)]
    with pytest.raises(ValidacaoFalhou):
        asyncio.run(ler_varios_limitados(arquivos, lambda _: 100, limite_total_bytes=100))
    assert arquivos[2].pedidos == []  # o terceiro nem chegou a ser lido


def test_varios_dentro_do_teto_voltam_na_ordem() -> None:
    arquivos = [ArquivoEspiao(10), ArquivoEspiao(20)]
    conteudos = asyncio.run(ler_varios_limitados(arquivos, lambda _: 100, limite_total_bytes=100))
    assert [len(c) for c in conteudos] == [10, 20]
