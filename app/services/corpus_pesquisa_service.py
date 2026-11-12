"""Corpus anonimizado de mensagens de prospecção para pesquisa (avaliação de afirmações sem lastro).

SOMENTE LEITURA: nada aqui grava, atualiza ou apaga dado. Cada linha do corpus descreve UMA mensagem gerada: o texto (com identificadores trocados
por marcadores), o que o vendedor decidiu, o perfil da empresa sem identificá-la e as evidências que existiam sobre a conta.

Anonimização (substituição por marcadores, sem manter o dado original no arquivo):
  * nomes do contato e da empresa (inteiros e por partes), CNPJ, domínio, e-mails, telefones e endereços da web conhecidos da conta;
  * além desses, qualquer e-mail, telefone, CNPJ e URL que apareça no texto, mesmo que não conste do cadastro.
LIMITE CONHECIDO: um nome de terceiro que não esteja no cadastro da conta (por exemplo, outra pessoa citada no texto) NÃO é detectado. Por isso a
exportação oferece uma amostra de revisão manual e o arquivo só deve sair da empresa depois dessa revisão.

Referências (`msg_0001`, `conta_0001`) são sequenciais por exportação e não reversíveis; o mapa para os ids reais é opcional e deve ser guardado à parte.

Sobre a evidência: guarda-se o que EXISTIA sobre a conta (sinais com fonte, trecho, confiança e data de observação). O texto de cada página do site é
sobrescrito a cada coleta, então o que a IA viu na hora da geração só é reconstruível para os sinais (que têm histórico); para as páginas, o corpus
informa a data da última coleta e se ela é posterior à mensagem.
"""

import re
import unicodedata
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.aprovacao import Aprovacao
from app.models.auditoria import AuditLog
from app.models.conta import Conta
from app.models.conteudo_pagina_site import ConteudoPaginaSite
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.sinal_conta import SinalConta

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_JUNTAR_MARCADORES = re.compile(r"(\[(?:PESSOA|EMPRESA)\])(?:\s+\1)+")
_TELEFONE = re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\d)")

# Partes de nome que não identificam ninguém e que, trocadas, estragariam o texto.
_PALAVRAS_COMUNS = frozenset({
    "ltda", "eireli", "epp", "sa", "me", "mei", "de", "da", "do", "das", "dos", "e", "em", "para", "com", "grupo", "empresa", "empresas",
    "comercio", "servicos", "servico", "industria", "consultoria", "tecnologia", "solucoes", "brasil", "brasileira", "sistemas", "digital",
    "associados", "participacoes", "holding", "company", "the", "and",
})

DECISOES = ("aprovada_sem_edicao", "aprovada_apos_edicao", "rejeitada_pelo_vendedor", "cancelada_sem_decisao_de_conteudo", "pendente")


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _classe_do_caractere(caractere: str) -> str:
    """Casa a letra com ou sem acento (maiúscula ou minúscula) sem depender de normalizar o texto inteiro."""
    base = _sem_acento(caractere)
    if not base.isalpha():
        return re.escape(caractere)
    variantes = {base.lower(), base.upper(), caractere}
    variantes |= {chr(codigo) for codigo in range(0xC0, 0x180) if _sem_acento(chr(codigo)).lower() == base.lower()}
    return "[" + "".join(re.escape(v) for v in sorted(variantes)) + "]"


def _padrao_da_expressao(expressao: str) -> re.Pattern[str]:
    partes = [_classe_do_caractere(c) if not c.isspace() else r"\s+" for c in expressao.strip()]
    return re.compile(r"(?<!\w)" + "".join(partes) + r"(?!\w)")


def _partes_distintivas(nome: str | None) -> list[str]:
    if not nome:
        return []
    partes = [p for p in re.split(r"[\s/&.,;:()\-]+", nome) if len(p) >= 3]
    return [p for p in partes if _sem_acento(p).lower() not in _PALAVRAS_COMUNS]


