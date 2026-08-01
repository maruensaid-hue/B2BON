from abc import ABC, abstractmethod

from pydantic import BaseModel


class FiltroBusca(BaseModel):
    cnae_codigos: list[str]
    ufs: list[str]
    porte: str | None = None
    situacao_cadastral: str = "ATIVA"
    limite: int = 50


class ContaCandidata(BaseModel):
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    cnae_principal: str
    porte: str | None = None
    capital_social: float | None = None
    uf: str
    municipio: str | None = None
    situacao_cadastral: str
    data_abertura: str | None = None
    fonte: str = "receita_federal_cnpj"


class DecisorCandidato(BaseModel):
    cnpj: str
    nome: str
    qualificacao: str
    fonte: str = "receita_federal_cnpj_qsa"


class AccountDataProvider(ABC):
    """Porta para dados de mercado (contas-alvo).

    Isola o PREDATOR do provedor concreto — nenhuma história do E2 pode se
    acoplar a uma implementação específica (Seção 11 da especificação).
    """

    @abstractmethod
    def buscar_candidatos(self, filtro: FiltroBusca) -> list[ContaCandidata]:
        raise NotImplementedError

    @abstractmethod
    def buscar_decisores(self, cnpj: str) -> list[DecisorCandidato]:
        raise NotImplementedError
