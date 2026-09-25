"""Registro de conectores do Integration Hub (Fase 3, §13).

Um conector é uma fábrica de `CrmAdapter` + metadados. Os domínios nunca
fazem `if salesforce`: pedem `obter_adapter(db, conexao)` e usam o
contrato. Conectores externos entram na Fase 13, um por vez; até lá
ficam listados como COMING_SOON e não podem ser conectados (§72: não
apresentar como disponível o que não existe).
"""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.contexts.integrations.adapters.b2bon_crm import B2BOnCrmAdapter
from app.contexts.integrations.contract import CrmAdapter
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

_CONECTORES: dict[str, tuple[Conector, FabricaAdapter | None]] = {
    "b2bon_crm": (
        Conector(sistema="b2bon_crm", nome="B2B ON CRM", status=StatusConector.AVAILABLE, auth=TipoAuth.NENHUMA,
                 descricao="O CRM da própria B2B ON (cliente zero do contrato de adapter)."),
        lambda db, conexao: B2BOnCrmAdapter(db),
    ),
    "salesforce": (Conector(sistema="salesforce", nome="Salesforce", status=StatusConector.COMING_SOON, auth=TipoAuth.OAUTH2, descricao="Fase 13."), None),
    "hubspot": (Conector(sistema="hubspot", nome="HubSpot", status=StatusConector.COMING_SOON, auth=TipoAuth.OAUTH2, descricao="Fase 13."), None),
    "pipedrive": (Conector(sistema="pipedrive", nome="Pipedrive", status=StatusConector.COMING_SOON, auth=TipoAuth.API_KEY, descricao="Fase 13."), None),
    "rd_station": (Conector(sistema="rd_station", nome="RD Station CRM", status=StatusConector.COMING_SOON, auth=TipoAuth.API_KEY, descricao="Fase 13."), None),
}


def listar_conectores() -> list[Conector]:
    return [conector for conector, _ in _CONECTORES.values()]


def obter_conector(sistema: str) -> Conector | None:
    item = _CONECTORES.get(sistema)
    return item[0] if item else None


def conectavel(sistema: str) -> bool:
    item = _CONECTORES.get(sistema)
    return bool(item and item[1] is not None and item[0].status != StatusConector.COMING_SOON)


def obter_adapter(db: Session, conexao: ConexaoIntegracao) -> CrmAdapter:
    item = _CONECTORES.get(conexao.sistema)
    if item is None or item[1] is None:
        raise ValueError(f"Conector '{conexao.sistema}' não está disponível.")
    return item[1](db, conexao)


def registrar(conector: Conector, fabrica: FabricaAdapter | None) -> None:
    """Usado pelos conectores da Fase 13 (e por testes)."""
    _CONECTORES[conector.sistema] = (conector, fabrica)


def remover(sistema: str) -> None:
    _CONECTORES.pop(sistema, None)
