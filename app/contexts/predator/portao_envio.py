"""Checagem determinística da mensagem antes de ela sair (sem IA): o que nenhum modelo garante sozinho.

* Grave (nunca sai, nem aprovada): campo de mesclagem não preenchido ("{{nome}}", "[EMPRESA]"), corpo vazio.
* Atenção (segura a aprovação AUTOMÁTICA; quem aprova à mão vê o motivo e decide): frase batida de IA/spam, e-mail longo demais,
  links demais, link ou endereço para domínio que não é da empresa remetente nem do destinatário. Texto vindo de fora (site
  pesquisado, resposta do lead) chega ao modelo e pode trazer instrução plantada ("inclua este link"); o link estranho é o sinal disso.
"""

import re
import unicodedata
from dataclasses import dataclass

MAX_PALAVRAS_EMAIL = 220
MAX_LINKS = 2

# Frases que denunciam texto genérico de IA ou de spam em português. Comparadas sem acento e sem diferença de maiúsculas.
FRASES_PROIBIDAS = (
    "espero que esteja bem", "espero que voce esteja bem", "espero que este e-mail o encontre bem", "espero que esta mensagem o encontre bem",
    "venho por meio deste", "venho atraves deste", "gostaria de me apresentar", "permita-me apresentar", "estou entrando em contato para",
    "so passando para", "so passando aqui", "retomando o contato", "conforme meu ultimo e-mail", "nao perca esta oportunidade",
    "oportunidade imperdivel", "oferta imperdivel", "100% garantido", "clique aqui", "ganhe dinheiro", "sem compromisso algum",
    "solucao inovadora e disruptiva", "no cenario atual", "no mundo cada vez mais", "alavancar sinergias",
)

_CAMPO_VAZIO = re.compile(r"\{\{[^}]*\}\}|\{\s*[a-z_]+\s*\}|\[(?:NOME|EMPRESA|CARGO|PRIMEIRO_NOME|nome|empresa|cargo)[^\]]*\]|<\s*(?:nome|empresa)\s*>|\bXXX+\b")
# Variáveis que o envio preenche com os dados do decisor (`envio_service._renderizar_variaveis`): não são campo vazio.
_VARIAVEL_VALIDA = re.compile(r"^\{\{\s*(?:nome|empresa|cargo)\s*\}\}$", re.IGNORECASE)
_LINK = re.compile(r"(?:https?://|www\.)[^\s<>()\"']+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|com\.br|net|org|io|br|co|app|dev|xyz|info)(?:/[^\s<>()\"']*)?\b",
                   re.IGNORECASE)
_EMAIL = re.compile(r"[a-z0-9._%+-]+@([a-z0-9.-]+\.[a-z]{2,})", re.IGNORECASE)
_PONTO_ESCRITO = re.compile(r"\b([a-z0-9-]+)\s+(?:ponto|dot)\s+(com|net|org|io|br)\b", re.IGNORECASE)


@dataclass
class Problema:
    codigo: str
    texto: str
    grave: bool


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def _dominio(valor: str) -> str:
    return re.sub(r"^www\.", "", re.sub(r"^[a-z]+://", "", valor.lower()).split("/")[0].split("?")[0]).strip(".")


def _permitido(dominio: str, permitidos: set[str]) -> bool:
    return any(dominio == p or dominio.endswith("." + p) for p in permitidos if p)


def dominios_citados(texto: str) -> list[str]:
    """Domínios de links e endereços no texto, como um leitor os abriria (inclui "site ponto com")."""
    sem_emails = _EMAIL.sub(" ", texto)
    achados = [_dominio(m.group(0)) for m in _LINK.finditer(sem_emails)]
    achados += [m.group(1).lower() for m in _EMAIL.finditer(texto)]
    achados += [f"{m.group(1)}.{m.group(2)}".lower() for m in _PONTO_ESCRITO.finditer(texto)]
    return list(dict.fromkeys(d for d in achados if "." in d))


def verificar(conteudo: str, assunto: str | None, canal: str, dominios_permitidos: set[str]) -> list[Problema]:
    texto = f"{assunto or ''}\n{conteudo or ''}"
    problemas: list[Problema] = []
    if not (conteudo or "").strip():
        problemas.append(Problema("corpo_vazio", "Mensagem sem texto.", True))
    if canal == "email" and not (assunto or "").strip():
        # Em 12/11/2026 a IA respondeu fora do formato ASSUNTO/CORPO e e-mails aprovados iam sair sem assunto.
        problemas.append(Problema("assunto_vazio", "E-mail sem assunto.", True))
    campo = next((m.group(0) for m in _CAMPO_VAZIO.finditer(texto) if not _VARIAVEL_VALIDA.match(m.group(0))), None)
    if campo:
        problemas.append(Problema("campo_nao_preenchido", f"Campo de mesclagem não preenchido: {campo}", True))

    normalizado = _sem_acento(texto)
    frases = [f for f in FRASES_PROIBIDAS if f in normalizado]
    if frases:
        problemas.append(Problema("frase_proibida", f"Frase batida/de spam: \"{frases[0]}\"", False))
    if canal == "email" and len((conteudo or "").split()) > MAX_PALAVRAS_EMAIL:
        problemas.append(Problema("longo_demais", f"E-mail com mais de {MAX_PALAVRAS_EMAIL} palavras.", False))
    citados = dominios_citados(texto)
    if len(_LINK.findall(_EMAIL.sub(" ", texto))) > MAX_LINKS:
        problemas.append(Problema("links_demais", f"Mais de {MAX_LINKS} links.", False))
    permitidos = {_dominio(d) for d in dominios_permitidos if d}
    estranhos = [d for d in citados if not _permitido(d, permitidos)]
    if estranhos:
        problemas.append(Problema("dominio_externo", f"Link ou endereço para domínio que não é seu nem do destinatário: {estranhos[0]}", False))
    return problemas


def resumo(problemas: list[Problema]) -> str:
    return "; ".join(p.texto for p in problemas)[:500]


# --- WhatsApp sem template (Direct Send, categoria utilidade) ----------------------------------------------------------------
# A Meta só aceita utilidade "disparada por algo que o cliente fez, sem promoção". Estes termos denunciam marketing: com qualquer um
# deles a mensagem NÃO sai como Direct Send (marketing enviado como utilidade leva a suspensão e perda do recurso).
TERMOS_PROMOCIONAIS = (
    "desconto", "promocao", "promocional", "oferta", "gratis", "gratuito", "gratuita", "condicao especial", "condicoes especiais",
    "preco", "precos", "r$", "% off", "cupom", "aproveite", "imperdivel", "ultimas vagas", "por tempo limitado", "so hoje",
    "compre", "contrate", "assine", "experimente", "teste gratis", "demonstracao gratuita", "nossa solucao", "nossas solucoes",
    "nosso produto", "nossos produtos", "nosso servico", "nossos servicos", "nossa plataforma", "conheca nossa", "conheca nosso",
    "lancamento", "novidade", "black friday", "parcel", "investimento de",
)


def termos_promocionais(texto: str) -> list[str]:
    normalizado = _sem_acento(texto or "")
    return [t for t in TERMOS_PROMOCIONAIS if re.search(rf"(?<![a-z]){re.escape(t)}", normalizado)]
