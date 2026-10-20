"""Inteligência determinística do site institucional (sem IA): confirmação do domínio e indicadores financeiros públicos.

Tudo aqui é regra reproduzível sobre o texto já coletado. A IA só resume depois; nada deste módulo depende dela.

* `verificar_dominio`: o nome parecido NÃO confirma domínio. Confirmam CNPJ exibido no site, e-mail do cadastro público no mesmo
  domínio, endereço (CEP, logradouro + número) e telefone. Sem prova suficiente o resultado é `provavel`/`inconclusivo`, e CNPJ
  diferente do da conta sem outra prova é `divergente`. Cada limitação (dado ausente) é registrada, nunca preenchida.
* `extrair_indicadores`: só o que está escrito no texto, com valor, moeda, escala, período, trecho e URL da fonte. Ausência de
  dado não vira indicador (nem "zero"). `derivar_indicadores` calcula apenas o que a fórmula permite, sem misturar períodos,
  moedas ou páginas, e registra a fórmula e as origens.
"""

import re
import unicodedata
from dataclasses import dataclass, field

Pagina = tuple[str, str]  # (url, texto visível)

# --- Domínio -------------------------------------------------------------------------------------------------------------

_REGEX_CNPJ = re.compile(r"(?<!\d)(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})(?!\d)")
_REGEX_CEP = re.compile(r"(?<!\d)(\d{5})-?(\d{3})(?!\d)")
_PESOS = {"cnpj_exato": 70, "cnpj_mesma_raiz": 55, "email_dominio": 35, "endereco": 25, "cep": 20, "telefone": 10, "nome": 5}
_SUFIXOS_JURIDICOS = re.compile(r"\b(ltda|eireli|epp|mei|s\s*/?\s*a|sa|me|sociedade anonima|comercio|industria|servicos)\b")


def normalizar(texto: str | None) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/@.\- ]+", " ", sem_acento)).strip()


def so_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def dominio_base(dominio: str | None) -> str:
    limpo = re.sub(r"^[a-z]+://", "", (dominio or "").strip().lower()).split("/")[0]
    return re.sub(r"^www\.", "", limpo)


def _mesmo_dominio(a: str, b: str) -> bool:
    a, b = dominio_base(a), dominio_base(b)
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


@dataclass
class VerificacaoDominio:
    situacao: str  # confirmado | provavel | inconclusivo | divergente
    pontuacao: int
    evidencias: list[dict] = field(default_factory=list)  # {tipo, detalhe, encontrada}
    limitacoes: list[str] = field(default_factory=list)

    @property
    def exige_validacao_manual(self) -> bool:
        return self.situacao != "confirmado"