class Anonimizador:
    """Troca, em um texto, os identificadores CONHECIDOS de uma conta e de um contato, e os padrões de e-mail/telefone/CNPJ/URL."""

    def __init__(self, conta: Conta | None, decisor: Decisor | None) -> None:
        exatos: list[tuple[str, str]] = []
        partes: list[tuple[str, str]] = []
        if decisor is not None:
            exatos.append((decisor.nome or "", "[PESSOA]"))
            partes += [(p, "[PESSOA]") for p in _partes_distintivas(decisor.nome)]
            for campo, marcador in ((decisor.email, "[EMAIL]"), (decisor.telefone, "[TELEFONE]"), (decisor.linkedin_url, "[URL]")):
                exatos.append((campo or "", marcador))
        if conta is not None:
            for nome in (conta.nome, conta.nome_fantasia):
                exatos.append((nome or "", "[EMPRESA]"))
                partes += [(p, "[EMPRESA]") for p in _partes_distintivas(nome)]
            exatos += [(conta.cnpj or "", "[CNPJ]"), (conta.dominio or "", "[DOMINIO]")]
        # Do mais longo para o mais curto: "Maria da Silva" antes de "Silva".
        self._substituicoes = [
            (_padrao_da_expressao(valor), marcador)
            for valor, marcador in sorted([*exatos, *partes], key=lambda par: -len(par[0]))
            if len(valor.strip()) >= 3
        ]

    def __call__(self, texto: str | None) -> str | None:
        if texto is None:
            return None
        resultado = texto
        for padrao, marcador in self._substituicoes:
            resultado = padrao.sub(marcador, resultado)
        for padrao, marcador in ((_EMAIL, "[EMAIL]"), (_URL, "[URL]"), (_CNPJ, "[CNPJ]"), (_TELEFONE, "[TELEFONE]")):
            resultado = padrao.sub(marcador, resultado)
        return _JUNTAR_MARCADORES.sub(r"\1", resultado)  # "João Álvares" vira um marcador só, não dois


def _dia(momento: datetime | None) -> str | None:
    return momento.date().isoformat() if momento else None


def _decisao(aprovacao: Aprovacao | None, editada: bool, rejeicao_humana: bool) -> str:
    """Rejeição SEM evento de rejeição no histórico é limpeza administrativa (cancelamento em massa), não decisão sobre o conteúdo."""
    if aprovacao is None or aprovacao.status == "pendente":
        return "pendente"
    if aprovacao.status == "rejeitado":
        return "rejeitada_pelo_vendedor" if rejeicao_humana else "cancelada_sem_decisao_de_conteudo"
    return "aprovada_apos_edicao" if editada or aprovacao.status == "editado" else "aprovada_sem_edicao"


def _evidencias(db: Session, tenant_id: str, conta_id: int, criada_em: datetime | None, anonimizar: Anonimizador) -> list[dict[str, Any]]:
    sinais = db.query(SinalConta).filter_by(tenant_id=tenant_id, conta_id=conta_id).order_by(SinalConta.observado_em).all()
    return [
        {
            "tipo": "sinal", "codigo": s.codigo, "fonte": s.fonte, "confianca": s.confianca, "valor_num": s.valor_num, "valor_texto": anonimizar(s.valor_texto),
            "trecho": anonimizar(s.trecho), "observado_em": _dia(s.observado_em), "vigente_hoje": bool(s.vigente),
            # Existia quando a mensagem foi gerada? (aproximação: foi observado antes da criação da mensagem)
            "existia_na_geracao": bool(s.observado_em and criada_em and s.observado_em <= criada_em),
        }
        for s in sinais
    ]


