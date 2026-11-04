"""Busca de mapa na base aberta de mapas (OpenStreetMap): fonte padrão da descoberta enquanto não há fonte paga configurada.

Sem chave e sem custo por chamada; a licença (ODbL) permite guardar e reutilizar os dados, com atribuição da fonte. Duas etapas por busca:
1. a cidade vira uma área do mapa (serviço de geocodificação; uma vez por cidade por execução, no máximo 1 pedido por segundo, como a
   política de uso dele pede);
2. a consulta de dados do mapa traz, dentro da área, os lugares de negócio (loja, escritório, serviço, saúde...) cujo nome ou categoria
   bate com o termo.
Não traz nota nem quantidade de avaliações (a base não tem): esses sinais simplesmente não são gravados. O nome da fonte não aparece
para o cliente (regra de não expor fornecedores): a tela fala só em "busca de mapa".
"""

import re
import time
import unicodedata

import httpx

from app.core.config import settings
from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider, DescobertaIndisponivel, EmpresaDescoberta

_GEOCODIFICACAO = "https://nominatim.openstreetmap.org/search"
_DADOS_MAPA = "https://overpass-api.de/api/interpreter"
_TIMEOUT = 120.0
_STATUS_SERVIDOR_CHEIO = {429, 502, 503, 504}
_ESPERAS_SERVIDOR_CHEIO = (10, 20, 40)  # segundos; roda em segundo plano, então esperar não trava a tela

# Chaves de categoria que indicam negócio (fora delas vêm ruas, bairros, praças etc.).
_CHAVES_NEGOCIO = "shop|office|amenity|craft|healthcare|tourism|leisure|industrial"

# Termo comum em português -> categorias do mapa. O nome também é buscado, então o dicionário só amplia o que o nome sozinho não pega.
_CATEGORIAS: dict[str, list[tuple[str, str]]] = {
    "contab": [("office", "accountant")],
    "advoga": [("office", "lawyer")],
    "advocacia": [("office", "lawyer")],
    "odonto": [("amenity", "dentist"), ("healthcare", "dentist")],
    "dentist": [("amenity", "dentist"), ("healthcare", "dentist")],
    "clinica": [("amenity", "clinic"), ("healthcare", "clinic")],
    "medic": [("amenity", "doctors"), ("healthcare", "doctor")],
    "farmac": [("amenity", "pharmacy")],
    "veterin": [("amenity", "veterinary")],
    "imobili": [("office", "estate_agent")],
    "seguro": [("office", "insurance")],
    "seguradora": [("office", "insurance")],
    "academia": [("leisure", "fitness_centre")],
    "restaurante": [("amenity", "restaurant")],
    "hotel": [("tourism", "hotel")],
    "escola": [("amenity", "school")],
    "faculdade": [("amenity", "college"), ("amenity", "university")],
    "oficina": [("shop", "car_repair")],
    "mecanic": [("shop", "car_repair")],
    "padaria": [("shop", "bakery")],
    "supermercado": [("shop", "supermarket")],
    "otica": [("shop", "optician")],
    "arquitet": [("office", "architect")],
    "engenhar": [("office", "engineer")],
    "tecnologia": [("office", "it"), ("office", "company")],
    "software": [("office", "it")],
    "informatica": [("shop", "computer"), ("office", "it")],
    "construtora": [("office", "construction_company")],
    "transportadora": [("office", "logistics")],
    "logistica": [("office", "logistics")],
    "industria": [("industrial", "factory"), ("man_made", "works")],
    "fabrica": [("industrial", "factory"), ("man_made", "works")],
}

_PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "e", "em", "para", "com", "escritorio", "empresa", "empresas", "loja", "servico", "servicos"}


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def _palavras(termo: str) -> list[str]:
    return [p for p in re.findall(r"[a-z0-9]+", _sem_acento(termo)) if len(p) >= 4 and p not in _PALAVRAS_VAZIAS]


def _radical(palavra: str) -> str:
    """Corta a terminação para casar variações (contabilidade/contábil -> contab, clínica/clínicas -> clinic)."""
    return palavra[:6] if len(palavra) > 6 else palavra


def _regex_nome(palavras: list[str]) -> str:
    """Regex do nome, tolerante a acento: cada vogal casa com as variantes acentuadas (a base guarda o nome como foi escrito)."""
    variantes = {"a": "[aáàâã]", "e": "[eéê]", "i": "[ií]", "o": "[oóôõ]", "u": "[uúü]", "c": "[cç]"}
    partes = ["".join(variantes.get(letra, letra) for letra in _radical(p)) for p in palavras]
    return "|".join(partes)


def _categorias(palavras: list[str]) -> list[tuple[str, str]]:
    achadas: list[tuple[str, str]] = []
    for palavra in palavras:
        for prefixo, categorias in _CATEGORIAS.items():
            if palavra.startswith(prefixo) or prefixo.startswith(_radical(palavra)):
                achadas += [c for c in categorias if c not in achadas]
    return achadas


