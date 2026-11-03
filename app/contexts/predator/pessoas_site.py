"""Pessoas e e-mails lidos no próprio site da empresa, sem IA e sem provedor pago.

* `pessoas`: quem o site nomeia com cargo de decisão — linhas "Nome Sobrenome — CEO", nome com o cargo na linha seguinte, e frases
  como "fundada por Nome Sobrenome". Dono (fundador, sócio, proprietário, CEO, presidente) vem primeiro. Palavra comum com inicial
  maiúscula ("Nossa Equipe", "Fale Conosco") não é pessoa; depoimento de cliente entre aspas não é da empresa.
* `emails_publicados`: endereços do domínio da empresa escritos no site (inclusive "nome [arroba] dominio [ponto] com").
* `padrao_de` / `aplicar_padrao`: o formato de e-mail da empresa aprendido de um endereço publicado que pertence a uma pessoa nomeada
  ("joao.silva@" ao lado de João Silva = nome.sobrenome). Endereço que duas pessoas poderiam ter não ensina nada.
"""

import re
import unicodedata
from dataclasses import dataclass

_CONECTORES = {"de", "da", "do", "das", "dos", "e"}
_PALAVRA_NOME = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõçü]+(?:-[A-ZÁÉÍÓÚ][a-záéíóúâêôãõç]+)?"
_NOME = rf"{_PALAVRA_NOME}(?:\s+(?:(?:de|da|do|das|dos|e)\s+)?{_PALAVRA_NOME}){{1,4}}"

# Cargo sem distinção de maiúsculas (o nome continua exigindo inicial maiúscula).
_CARGO = (
    r"(?i:CEO|CFO|CTO|COO|CMO|CIO|CISO|CRO|"
    r"(?:co-?)?fundador[a]?(?:\s+e\s+CEO)?|s[óo]ci[oa](?:[\s-]+(?:fundador[a]?|diretor[a]?|administrador[a]?|propriet[áa]ri[oa]|gerente))?|"
    r"propriet[áa]ri[oa]|presidente|vice-presidente|superintendente|"
    r"diretor[a]?(?:[\s-]+(?:executiv[oa]|geral|presidente|comercial|financeir[oa]|de\s+\w+|\w+))?|"
    r"gerente(?:\s+(?:geral|comercial|de\s+\w+|\w+))?|head(?:\s+(?:de|of)\s+\w+)?|"
    r"managing\s+partner|partner)"
)
_RE_CARGO = re.compile(rf"^\s*{_CARGO}\b", re.IGNORECASE)
_DONO = re.compile(r"\b(ceo|fundador|fundadora|cofundador|cofundadora|co-fundador|co-fundadora|s[óo]ci[oa]|propriet[áa]ri[oa]|presidente)\b", re.IGNORECASE)
_VICE_OU_EX = re.compile(r"\b(vice|ex-|ex\s|antig[oa]|falecid[oa])", re.IGNORECASE)

_MESMA_LINHA = re.compile(rf"^\s*(?P<nome>{_NOME})\s*(?:[,–—|:-]|\(|\s{{2,}})\s*(?P<cargo>{_CARGO}[^\n()]*)\)?\s*$")
_CARGO_ANTES = re.compile(rf"^\s*(?P<cargo>{_CARGO})\s*[:–—-]\s*(?P<nome>{_NOME})\s*$")
_PROSA = re.compile(
    rf"(?:(?i:fundad[ao])\s+(?:em\s+\d{{4}}\s+)?por|criad[ao]\s+por|liderad[ao]\s+por|comandad[ao]\s+por|"
    rf"(?P<cargo>(?:noss[oa]\s+)?(?:CEO|fundador[a]?|s[óo]ci[oa]-fundador[a]?|presidente|diretor[a]?(?:-geral| executiv[oa])?))\s*,?)\s+(?P<nome>{_NOME})"
)

# Palavras que começam com maiúscula em títulos e menus, mas não são nome de gente.
_NAO_NOME = {
    "nossa", "nosso", "equipe", "time", "sobre", "contato", "fale", "conosco", "conheça", "missão", "visão", "valores", "diretoria",
    "empresa", "grupo", "serviços", "soluções", "clientes", "parceiros", "home", "blog", "notícias", "política", "privacidade",
    "termos", "trabalhe", "vagas", "carreiras", "todos", "direitos", "reservados", "brasil", "são", "paulo", "rio", "janeiro",
    "ltda", "s.a", "atendimento", "suporte", "comercial", "financeiro", "jurídico", "unidade", "matriz", "filial", "leia", "mais",
}


@dataclass
class PessoaSite:
    nome: str
    cargo: str
    dono: bool
    url: str
    trecho: str


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def _nome_plausivel(nome: str) -> bool:
    palavras = nome.split()
    significativas = [p for p in palavras if p.lower() not in _CONECTORES]
    if len(significativas) < 2:
        return False
    return not any(p.lower() in _NAO_NOME for p in palavras)


def _limpar_cargo(cargo: str) -> str:
    return re.sub(r"\s+", " ", cargo).strip(" .,;:-–—")[:80]


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def _entre_aspas(linha: str) -> bool:
    return bool(re.search(r"[\"“”]", linha))


