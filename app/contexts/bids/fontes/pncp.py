"""Adapter PNCP — Portal Nacional de Contratações Públicas (§49).

API pública de consulta (`/api/consulta/v1/contratacoes/publicacao`).
EXPERIMENTAL: implementado a partir do formato documentado da API, mas não
validado contra o serviço real no ambiente de desenvolvimento (egress
bloqueado). Desligado por padrão (`PNCP_HABILITADO`); a ingestão guarda o
registro bruto e o link da fonte. Respeitar os termos de uso do portal.
"""

from datetime import datetime

import httpx

from app.contexts.bids.fontes.base import FonteLicitacoes, LicitacaoExterna
from app.services.errors import RegraNegocioViolada

URL_BASE = "https://pncp.gov.br/api/consulta/v1"
# Códigos de modalidade do PNCP (Lei 14.133) → modalidade canônica.
_MODALIDADES = {8: "DIRECT_AWARD", 9: "DIRECT_AWARD", 10: "EOI"}


def _data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def normalizar(registro: dict) -> LicitacaoExterna | None:
    controle = registro.get("numeroControlePNCP")
    if not controle:
        return None
    orgao = registro.get("orgaoEntidade") or {}
    codigo = registro.get("modalidadeId")
    modalidade = "PRICE_REGISTRATION" if registro.get("srp") else _MODALIDADES.get(codigo, "PUBLIC_TENDER")
    objeto = registro.get("objetoCompra")
    cnpj = "".join(c for c in (orgao.get("cnpj") or "") if c.isdigit()) or None
    link = None
    if cnpj and registro.get("anoCompra") and registro.get("sequencialCompra"):
        link = f"https://pncp.gov.br/app/editais/{cnpj}/{registro['anoCompra']}/{registro['sequencialCompra']}"
    valor = registro.get("valorTotalEstimado")
    return LicitacaoExterna(
        fonte="PNCP",
        id_externo=str(controle),
        titulo=(objeto or str(controle))[:200],
        objeto=objeto,
        orgao_nome=orgao.get("razaoSocial"),
        orgao_cnpj=cnpj,
        modalidade=modalidade,
        data_publicacao=_data(registro.get("dataPublicacaoPncp")),
        prazo_proposta=_data(registro.get("dataEncerramentoProposta")),
        valor_estimado=float(valor) if isinstance(valor, int | float) else None,
        url=link or registro.get("linkSistemaOrigem"),
        bruto=registro,
    )


class FontePncp(FonteLicitacoes):
    nome = "PNCP"
    status = "EXPERIMENTAL"

    def __init__(self, cliente: httpx.Client | None = None) -> None:
        self._cliente = cliente or httpx.Client(base_url=URL_BASE, timeout=20)

    def buscar(self, data_inicial: str, data_final: str, modalidade: int | None = None, pagina: int = 1) -> list[LicitacaoExterna]:
        params = {"dataInicial": data_inicial, "dataFinal": data_final, "pagina": pagina, "tamanhoPagina": 50}
        if modalidade is not None:
            params["codigoModalidadeContratacao"] = modalidade
        try:
            resposta = self._cliente.get("/contratacoes/publicacao", params=params)
        except httpx.HTTPError as erro:
            raise RegraNegocioViolada("PNCP indisponível no momento.") from erro
        if resposta.status_code == 204:
            return []
        if resposta.status_code != 200:
            raise RegraNegocioViolada(f"PNCP respondeu {resposta.status_code}.")
        corpo = resposta.json()
        return [n for n in (normalizar(r) for r in corpo.get("data") or []) if n is not None]
