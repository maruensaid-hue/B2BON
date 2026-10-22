import httpx

from app.providers.contact_enrichment.base import (
    ContactEnrichmentProvider,
    ContatoCandidato,
    FiltroContatos,
    ResultadoBuscaContatos,
    UsoProvedor,
)


def _inteiro(valor) -> int | None:
    """Inteiro não negativo ou None. Booleano, texto e negativo não são medição válida."""
    if isinstance(valor, bool) or not isinstance(valor, int | float) or valor < 0 or int(valor) != valor:
        return None
    return int(valor)


class ProvedorContatosB2B(ContactEnrichmentProvider):
    """Integração real com a API de prospecção B2B contratada (v3) — busca por filtros (`POST /v3/contacts/prospecting`) seguida de revelação dos ids
    escolhidos (`POST /v3/contacts/enrich`), as duas síncronas. Formato conferido na documentação oficial do provedor, não por suposição:

    * a busca é cobrada por resultado devolvido e a revelação por dado revelado (e-mail e telefone têm tarifas diferentes); as duas respostas
      trazem `billing.creditsCharged`, o consumo REAL da requisição, que é o que a governança de créditos usa (nunca "1 contato = 1 crédito");
    * `pagination.size` aceita de 10 a 100; `enrich` aceita de 1 a 100 ids; `waterfallEnabled` é desligado para não acionar provedores externos
      (e custo extra) que o assinante não escolheu;
    * 402 = créditos insuficientes (nada processado), 429 = limite de taxa."""

    _BASE_URL = "https://api.lusha.com"
    _TAMANHO_MAX_PAGINA = 100  # teto documentado de `pagination.size` e de ids por `enrich`
    _TAMANHO_MIN_PAGINA = 10  # piso documentado de `pagination.size`

    nome_provedor = "contatos"
    max_contatos_por_consulta = _TAMANHO_MAX_PAGINA
    tamanho_pagina_minimo = _TAMANHO_MIN_PAGINA
    pago = True  # cada consulta consome crédito contratado: só pelo caminho governado

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _headers(self) -> dict:
        return {"api_key": self._api_key, "Content-Type": "application/json"}

    # ----------------------------------------------------------------------------------------------------------------- caminho governado

    def buscar_contatos_governado(self, filtro: FiltroContatos) -> ResultadoBuscaContatos:
        """Busca + revelação com limite, tamanho de página e dados a revelar vindos da política aprovada, e com o consumo medido pela resposta.

        Classificação (a mesma regra vale para as duas etapas, porque as duas consomem crédito):
        * certa de não-cobrança (`erro_seguro`): erro de conexão antes do envio, rejeição 4xx (inclui 402 e 429);
        * ambígua (`ambiguo`): timeout, 5xx, queda no meio, resposta ilegível, ou resposta 2xx SEM a medição `billing.creditsCharged`.
        Se a busca já consumiu crédito e a revelação falha, o consumo da busca vai junto no resultado (`creditos_provedor`)."""
        limite, pagina, revelar = filtro.limite_contatos, filtro.tamanho_pagina, filtro.revelar
        if limite is None or limite < 1:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="limite_de_contatos_ausente")
        if pagina is None or not self._TAMANHO_MIN_PAGINA <= pagina <= self._TAMANHO_MAX_PAGINA or limite > pagina:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="tamanho_de_pagina_invalido")
        if not revelar or not set(revelar) <= {"emails", "phones"}:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="dados_a_revelar_invalidos")

        filtros_empresa: dict = {"include": {}}
        if filtro.dominio:
            filtros_empresa["include"]["domains"] = [filtro.dominio]
        else:
            filtros_empresa["include"]["names"] = [filtro.nome_empresa]
        corpo_busca = {
            "pagination": {"page": 0, "size": pagina},
            "filters": {"contacts": {"include": {"jobTitles": filtro.cargos_alvo}}, "companies": filtros_empresa},
        }
        dados_busca, falha = self._chamar_classificado("/v3/contacts/prospecting", corpo_busca)
        if dados_busca is None:
            return ResultadoBuscaContatos(estado=self._estado_da_falha(falha), detalhe=f"busca_{falha}")
        creditos_busca = _inteiro((dados_busca.get("billing") or {}).get("creditsCharged"))
        if creditos_busca is None:
            return ResultadoBuscaContatos(estado="ambiguo", detalhe="medicao_ausente_na_busca")

        ids = [str(item["id"]) for item in dados_busca.get("results", []) if item.get("id") and not item.get("error")][:limite]
        if not ids:
            return ResultadoBuscaContatos(estado="sem_resultados", creditos_provedor=creditos_busca, creditos_busca=creditos_busca)

        corpo_enrich = {"ids": ids, "reveal": list(revelar), "waterfallEnabled": False}
        dados_enrich, falha = self._chamar_classificado("/v3/contacts/enrich", corpo_enrich)
        if dados_enrich is None:
            # a busca já foi cobrada e medida; só o desfecho da revelação é certo (seguro) ou incerto (ambíguo)
            return ResultadoBuscaContatos(
                estado=self._estado_da_falha(falha), ids_provedor=ids, detalhe=f"revelacao_{falha}",
                creditos_provedor=creditos_busca, creditos_busca=creditos_busca,
            )
        creditos_revelacao = _inteiro((dados_enrich.get("billing") or {}).get("creditsCharged"))
        if creditos_revelacao is None or str(dados_enrich.get("status", "")).upper().endswith("OUT_OF_CREDITS"):
            return ResultadoBuscaContatos(
                estado="ambiguo", ids_provedor=ids, detalhe="medicao_ausente_na_revelacao" if creditos_revelacao is None else "revelacao_sem_creditos",
                creditos_busca=creditos_busca,
            )

        total = creditos_busca + creditos_revelacao
        contatos = self._mapear_contatos(dados_enrich)
        if not contatos:
            return ResultadoBuscaContatos(estado="sem_resultados", ids_provedor=ids, creditos_provedor=total, creditos_busca=creditos_busca,
                                          creditos_revelacao=creditos_revelacao)
        return ResultadoBuscaContatos(estado="ok", contatos=contatos[:limite], ids_provedor=ids, creditos_provedor=total, creditos_busca=creditos_busca,
                                      creditos_revelacao=creditos_revelacao)

    @staticmethod
    def _estado_da_falha(falha: str | None) -> str:
        return "erro_seguro" if falha in ("conexao", "rejeitada", "sem_creditos", "limite_de_taxa") else "ambiguo"

    def _chamar_classificado(self, caminho: str, corpo: dict) -> tuple[dict | None, str | None]:
        """(dados, None) em sucesso; (None, causa) em falha. Causas: conexao (nada foi enviado), sem_creditos (402), limite_de_taxa (429),
        rejeitada (outro 4xx), timeout, servidor (5xx), transporte (queda no meio), resposta_ilegivel."""
        try:
            resposta = httpx.post(f"{self._BASE_URL}{caminho}", json=corpo, headers=self._headers(), timeout=15.0)
            resposta.raise_for_status()
        except httpx.HTTPStatusError as erro:
            codigo = getattr(erro.response, "status_code", 500)
            if codigo == 402:
                return None, "sem_creditos"
            if codigo == 429:
                return None, "limite_de_taxa"
            return None, "rejeitada" if 400 <= codigo < 500 else "servidor"
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return None, "conexao"
        except httpx.TimeoutException:
            return None, "timeout"
        except httpx.HTTPError:
            return None, "transporte"
        try:
            dados = resposta.json()
        except ValueError:
            return None, "resposta_ilegivel"
        return (dados, None) if isinstance(dados, dict) else (None, "resposta_ilegivel")

    def consultar_uso(self) -> UsoProvedor:
        """`GET /v3/account/usage`: créditos do ciclo e tarifas por ação, como o provedor publica. Levanta `httpx.HTTPError` em falha."""
        resposta = httpx.get(f"{self._BASE_URL}/v3/account/usage", headers=self._headers(), timeout=15.0)
        resposta.raise_for_status()
        dados = resposta.json()
        creditos = dados.get("credits") or {}
        return UsoProvedor(
            creditos_total=_inteiro(creditos.get("total")), creditos_usados=_inteiro(creditos.get("used")),
            creditos_restantes=_inteiro(creditos.get("remaining")), tarifas=dict(dados.get("pricing") or {}),
        )

    # ----------------------------------------------------------------------------------------------------------------- mapeamento

    @staticmethod
    def _link_linkedin(contato: dict) -> str | None:
        """Link do perfil no LinkedIn: o provedor o devolve em `socialLinks.linkedin`; aceita também chaves planas. Nunca inventa: sem link, None."""
        social = contato.get("socialLinks") or {}
        for bruto in (social.get("linkedin"), contato.get("linkedinUrl"), contato.get("linkedin")):
            if isinstance(bruto, dict):
                bruto = bruto.get("url")
            if isinstance(bruto, str) and bruto.strip():
                link = bruto.strip()
                return link if link.lower().startswith(("http://", "https://")) else "https://" + link.lstrip("/")
        return None

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
                    linkedin_url=self._link_linkedin(contato),
                    fonte="contatos",
                )
            )
        return candidatos

    # ----------------------------------------------------------------------------------------------------------------- caminho legado

    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        """Caminho antigo, sem governança: mantido só para o adaptador continuar testável isoladamente. Nada na aplicação o chama."""
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
        return self._mapear_contatos(dados_enrich)

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