def pessoas(paginas: list[tuple[str, str]], limite: int = 3) -> list[PessoaSite]:
    """Pessoas com cargo de decisão nomeadas no site, sem repetição (por nome), dono primeiro, no máximo `limite`."""
    achadas: dict[str, PessoaSite] = {}

    def anotar(nome: str, cargo: str, url: str, trecho: str) -> None:
        nome = re.sub(r"\s+", " ", nome).strip()
        cargo = _limpar_cargo(cargo)
        if not _nome_plausivel(nome) or not cargo or _VICE_OU_EX.search(cargo) and not cargo.lower().startswith("vice-presidente"):
            return
        chave = _sem_acento(nome)
        if chave not in achadas:
            dono = bool(_DONO.search(cargo)) and not _VICE_OU_EX.search(cargo)
            achadas[chave] = PessoaSite(nome=nome, cargo=cargo, dono=dono, url=url, trecho=trecho[:200])

    for url, texto in paginas:
        linhas = _linhas(texto)
        for i, linha in enumerate(linhas):
            if _entre_aspas(linha):
                continue  # depoimento: quem fala ali costuma ser cliente, não a empresa
            if len(linha) <= 160:
                if m := _MESMA_LINHA.match(linha) or _CARGO_ANTES.match(linha):
                    anotar(m.group("nome"), m.group("cargo"), url, linha)
                    continue
                proxima = linhas[i + 1] if i + 1 < len(linhas) else ""
                if re.fullmatch(_NOME, linha) and _RE_CARGO.match(proxima) and len(proxima) <= 80:
                    anotar(linha, proxima, url, f"{linha} / {proxima}")
                    continue
            for m in _PROSA.finditer(linha):
                cargo = m.group("cargo") or "Fundador(a)"
                anotar(m.group("nome"), re.sub(r"^noss[oa]\s+", "", cargo, flags=re.IGNORECASE), url, m.group(0))

    ordenadas = sorted(achadas.values(), key=lambda p: (not p.dono))
    return ordenadas[:limite]


# --- E-mails --------------------------------------------------------------------------------------------------------------

_EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
_EMAIL_OFUSCADO = re.compile(
    r"([a-z0-9][a-z0-9._-]*)\s*[\[(]\s*(?:at|arroba)\s*[\])]\s*([a-z0-9-]+(?:\s*[\[(]\s*(?:dot|ponto)\s*[\])]\s*[a-z0-9-]+)+)",
    re.IGNORECASE,
)


def _dominio_base(dominio: str) -> str:
    return re.sub(r"^www\.", "", re.sub(r"^[a-z]+://", "", dominio.lower()).split("/")[0])


def emails_publicados(paginas: list[tuple[str, str]], dominio: str) -> list[str]:
    """Endereços do domínio da empresa (ou de subdomínio dele) escritos no site, em ordem de aparição."""
    base = _dominio_base(dominio)
    vistos: list[str] = []
    for _url, texto in paginas:
        candidatos = [m.group(0) for m in _EMAIL.finditer(texto)]
        for m in _EMAIL_OFUSCADO.finditer(texto):
            dominio_ofuscado = re.sub(r"\s*[\[(]\s*(?:dot|ponto)\s*[\])]\s*", ".", m.group(2), flags=re.IGNORECASE)
            candidatos.append(f"{m.group(1)}@{dominio_ofuscado}")
        for email in candidatos:
            email = email.lower().rstrip(".")
            dominio_email = email.rsplit("@", 1)[1]
            if (dominio_email == base or dominio_email.endswith("." + base)) and email not in vistos:
                vistos.append(email)
    return vistos


_GENERICOS = re.compile(r"^(contato|comercial|vendas|atendimento|sac|faleconosco|fale|info|ola|oi|hello|suporte|rh|financeiro|"
                        r"administrativo|adm|marketing|diretoria|ouvidoria|lgpd|dpo|privacidade|juridico|compras|noreply|nao-?responda)$")


def generico(email: str) -> bool:
    return bool(_GENERICOS.match(email.split("@", 1)[0]))


def _partes(nome: str) -> tuple[str, str] | None:
    palavras = [re.sub(r"[^a-z]", "", _sem_acento(p)) for p in nome.split() if p.lower() not in _CONECTORES]
    palavras = [p for p in palavras if p]
    return (palavras[0], palavras[-1]) if len(palavras) >= 2 else None


_FORMATOS = ("{n}.{s}", "{n}{s}", "{n}_{s}", "{i}{s}", "{i}.{s}", "{n}", "{s}.{n}", "{n}{i2}")


def _local(formato: str, primeiro: str, ultimo: str) -> str:
    return formato.format(n=primeiro, s=ultimo, i=primeiro[0], i2=ultimo[0])


def padrao_de(email: str, nome: str) -> str | None:
    """Formato do endereço (ex.: "{n}.{s}") se ele é desta pessoa; senão `None`."""
    partes = _partes(nome)
    if partes is None:
        return None
    local = email.split("@", 1)[0].lower()
    for formato in _FORMATOS:
        if _local(formato, *partes) == local:
            return formato
    return None


def dono_do_email(email: str, nomes: list[str]) -> str | None:
    """A pessoa nomeada a quem o endereço pertence, se for exatamente uma."""
    donos = [nome for nome in nomes if padrao_de(email, nome) is not None]
    return donos[0] if len(donos) == 1 else None


def aprender_padrao(emails: list[str], nomes_do_site: list[str]) -> str | None:
    """Formato da empresa a partir de endereços publicados de pessoas nomeadas. Formato de um nome só ("{n}") só vale se nenhum outro
    endereço contradiz; endereços de pessoas diferentes que discordam deixam o padrão indefinido."""
    formatos = {padrao_de(e, dono) for e in emails if not generico(e) and (dono := dono_do_email(e, nomes_do_site))}
    formatos.discard(None)
    return formatos.pop() if len(formatos) == 1 else None


def aplicar_padrao(formato: str, nome: str, dominio: str) -> str | None:
    partes = _partes(nome)
    return f"{_local(formato, *partes)}@{_dominio_base(dominio)}" if partes else None