def _consulta(area_id: int, palavras: list[str], limite: int) -> str:
    # Uma instrução por chave de negócio (filtro por chave existente é indexado e leve; regex sobre a chave inteira estourava 40 s).
    regex = _regex_nome(palavras)
    filtros = [f'nwr(area.a)["{chave}"]["name"~"{regex}",i];' for chave in _CHAVES_NEGOCIO.split("|")]
    filtros += [f'nwr(area.a)["{chave}"="{valor}"]["name"];' for chave, valor in _categorias(palavras)]
    return f"[out:json][timeout:90];area(id:{area_id})->.a;({''.join(filtros)});out center tags {max(limite * 3, 30)};"


def _categoria(tags: dict) -> str | None:
    for chave in ("office", "shop", "amenity", "healthcare", "craft", "tourism", "leisure", "industrial"):
        if tags.get(chave) and tags[chave] != "yes":
            return tags[chave].replace("_", " ")
    return None


def _endereco(tags: dict) -> str | None:
    rua = " ".join(v for v in (tags.get("addr:street"), tags.get("addr:housenumber")) if v)
    partes = [rua, tags.get("addr:suburb"), tags.get("addr:city")]
    return ", ".join(p for p in partes if p) or None


class MapaAbertoProvider(DescobertaEmpresasProvider):
    """Base aberta de mapas: sem chave, sem custo por busca. Cidade -> área (cacheada na execução) -> lugares de negócio."""

    custo_por_busca_usd = 0.0
    lenta = True  # servidor público: uma busca pode levar mais de um minuto quando está cheio

    def __init__(self, cliente: httpx.Client | None = None) -> None:
        self._cliente = cliente
        self._areas: dict[str, int] = {}
        self._ultima_geocodificacao = 0.0

    def _http(self) -> httpx.Client:
        if self._cliente is None:
            # As duas políticas de uso pedem um User-Agent que identifique o aplicativo.
            self._cliente = httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": f"B2BON-prospeccao/1.0 (+{settings.url_base_api})"})
        return self._cliente

    def _area(self, cidade: str) -> int:
        chave = _sem_acento(cidade).strip()
        if chave in self._areas:
            return self._areas[chave]
        espera = 1.1 - (time.monotonic() - self._ultima_geocodificacao)
        if espera > 0:
            time.sleep(espera)  # política da geocodificação: no máximo 1 pedido por segundo
        try:
            resposta = self._http().get(_GEOCODIFICACAO, params={"q": cidade, "countrycodes": "br", "format": "jsonv2", "limit": 5})
            resposta.raise_for_status()
        except httpx.HTTPError as erro:
            raise DescobertaIndisponivel(f"a busca de mapa não respondeu ao localizar a cidade ({type(erro).__name__})") from erro
        finally:
            self._ultima_geocodificacao = time.monotonic()
        relacoes = [r for r in resposta.json() if r.get("osm_type") == "relation" and r.get("osm_id")]
        if not relacoes:
            raise DescobertaIndisponivel(f"cidade não encontrada no mapa: informe também a UF (ex.: \"{cidade} SP\")")
        self._areas[chave] = 3_600_000_000 + int(relacoes[0]["osm_id"])  # área do mapa = id da relação + 3.600.000.000
        return self._areas[chave]

    def buscar(self, termo: str, cidade: str, limite: int = 20) -> list[EmpresaDescoberta]:
        palavras = _palavras(termo)
        if not palavras:
            raise DescobertaIndisponivel("termo genérico demais: descreva o que a empresa faz (ex.: \"contabilidade\")")
        area = self._area(cidade)
        consulta = _consulta(area, palavras, limite)
        resposta = None
        for espera in (*_ESPERAS_SERVIDOR_CHEIO, None):
            try:
                resposta = self._http().post(_DADOS_MAPA, data={"data": consulta})
            except httpx.TimeoutException:
                resposta = None  # servidor lento: conta como cheio
            except httpx.HTTPError as erro:
                raise DescobertaIndisponivel(f"a busca de mapa não respondeu ({type(erro).__name__})") from erro
            if resposta is not None and resposta.status_code not in _STATUS_SERVIDOR_CHEIO:
                break
            if espera is not None:
                time.sleep(espera)  # o servidor público pede nova tentativa com espera crescente quando está cheio
        if resposta is None or not resposta.is_success:
            situacao = "sem resposta" if resposta is None else f"HTTP {resposta.status_code}"
            raise DescobertaIndisponivel(f"a busca de mapa está sobrecarregada ({situacao}); tente de novo mais tarde")

        busca = f"{termo} {cidade}".strip()
        vistos: set[str] = set()
        achadas: list[EmpresaDescoberta] = []
        for elemento in resposta.json().get("elements") or []:
            tags = elemento.get("tags") or {}
            nome = (tags.get("name") or "").strip()
            if not nome or _sem_acento(nome) in vistos:
                continue
            vistos.add(_sem_acento(nome))
            achadas.append(EmpresaDescoberta(
                nome=nome,
                site=tags.get("website") or tags.get("contact:website") or None,
                telefone=tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or None,
                endereco=_endereco(tags),
                categoria=_categoria(tags),
                posicao=len(achadas) + 1,
                busca=busca,
            ))
            if len(achadas) >= limite:
                break
        return achadas
