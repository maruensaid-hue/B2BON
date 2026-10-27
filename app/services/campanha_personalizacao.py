"""Marcadores de personalização do texto de campanha: `[Nome]` (primeiro nome), `[Nome completo]` e `[Empresa]`, trocados pelos dados de cada
destinatário na hora do envio. Sem o nome, o marcador some e a saudação fica só com a pontuação ("Olá, [Nome]," vira "Olá!"); sem a empresa, entra
"a sua empresa". Maiúsculas/minúsculas e espaços dentro dos colchetes não importam."""

import re

EMPRESA_PADRAO = "a sua empresa"

_TRATAMENTOS = {"dr", "dra", "sr", "sra", "srta", "prof", "profa", "eng"}

_NOME_COMPLETO = r"\[\s*nome\s+completo\s*\]"
_NOME = r"\[\s*nome\s*\]"
_EMPRESA = re.compile(r"\[\s*empresa\s*\]", re.IGNORECASE)


def primeiro_nome(nome_completo: str | None) -> str:
    """Primeiro nome sem tratamento ("Dra. maria silva" → "Maria"); nomes todo em maiúsculas ou minúsculas ganham inicial maiúscula."""
    for parte in (nome_completo or "").split():
        if parte.strip(".").lower() in _TRATAMENTOS:
            continue
        return parte.capitalize() if parte.isupper() or parte.islower() else parte
    return ""


def _sem_nome(m: re.Match[str]) -> str:
    texto = m.string
    antes_vazio = m.start() == 0 or texto[m.start() - 1] == "\n"
    depois = texto[m.end():]
    resto = depois.lstrip(" \t")
    if antes_vazio and not m.group("antes").strip(" \t,"):
        return ""  # o marcador abria a linha: não sobra nada para pontuar
    if m.group("virgula"):
        return "!"  # "Olá, [Nome], tudo bem?" → "Olá! tudo bem?"
    if resto[:1] in ("!", "?", ".", ":", ";"):
        return ""  # "Olá, [Nome]!" → "Olá!"
    if resto == "" or resto[0] in "\r\n":
        return "!"  # "Olá, [Nome]" no fim da linha → "Olá!"
    return ""  # no meio da frase: o espaço que já vem depois do marcador separa as palavras


def _trocar_nome(texto: str, padrao: str, valor: str) -> str:
    if valor:
        return re.sub(padrao, lambda _m: valor, texto, flags=re.IGNORECASE)
    ausente = re.compile(rf"(?P<antes>[ \t]*,?[ \t]*){padrao}(?:[ \t]*(?P<virgula>,))?", re.IGNORECASE)
    return ausente.sub(_sem_nome, texto)


def renderizar(texto: str | None, nome_completo: str | None, empresa: str | None) -> str:
    resultado = texto or ""
    resultado = _trocar_nome(resultado, _NOME_COMPLETO, (nome_completo or "").strip())
    resultado = _trocar_nome(resultado, _NOME, primeiro_nome(nome_completo))
    return _EMPRESA.sub(lambda _m: (empresa or "").strip() or EMPRESA_PADRAO, resultado)
