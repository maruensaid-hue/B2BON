"""Sonda de RLS (D-110): registra, nos testes HTTP existentes, as consultas a tabelas protegidas feitas SEM o contexto que as políticas do banco exigem.

Liga com `B2BON_RLS_SONDA=<arquivo.json>` (nenhum efeito sem a variável). Imita no SQLite o que o PostgreSQL faria: o contexto da sessão vira uma marca da transação da
conexão (apagada no commit/rollback, como o `SET LOCAL`), e cada consulta feita DENTRO de uma requisição HTTP (pilha com starlette) a uma tabela protegida é conferida.
Não prova o enforcement (isso é dos testes em PostgreSQL); mostra, usando os 3 mil testes já existentes, quais rotas precisam de um contexto explícito.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.db import rls

_REFERENCIA = re.compile(r'\b(?:FROM|JOIN|INTO|UPDATE)\s+"?([a-z_][a-z0-9_]*)"?', re.IGNORECASE)
_achados: Counter = Counter()
_acessos: Counter = Counter()  # (escopo, tabela, verbo) — base para montar os contextos de sistema


def _tabelas_protegidas() -> set[str]:
    import app.models  # noqa: F401
    from app.db.base import Base

    return {nome for nome, tabela in Base.metadata.tables.items() if any(c == "tenant_id" or c.startswith("tenant_id_") for c in tabela.columns.keys())}


def _manipulador_da_requisicao() -> str | None:
    """Função mais externa de `app/api` na pilha, se a consulta roda dentro de uma requisição HTTP; `None` se vem de teste/serviço direto.
    Rotas síncronas rodam num thread do pool, sem quadros do starlette: o que marca a requisição são os quadros de `app/api/`."""
    quadro = sys._getframe(2)
    em_requisicao, manipulador = False, None
    while quadro is not None:
        arquivo = quadro.f_code.co_filename.replace("\\", "/")
        if "/app/api/" in arquivo:
            em_requisicao = True
            if not arquivo.endswith("deps.py"):
                manipulador = f"{arquivo.split('/app/')[-1]}:{quadro.f_code.co_name}"
        quadro = quadro.f_back
    if not em_requisicao:
        return None
    return manipulador or "app/api/deps.py:(dependência)"


def _sessao_que_executa():
    """A `Session` que está executando a consulta (procura `self` do tipo Session nos quadros). Em produção cada sessão tem a própria conexão; no SQLite dos testes todas
    dividem uma só, então o contexto da CONEXÃO misturaria sessões. O contexto da própria sessão é o que o `after_begin` gravaria no PostgreSQL."""
    from sqlalchemy.orm import Session

    quadro = sys._getframe(2)
    while quadro is not None:
        candidato = quadro.f_locals.get("self")
        if isinstance(candidato, Session):
            return candidato
        quadro = quadro.f_back
    return None


def ativar() -> None:
    protegidas = _tabelas_protegidas()
    _instalar_verificacao_de_escrita()
    _instalar_verificacao_de_leitura()

    @event.listens_for(Engine, "before_cursor_execute")
    def _conferir(conexao, _cursor, instrucao, _parametros, _contexto, _muitos) -> None:
        tabelas = {t for t in _REFERENCIA.findall(instrucao) if t in protegidas}
        if not tabelas:
            return
        manipulador = _manipulador_da_requisicao()
        if manipulador is None:
            return
        sessao = _sessao_que_executa()
        contexto = (sessao.info.get("rls_contexto") if sessao is not None else None) or rls.SEM_CONTEXTO
        verbo = "ler" if instrucao.lstrip().split(None, 1)[0].upper() == "SELECT" else "escrever"
        for tabela in tabelas:
            _achados[(_classificar(contexto, tabela, verbo), tabela, manipulador)] += 1
            _acessos[(contexto.escopo or "SEM_CONTEXTO", tabela, verbo)] += 1


def _classificar(contexto, tabela: str, verbo: str) -> str:
    """Nome do escopo se a consulta é coberta pelo registro; `FORA:<escopo>` se não é; `SEM_CONTEXTO` se não há contexto."""
    from app.db import rls_registro

    if not contexto.escopo:
        return "SEM_CONTEXTO"
    if contexto.escopo == rls.ESCOPO_TENANT:
        return rls.ESCOPO_TENANT
    if contexto.escopo.startswith(rls.PREFIXO_SISTEMA):
        liberado = rls_registro.CONTEXTOS_SISTEMA.get(contexto.escopo[len(rls.PREFIXO_SISTEMA):], {}).get(tabela)
        coberto = liberado == "escrever" or (liberado == "ler" and verbo == "ler")
        return contexto.escopo if coberto else f"FORA:{contexto.escopo}"
    busca = rls_registro.BUSCAS.get(contexto.escopo, ())
    coberto = verbo == "ler" and any(item.tabela == tabela for item in busca)
    return contexto.escopo if coberto else f"FORA:{contexto.escopo}"


def _instalar_verificacao_de_leitura() -> None:
    """Imita o `USING` de leitura: objeto carregado de OUTRO tenant (fora do tenant do contexto e da leitura ampliada) seria invisível no PostgreSQL."""
    from sqlalchemy.orm import Session

    @event.listens_for(Session, "loaded_as_persistent")
    def _leitura(sessao, objeto) -> None:
        if not hasattr(objeto, "tenant_id"):
            return
        manipulador = _manipulador_da_requisicao()
        if manipulador is None:
            return
        contexto = sessao.info.get("rls_contexto") or rls.SEM_CONTEXTO
        if contexto.escopo != rls.ESCOPO_TENANT:
            return  # contexto ausente ou de busca/sistema já é contado pela consulta
        tenant = objeto.tenant_id
        if tenant == contexto.tenant_id or rls.LEITURA_TOTAL in contexto.visiveis or tenant in contexto.visiveis:
            return
        _achados[("LEITURA_OUTRO_TENANT", objeto.__table__.name, manipulador)] += 1


def _instalar_verificacao_de_escrita() -> None:
    """Imita o `WITH CHECK`: objeto novo/alterado cujo `tenant_id` difere do tenant do contexto da sessão (ou sem contexto) é registrado como ESCRITA_*."""
    from sqlalchemy.orm import Session

    @event.listens_for(Session, "before_flush")
    def _escrita(sessao, _contexto, _instancias) -> None:
        manipulador = _manipulador_da_requisicao()
        if manipulador is None:
            return
        contexto = sessao.info.get("rls_contexto") or rls.SEM_CONTEXTO
        for objeto in list(sessao.new) + list(sessao.dirty):
            tenant = getattr(objeto, "tenant_id", None)
            tabela = getattr(getattr(objeto, "__table__", None), "name", None)
            if tabela is None or not hasattr(objeto, "tenant_id"):
                continue
            if contexto.escopo == rls.ESCOPO_TENANT:
                if tenant != contexto.tenant_id:
                    _achados[("ESCRITA_OUTRO_TENANT", tabela, manipulador)] += 1
            elif _classificar(contexto, tabela, "escrever").startswith(("FORA:", "SEM_CONTEXTO")):
                _achados[(f"ESCRITA_{contexto.escopo or 'SEM_CONTEXTO'}", tabela, manipulador)] += 1


def gravar_relatorio() -> None:
    destino = os.environ.get("B2BON_RLS_SONDA")
    if not destino:
        return
    linhas = [{"escopo": e, "tabela": t, "manipulador": m, "consultas": n} for (e, t, m), n in sorted(_achados.items())]
    acessos = [{"escopo": e, "tabela": t, "verbo": v, "consultas": n} for (e, t, v), n in sorted(_acessos.items())]
    with open(destino, "w", encoding="utf-8") as arquivo:
        json.dump(linhas, arquivo, ensure_ascii=False, indent=1)
    with open(destino + ".acessos.json", "w", encoding="utf-8") as arquivo:
        json.dump(acessos, arquivo, ensure_ascii=False, indent=1)
