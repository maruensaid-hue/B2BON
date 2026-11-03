import httpx

from app.core.config import settings
from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider, DescobertaIndisponivel, EmpresaDescoberta

_URL_MAPAS = "https://google.serper.dev/places"


class SerperMapasProvider(DescobertaEmpresasProvider):
    """Busca de mapa (lugares) via API paga por consulta. Uma chamada = uma busca cobrada, independentemente de quantos resultados volta."""

    def __init__(self) -> None:
        self.custo_por_busca_usd = settings.descoberta_busca_custo_por_busca_usd

    def buscar(self, termo: str, cidade: str, limite: int = 20) -> list[EmpresaDescoberta]:
        consulta = f"{termo} {cidade}".strip()
        try:
            resposta = httpx.post(
                _URL_MAPAS,
                json={"q": consulta, "gl": "br", "hl": "pt-br", "num": min(limite, 20)},
                headers={"X-API-KEY": settings.descoberta_busca_api_key, "Content-Type": "application/json"},
                timeout=15.0,
            )
            resposta.raise_for_status()
        except httpx.HTTPError as erro:
            raise DescobertaIndisponivel(f"A fonte de descoberta não respondeu ({type(erro).__name__}).") from erro
        lugares = resposta.json().get("places") or []
        return [
            EmpresaDescoberta(
                nome=(item.get("title") or "").strip(),
                site=item.get("website") or None,
                telefone=item.get("phoneNumber") or None,
                endereco=item.get("address") or None,
                categoria=item.get("category") or None,
                posicao=item.get("position") or indice,
                nota=item.get("rating"),
                avaliacoes=item.get("ratingCount"),
                busca=consulta,
            )
            for indice, item in enumerate(lugares[:limite], start=1)
            if (item.get("title") or "").strip()
        ]
