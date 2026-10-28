"""Conserta texto colado de planilha com a codificação trocada ("JoÃ£o" no lugar de "João").

Acontece quando um arquivo UTF-8 é aberto como Latin-1/Windows-1252 e o texto é copiado dali: cada letra acentuada vira duas ou três. O conserto é o caminho
inverso (cada caractere volta ao byte original e os bytes são lidos como UTF-8) e só vale quando o texto tem a marca típica da troca e o resultado é UTF-8
válido; qualquer outra coisa ("SÃO PAULO", "CÂMBIO", "José") passa intacta.
"""

import re

# Caracteres que o Windows-1252 coloca nas posições 0x80–0x9F, onde o Latin-1 tem controles.
_CP1252 = {
    "€": 0x80, "‚": 0x82, "ƒ": 0x83, "„": 0x84, "…": 0x85, "†": 0x86, "‡": 0x87, "ˆ": 0x88, "‰": 0x89, "Š": 0x8A, "‹": 0x8B, "Œ": 0x8C, "Ž": 0x8E,
    "‘": 0x91, "’": 0x92, "“": 0x93, "”": 0x94, "•": 0x95, "–": 0x96, "—": 0x97, "˜": 0x98, "™": 0x99, "š": 0x9A, "›": 0x9B, "œ": 0x9C, "ž": 0x9E, "Ÿ": 0x9F,
}

# "Ã" ou "Â" seguidos de um caractere da faixa 0x80–0xBF (inclusive os do Windows-1252), "â€" (aspas e travessões) e "ðŸ" (emojis).
_MARCA = re.compile("[ÃÂ][\u0080-¿" + "".join(_CP1252) + "]|â€|ðŸ")


def corrigir_codificacao(texto: str | None) -> str | None:
    """Desfaz a troca de codificação ("JoÃ£o" vira "João") quando o texto tem a marca típica e o resultado é UTF-8 válido; qualquer outro texto volta intacto."""
    if not texto or not _MARCA.search(texto):
        return texto
    octetos = bytearray()
    for caractere in texto:
        if caractere in _CP1252:
            octetos.append(_CP1252[caractere])
        elif ord(caractere) < 256:
            octetos.append(ord(caractere))
        else:
            return texto  # tem caractere que não veio dessa troca: não arrisca
    try:
        corrigido = octetos.decode("utf-8")
    except UnicodeDecodeError:
        return texto  # byte perdido na cópia (ex.: invisível): deixa como veio
    return corrigido if len(corrigido) < len(texto) else texto
