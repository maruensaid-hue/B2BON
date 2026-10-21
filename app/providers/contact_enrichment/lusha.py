import httpx

from app.providers.contact_enrichment.base import (
    ContactEnrichmentProvider,
    ContatoCandidato,
    FiltroContatos,
    ResultadoBuscaContatos,
)


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
    _TAMANHO_MAX_PAGINA = 20  # o que o adaptador já usava; não é um limite contratual conhecido da Lusha

    nome_provedor = "lusha"
    max_contatos_por_consulta = _TAMANHO_MAX_PAGINA  # o adaptador não pagina: uma página por consulta
    pago = True  # cada contato revelado consome crédito contratado: só pelo caminho governado

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _headers(self) -> dict:
        return {"api_key": self._api_key, "Content-Type": "application/json"}

    def buscar_contatos_governado(self, filtro: FiltroContatos) -> ResultadoBuscaContatos:
        """Mesma busca em duas etapas, mas (1) revela no máximo `limite_contatos` ids, (2) separa o que é certeza de não-cobrança do que é
        desfecho desconhecido. A busca (`prospecting`) não revela dado pessoal; só o `enrich` revela, então falha na busca é sempre segura.
        No `enrich`: erro de conexão antes do envio e rejeição 4xx (inclui 429) são seguros; timeout de leitura/escrita, 5xx e resposta ilegível
        são ambíguos. Sem limite informado nada é revelado (falha segura). Se a própria busca consome crédito da Lusha é ponto contratual
        a confirmar — o adaptador não presume."""
        limite = filtro.limite_contatos
        if limite is None or limite < 1:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="limite_de_contatos_ausente")

        filtros_empresa: dict = {"include": {}}
        if filtro.dominio:
            filtros_empresa["include"]["domains"] = [filtro.dominio]
        else:
            filtros_empresa["include"]["names"] = [filtro.nome_empresa]
        corpo_busca = {
            "pagination": {"page": 0, "size": min(limite, self._TAMANHO_MAX_PAGINA)},
            "filters": {"contacts": {"include": {"jobTitles": filtro.cargos_alvo}}, "companies": filtros_empresa},
        }
        dados_busca, falha = self._chamar_classificado("/v3/contacts/prospecting", corpo_busca)
        if dados_busca is None:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe=f"busca_{falha}")

        ids = [str(item["id"]) for item in dados_busca.get("results", []) if item.get("id")][:limite]
        if not ids:
            return ResultadoBuscaContatos(estado="sem_resultados")

        dados_enrich, falha = self._chamar_classificado("/v3/contacts/enrich", {"ids": ids, "reveal": ["emails", "phones"]})
        if dados_enrich is None:
            seguro = falha in ("conexao", "rejeitada")
            return ResultadoBuscaContatos(estado="erro_seguro" if seguro else "ambiguo", ids_provedor=ids, detalhe=f"revelacao_{falha}")

        contatos = self._mapear_contatos(dados_enrich)
        if not contatos:
            return ResultadoBuscaContatos(estado="sem_resultados", ids_provedor=ids)
        return ResultadoBuscaContatos(estado="ok", contatos=contatos[:limite], ids_provedor=ids)

    def _chamar_classificado(self, caminho: str, corpo: dict) -> tuple[dict | None, str | None]:
        """(dados, None) em sucesso; (None, causa) em falha. Causas: conexao (nada foi enviado), rejeitada (4xx), timeout, servidor (5xx),
        transporte (queda no meio), resposta_ilegivel."""
        try:
            resposta = httpx.post(f"{self._BASE_URL}{caminho}", json=corpo, headers=self._headers(), timeout=15.0)
            resposta.raise_for_status()
        except httpx.HTTPStatusError as erro:
            codigo = getattr(erro.response, "status_code", 500)
            return None, "rejeitada" if 400 <= codigo < 500 else "servidor"
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return None, "conexao"
        except httpx.TimeoutException:
            return None, "timeout"
        except httpx.HTTPError:
            return None, "transporte"
        try:
            return resposta.json(), None
        except ValueError:
            return None, "resposta_ilegivel"

    def _mapear_contatos(self, dados_enrich: dict) -> list[ContatoCandidato]:
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
