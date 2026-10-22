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
    # Só o caminho governado (`buscar_contatos_governado`) usa e exige os três campos abaixo; eles vêm da política aprovada do provedor.
    limite_contatos: int | None = None  # teto de contatos que podem ser REVELADOS nesta consulta
    tamanho_pagina: int | None = None  # tamanho da página da busca (o provedor cobra por resultado devolvido)
    revelar: list[str] | None = None  # dados a revelar (ex.: ["emails", "phones"]); cada tipo tem tarifa própria


class ContatoCandidato(BaseModel):
    nome: str
    cargo: str
    email: str | None = None
    telefone: str | None = None
    linkedin_url: str | None = None
    fonte: str = "enriquecimento_contatos"


# ok: o provedor devolveu contatos revelados. sem_resultados: respondeu e não havia ninguém. erro_seguro: tem-se certeza de que NADA foi
# revelado e cobrado na etapa que falhou (falha antes do envio ou rejeição definitiva), então a reserva dessa etapa pode ser liberada.
# ambiguo: a etapa foi enviada e o desfecho (ou o consumo) é desconhecido (timeout, 5xx, resposta ilegível, medição ausente) — não se repete e
# não se libera sem reconciliar com o uso informado pelo provedor.
EstadoBusca = Literal["ok", "sem_resultados", "erro_seguro", "ambiguo"]


class ResultadoBuscaContatos(BaseModel):
    estado: EstadoBusca
    contatos: list[ContatoCandidato] = []
    ids_provedor: list[str] = []  # ids opacos de contato, sem dado pessoal; servem de rastro para reconciliar
    detalhe: str | None = None  # motivo curto e sem dado sensível (nunca o corpo da resposta nem a chave)
    # Consumo MEDIDO pelo provedor nesta consulta (soma das etapas já concluídas). None = o provedor não informou: o consumo é desconhecido e
    # nunca é substituído por estimativa.
    creditos_provedor: int | None = None
    creditos_busca: int | None = None
    creditos_revelacao: int | None = None


class UsoProvedor(BaseModel):
    """Uso informado pelo próprio provedor (créditos do ciclo e tarifas por ação)."""

    creditos_total: int | None = None
    creditos_usados: int | None = None
    creditos_restantes: int | None = None
    tarifas: dict[str, dict] = {}  # ação -> {"credits": n, "perQuantity": m}, como o provedor publica


class ContactEnrichmentProvider(ABC):
    """Porta para bases de dados B2B licenciadas (Apollo/Hunter/provedor de contatos etc.).

    Provedor `pago` (cada consulta e cada contato revelado consomem crédito contratado) só pode ser chamado pelo caminho governado
    (`buscar_contatos_governado`, via `app/contexts/enriquecimento`): seleção explícita, confirmação, política aprovada, reserva de créditos
    e orçamento global. O mapeamento de decisores e a fila automática NÃO usam esta porta: trazem só o QSA da Receita."""

    nome_provedor: str = "desconhecido"
    pago: bool = False
    disponivel: bool = True  # False = sem credencial/contrato: nenhuma pesquisa pode ser reservada
    max_contatos_por_consulta: int | None = None  # teto que o adaptador consegue entregar numa consulta (None = não declarado)
    tamanho_pagina_minimo: int | None = None  # menor página que o provedor aceita na busca (None = não declarado)

    @abstractmethod
    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        raise NotImplementedError

    def buscar_contatos_governado(self, filtro: FiltroContatos) -> ResultadoBuscaContatos:
        """Versão que distingue falha de "sem resultados", respeita `limite_contatos` e devolve o consumo medido. O padrão serve a provedores
        sem custo (stub, testes), que não medem consumo (`creditos_provedor=None`); como não sabe o que a falha deixou para trás, trata
        qualquer exceção como desfecho ambíguo."""
        try:
            contatos = self.buscar_contatos(filtro)
        except Exception:  # noqa: BLE001 — o adaptador é desconhecido; ambíguo é a leitura segura
            return ResultadoBuscaContatos(estado="ambiguo", detalhe="falha_inesperada_no_provedor")
        if filtro.limite_contatos is not None:
            contatos = contatos[: filtro.limite_contatos]
        return ResultadoBuscaContatos(estado="ok" if contatos else "sem_resultados", contatos=contatos)

    def consultar_uso(self) -> UsoProvedor:
        """Uso e tarifas segundo o provedor. Provedores sem essa consulta levantam NotImplementedError."""
        raise NotImplementedError("Este provedor não informa uso.")