def verificar_dominio(dominio: str, paginas: list[Pagina], cnpj_conta: str | None, nome_conta: str | None,
                      registro: dict | None) -> VerificacaoDominio:
    """`registro`: dados do cadastro público do CNPJ (formato da BrasilAPI) ou `None` se não foi possível consultar."""
    texto = "\n".join(t for _, t in paginas)
    texto_norm = normalizar(texto)
    digitos_texto = so_digitos(texto)
    evidencias: list[dict] = []
    limitacoes: list[str] = []

    def evidencia(tipo: str, detalhe: str, encontrada: bool) -> None:
        evidencias.append({"tipo": tipo, "detalhe": detalhe, "encontrada": encontrada})

    cnpj = so_digitos(cnpj_conta)
    cnpj_valido = len(cnpj) == 14
    cnpjs_no_site = {"".join(m.groups()) for m in _REGEX_CNPJ.finditer(texto)}
    exato = mesma_raiz = False
    if not cnpj_valido:
        limitacoes.append("CNPJ da conta não informado ou inválido: não foi possível comparar com o que o site exibe.")
    elif not cnpjs_no_site:
        limitacoes.append("O site não exibe CNPJ nas páginas coletadas (ausência de evidência, não prova de divergência).")
    else:
        exato = cnpj in cnpjs_no_site
        mesma_raiz = not exato and any(c[:8] == cnpj[:8] for c in cnpjs_no_site)
        evidencia("cnpj_exato", f"CNPJ {cnpj} exibido no site", exato)
        if mesma_raiz:
            evidencia("cnpj_mesma_raiz", "CNPJ de outro estabelecimento da mesma empresa (mesma raiz) exibido no site", True)

    outros_cnpjs = {c for c in cnpjs_no_site if cnpj_valido and c[:8] != cnpj[:8]}

    pontuacao = 0
    if exato:
        pontuacao += _PESOS["cnpj_exato"]
    elif mesma_raiz:
        pontuacao += _PESOS["cnpj_mesma_raiz"]

    if registro is None:
        limitacoes.append(
            "Cadastro público do CNPJ indisponível ou CNPJ não informado: e-mail, endereço e telefone oficiais não foram comparados."
        )
    else:
        email = (registro.get("email") or "").strip().lower()
        if "@" in email:
            ok = _mesmo_dominio(email.split("@", 1)[1], dominio)
            evidencia("email_dominio", f"E-mail do cadastro público ({email.split('@', 1)[1]}) {'bate' if ok else 'não bate'} com o domínio", ok)
            pontuacao += _PESOS["email_dominio"] if ok else 0
        else:
            limitacoes.append("O cadastro público não informa e-mail para comparar com o domínio.")

        cep = so_digitos(registro.get("cep"))
        if len(cep) == 8:
            achou = any("".join(m.groups()) == cep for m in _REGEX_CEP.finditer(texto))
            evidencia("cep", f"CEP {cep[:5]}-{cep[5:]} do cadastro {'aparece' if achou else 'não aparece'} no site", achou)
            pontuacao += _PESOS["cep"] if achou else 0
        logradouro = normalizar(registro.get("logradouro"))
        numero = so_digitos(registro.get("numero"))
        if len(logradouro) >= 6:
            achou = False
            for m in re.finditer(re.escape(logradouro), texto_norm):
                janela = texto_norm[m.end(): m.end() + 30]
                if not numero or re.search(rf"(?<!\d){re.escape(numero)}(?!\d)", janela):
                    achou = True
                    break
            evidencia("endereco", f"Logradouro e número do cadastro {'aparecem' if achou else 'não aparecem'} juntos no site", achou)
            pontuacao += _PESOS["endereco"] if achou else 0
        telefone = so_digitos(registro.get("ddd_telefone_1"))
        if len(telefone) in (10, 11):
            achou = telefone in digitos_texto
            evidencia("telefone", "Telefone do cadastro " + ("aparece" if achou else "não aparece") + " no site", achou)
            pontuacao += _PESOS["telefone"] if achou else 0

    nomes = [n for n in {normalizar(nome_conta), normalizar((registro or {}).get("razao_social")),
                         normalizar((registro or {}).get("nome_fantasia"))} if n]
    nucleos = [n for n in (re.sub(r"\s+", " ", _SUFIXOS_JURIDICOS.sub(" ", n)).strip() for n in nomes) if len(n) >= 5]
    if nucleos:
        achou = any(n in texto_norm for n in nucleos)
        evidencia("nome", "Nome da empresa " + ("aparece" if achou else "não aparece") + " no site (indício fraco, nunca confirma sozinho)", achou)
        pontuacao += _PESOS["nome"] if achou else 0

    if exato or mesma_raiz or pontuacao >= 60:
        situacao = "confirmado"
    elif outros_cnpjs and not exato and not mesma_raiz and pontuacao < 30:
        situacao = "divergente"
        evidencia("cnpj_divergente", f"O site exibe outro CNPJ ({', '.join(sorted(outros_cnpjs))}) e nenhuma prova de que seja a empresa", True)
    elif pontuacao >= 30:
        situacao = "provavel"
    else:
        situacao = "inconclusivo"
    return VerificacaoDominio(situacao, pontuacao, evidencias, limitacoes)


# --- Indicadores financeiros ---------------------------------------------------------------------------------------------

_ROTULOS = {
    "receita_liquida": r"receitas?\s+l[ií]quidas?",
    "receita_bruta": r"receitas?\s+brutas?",
    "lucro_liquido": r"lucro\s+l[ií]quido",
    "ebitda": r"ebitda(?:\s+ajustado)?",
    "divida_liquida": r"d[ií]vida\s+l[ií]quida",
}
_ESCALAS = {"mil": 1e3, "milhao": 1e6, "milhoes": 1e6, "bilhao": 1e9, "bilhoes": 1e9, "trilhao": 1e12, "trilhoes": 1e12}
_VALOR = re.compile(
    r"(?P<moeda>R\$|US\$)\s*(?P<numero>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)\s*(?P<escala>mil(?:h[aã]o|h[oõ]es)?|bilh[aã]o|bilh[oõ]es|trilh[aã]o|trilh[oõ]es)?",
    re.IGNORECASE,
)
_PERIODOS = (
    (re.compile(r"\b([1-4])\s?T\s?(20\d{2}|\d{2})\b", re.IGNORECASE), lambda m: f"{_ano(m.group(2))}-T{m.group(1)}"),
    (re.compile(r"\b([12])\s?S\s?(20\d{2}|\d{2})\b", re.IGNORECASE), lambda m: f"{_ano(m.group(2))}-S{m.group(1)}"),
    (re.compile(r"\b(?:exerc[ií]cio|ano)\s+(?:de\s+|social\s+de\s+)?(20\d{2})\b", re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r"\b(?:em|de|no)\s+(20\d{2})\b", re.IGNORECASE), lambda m: m.group(1)),
)
_JANELA_ROTULO_VALOR = 90  # caracteres entre o nome do indicador e o valor
_JANELA_PERIODO = 140


