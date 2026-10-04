"""Webhooks de entrada do CRM do cliente (D-087): frescor por evento.

O CRM avisa "algo mudou" numa URL secreta por conexão
(`/hub-integracoes/webhook/<token>`). O request só marca a conexão
(`sync_solicitado_em`) e responde 202 — nunca processa nada no request, não
lê o corpo além do limite e não devolve dado. O cron (a cada 15 min) relê o
CRM e atualiza o índice de deduplicação do PREDATOR (cliente novo, negócio
aberto, opt-out). O MAP já lê o CRM ao vivo, então não precisa de cópia.

Segurança: o token (256 bits) é mostrado uma vez; o banco guarda só o
SHA-256. Token errado = 404 sem diferença de tempo útil (busca por hash).
Gerar de novo invalida o anterior. Marcação repetida dentro de 1 minuto é
ignorada (um CRM barulhento não vira carga).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.integrations import registry
from app.models.conexao_integracao import ConexaoIntegracao
from app.services import auditoria_service

PREFIXO = "whin_"
INTERVALO_MINIMO = timedelta(minutes=1)
TAMANHO_MAXIMO = 64 * 1024


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def gerar_token(db: Session, conexao: ConexaoIntegracao, ator_id: str | None) -> str:
    token = PREFIXO + secrets.token_urlsafe(32)
    conexao.webhook_token_hash = _hash(token)
    auditoria_service.registrar(db, conexao.tenant_id, "conexao_integracao_webhook_gerado", "conexao_integracao", conexao.id, ator_id, {"sistema": conexao.sistema})
    db.commit()
    return token


def revogar_token(db: Session, conexao: ConexaoIntegracao, ator_id: str | None) -> None:
    conexao.webhook_token_hash = None
    auditoria_service.registrar(db, conexao.tenant_id, "conexao_integracao_webhook_revogado", "conexao_integracao", conexao.id, ator_id, {"sistema": conexao.sistema})
    db.commit()


def receber(db: Session, token: str) -> bool:
    if not token.startswith(PREFIXO) or len(token) > 100:
        return False
    conexao = db.query(ConexaoIntegracao).filter_by(webhook_token_hash=_hash(token)).one_or_none()
    if conexao is None:
        return False
    agora = datetime.now(UTC)
    ultimo = conexao.sync_solicitado_em
    if ultimo is None or agora - (ultimo if ultimo.tzinfo else ultimo.replace(tzinfo=UTC)) >= INTERVALO_MINIMO:
        conexao.sync_solicitado_em = agora
        db.commit()
    return True


def processar_solicitacoes(db: Session, limite: int = 20) -> dict:
    """Cron: relê o CRM das conexões que receberam webhook (índice de deduplicação)."""
    from app.contexts.integrations import escrita

    conexoes = (
        db.query(ConexaoIntegracao)
        .filter(ConexaoIntegracao.sync_solicitado_em.isnot(None), ConexaoIntegracao.status == "ativa")
        .order_by(ConexaoIntegracao.sync_solicitado_em)
        .limit(limite)
        .all()
    )
    resultado = {"conexoes": 0, "falhas": 0}
    for conexao in conexoes:
        conexao.sync_solicitado_em = None
        db.commit()
        if conexao.sistema not in escrita.SISTEMAS_EXTERNOS or not registry.conectavel(conexao.sistema) or not escrita.config(conexao).get("deduplicar"):
            continue
        try:
            escrita.atualizar_indice(db, conexao)
            resultado["conexoes"] += 1
        except Exception as erro:  # noqa: BLE001 — melhor-esforço; a rotina diária refaz
            db.rollback()
            escrita.registrar_falha_leitura(db, conexao, erro)
            resultado["falhas"] += 1
    return resultado
