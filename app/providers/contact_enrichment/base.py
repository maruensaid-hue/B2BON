from abc import ABC, abstractmethod

from pydantic import BaseModel

SENIORIDADE_ALVO = [
    "CEO", "CFO", "COO", "CTO", "CMO", "CPO",
    "Presidente", "Diretor", "Diretora", "VP", "Vice-Presidente",
    "Gerente", "Head", "Superintendente",
]


class FiltroContatos(BaseModel):
    nome_empresa: str
    dominio: str | None = None
    cnpj: str | None = None
    cargos_alvo: list[str] = SENIORIDADE_ALVO


class ContatoCandidato(BaseModel):
    nome: str
    cargo: str
    email: str | None = None
    telefone: str | None = None
    linkedin_url: str | None = None
    fonte: str = "enriquecimento_contatos"


class ContactEnrichmentProvider(ABC):
    """Porta para bases de dados B2B licenciadas (Apollo/Hunter/Lusha etc.).

    Complementa o AccountDataProvider (QSA da Receita Federal): busca
    lideranças reais de área (C-Level, Diretor, Gerente, Head) que não
    aparecem no quadro societário formal do CNPJ.
    """

    @abstractmethod
    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        raise NotImplementedError
