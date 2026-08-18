import httpx

from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos


class LushaContactEnrichmentProvider(ContactEnrichmentProvider):
    """Integração real com a Prospecting API da Lusha — busca por
    filtros (`/prospecting/contact/search`, sem PII) seguida de
    revelação dos contatos encontrados (`/prospecting/contact/enrich`,
    com e-mail/telefone), as duas síncronas (diferente do Apollo, cujo
    telefone só sai por webhook assíncrono — por isso a escolha pela
    Lusha). Nomes de campo conferidos pela documentação pública; como o
    site da Lusha é uma SPA que não expõe o texto completo pra scraping,
    vale um teste de ponta a ponta com a chave real antes de confiar
    cegamente — ajustar aqui se algum campo vier diferente."""

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
            "pages": {"page": 0, "size": 20},
            "filters": {
                "contacts": {"include": {"jobTitles": filtro.cargos_alvo}},
                "companies": filtros_empresa,
            },
        }
        dados_busca = self._chamar("/prospecting/contact/search", corpo_busca)
        if dados_busca is None:
            return []

        request_id = dados_busca.get("requestId")
        contact_ids = [c.get("contactId") for c in dados_busca.get("contacts", []) if c.get("contactId")]
        if not request_id or not contact_ids:
            return []

        dados_enrich = self._chamar(
            "/prospecting/contact/enrich", {"requestId": request_id, "contactIds": contact_ids}
        )
        if dados_enrich is None:
            return []

        candidatos = []
        for contato in dados_enrich.get("contacts", []):
            nome = contato.get("fullName") or " ".join(
                parte for parte in [contato.get("firstName"), contato.get("lastName")] if parte
            )
            if not nome:
                continue
            candidatos.append(
                ContatoCandidato(
                    nome=nome,
                    cargo=contato.get("jobTitle", ""),
                    email=self._primeiro_valor(contato.get("emailAddresses")),
                    telefone=self._primeiro_valor(contato.get("phoneNumbers")),
                    linkedin_url=contato.get("linkedinUrl"),
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
    def _primeiro_valor(itens: list | None) -> str | None:
        if not itens:
            return None
        primeiro = itens[0]
        if isinstance(primeiro, dict):
            return primeiro.get("email") or primeiro.get("phoneNumber") or primeiro.get("value")
        return str(primeiro)
