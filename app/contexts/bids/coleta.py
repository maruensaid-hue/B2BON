"""Coleta agendada e monitorada de fontes públicas de licitação (hoje só o PNCP).

Roda sem nenhuma IA. Reaproveita a ingestão idempotente (`licitacoes.ingerir`, única por tenant+fonte+id externo) e o agendador
que o projeto já usa (GitHub Actions → `POST /cron/coletar-licitacoes`), sem serviço novo nem custo.

* **Desligada por padrão** e sempre filtrada (UF e/ou palavras-chave): ingerir todas as contratações do país estouraria o banco.
* **Uma execução por vez** por tenant e fonte (índice único parcial); execução esquecida há mais de 30 min é encerrada como falha.
* **Retomável sem duplicar**: o cursor só avança quando a janela inteira termina; falha ou teto atingido repete a janela e a
  ingestão idempotente só atualiza o que já existe. A janela é de no máximo 7 dias por execução (recupera atraso aos poucos).
* **Gentil com a fonte**: pausa entre páginas, teto de páginas por execução, retentativa com espera progressiva no adapter.
* **Detectável**: cada execução grava estado, contadores, duração, tentativas, erro e cursor; `saude()` resume e o log de erro
  `COLETA_FONTE_FALHANDO` / `COLETA_FONTE_ATRASADA` (capturado pelo Sentry) sinaliza a degradação.
* **Nunca apaga**: falha de atualização não remove nada do que já foi ingerido.
"""

import logging
import time
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import sentry_sdk
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.bids import licitacoes
from app.contexts.bids.fontes.pncp import MODALIDADES_VALIDAS, ErroFonte, FontePncp, PaginaPncp
from app.core.config import settings
from app.models.coleta_fonte import ConfiguracaoColetaFonte, ExecucaoColetaFonte
from app.models.tenant import Tenant
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

logger = logging.getLogger(__name__)

FONTE = "PNCP"
_EXECUCAO_ABANDONADA = timedelta(minutes=30)
_PAUSA_ENTRE_PAGINAS_SEGUNDOS = 0.5
_MAX_PAGINAS_POR_EXECUCAO = 100  # 5.000 registros por execução
_MAX_JANELA_DIAS = 7
_LIMITES = {"janela_dias": (1, _MAX_JANELA_DIAS), "max_novas_por_execucao": (1, 1000)}


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _aaaammdd(dia: date) -> str:
    return dia.strftime("%Y%m%d")


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def obter_configuracao(db: Session, tenant_id: str) -> ConfiguracaoColetaFonte | None:
    return db.query(ConfiguracaoColetaFonte).filter_by(tenant_id=tenant_id, fonte=FONTE).one_or_none()


def salvar_configuracao(db: Session, tenant_id: str, ator_id: str | None, dados: dict) -> ConfiguracaoColetaFonte:
    modalidades = sorted({int(m) for m in dados.get("modalidades") or []})
    ufs = sorted({u.strip().upper() for u in dados.get("ufs") or [] if u and u.strip()})
    palavras = sorted({p.strip() for p in dados.get("palavras_chave") or [] if p and p.strip()}, key=str.lower)
    if any(m not in MODALIDADES_VALIDAS for m in modalidades):
        raise ValidacaoFalhou("Modalidade inválida: use os códigos de 1 a 19 do PNCP.")
    if any(len(u) != 2 or not u.isalpha() for u in ufs):
        raise ValidacaoFalhou("UF inválida: use a sigla com duas letras (ex.: SP).")
    for campo, (minimo, maximo) in _LIMITES.items():
        if not minimo <= int(dados.get(campo, minimo)) <= maximo:
            raise ValidacaoFalhou(f"{campo} deve estar entre {minimo} e {maximo}.")
    ativa = bool(dados.get("ativa"))
    if ativa and not modalidades:
        raise ValidacaoFalhou("Escolha ao menos uma modalidade para ativar a coleta (o PNCP exige a modalidade).")
    if ativa and not (ufs or palavras):
        raise ValidacaoFalhou("Informe UF e/ou palavras-chave: coletar tudo do país não é permitido.")
    cfg = obter_configuracao(db, tenant_id) or ConfiguracaoColetaFonte(tenant_id=tenant_id, fonte=FONTE)
    cfg.ativa, cfg.modalidades, cfg.ufs, cfg.palavras_chave = ativa, modalidades, ufs, palavras
    cfg.janela_dias = int(dados.get("janela_dias", 2))
    cfg.max_novas_por_execucao = int(dados.get("max_novas_por_execucao", 200))
    db.add(cfg)
    auditoria_service.registrar(db, tenant_id, "coleta_fonte_configurada", "configuracao_coleta_fonte", 0, ator_id,
                                {"fonte": FONTE, "ativa": ativa, "modalidades": modalidades, "ufs": ufs})
    db.commit()
    db.refresh(cfg)
    return cfg


