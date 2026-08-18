import httpx

from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos


class LushaContactEnrichmentProvider(ContactEnrichmentProvider):
    """Integração real com a Prospecting API v3 da Lusha — busca por
    filtros (`POST /v3/contacts/prospecting`, sem PII) seguida de
    revelação dos IDs encontrados (`POST /v3/contacts/enrich`, com
    e-mail/telefone), as duas síncronas (diferente do Apollo, cujo
    telefone só sai por webhook assíncrono — por isso a escolha pela
    Lusha). Formato de requisição/resposta dos dois endpoints conferido
    direto no OpenAPI spec oficial da Lusha (`V3EnrichedContact`,
    `V3EmailAddress`, `V3PhoneNumber`), não por suposição."""

    _BASE_URL = "https://api.lusha.com"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _headers(self) -> dict:
        return {"api_key": self._api_key, "Content-Type": "application/json"}

    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        filtros_empresa: dict = {"include": {}}
        if filtro.dominio:
            filtros_empresa["include"]["domains"] = [filtro.dominio]
        else:
            filtros_empresa["include"]["names"] = [filtro.nome_empresa]

        corpo_busca = {
            "pagination": {"page": 0, "size": 20},
            "filters": {
                "contacts": {"include": {"jobTitles": filtro.cargos_alvo}},
                "companies": filtros_empresa,
            },
        }
        dados_busca = self._chamar("/v3/contacts/prospecting", corpo_busca)
        if dados_busca is None:
            return []

        ids = [item.get("id") for item in dados_busca.get("results", []) if item.get("id")]
        if not ids:
            return []

        dados_enrich = self._chamar("/v3/contacts/enrich", {"ids": ids, "reveal": ["emails", "phones"]})
        if dados_enrich is None:
            return []

        candidatos = []
        for contato in dados_enrich.get("results", []):
            if contato.get("error"):
                continue
            nome = contato.get("fullName") or " ".join(
                parte for parte in [contato.get("firstName"), contato.get("lastName")] if parte
            )
            if not nome:
                continue
            candidatos.append(
                ContatoCandidato(
                    nome=nome,
                    cargo=(contato.get("jobTitle") or {}).get("title", ""),
                    email=self._primeiro_valor(contato.get("emails"), "email"),
                    telefone=self._primeiro_valor(contato.get("phones"), "number"),
                    linkedin_url=(contato.get("socialLinks") or {}).get("linkedin"),
                    fonte="lusha",
                )
            )
        return candidatos

    def _chamar(self, caminho: str, corpo: dict) -> dict | None:
        try:
            resposta = httpx.post(f"{self._BASE_URL}{caminho}", json=corpo, headers=self._headers(), timeout=15.0)
            resposta.raise_for_status()
            return resposta.json()
        except httpx.HTTPError:
            return None

    @staticmethod
    def _primeiro_valor(itens: list | None, campo: str) -> str | None:
        if not itens:
            return None
        return itens[0].get(campo)
