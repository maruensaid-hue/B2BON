"""Pedido de descadastro escrito na RESPOSTA do lead (e-mail ou WhatsApp), em português, sem IA.

O link assinado do rodapé continua valendo; isto cobre quem só responde "SAIR" ou "me tire da lista". Opt-out é imediato e permanente.
* Pedido explícito vale em qualquer ponto da resposta ("Por favor, parem de me enviar e-mails").
* Recusa curta ("Não tenho interesse.", "Não, obrigado") só vale dita sozinha: "não tenho interesse agora, me procure em março" é
  conversa, não descadastro.
* O texto citado do nosso próprio e-mail (linhas com ">" e o que vem depois de "Em ... escreveu:") é descartado antes: citar o rodapé
  não é pedir para sair.
* Ameaça jurídica ou reclamação ("Procon", "meu advogado", "denúncia de spam") também vai para um humano, sem resposta automática.
"""

import re
import unicodedata
from dataclasses import dataclass

_PALAVRA_SOZINHA = {"sair", "parar", "pare", "stop", "cancelar", "descadastrar", "remover", "unsubscribe", "remova", "chega"}

_EXPLICITO = re.compile(
    r"\b(?:me\s+(?:tire|tira|retire|remova|exclua|descadastre)|(?:tire|tirem|retire|retirem|remova|removam|exclua|excluam)\s+(?:o\s+)?(?:meu|meus|este|esse|nosso)\b"
    r"|(?:pare|parem|para\s+de|deixe|deixem)\s+(?:de\s+)?(?:me\s+)?(?:enviar|mandar|escrever|ligar|contatar|procurar)"
    r"|nao\s+(?:quero|desejo|gostaria\s+de)\s+(?:mais\s+)?receber|nao\s+(?:me\s+)?(?:envie|enviem|mande|mandem|escreva|escrevam|contate|procure)\s*(?:mais|novamente)"
    r"|nao\s+entr(?:e|em)\s+mais\s+em\s+contato|descadastr(?:e|ar|em)|cancel(?:e|ar)\s+(?:minha\s+)?inscricao|remover\s+da\s+lista|sair\s+da\s+lista)"
)
_RECUSA_CURTA = re.compile(r"^(?:nao\s+tenho\s+interesse|sem\s+interesse|nao\s+temos\s+interesse|nao\s*,?\s*obrigad[oa]|nao\s+obrigad[oa]|nao\s+me\s+interessa)$")
_JURIDICO = re.compile(r"\b(?:procon|advogad[oa]|juridico|processar|processo\s+judicial|denuncia|denunciar|anpd|reclame\s+aqui|lgpd\s+art|spam)\b")
_CITACAO = re.compile(r"^\s*(?:em\s.+escreveu:|on\s.+wrote:|-{2,}\s*mensagem\s+original|de:\s.+@)", re.IGNORECASE)
_SAUDACOES = re.compile(r"^(?:ola|oi|bom\s+dia|boa\s+tarde|boa\s+noite|prezad[oa]s?|caro|cara)\b[^\n]*$|^(?:obrigad[oa]|att|atenciosamente|abs|abracos)[.,!]*$")


@dataclass
class Leitura:
    optout: bool
    trecho: str | None
    escalar: bool  # ameaça jurídica/reclamação: um humano precisa ver


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[ \t]+", " ", sem_acento)


def _texto_proprio(texto: str) -> str:
    """Só o que a pessoa escreveu: corta a partir da primeira linha de citação."""
    linhas = []
    for linha in (texto or "").splitlines():
        if _CITACAO.match(linha):
            break
        if linha.lstrip().startswith(">"):
            continue
        linhas.append(linha)
    return "\n".join(linhas)


def ler(texto: str) -> Leitura:
    proprio = _normalizar(_texto_proprio(texto))
    escalar = bool(_JURIDICO.search(proprio))
    nucleo = [l.strip(" .!,;") for l in proprio.splitlines() if l.strip() and not _SAUDACOES.match(l.strip())]
    junto = " ".join(nucleo).strip(" .!,;")
    if junto in _PALAVRA_SOZINHA:
        return Leitura(True, junto, escalar)
    if m := _EXPLICITO.search(proprio):
        return Leitura(True, m.group(0), escalar)
    if _RECUSA_CURTA.match(junto):
        return Leitura(True, junto, escalar)
    return Leitura(False, None, escalar)