def _casa(item, cfg: ConfiguracaoColetaFonte) -> bool:
    if not cfg.palavras_chave:
        return True
    texto = _normalizar(f"{item.objeto or ''} {item.titulo}")
    return any(_normalizar(p) in texto for p in cfg.palavras_chave)


def _ultima_concluida(db: Session, tenant_id: str) -> ExecucaoColetaFonte | None:
    return (
        db.query(ExecucaoColetaFonte).filter_by(tenant_id=tenant_id, fonte=FONTE, estado="concluida")
        .order_by(ExecucaoColetaFonte.id.desc()).first()
    )


def _janela(db: Session, tenant_id: str, cfg: ConfiguracaoColetaFonte, hoje: date) -> tuple[date, date]:
    ultima = _ultima_concluida(db, tenant_id)
    if ultima is None or not ultima.cursor_referencia:
        return hoje - timedelta(days=cfg.janela_dias), hoje
    cursor = datetime.strptime(ultima.cursor_referencia, "%Y%m%d").date()
    inicio = cursor - timedelta(days=1)  # um dia de sobreposição: publicação tardia e retificação (idempotente)
    return inicio, min(hoje, inicio + timedelta(days=_MAX_JANELA_DIAS))


def _encerrar_abandonadas(db: Session, tenant_id: str, agora: datetime) -> None:
    abandonadas = db.query(ExecucaoColetaFonte).filter(
        ExecucaoColetaFonte.tenant_id == tenant_id, ExecucaoColetaFonte.fonte == FONTE,
        ExecucaoColetaFonte.estado == "em_andamento", ExecucaoColetaFonte.iniciada_em < agora - _EXECUCAO_ABANDONADA,
    ).all()
    for execucao in abandonadas:
        execucao.estado, execucao.concluida_em = "falhou", agora
        execucao.erro = "Execução interrompida (processo reiniciado ou tempo excedido)."
    if abandonadas:
        db.commit()


def _falhas_consecutivas(db: Session, tenant_id: str) -> int:
    recentes = (
        db.query(ExecucaoColetaFonte).filter_by(tenant_id=tenant_id, fonte=FONTE)
        .filter(ExecucaoColetaFonte.estado != "em_andamento").order_by(ExecucaoColetaFonte.id.desc()).limit(20).all()
    )
    total = 0
    for execucao in recentes:
        if execucao.estado != "falhou":
            break
        total += 1
    return total


def _sinalizar_falha(tenant_id: str, falhas: int, erro: str | None) -> None:
    if falhas < settings.coleta_falhas_alerta:
        return
    mensagem = f"COLETA_FONTE_FALHANDO fonte={FONTE} tenant={tenant_id} falhas_consecutivas={falhas} ultimo_erro={erro}"
    logger.error(mensagem)
    if settings.sentry_dsn:
        sentry_sdk.capture_message(mensagem, level="error")


