from abc import ABC, abstractmethod

from pydantic import BaseModel


class EmpresaDescoberta(BaseModel):
    nome: str
    site: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    categoria: str | None = None
    posicao: int  # ordem em que apareceu na busca (1 = primeira)
    nota: float | None = None
    avaliacoes: int | None = None
    busca: str  # o termo e a cidade pesquisados, guardados com o resultado


class DescobertaIndisponivel(Exception):
    """Fonte sem chave, sem saldo ou fora do ar: nada foi cobrado por esta chamada."""


class DescobertaEmpresasProvider(ABC):
    """Porta para achar empresas por busca de mapa (nome, site, telefone, nota, posição), fora do recorte de CNPJ.

    Pago por busca: quem chama estima antes (`custo_por_busca_usd`) e só executa com o custo confirmado."""

    configurado: bool = True
    custo_por_busca_usd: float = 0.0
    # Fonte que pode levar mais de um minuto por busca: a execução vai para o segundo plano (a tela não espera a resposta).
    lenta: bool = False

    @abstractmethod
    def buscar(self, termo: str, cidade: str, limite: int = 20) -> list[EmpresaDescoberta]:
        raise NotImplementedError
