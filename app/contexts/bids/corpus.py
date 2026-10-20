"""Corpus público comum de licitações (V5.2.1, Fase 3).

Um edital é um FATO público: existe uma única linha por (fonte, id externo) para toda a plataforma (`licitacao_publica`). Cada tenant que
acompanha o edital tem a sua cópia PRIVADA em `licitacao` (score, anotações, estratégia, conta/oferta, responsável, resultado), ligada ao fato por
`licitacao.corpus_id`. Este módulo cuida só do lado público e **não conhece tenant**, por construção.

Regras
- **Idempotente**: recoletar o mesmo edital sem mudança não cria linha, não gera evento e só atualiza `ultima_coleta_em`.
- **Retificação**: o hash do conteúdo público muda → nova `versao` + evento `retificada` com `{campo: [antes, depois]}`. Mudança de situação
  (Divulgada → Suspensa/Anulada/Revogada) gera evento próprio `situacao_alterada`. Fonte que não informa situação não apaga a que já se sabe.
- **Ordem**: página mais antiga que o estado guardado (`atualizado_externo_em` menor) não desfaz uma atualização mais nova.
- **Corrida**: duas coletas inserindo o mesmo edital ao mesmo tempo terminam com uma linha só (savepoint + refetch na violação de unicidade).
- **Nunca apaga** por falha: a poda (`retencao_historicos_service`) só remove edital que nenhum tenant acompanha e que não é coletado há muito tempo.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.bids.fontes.base import LicitacaoExterna
from app.contexts.shared import paginacao
from app.models.licitacao import Licitacao
from app.models.licitacao_publica import EventoLicitacaoPublica, LicitacaoPublica

# Campos que definem "o conteúdo do edital" (e, portanto, uma retificação). uf/município/código da modalidade são enriquecimento de localização:
# preenchem-se em silêncio, não contam como retificação (e ficam de fora do hash para o backfill não gerar falso evento).
CAMPOS_CONTEUDO = ("titulo", "objeto", "orgao_nome", "orgao_cnpj", "modalidade", "data_publicacao", "prazo_proposta", "valor_estimado",
                   "situacao_externa", "url")
CAMPOS_LOCALIZACAO = ("uf", "municipio", "modalidade_codigo")


def _iso(valor):
    return valor.isoformat() if isinstance(valor, datetime) else valor


def hash_conteudo(conteudo: dict) -> str:
    """SHA-256 do JSON canônico dos campos de conteúdo, em ordem fixa. A migração `d1b3e5a7c9f1` guarda uma cópia congelada deste algoritmo."""
    campos = [_iso(conteudo.get(campo)) for campo in CAMPOS_CONTEUDO]
    return hashlib.sha256(json.dumps(campos, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def chave(fonte: str, id_externo: str) -> str:
    return f"{fonte}:{id_externo}"


def _conteudo_da_fonte(ext: LicitacaoExterna) -> dict:
    return {"titulo": ext.titulo, "objeto": ext.objeto, "orgao_nome": ext.orgao_nome, "orgao_cnpj": ext.orgao_cnpj, "modalidade": ext.modalidade,
            "data_publicacao": ext.data_publicacao, "prazo_proposta": ext.prazo_proposta, "valor_estimado": ext.valor_estimado,
            "situacao_externa": ext.situacao_externa, "url": ext.url}


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class ResultadoRegistro:
    mapa: dict[str, LicitacaoPublica]
    criadas: int = 0
    retificadas: int = 0
    situacoes_alteradas: int = 0
    sem_mudanca: int = 0
    obsoletas: int = 0  # página mais antiga que o estado guardado: ignorada


def _criar(db: Session, ext: LicitacaoExterna, conteudo: dict, agora: datetime) -> LicitacaoPublica | None:
    """Insere dentro de um savepoint: se outra coleta inseriu a mesma chave primeiro, devolve `None` para o chamador atualizar a existente."""
    publica = LicitacaoPublica(
        fonte=ext.fonte, fonte_id_externo=ext.id_externo, **conteudo, atualizado_externo_em=ext.atualizado_externo_em, uf=ext.uf,
        municipio=ext.municipio, modalidade_codigo=ext.modalidade_codigo, hash_conteudo=hash_conteudo(conteudo), versao=1,
        primeira_coleta_em=agora, ultima_coleta_em=agora,
    )
    try:
        with db.begin_nested():
            db.add(publica)
            db.flush()
            db.add(EventoLicitacaoPublica(licitacao_publica_id=publica.id, tipo="criada", mudancas={}, versao=1, observado_em=agora))
    except IntegrityError:
        return None
    return publica


def registrar(db: Session, externas: list[LicitacaoExterna], agora: datetime | None = None) -> ResultadoRegistro:
    """Grava/atualiza o fato público de cada edital. Não faz commit (o chamador decide), mas faz flush."""
    agora = agora or _agora()
    resultado = ResultadoRegistro(mapa={})
    for ext in externas:
        if ext.fonte == "MANUAL" or not ext.id_externo:
            continue
        conteudo = _conteudo_da_fonte(ext)
        existente = db.query(LicitacaoPublica).filter_by(fonte=ext.fonte, fonte_id_externo=ext.id_externo).one_or_none()
        if existente is None:
            criada = _criar(db, ext, conteudo, agora)
            if criada is not None:
                resultado.mapa[chave(ext.fonte, ext.id_externo)] = criada
                resultado.criadas += 1
                continue
            existente = db.query(LicitacaoPublica).filter_by(fonte=ext.fonte, fonte_id_externo=ext.id_externo).one()
        resultado.mapa[chave(ext.fonte, ext.id_externo)] = existente
        _atualizar(db, existente, ext, conteudo, agora, resultado)
    db.flush()
    return resultado


def _atualizar(db: Session, existente: LicitacaoPublica, ext: LicitacaoExterna, conteudo: dict, agora: datetime, resultado: ResultadoRegistro) -> None:
    existente.ultima_coleta_em = agora
    for campo in CAMPOS_LOCALIZACAO:  # enriquecimento: só preenche, nunca troca por vazio
        novo = getattr(ext, campo)
        if novo is not None and getattr(existente, campo) != novo:
            setattr(existente, campo, novo)
    if ext.atualizado_externo_em and existente.atualizado_externo_em and ext.atualizado_externo_em < existente.atualizado_externo_em:
        resultado.obsoletas += 1  # leitura antiga: não desfaz uma atualização mais nova
        return
    if conteudo["situacao_externa"] is None:
        conteudo["situacao_externa"] = existente.situacao_externa  # fonte que não informa não apaga o que já se sabe
    if ext.atualizado_externo_em is not None:
        existente.atualizado_externo_em = ext.atualizado_externo_em
    novo_hash = hash_conteudo(conteudo)
    if novo_hash == existente.hash_conteudo:
        resultado.sem_mudanca += 1
        return
    mudancas = {campo: [_iso(getattr(existente, campo)), _iso(valor)] for campo, valor in conteudo.items() if getattr(existente, campo) != valor}
    for campo, valor in conteudo.items():
        setattr(existente, campo, valor)
    existente.hash_conteudo = novo_hash
    existente.versao += 1
    existente.ultima_alteracao_em = agora
    situacao = mudancas.pop("situacao_externa", None)
    if situacao is not None and situacao[0] is not None:
        db.add(EventoLicitacaoPublica(licitacao_publica_id=existente.id, tipo="situacao_alterada", mudancas={"situacao_externa": situacao},
                                      versao=existente.versao, observado_em=agora))
        resultado.situacoes_alteradas += 1
    elif situacao is not None:
        mudancas["situacao_externa"] = situacao  # primeira vez que a situação é conhecida: conta como dado novo, não como mudança de situação
    if mudancas:
        db.add(EventoLicitacaoPublica(licitacao_publica_id=existente.id, tipo="retificada", mudancas=mudancas, versao=existente.versao,
                                      observado_em=agora))
        resultado.retificadas += 1


# --- Consulta (dados públicos; o tenant só enxerga o PRÓPRIO vínculo) ----------------------------------------------------------------------


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar(db: Session, tenant_id: str, *, q: str | None = None, uf: str | None = None, modalidade: str | None = None,
           situacao: str | None = None, desde: datetime | None = None, cursor: str | None = None, limite: int | None = None) -> paginacao.Pagina[dict]:
    """Mais recentemente publicados primeiro (keyset por (data_publicacao, id)). `ja_acompanho` revela apenas se O PRÓPRIO tenant acompanha."""
    quantidade = paginacao.limite(limite)
    consulta = db.query(LicitacaoPublica)
    if q:
        padrao = f"%{_escapar_like(q.strip().lower())}%"
        consulta = consulta.filter(or_(func.lower(LicitacaoPublica.titulo).like(padrao, escape="\\"),
                                       func.lower(LicitacaoPublica.objeto).like(padrao, escape="\\"),
                                       func.lower(LicitacaoPublica.orgao_nome).like(padrao, escape="\\")))
    if uf:
        consulta = consulta.filter(LicitacaoPublica.uf == uf.strip().upper())
    if modalidade:
        consulta = consulta.filter(LicitacaoPublica.modalidade == modalidade)
    if situacao:
        consulta = consulta.filter(func.lower(LicitacaoPublica.situacao_externa) == situacao.strip().lower())
    if desde:
        consulta = consulta.filter(LicitacaoPublica.primeira_coleta_em >= desde)
    posicao = paginacao.decodificar(cursor)
    if posicao is not None:
        consulta = consulta.filter(LicitacaoPublica.id < int(posicao["id"]))
    linhas = consulta.order_by(LicitacaoPublica.id.desc()).limit(quantidade + 1).all()
    seguidas = ids_acompanhados(db, tenant_id, [p.id for p in linhas])
    return paginacao.fatiar([como_dict(p, p.id in seguidas) for p in linhas], quantidade, lambda item: {"id": item["id"]})


def ids_acompanhados(db: Session, tenant_id: str, corpus_ids: list[int]) -> dict[int, int]:
    if not corpus_ids:
        return {}
    return {c: i for i, c in db.query(Licitacao.id, Licitacao.corpus_id).filter(Licitacao.tenant_id == tenant_id, Licitacao.corpus_id.in_(corpus_ids)).all()}


def obter(db: Session, corpus_id: int) -> LicitacaoPublica | None:
    return db.get(LicitacaoPublica, corpus_id)


def historico(db: Session, corpus_id: int) -> list[dict]:
    eventos = db.query(EventoLicitacaoPublica).filter_by(licitacao_publica_id=corpus_id).order_by(EventoLicitacaoPublica.id).all()
    return [{"tipo": e.tipo, "versao": e.versao, "observado_em": e.observado_em, "mudancas": e.mudancas} for e in eventos]


def como_dict(publica: LicitacaoPublica, ja_acompanho: bool = False) -> dict:
    return {
        "id": publica.id, "fonte": publica.fonte, "fonte_id_externo": publica.fonte_id_externo, "titulo": publica.titulo, "objeto": publica.objeto,
        "orgao_nome": publica.orgao_nome, "orgao_cnpj": publica.orgao_cnpj, "uf": publica.uf, "municipio": publica.municipio,
        "modalidade": publica.modalidade, "data_publicacao": publica.data_publicacao, "prazo_proposta": publica.prazo_proposta,
        "valor_estimado": publica.valor_estimado, "situacao_externa": publica.situacao_externa, "atualizado_externo_em": publica.atualizado_externo_em,
        "url": publica.url, "versao": publica.versao, "primeira_coleta_em": publica.primeira_coleta_em, "ultima_alteracao_em": publica.ultima_alteracao_em,
        "ja_acompanho": ja_acompanho,
    }