def executar(db: Session, tenant_id: str, fonte: FontePncp, disparo: str = "agendado", agora: datetime | None = None,
             dormir: Callable[[float], None] = time.sleep) -> ExecucaoColetaFonte | None:
    """Uma execução da coleta do tenant. Devolve `None` quando não há o que fazer (sem configuração ativa) ou já existe
    outra execução em andamento."""
    agora = agora or _agora()
    cfg = obter_configuracao(db, tenant_id)
    if cfg is None or not cfg.ativa:
        return None
    _encerrar_abandonadas(db, tenant_id, agora)
    inicio_janela, fim_janela = _janela(db, tenant_id, cfg, agora.date())
    execucao = ExecucaoColetaFonte(
        tenant_id=tenant_id, fonte=FONTE, disparo=disparo, estado="em_andamento", iniciada_em=agora,
        data_inicial=_aaaammdd(inicio_janela), data_final=_aaaammdd(fim_janela),
    )
    db.add(execucao)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None  # outra execução está em andamento para este tenant
    execucao_id, cronometro = execucao.id, time.monotonic()
    try:
        parcial = _coletar(db, tenant_id, cfg, fonte, execucao, dormir)
        execucao.estado = "parcial" if parcial else "concluida"
        if not parcial:
            execucao.cursor_referencia = execucao.data_final
    except ErroFonte as erro:
        db.rollback()
        execucao = db.get(ExecucaoColetaFonte, execucao_id)
        execucao.estado, execucao.erro = "falhou", str(erro)[:500]
        execucao.tentativas = max(execucao.tentativas, erro.tentativas)
    except Exception as erro:  # noqa: BLE001 — registrar e seguir: uma falha nunca derruba a rotina dos outros tenants
        db.rollback()
        logger.exception("Falha inesperada na coleta %s do tenant %s", FONTE, tenant_id)
        execucao = db.get(ExecucaoColetaFonte, execucao_id)
        execucao.estado, execucao.erro = "falhou", f"Erro interno ({type(erro).__name__})."
    execucao.duracao_ms = int((time.monotonic() - cronometro) * 1000)
    execucao.concluida_em = agora + timedelta(milliseconds=execucao.duracao_ms)
    db.commit()
    if execucao.estado == "falhou":
        _sinalizar_falha(tenant_id, _falhas_consecutivas(db, tenant_id), execucao.erro)
    return execucao


def _coletar(db: Session, tenant_id: str, cfg: ConfiguracaoColetaFonte, fonte: FontePncp, execucao: ExecucaoColetaFonte,
             dormir: Callable[[float], None]) -> bool:
    """Percorre modalidade × UF × páginas da janela e ingere. Devolve `True` se parou por teto (execução parcial)."""
    for modalidade in cfg.modalidades:
        for uf in cfg.ufs or [None]:
            pagina = 1
            while True:
                if execucao.paginas >= _MAX_PAGINAS_POR_EXECUCAO or execucao.inseridos >= cfg.max_novas_por_execucao:
                    return True
                # `atualizacao` traz o publicado E o alterado na janela: é por ele que anulação, revogação, suspensão e retificação de edital
                # já ingerido chegam (a consulta por `publicacao` só enxerga edital novo).
                resultado: PaginaPncp = fonte.buscar_pagina(
                    execucao.data_inicial, execucao.data_final, modalidade, pagina, uf, "atualizacao"
                )
                execucao.paginas += 1
                execucao.tentativas += resultado.tentativas
                relevantes = [i for i in resultado.itens if _casa(i, cfg)]
                execucao.consultados += len(resultado.itens) + resultado.ignorados
                execucao.ignorados += resultado.ignorados + len(resultado.itens) - len(relevantes)
                if relevantes:
                    ingerido = licitacoes.ingerir_detalhado(db, tenant_id, None, relevantes)
                    execucao.inseridos += len(ingerido["criadas"])
                    execucao.atualizados += len(ingerido["atualizadas"])
                    execucao.alterados_na_fonte += len(ingerido["alteradas"])
                db.commit()  # progresso por página: uma falha adiante não perde o que já entrou
                if pagina >= resultado.total_paginas:
                    break
                pagina += 1
                dormir(_PAUSA_ENTRE_PAGINAS_SEGUNDOS)
    return False


class _FonteComCache:
    """Dentro de uma rodada, tenants com o mesmo filtro compartilham as respostas da fonte (menos chamadas ao portal)."""

    def __init__(self, fonte: FontePncp) -> None:
        self._fonte, self._cache = fonte, {}

    def buscar_pagina(self, *args) -> PaginaPncp:
        if args not in self._cache:
            self._cache[args] = self._fonte.buscar_pagina(*args)
        return self._cache[args]


