"""Registro de conectores do Integration Hub (Fase 3, §13).

Um conector é uma fábrica de `CrmAdapter` + metadados. Os domínios nunca
fazem `if salesforce`: pedem `obter_adapter(db, conexao)` e usam o
contrato. Conectores externos entram na Fase 13, um por vez: enquanto
não existem ficam COMING_SOON; implementados, entram como BETA e só
conectam quando o operador os habilita em `CONECTORES_CRM_HABILITADOS`
(§72: não apresentar como disponível o que não foi validado).
"""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.contexts.integrations.adapters import hubspot, salesforce
from app.contexts.integrations.adapters.b2bon_crm import B2BOnCrmAdapter
from app.contexts.integrations.contract import CrmAdapter
from app.core.config import settings
from app.models.conexao_integracao import ConexaoIntegracao


class StatusConector(StrEnum):
    AVAILABLE = "AVAILABLE"
    BETA = "BETA"
    COMING_SOON = "COMING_SOON"


class TipoAuth(StrEnum):
    NENHUMA = "NENHUMA"
    OAUTH2 = "OAUTH2"
    API_KEY = "API_KEY"


class Conector(BaseModel):
    model_config = ConfigDict(frozen=True)

    sistema: str
    nome: str
    status: StatusConector
    auth: TipoAuth
    descricao: str


FabricaAdapter = Callable[[Session, ConexaoIntegracao], CrmAdapter]
# Valida credenciais/configuração antes de gravar (levanta ValueError).
ValidadorConexao = Callable[[dict, dict], None]

_CONECTORES: dict[str, tuple[Conector, FabricaAdapter | None]] = {
    "b2bon_crm": (
        Conector(sistema="b2bon_crm", nome="B2B ON CRM", status=StatusConector.AVAILABLE, auth=TipoAuth.NENHUMA,
                 descricao="O CRM da própria B2B ON (cliente zero do contrato de adapter)."),
        lambda db, conexao: B2BOnCrmAdapter(db),
    ),
    "salesforce": (
        Conector(sistema="salesforce", nome="Salesforce", status=StatusConector.BETA, auth=TipoAuth.OAUTH2,
                 descricao="Leitura de contas, contatos, oportunidades, estágios, tarefas, eventos e produtos (REST API)."),
        salesforce.fabrica,
    ),
    "hubspot": (
        Conector(sistema="hubspot", nome="HubSpot", status=StatusConector.BETA, auth=TipoAuth.OAUTH2,
                 descricao="Leitura de empresas, contatos, pipelines, negócios, engajamentos e produtos (CRM API v3)."),
        hubspot.fabrica,
    ),
    "pipedrive": (Conector(sistema="pipedrive", nome="Pipedrive", status=StatusConector.COMING_SOON, auth=TipoAuth.API_KEY, descricao="Fase 13."), None),
    "rd_station": (Conector(sistema="rd_station", nome="RD Station CRM", status=StatusConector.COMING_SOON, auth=TipoAuth.API_KEY, descricao="Fase 13."), None),
}


_VALIDADORES: dict[str, ValidadorConexao] = {"salesforce": salesforce.validar, "hubspot": hubspot.validar}


def listar_conectores() -> list[Conector]:
    return [conector for conector, _ in _CONECTORES.values()]


def habilitados() -> set[str]:
    return {s.strip() for s in settings.conectores_crm_habilitados.split(",") if s.strip()}


def obter_conector(sistema: str) -> Conector | None:
    item = _CONECTORES.get(sistema)
    return item[0] if item else None


def conectavel(sistema: str) -> bool:
    item = _CONECTORES.get(sistema)
    if not item or item[1] is None or item[0].status == StatusConector.COMING_SOON:
        return False
    return item[0].status == StatusConector.AVAILABLE or sistema in habilitados()


def validar_conexao(sistema: str, credenciais: dict, configuracao: dict) -> None:
    validador = _VALIDADORES.get(sistema)
    if validador is not None:
        validador(credenciais, configuracao)
    elif credenciais:
        raise ValueError(f"O conector {sistema} não usa credenciais.")


def obter_adapter(db: Session, conexao: ConexaoIntegracao) -> CrmAdapter:
    item = _CONECTORES.get(conexao.sistema)
    if item is None or item[1] is None:
        raise ValueError(f"Conector '{conexao.sistema}' não está disponível.")
    return item[1](db, conexao)


def registrar(conector: Conector, fabrica: FabricaAdapter | None, validador: ValidadorConexao | None = None) -> None:
    """Usado pelos conectores da Fase 13 (e por testes)."""
    _CONECTORES[conector.sistema] = (conector, fabrica)
    if validador is not None:
        _VALIDADORES[conector.sistema] = validador


def remover(sistema: str) -> None:
    _CONECTORES.pop(sistema, None)
    _VALIDADORES.pop(sistema, None)
