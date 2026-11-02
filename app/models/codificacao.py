"""Conserta, na gravação, nome de empresa e de contato que chegam com a codificação trocada ("QuÃ©bec" no lugar de "Québec").

Importações de planilha e de CSV (conexões do LinkedIn, listas de prospecção, contatos) trazem esse defeito quando o arquivo passou por um programa que leu UTF-8 como
Latin-1. Em vez de lembrar de corrigir em cada caminho de entrada, o conserto roda no `before_insert` e no `before_update` dos dois modelos. É o mesmo
`corrigir_codificacao` das campanhas: só age quando o texto tem a marca típica da troca e o resultado é UTF-8 válido, então "SÃO PAULO" e "José" passam intactos.
"""

from sqlalchemy import event

from app.core.texto import corrigir_codificacao
from app.models.conta import Conta
from app.models.decisor import Decisor

# Só os campos curtos de identificação; texto livre (observações, resumo do site) não é mexido.
CAMPOS_CORRIGIDOS: dict[type, tuple[str, ...]] = {
    Conta: ("nome", "nome_fantasia", "segmento", "regiao"),
    Decisor: ("nome", "cargo"),
}


def _corrigir(_mapper, _conexao, alvo) -> None:
    for campo in CAMPOS_CORRIGIDOS[type(alvo)]:
        valor = getattr(alvo, campo)
        if isinstance(valor, str):
            corrigido = corrigir_codificacao(valor)
            if corrigido != valor:
                setattr(alvo, campo, corrigido)


def aplicar() -> None:
    for modelo in CAMPOS_CORRIGIDOS:
        event.listen(modelo, "before_insert", _corrigir)
        event.listen(modelo, "before_update", _corrigir)