def _paginas(db: Session, tenant_id: str, conta_id: int, criada_em: datetime | None) -> dict[str, Any]:
    paginas = db.query(ConteudoPaginaSite).filter_by(tenant_id=tenant_id, conta_id=conta_id).all()
    ultima = max((p.coletado_em for p in paginas if p.coletado_em), default=None)
    return {
        "quantidade": len(paginas), "ultima_coleta": _dia(ultima),
        # O texto da página é sobrescrito a cada coleta: se a última coleta é posterior à mensagem, não dá para saber o que a IA viu.
        "pode_ter_mudado_depois_da_mensagem": bool(ultima and criada_em and ultima > criada_em),
    }


def montar_corpus(db: Session, tenant_id: str, *, desde: date | None = None, ate: date | None = None, limite: int | None = None) -> Iterator[dict[str, Any]]:
    """Uma linha por mensagem do tenant, em ordem de id. Nada é gravado."""
    consulta = db.query(Mensagem).filter(Mensagem.tenant_id == tenant_id).order_by(Mensagem.id)
    if desde:
        consulta = consulta.filter(Mensagem.criado_em >= datetime.combine(desde, datetime.min.time()))
    if ate:
        consulta = consulta.filter(Mensagem.criado_em < datetime.combine(ate, datetime.max.time()))
    if limite:
        consulta = consulta.limit(limite)

    referencias_conta: dict[int, str] = {}
    for posicao, mensagem in enumerate(consulta.all(), start=1):
        decisor = db.get(Decisor, mensagem.decisor_id)
        conta = db.get(Conta, decisor.conta_id) if decisor is not None else None
        anonimizar = Anonimizador(conta, decisor)
        aprovacao = db.query(Aprovacao).filter_by(tenant_id=tenant_id, mensagem_id=mensagem.id).order_by(Aprovacao.id.desc()).first()

        edicao = db.query(AuditLog).filter_by(tenant_id=tenant_id, evento_tipo="mensagem_editada", entidade_tipo="mensagem", entidade_id=mensagem.id).order_by(
            AuditLog.id).first()
        rejeicao = None
        if aprovacao is not None:
            rejeicao = db.query(AuditLog).filter_by(tenant_id=tenant_id, evento_tipo="aprovacao_rejeitada", entidade_id=aprovacao.id).order_by(AuditLog.id).first()

        referencia_conta = referencias_conta.setdefault(conta.id, f"conta_{len(referencias_conta) + 1:04d}") if conta is not None else None
        yield {
            "mensagem_ref": f"msg_{posicao:04d}", "_mensagem_id": mensagem.id, "conta_ref": referencia_conta,
            "canal": mensagem.canal, "variante_ab": mensagem.variante_ab, "status_mensagem": mensagem.status,
            "decisao": _decisao(aprovacao, edicao is not None, rejeicao is not None),
            "criada_em": _dia(mensagem.criado_em), "enviada_em": _dia(mensagem.enviado_em),
            "assunto": anonimizar(mensagem.assunto), "conteudo": anonimizar(mensagem.conteudo),
            "texto_antes_da_edicao": anonimizar((edicao.detalhes or {}).get("conteudo_anterior")) if edicao else None,
            "motivo_da_rejeicao": anonimizar((rejeicao.detalhes or {}).get("motivo")) if rejeicao else None,
            "contexto": {
                "cargo": anonimizar(decisor.cargo) if decisor else None, "segmento": conta.segmento if conta else None, "porte": conta.porte if conta else None,
                "regiao": conta.regiao if conta else None, "origem_da_conta": conta.origem if conta else None,
            },
            "evidencias": _evidencias(db, tenant_id, conta.id, mensagem.criado_em, anonimizar) if conta is not None else [],
            "paginas_do_site": _paginas(db, tenant_id, conta.id, mensagem.criado_em) if conta is not None else None,
            # O resumo do site entrou no prompt, mas é texto gerado por IA e só existe a versão atual: serve de pista, não de evidência.
            "resumo_do_site_atual": anonimizar(conta.resumo_site) if conta is not None else None,
        }
