from abc import ABC, abstractmethod
from typing import Literal

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
    # Teto de contatos que o provedor pode REVELAR (e cobrar) nesta consulta. Só o caminho governado (`buscar_contatos_governado`) o exige;
    # o contrato de créditos de enriquecimento parte desse número.
    limite_contatos: int | None = None


class ContatoCandidato(BaseModel):
    nome: str
    cargo: str
    email: str | None = None
    telefone: str | None = None
    linkedin_url: str | None = None
    fonte: str = "enriquecimento_contatos"


# ok: o provedor devolveu contatos revelados. sem_resultados: respondeu e não havia ninguém. erro_seguro: tem-se certeza de que NADA foi
# revelado (falha antes do envio ou rejeição definitiva), então a reserva pode ser liberada. ambiguo: a revelação foi enviada e o desfecho é
# desconhecido (timeout, 5xx, resposta ilegível) — não se repete e não se libera sem reconciliar com o uso informado pelo provedor.
EstadoBusca = Literal["ok", "sem_resultados", "erro_seguro", "ambiguo"]


class ResultadoBuscaContatos(BaseModel):
    estado: EstadoBusca
    contatos: list[ContatoCandidato] = []
    ids_provedor: list[str] = []  # ids opacos de contato, sem dado pessoal; servem de rastro para reconciliar
    detalhe: str | None = None  # motivo curto e sem dado sensível (nunca o corpo da resposta nem a chave)


class ContactEnrichmentProvider(ABC):
    """Porta para bases de dados B2B licenciadas (Apollo/Hunter/Lusha etc.).

    Complementa o AccountDataProvider (QSA da Receita Federal): busca
    lideranças reais de área (C-Level, Diretor, Gerente, Head) que não
    aparecem no quadro societário formal do CNPJ.

    Provedor `pago` (cada contato revelado consome crédito contratado) só pode ser chamado pelo caminho governado
    (`buscar_contatos_governado`, via `app/contexts/enriquecimento`): seleção explícita, reserva de créditos e orçamento global."""

    nome_provedor: str = "desconhecido"
    pago: bool = False
    disponivel: bool = True  # False = sem credencial/contrato: nenhuma pesquisa pode ser reservada
    max_contatos_por_consulta: int | None = None  # teto que o adaptador consegue entregar numa consulta (None = não declarado)

    @abstractmethod
    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        raise NotImplementedError

    def buscar_contatos_governado(self, filtro: FiltroContatos) -> ResultadoBuscaContatos:
        """Versão que distingue falha de "sem resultados" e respeita `filtro.limite_contatos`. O padrão serve a provedores sem custo (stub,
        testes); como não sabe o que a falha deixou para trás, trata qualquer exceção como desfecho ambíguo."""
        try:
            contatos = self.buscar_contatos(filtro)
        except Exception:  # noqa: BLE001 — o adaptador é desconhecido; ambíguo é a leitura segura
            return ResultadoBuscaContatos(estado="ambiguo", detalhe="falha_inesperada_no_provedor")
        if filtro.limite_contatos is not None:
            contatos = contatos[: filtro.limite_contatos]
        return ResultadoBuscaContatos(estado="ok" if contatos else "sem_resultados", contatos=contatos)