def _ano(texto: str) -> str:
    return texto if len(texto) == 4 else f"20{texto}"


@dataclass
class IndicadorExtraido:
    nome: str
    valor_original: str
    valor: float
    moeda: str
    escala: str
    periodo: str | None
    trecho: str
    url: str
    confianca: str  # alta: período no mesmo trecho; baixa: período não identificado
    tipo: str = "publicado"
    formula: str | None = None
    origens: list[str] = field(default_factory=list)
    metodo: str = "regex_deterministico_v1"


def _periodo_proximo(texto: str, inicio: int, fim: int) -> str | None:
    """Período mencionado MAIS PRÓXIMO do indicador (não o primeiro da janela): duas frases vizinhas com anos diferentes não
    podem trocar o período uma da outra. Empate: vale o padrão mais específico (trimestre/semestre antes de ano solto)."""
    base = max(0, inicio - _JANELA_PERIODO)
    janela = texto[base: fim + _JANELA_PERIODO]
    melhor: tuple[int, int, str] | None = None
    for prioridade, (regex, formatar) in enumerate(_PERIODOS):
        for achado in regex.finditer(janela):
            distancia = abs(base + achado.start() - inicio)
            if melhor is None or (distancia, prioridade) < melhor[:2]:
                melhor = (distancia, prioridade, formatar(achado))
    return melhor[2] if melhor else None


def extrair_indicadores(paginas: list[Pagina]) -> list[IndicadorExtraido]:
    """Só valores escritos com moeda explícita ao lado do rótulo do indicador. Nada é inferido."""
    achados: list[IndicadorExtraido] = []
    vistos: set[tuple] = set()
    for url, texto in paginas:
        for nome, rotulo in _ROTULOS.items():
            for m_rotulo in re.finditer(rotulo, texto, re.IGNORECASE):
                trecho_valor = texto[m_rotulo.end(): m_rotulo.end() + _JANELA_ROTULO_VALOR]
                m_valor = _VALOR.search(trecho_valor)
                if not m_valor:
                    continue
                numero = float(m_valor.group("numero").replace(".", "").replace(",", "."))
                escala_txt = normalizar(m_valor.group("escala") or "")
                escala_txt = escala_txt if escala_txt in _ESCALAS else ""
                fator = _ESCALAS.get(escala_txt, 1.0)
                inicio, fim = m_rotulo.start(), m_rotulo.end() + m_valor.end()
                periodo = _periodo_proximo(texto, inicio, fim)
                moeda = "BRL" if m_valor.group("moeda").upper() == "R$" else "USD"
                chave = (url, nome, round(numero * fator, 2), moeda, periodo)
                if chave in vistos:
                    continue
                vistos.add(chave)
                achados.append(IndicadorExtraido(
                    nome=nome, valor_original=re.sub(r"\s+", " ", m_valor.group(0)).strip(), valor=numero * fator, moeda=moeda,
                    escala=escala_txt or "unidade", periodo=periodo, trecho=re.sub(r"\s+", " ", texto[max(0, inicio - 40): fim + 40]).strip(),
                    url=url, confianca="alta" if periodo else "baixa",
                ))
    return achados


def derivar_indicadores(publicados: list[IndicadorExtraido]) -> list[IndicadorExtraido]:
    """Margem líquida = lucro líquido ÷ receita líquida × 100, só quando ambos vêm da MESMA página, do MESMO período
    identificado e da MESMA moeda. Qualquer outra combinação não é calculada."""
    derivados: list[IndicadorExtraido] = []
    receitas = {(i.url, i.periodo, i.moeda): i for i in publicados if i.nome == "receita_liquida" and i.periodo}
    for lucro in (i for i in publicados if i.nome == "lucro_liquido" and i.periodo):
        receita = receitas.get((lucro.url, lucro.periodo, lucro.moeda))
        if receita is None or receita.valor == 0:
            continue
        derivados.append(IndicadorExtraido(
            nome="margem_liquida_pct", valor_original=f"{lucro.valor / receita.valor * 100:.2f}%",
            valor=round(lucro.valor / receita.valor * 100, 4), moeda="%", escala="percentual", periodo=lucro.periodo,
            trecho=f"lucro líquido {lucro.valor_original} ÷ receita líquida {receita.valor_original}", url=lucro.url,
            confianca="alta", tipo="derivado",
            formula="lucro_liquido / receita_liquida × 100", origens=[lucro.trecho, receita.trecho], metodo="formula_v1",
        ))
    return derivados
