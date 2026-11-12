"""SEO e palavras-chave da oferta como matéria-prima das mensagens.

Dois campos opcionais da Inteligência de Oferta:

* `palavras_chave`: os termos que o público desse perfil usa ao procurar esse tipo de solução (a primeira é a principal);
* `seo_titulo` e `seo_descricao`: como a oferta é posicionada para busca (título curto e descrição de uma frase).

Eles entram no prompt de toda mensagem escrita pela IA (cadência, resposta comercial e amostra de comunicação) como VOCABULÁRIO: dizem qual assunto e quais
expressões usar, nunca fatos sobre a empresa da pessoa (isso continua vindo só dos fatos verificados). Sem nenhum dos campos preenchidos, o trecho é vazio e o
prompt fica exatamente como antes.

Duas proteções: palavra-chave que contém um termo das restrições do tenant ("Nunca mencione") não vai ao prompt (senão a IA receberia uma ordem e a
proibição ao mesmo tempo, e a mensagem seria descartada na validação); e o WhatsApp sem modelo (categoria utilidade da Meta, sem promoção) não recebe o trecho.
"""

import re
from collections.abc import Iterable
from typing import Any

LIMITE_PALAVRAS_CHAVE = 15
TAMANHO_MAXIMO_PALAVRA_CHAVE = 60
TAMANHO_MAXIMO_SEO_TITULO = 70  # o que a busca costuma mostrar de um título sem cortar
TAMANHO_MAXIMO_SEO_DESCRICAO = 200  # a descrição mostrada na busca fica em torno de 160; folga para a frase não ser cortada no meio


def normalizar_palavras_chave(valores: Iterable[Any] | None) -> list[str]:
    """Tira espaços e vazios, junta espaços repetidos e remove repetidas (sem diferenciar maiúsculas), mantendo a ordem: a primeira é a principal."""
    vistas: set[str] = set()
    limpas: list[str] = []
    for valor in valores or []:
        palavra = re.sub(r"\s+", " ", str(valor)).strip()
        if palavra and palavra.casefold() not in vistas:
            vistas.add(palavra.casefold())
            limpas.append(palavra)
    return limpas


def palavras_chave_permitidas(oferta: Any, restricoes: Iterable[str] | None) -> list[str]:
    proibidos = [r.casefold() for r in (restricoes or []) if r and r.strip()]
    return [p for p in normalizar_palavras_chave(getattr(oferta, "palavras_chave", None)) if not any(r in p.casefold() for r in proibidos)]


def trecho_prompt(oferta: Any, restricoes: Iterable[str] | None = None, *, canal: str | None = None) -> str:
    """Trecho pronto para entrar no prompt (começa com espaço, termina com ponto) ou vazio. `canal` só afina a orientação do e-mail (assunto)."""
    palavras = palavras_chave_permitidas(oferta, restricoes)
    titulo = (getattr(oferta, "seo_titulo", None) or "").strip()
    descricao = (getattr(oferta, "seo_descricao", None) or "").strip()
    partes: list[str] = []
    if palavras:
        partes.append(
            f" Palavras-chave da oferta (termos que o público desse perfil usa ao procurar esse tipo de solução; a primeira é a principal): "
            f"{', '.join(palavras)}. Use de uma a três delas, de forma natural e só quando fizerem sentido; nunca force, repita nem liste "
            "palavras-chave. Elas dizem sobre o que é a oferta, não são fatos sobre a empresa da pessoa."
        )
        if canal == "email":
            partes.append(" No assunto do e-mail, prefira a palavra-chave principal quando couber naturalmente, sem cara de propaganda.")
    if titulo or descricao:
        posicionamento = "; ".join(p for p in (f"título '{titulo}'" if titulo else "", f"descrição '{descricao}'" if descricao else "") if p)
        partes.append(f" Posicionamento da oferta para busca (referência de vocabulário e de proposta de valor; não copie literalmente): {posicionamento}.")
    return "".join(partes)
