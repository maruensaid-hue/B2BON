"""Contrato de adapter do Integration Hub (Fase 2, Master Prompt §13).

Todo sistema externo (e o próprio CRM da B2B ON) entra por um adapter
que fala o modelo canônico. Os domínios (MAP, PREDATOR, Intelligence)
nunca fazem `if salesforce / if hubspot`: recebem um `CrmAdapter`.

Leitura é paginada por cursor opaco e aceita `updated_since` para sync
incremental. Escrita é opcional (capacidade declarada); um adapter que
não suporta uma operação levanta `OperacaoNaoSuportada`, nunca finge.
Auth, retries, rate limit, webhooks e registro de conectores são da
Fase 3; conectores externos reais, da Fase 13. Ver ADAPTER_CONTRACT.md.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from app.contexts.shared.canonical.commercial import (
    Account,
    Activity,
    Contact,
    CSMetric,
    Customer,
    Interaction,
    Offer,
    Opportunity,
    Organization,
    Person,
    Pipeline,
    PipelineStage,
)

T = TypeVar("T")


# --- Escrita (D-087): o que a B2B ON envia ao CRM do cliente ---------------------
# DTOs próprios (não as entidades canônicas de leitura): na escrita não há id
# canônico nem proveniência ainda — o id nasce no CRM e volta para o vínculo.
class _Saida(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EmpresaSaida(_Saida):
    nome: str
    cnpj: str | None = None
    dominio: str | None = None
    dono_externo_id: str | None = None


class PessoaSaida(_Saida):
    nome: str
    email: str | None = None
    telefone: str | None = None
    cargo: str | None = None
    empresa_id: str | None = None  # id externo
    dono_externo_id: str | None = None


class TipoAtividadeSaida(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    LINKEDIN = "linkedin"
    LIGACAO = "ligacao"
    REUNIAO = "reuniao"
    NOTA = "nota"


class AtividadeSaida(_Saida):
    tipo: TipoAtividadeSaida
    assunto: str
    descricao: str = ""
    ocorrida_em: datetime
    duracao_minutos: int | None = None
    empresa_id: str | None = None
    pessoa_id: str | None = None
    negocio_id: str | None = None
    dono_externo_id: str | None = None


class NegocioSaida(_Saida):
    nome: str
    empresa_id: str
    pessoa_id: str | None = None
    pipeline_id: str | None = None
    estagio_id: str
    # Salesforce exige CloseDate: vem da configuração do tenant, nunca inventada.
    previsao_fechamento: date | None = None
    dono_externo_id: str | None = None


class TarefaSaida(_Saida):
    assunto: str
    descricao: str = ""
    vencimento: date
    empresa_id: str | None = None
    dono_externo_id: str | None = None


class SinaisContaSaida(_Saida):
    """Sinais do MAP gravados em campos PRÓPRIOS da B2B ON na conta do CRM."""

    empresa_id: str
    score_risco: float  # 0–100, maior = mais risco de churn (mesma escala do MAP)
    nivel_risco: str


class CamposProprios(_Saida):
    """Nomes/chaves dos campos da B2B ON no CRM do cliente (configuráveis).
    Campo não configurado = aquela escrita é pulada, nunca improvisada."""

    score_risco: str | None = None
    nivel_risco: str | None = None
    optout: str | None = None


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    items: list[T]
    next_cursor: str | None = None


ESCRITAS = frozenset({"empresas", "pessoas", "atividades", "negocios", "tarefas", "optout", "sinais_conta"})


class AdapterCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    system: str
    readable_entities: frozenset[str]
    writable_entities: frozenset[str] = frozenset()
    incremental_sync: bool = False
    webhooks: bool = False


class OperacaoNaoSuportada(Exception):
    """O adapter não suporta esta operação (capacidade não declarada)."""


class ErroTransitorio(Exception):
    """Falha que vale tentar de novo (429, 5xx, timeout)."""


class ErroCredencial(Exception):
    """Credencial inválida, expirada ou sem permissão (401/403). Não é
    transitória: tentar de novo só gasta cota e pode bloquear a conta."""


class CrmAdapter(ABC):
    """Porta de leitura/escrita de um CRM qualquer, em termos canônicos.

    Todo método recebe `tenant_id` e só pode devolver dados desse tenant
    (isolamento é responsabilidade do adapter, testado por contrato)."""

    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    def list_organizations(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Organization]: ...

    @abstractmethod
    def list_accounts(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Account]: ...

    @abstractmethod
    def list_customers(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[Customer]: ...

    @abstractmethod
    def list_people(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Person]: ...

    @abstractmethod
    def list_contacts(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[Contact]: ...

    @abstractmethod
    def list_pipelines(self, tenant_id: str) -> list[Pipeline]: ...

    @abstractmethod
    def list_stages(self, tenant_id: str) -> list[PipelineStage]: ...

    @abstractmethod
    def list_opportunities(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Opportunity]: ...

    @abstractmethod
    def list_activities(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[Activity]: ...

    @abstractmethod
    def list_interactions(self, tenant_id: str, account_id: str | None = None, cursor: str | None = None, limit: int = 100) -> Page[Interaction]: ...

    @abstractmethod
    def list_cs_metrics(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[CSMetric]: ...

    @abstractmethod
    def list_offers(self, tenant_id: str) -> list[Offer]: ...

    # --- Escrita (opcional) ------------------------------------------------
    def upsert_opportunity(self, tenant_id: str, opportunity: Opportunity) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de Opportunity")

    def add_note(self, tenant_id: str, target_id: str, text: str) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de notas")

    # D-087. Regra de conflito: o CRM do cliente é a fonte da verdade dos
    # campos dele. `garantir_*` PROCURA antes (CNPJ → domínio → nome; e-mail)
    # e, se achar, devolve o id SEM alterar nada; só cria o que não existe.
    # Atividades, negócios e tarefas são sempre criação. Os únicos campos que
    # a B2B ON atualiza são os próprios (`CamposProprios`).
    def garantir_empresa(self, tenant_id: str, empresa: EmpresaSaida) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de empresas")

    def garantir_pessoa(self, tenant_id: str, pessoa: PessoaSaida) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de pessoas")

    def registrar_atividade(self, tenant_id: str, atividade: AtividadeSaida) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de atividades")

    def criar_negocio(self, tenant_id: str, negocio: NegocioSaida) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de negócios")

    def criar_tarefa(self, tenant_id: str, tarefa: TarefaSaida) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de tarefas")

    def marcar_optout(self, tenant_id: str, pessoa_id: str, campos: CamposProprios) -> None:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta registrar opt-out")

    def gravar_sinais_conta(self, tenant_id: str, sinais: SinaisContaSaida, campos: CamposProprios) -> None:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta gravar sinais do MAP")

    def preparar_campos(self, tenant_id: str) -> CamposProprios:
        """Cria no CRM os campos próprios da B2B ON (quando a API permite) e
        devolve as chaves. Quem não permite pede configuração manual."""
        raise OperacaoNaoSuportada(f"{self.capabilities().system}: crie os campos manualmente e informe os nomes.")


def iterar_todos(listar, tenant_id: str, **kwargs) -> list:
    """Consome todas as páginas de um `list_*` paginado."""
    itens: list = []
    cursor = None
    while True:
        pagina = listar(tenant_id, cursor=cursor, **kwargs)
        itens.extend(pagina.items)
        if not pagina.next_cursor:
            return itens
        cursor = pagina.next_cursor


# --- Superfície pública do contexto para fora dele (Fase 3) ----------------------
def obter_registry():
    from app.contexts.integrations import registry

    return registry


def obter_sync():
    from app.contexts.integrations import sync

    return sync


def obter_escrita():
    """Escrita no CRM do cliente (D-087): enfileirar, deduplicar, processar."""
    from app.contexts.integrations import escrita

    return escrita


def obter_oauth():
    """Conectar CRM com 1 clique (D-087)."""
    from app.contexts.integrations import oauth

    return oauth


def obter_entrada():
    """Webhooks de entrada do CRM do cliente (D-087)."""
    from app.contexts.integrations import entrada

    return entrada


def adapter_b2bon(db):
    from app.contexts.integrations.adapters.b2bon_crm import B2BOnCrmAdapter

    return B2BOnCrmAdapter(db)


def adapter_de_payload(tenant_id: str, **colecoes: list) -> CrmAdapter:
    from app.contexts.integrations.adapters.payload import PayloadCrmAdapter

    return PayloadCrmAdapter(tenant_id, **colecoes)
