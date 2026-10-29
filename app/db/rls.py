"""Contexto de isolamento por tenant no PostgreSQL (Row-Level Security) — segunda barreira, atrás dos filtros por `tenant_id` do código (auditoria A01, D-110).

Como funciona
- O banco decide o que cada transação enxerga lendo variáveis de sessão locais à transação (`app.tenant_id`, `app.escopo`, `app.visiveis`, `app.chave`), que as políticas das
  tabelas consultam. O valor vem SEMPRE do backend (usuário já validado, tarefa de sistema nomeada), nunca de um `tenant_id` enviado pelo cliente.
- O contexto mora em `Session.info`. A cada transação iniciada, o evento `after_begin` grava as variáveis com `set_config(..., is_local => true)`: elas valem só até o
  `COMMIT`/`ROLLBACK` e desaparecem sozinhas, então nada vaza para a próxima requisição que reutilize a conexão do pool (nem atrás do pgbouncer em modo de transação).
  Como a sessão do SQLAlchemy abre uma transação nova depois de cada `commit` e `rollback`, o evento regrava o contexto toda vez; um `SAVEPOINT` não muda isso.
- Sem contexto nada é gravado, a variável fica ausente e as políticas negam (`NULL` nunca é igual a nada): o padrão é negar.
- No SQLite (desenvolvimento e testes) nada disso é emitido: o enforcement real só existe no PostgreSQL com o papel de aplicação sem `BYPASSRLS` (ver `docs/b2bon/RLS.md`).

Tipos de contexto (`escopo`)
- `tenant`: usuário autenticado; vê e grava só as linhas do próprio `tenant_id`. Pontos de leitura que o código já autoriza para a hierarquia (`tenant_service.tenant_ids_no_escopo`)
  ampliam a LEITURA, nunca a escrita, com `ampliar_leitura`.
- `autenticacao`/`login`: buscas feitas ANTES de saber o tenant (validar o token, entrar com e-mail e senha). Cada uma tem política própria que libera uma única linha, pela chave.
- `sistema:<nome>`: tarefas sem usuário (cron, webhooks). O nome precisa constar em `app/db/rls_registro.py` (rastreabilidade); na segunda etapa (D-111) o banco libera todas as
  tabelas protegidas a qualquer contexto de sistema (ver `FUNCOES_ETAPA2` em `rls_sql.py` para o porquê).
- `plataforma`: rotas de administração da plataforma, só para quem o banco confirmou como `super_admin` (`definir_plataforma`, chamado por `deps.exigir_papel`). Mesmo acesso
  total dos contextos de sistema; o que os separa do contexto de tenant é exatamente a verificação do papel.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_CHAVE_INFO = "rls_contexto"

ESCOPO_TENANT = "tenant"
ESCOPO_AUTENTICACAO = "autenticacao"
ESCOPO_LOGIN = "login"
ESCOPO_REDEFINICAO = "redefinicao"
ESCOPO_CONVITE_CADASTRO = "convite-cadastro"
ESCOPO_CONVITE_VITRINE = "convite-vitrine"
ESCOPO_WHATSAPP_NUMERO = "whatsapp-numero"
ESCOPO_CAPTURA_LEAD = "captura-lead"
ESCOPO_INTEGRACAO_WEBHOOK = "integracao-webhook"
ESCOPO_PORTAL_FORNECEDOR = "portal-fornecedor"
ESCOPO_RECALL_BOT = "recall-bot"
ESCOPO_PAGAMENTO = "pagamento-referencia"
ESCOPO_CHAVE_API = "chave-api"
ESCOPO_CHAVE_API_PARCEIRO = "chave-api-parceiro"
ESCOPO_PLATAFORMA = "plataforma"
PREFIXO_SISTEMA = "sistema:"
LEITURA_TOTAL = "*"  # só `tenant_service.tenant_ids_no_escopo` para super_admin, que o código já autoriza a ver todos


@dataclass(frozen=True)
class ContextoRls:
    """O que as políticas do banco enxergam. Vazio = nenhuma linha de tabela protegida."""

    tenant_id: str | None = None
    escopo: str = ""
    visiveis: tuple[str, ...] = ()
    chave: str | None = None

    @property
    def vazio(self) -> bool:
        return not (self.tenant_id or self.escopo or self.visiveis or self.chave)


SEM_CONTEXTO = ContextoRls()


def contexto_atual(db: Session) -> ContextoRls:
    return db.info.get(_CHAVE_INFO, SEM_CONTEXTO)


def _eh_postgres(conexao: Connection) -> bool:
    return conexao.dialect.name == "postgresql"


def _emitir(conexao: Connection, contexto: ContextoRls) -> None:
    """Grava o contexto na transação em curso. `is_local => true` equivale a `SET LOCAL`: some no `COMMIT`/`ROLLBACK`."""
    conexao.execute(
        text(
            "SELECT set_config('app.tenant_id', :tenant, true), set_config('app.escopo', :escopo, true), "
            "set_config('app.visiveis', :visiveis, true), set_config('app.chave', :chave, true)"
        ),
        {
            "tenant": contexto.tenant_id or "",
            "escopo": contexto.escopo,
            "visiveis": ",".join(contexto.visiveis),
            "chave": contexto.chave or "",
        },
    )


@event.listens_for(Session, "after_begin")
def _ao_iniciar_transacao(sessao: Session, _transacao, conexao: Connection) -> None:
    contexto = sessao.info.get(_CHAVE_INFO)
    if contexto is None or contexto.vazio or not _eh_postgres(conexao):
        return  # sem contexto: nada é gravado e as políticas negam
    _emitir(conexao, contexto)


def _aplicar_na_transacao_em_curso(db: Session, contexto: ContextoRls) -> None:
    """Se a sessão já tem transação aberta (ex.: a busca do usuário que acabou de ser validado), a mudança vale já; senão, valerá no próximo `after_begin`."""
    if not db.in_transaction():
        return
    conexao = db.connection()
    if _eh_postgres(conexao):
        _emitir(conexao, contexto if not contexto.vazio else SEM_CONTEXTO)


def definir(db: Session, contexto: ContextoRls) -> None:
    # O autoflush da aplicação é desligado: o que está pendente só seria gravado no próximo commit, já sob OUTRO contexto, e o `WITH CHECK` o recusaria. Por isso
    # o pendente é gravado agora, sob o contexto anterior (o dono da mudança).
    if db.new or db.dirty or db.deleted:
        db.flush()
    db.info[_CHAVE_INFO] = contexto
    _aplicar_na_transacao_em_curso(db, contexto)


def limpar(db: Session) -> None:
    definir(db, SEM_CONTEXTO)


def definir_tenant(db: Session, tenant_id: str) -> None:
    """Contexto do usuário autenticado (o `tenant_id` vem do usuário validado no banco, nunca da requisição)."""
    if not tenant_id:
        raise ValueError("tenant_id vazio: o contexto de tenant exige um tenant")
    definir(db, ContextoRls(tenant_id=tenant_id, escopo=ESCOPO_TENANT))


def definir_plataforma(db: Session) -> None:
    """Contexto das rotas de administração da plataforma. Só chamar DEPOIS de confirmar que o usuário validado no banco é `super_admin` (`deps.exigir_papel`)."""
    definir(db, ContextoRls(escopo=ESCOPO_PLATAFORMA))


def ampliar_leitura(db: Session, tenant_ids: list[str] | tuple[str, ...] | str) -> None:
    """Amplia só a LEITURA para os tenants que a regra de hierarquia da aplicação já autorizou (`LEITURA_TOTAL` para o super_admin). A escrita continua só no tenant do contexto."""
    atual = contexto_atual(db)
    if atual.escopo != ESCOPO_TENANT:
        return  # sem contexto de tenant (serviço chamado fora de uma requisição, ou SQLite) não há o que ampliar; o banco continua negando
    visiveis = (LEITURA_TOTAL,) if tenant_ids == LEITURA_TOTAL else tuple(sorted(set(tenant_ids)))
    definir(db, replace(atual, visiveis=visiveis))


@contextmanager
def contexto_tenant(db: Session, tenant_id: str) -> Iterator[None]:
    """Roda um trecho (ex.: uma volta de um cron) no contexto de UM tenant e restaura o anterior ao sair, inclusive em caso de erro."""
    anterior = contexto_atual(db)
    definir_tenant(db, tenant_id)
    try:
        yield
    finally:
        definir(db, anterior)


@contextmanager
def contexto_sistema(db: Session, nome: str, chave: str | None = None) -> Iterator[None]:
    """Tarefa sem usuário (cron, webhook): o nome precisa constar em `rls_registro.CONTEXTOS_SISTEMA`; ele só libera as tabelas listadas lá."""
    from app.db import rls_registro

    if nome not in rls_registro.CONTEXTOS_SISTEMA:
        raise ValueError(f"contexto de sistema desconhecido: {nome}")
    anterior = contexto_atual(db)
    definir(db, ContextoRls(escopo=PREFIXO_SISTEMA + nome, chave=chave))
    try:
        yield
    finally:
        definir(db, anterior)


@contextmanager
def contexto_busca(db: Session, escopo: str, chave: str) -> Iterator[None]:
    """Busca de UMA linha antes de saber o tenant (token da sessão, e-mail do login): a política da tabela só libera a linha cuja chave coincide."""
    from app.db import rls_registro

    if escopo not in rls_registro.BUSCAS:
        raise ValueError(f"escopo de busca desconhecido: {escopo}")
    anterior = contexto_atual(db)
    definir(db, ContextoRls(escopo=escopo, chave=str(chave)))
    try:
        yield
    finally:
        definir(db, anterior)


def sessao_irma(db: Session, **opcoes) -> Session:
    """Sessão nova no mesmo banco e com o MESMO contexto (o gateway de IA e o financeiro gravam em transação própria; uma sessão nova nasceria sem contexto e seria negada)."""
    nova = sessionmaker(bind=db.get_bind(), **opcoes)()
    contexto = db.info.get(_CHAVE_INFO)
    if contexto is not None:
        nova.info[_CHAVE_INFO] = contexto
    return nova
