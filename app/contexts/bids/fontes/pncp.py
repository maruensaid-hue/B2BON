"""Adapter PNCP — Portal Nacional de Contratações Públicas (§49).

API pública de consulta (`/api/consulta/v1/contratacoes/publicacao`). Contrato verificado contra o serviço real em
2026-10-20 (consulta de leitura): `codigoModalidadeContratacao` é OBRIGATÓRIO (HTTP 400 sem ele); `tamanhoPagina` aceita
até 50 (100 devolve 400); a resposta traz `data`, `totalRegistros`, `totalPaginas`, `numeroPagina`, `paginasRestantes` e
`empty`; `uf` filtra no servidor; 204 = sem registros. Desligado por padrão no produto (`PNCP_HABILITADO`): habilitar é decisão
de operação. A ingestão guarda o link da fonte. Respeitar os termos de uso do portal: sem polling agressivo (a coleta agendada
espaça as páginas e usa janela curta).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.contexts.bids.fontes.base import FonteLicitacoes, LicitacaoExterna
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

URL_BASE = "https://pncp.gov.br/api/consulta/v1"
TAMANHO_PAGINA = 50  # máximo aceito pelo serviço
MODALIDADES_VALIDAS = range(1, 20)  # 1..19 conforme GET /api/pncp/v1/modalidades
# Códigos de modalidade do PNCP (Lei 14.133) → modalidade canônica.
_MODALIDADES = {8: "DIRECT_AWARD", 9: "DIRECT_AWARD", 10: "EOI"}
_TENTATIVAS = 3
_ESPERA_MAXIMA_SEGUNDOS = 30.0


class ErroFonte(RegraNegocioViolada):
    """Falha ao consultar a fonte pública. `tentativas` = chamadas feitas; `transitorio` = vale tentar de novo depois."""

    def __init__(self, mensagem: str, tentativas: int = 1, transitorio: bool = True) -> None:
        super().__init__(mensagem)
        self.tentativas, self.transitorio = tentativas, transitorio


@dataclass(frozen=True)
class PaginaPncp:
    itens: list[LicitacaoExterna]
    pagina: int
    total_paginas: int
    total_registros: int
    ignorados: int  # registros sem `numeroControlePNCP` (não dá para identificar nem deduplicar)
    tentativas: int


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

    def __init__(self, cliente: httpx.Client | None = None, dormir: Callable[[float], None] = time.sleep) -> None:
        self._cliente = cliente or httpx.Client(base_url=URL_BASE, timeout=20)
        self._dormir = dormir

    def _consultar(self, params: dict) -> tuple[dict | None, int]:
        """GET com retentativa limitada e espera progressiva (1 s, 2 s, ...; respeita `Retry-After` até 30 s) só para
        falhas transitórias: erro de rede/timeout, 429 e 5xx. 4xx de requisição inválida não se repete."""
        ultimo = "PNCP indisponível no momento."
        for tentativa in range(1, _TENTATIVAS + 1):
            espera = float(2 ** (tentativa - 1))
            try:
                resposta = self._cliente.get("/contratacoes/publicacao", params=params)
            except httpx.HTTPError as erro:
                ultimo = f"PNCP indisponível no momento ({type(erro).__name__})."
            else:
                if resposta.status_code == 204:
                    return None, tentativa
                if resposta.status_code == 200:
                    try:
                        corpo = resposta.json()
                    except ValueError as erro:
                        raise ErroFonte("PNCP devolveu uma resposta que não é JSON válido.", tentativa, True) from erro
                    if not isinstance(corpo, dict) or not isinstance(corpo.get("data"), list):
                        raise ErroFonte("PNCP devolveu uma resposta fora do formato esperado.", tentativa, True)
                    return corpo, tentativa
                if resposta.status_code == 429 or resposta.status_code >= 500:
                    ultimo = f"PNCP respondeu {resposta.status_code}."
                    retry_after = resposta.headers.get("retry-after", "")
                    if retry_after.isdigit():
                        espera = float(retry_after)
                else:
                    raise ErroFonte(f"PNCP respondeu {resposta.status_code}.", tentativa, False)
            if tentativa < _TENTATIVAS:
                self._dormir(min(espera, _ESPERA_MAXIMA_SEGUNDOS))
        raise ErroFonte(ultimo, _TENTATIVAS, True)

    def buscar_pagina(self, data_inicial: str, data_final: str, modalidade: int | None, pagina: int = 1,
                      uf: str | None = None) -> PaginaPncp:
        """Datas AAAAMMDD. A modalidade é obrigatória no serviço real."""
        if modalidade not in MODALIDADES_VALIDAS:
            raise ValidacaoFalhou("Informe a modalidade do PNCP (código de 1 a 19).")
        params: dict = {"dataInicial": data_inicial, "dataFinal": data_final, "pagina": pagina,
                        "tamanhoPagina": TAMANHO_PAGINA, "codigoModalidadeContratacao": modalidade}
        if uf:
            params["uf"] = uf.upper()
        corpo, tentativas = self._consultar(params)
        if corpo is None:
            return PaginaPncp([], pagina, 0, 0, 0, tentativas)
        brutos = corpo["data"]
        itens = [n for n in (normalizar(r) for r in brutos if isinstance(r, dict)) if n is not None]
        return PaginaPncp(
            itens, int(corpo.get("numeroPagina") or pagina), int(corpo.get("totalPaginas") or 0),
            int(corpo.get("totalRegistros") or len(brutos)), len(brutos) - len(itens), tentativas,
        )

    def buscar(self, data_inicial: str, data_final: str, modalidade: int | None = None, pagina: int = 1) -> list[LicitacaoExterna]:
        return self.buscar_pagina(data_inicial, data_final, modalidade, pagina).itens