def executar_agendada(db: Session, fonte: FontePncp, dormir: Callable[[float], None] = time.sleep) -> dict:
    """Entrada do cron: percorre os tenants reais com a coleta ativa, isolando a falha de cada um."""
    if not settings.pncp_habilitado:
        return {"estado": "desabilitada_no_ambiente"}
    compartilhada = _FonteComCache(fonte)
    resumo = {"estado": "ok", "tenants": 0, "concluidas": 0, "parciais": 0, "falhas": 0, "em_andamento": 0, "atrasadas": 0}
    tenants = (
        db.query(ConfiguracaoColetaFonte.tenant_id).join(Tenant, Tenant.id == ConfiguracaoColetaFonte.tenant_id)
        .filter(ConfiguracaoColetaFonte.fonte == FONTE, ConfiguracaoColetaFonte.ativa.is_(True), Tenant.ativo.is_(True),
                Tenant.demo_expira_em.is_(None)).order_by(ConfiguracaoColetaFonte.tenant_id).all()
    )
    for (tenant_id,) in tenants:
        resumo["tenants"] += 1
        try:
            execucao = executar(db, tenant_id, compartilhada, "agendado", dormir=dormir)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Falha ao coletar %s para o tenant %s", FONTE, tenant_id)
            resumo["falhas"] += 1
            continue
        if execucao is None:
            resumo["em_andamento"] += 1
        else:
            chave = {"concluida": "concluidas", "parcial": "parciais", "falhou": "falhas"}.get(execucao.estado)
            if chave:
                resumo[chave] += 1
        if saude(db, tenant_id)["estado"] == "atrasada":
            resumo["atrasadas"] += 1
            logger.error("COLETA_FONTE_ATRASADA fonte=%s tenant=%s", FONTE, tenant_id)
    return resumo


def saude(db: Session, tenant_id: str, agora: datetime | None = None) -> dict:
    """Resumo operacional: `desabilitada` | `nunca_executada` | `saudavel` | `atrasada` | `falhando`."""
    agora = agora or _agora()
    cfg = obter_configuracao(db, tenant_id)
    base = {"fonte": FONTE, "habilitada_no_ambiente": settings.pncp_habilitado, "configuracao_ativa": bool(cfg and cfg.ativa)}
    if cfg is None or not cfg.ativa:
        return {**base, "estado": "desabilitada"}
    execucoes = db.query(ExecucaoColetaFonte).filter_by(tenant_id=tenant_id, fonte=FONTE)
    ultima = execucoes.order_by(ExecucaoColetaFonte.id.desc()).first()
    concluida = _ultima_concluida(db, tenant_id)
    falhas = _falhas_consecutivas(db, tenant_id)
    if ultima is None:
        estado = "nunca_executada"
    elif falhas >= settings.coleta_falhas_alerta:
        estado = "falhando"
    elif concluida is None or agora - concluida.concluida_em > timedelta(hours=settings.coleta_atraso_horas):
        estado = "atrasada"
    else:
        estado = "saudavel"
    return {
        **base, "estado": estado, "falhas_consecutivas": falhas,
        "ultima_iniciada_em": ultima.iniciada_em if ultima else None,
        "ultima_concluida_em": concluida.concluida_em if concluida else None,
        "cursor_referencia": concluida.cursor_referencia if concluida else None,
        "ultimo_erro": ultima.erro if ultima and ultima.estado == "falhou" else None,
        "ultima_execucao": execucao_dict(ultima) if ultima else None,
    }


def historico(db: Session, tenant_id: str, limite: int = 20) -> list[dict]:
    linhas = (
        db.query(ExecucaoColetaFonte).filter_by(tenant_id=tenant_id, fonte=FONTE)
        .order_by(ExecucaoColetaFonte.id.desc()).limit(max(1, min(limite, 100))).all()
    )
    return [execucao_dict(e) for e in linhas]


def execucao_dict(e: ExecucaoColetaFonte) -> dict:
    return {
        "id": e.id, "fonte": e.fonte, "disparo": e.disparo, "estado": e.estado, "iniciada_em": e.iniciada_em,
        "concluida_em": e.concluida_em, "duracao_ms": e.duracao_ms, "consultados": e.consultados, "inseridos": e.inseridos,
        "atualizados": e.atualizados, "alterados_na_fonte": e.alterados_na_fonte, "ignorados": e.ignorados, "paginas": e.paginas, "tentativas": e.tentativas,
        "erro": e.erro, "data_inicial": e.data_inicial, "data_final": e.data_final, "cursor_referencia": e.cursor_referencia,
    }


def configuracao_dict(cfg: ConfiguracaoColetaFonte | None) -> dict:
    if cfg is None:
        return {"fonte": FONTE, "ativa": False, "modalidades": [], "ufs": [], "palavras_chave": [], "janela_dias": 2,
                "max_novas_por_execucao": 200}
    return {"fonte": cfg.fonte, "ativa": cfg.ativa, "modalidades": cfg.modalidades, "ufs": cfg.ufs,
            "palavras_chave": cfg.palavras_chave, "janela_dias": cfg.janela_dias,
            "max_novas_por_execucao": cfg.max_novas_por_execucao}
