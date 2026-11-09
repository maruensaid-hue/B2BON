import httpx

from app.providers.contact_enrichment.base import (
    ContactEnrichmentProvider,
    ContatoCandidato,
    FiltroContatos,
    ResultadoBuscaContatos,
)

_BASE_URL = "https://api.hunter.io"
_TIMEOUT_S = 10.0
_LIMITE_PLANO_GRATUITO = 10  # `limit + offset` acima de 10 devolve `pagination_error` no plano gratuito (documentação da API)


def _inteiro(valor) -> int | None:
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return numero if numero >= 0 else None


def _status_do_email(item: dict) -> str:
    """`verificado`: o próprio provedor checou a caixa (`verification.status == "valid"`); `inferido`: o provedor deduziu o endereço e ninguém o checou
    (NÃO sai no envio, como o e-mail montado pelo padrão da empresa); `publicado`: visto numa fonte pública. Nunca `confirmado`: esse é só de uma pessoa."""
    verificacao = item.get("verification") or {}
    if verificacao.get("status") == "valid":
        return "verificado"
    if item.get("provenance") == "inferred":
        return "inferido"
    return "publicado"


def _candidato(item: dict) -> ContatoCandidato | None:
    nome = f"{(item.get('first_name') or '').strip()} {(item.get('last_name') or '').strip()}".strip()
    email = (item.get("value") or "").strip() or None
    if not nome or not email:
        return None  # sem nome e e-mail não há decisor utilizável (e `required_field` já pede nome e cargo)
    linkedin = (item.get("linkedin") or "").strip()
    return ContatoCandidato(
        nome=nome,
        cargo=(item.get("position") or "").strip(),
        email=email,
        telefone=(item.get("phone_number") or None),
        # A documentação não diz se o campo é um endereço ou só o identificador do perfil: só se guarda o que já é um endereço.
        linkedin_url=linkedin if linkedin.startswith(("http://", "https://")) else None,
        fonte="hunter",
        email_status=_status_do_email(item),
    )


class ProvedorHunter(ContactEnrichmentProvider):
    """Hunter (Domain Search). Plano gratuito: 50 créditos/mês e no máximo 10 resultados por consulta; a franquia é do FORNECEDOR e quem a controla é o
    gerenciador de recursos (`app/contexts/enriquecimento/gerenciador.py`), não este adaptador. Para o cliente é uma fonte sem custo próprio (`pago=False`).

    Contrato conferido na documentação oficial (2026-11-09): `GET /v2/domain-search`, chave em `X-API-KEY`, filtros `type`, `seniority`, `required_field`
    e `limit`; 401 = chave inválida, **403 = limite de taxa**, **429 = limite de uso do plano**, 400 = parâmetro inválido (inclui `pagination_error`).
    O consumo vem no cabeçalho `X-Credits-Used`. NÃO foi chamado contra a API real (não há chave): os testes provam a leitura do formato documentado,
    não o funcionamento da integração."""

    nome_provedor = "hunter"
    pago = False
    max_contatos_por_consulta = _LIMITE_PLANO_GRATUITO

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport
        self.disponivel = bool(api_key)

    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        resultado = self.buscar_contatos_governado(filtro)
        return resultado.contatos if resultado.estado == "ok" else []

    def buscar_contatos_governado(self, filtro: FiltroContatos) -> ResultadoBuscaContatos:
        if not self._api_key:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="hunter_sem_chave")
        parametros: dict[str, str | int] = {
            "type": "personal",  # pessoa, não caixa genérica (contato@, vendas@)
            "seniority": "senior,executive",
            "required_field": "full_name,position",
            "limit": min(filtro.limite_contatos or _LIMITE_PLANO_GRATUITO, _LIMITE_PLANO_GRATUITO),
        }
        if filtro.dominio:
            parametros["domain"] = filtro.dominio
        elif filtro.nome_empresa:
            parametros["company"] = filtro.nome_empresa
        else:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="hunter_sem_dominio_nem_empresa")

        try:
            with httpx.Client(timeout=_TIMEOUT_S, transport=self._transport) as cliente:
                resposta = cliente.get(f"{_BASE_URL}/v2/domain-search", params=parametros, headers={"X-API-KEY": self._api_key})
        except httpx.HTTPError:
            return ResultadoBuscaContatos(estado="ambiguo", detalhe="hunter_falha_de_rede")

        consumo = _inteiro(resposta.headers.get("X-Credits-Used"))
        if resposta.status_code == 401:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="hunter_chave_invalida")
        if resposta.status_code == 403:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="hunter_limite_de_taxa")
        if resposta.status_code == 429:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="hunter_sem_creditos")  # sufixo lido pela execução ("...sem_creditos")
        if resposta.status_code == 400:
            return ResultadoBuscaContatos(estado="erro_seguro", detalhe="hunter_requisicao_invalida")
        if resposta.status_code != 200:
            return ResultadoBuscaContatos(estado="ambiguo", detalhe=f"hunter_http_{resposta.status_code}", creditos_provedor=consumo)
        try:
            itens = ((resposta.json().get("data") or {}).get("emails")) or []
        except ValueError:
            return ResultadoBuscaContatos(estado="ambiguo", detalhe="hunter_resposta_ilegivel", creditos_provedor=consumo)

        contatos = [c for c in (_candidato(item) for item in itens if isinstance(item, dict)) if c is not None]
        if filtro.limite_contatos is not None:
            contatos = contatos[: filtro.limite_contatos]
        return ResultadoBuscaContatos(estado="ok" if contatos else "sem_resultados", contatos=contatos, creditos_provedor=consumo)
