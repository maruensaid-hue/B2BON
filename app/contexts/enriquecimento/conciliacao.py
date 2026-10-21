"""Conciliação do razão com o uso informado pelo próprio provedor (`GET /v3/account/usage` na Lusha).

Cada leitura guarda os créditos usados segundo o provedor e compara a variação desde a leitura anterior com os créditos do provedor lançados
como consumo no razão no mesmo intervalo. Diferença ≠ 0 é divergência: vira alerta (log de erro, destaque no painel administrativo) e exige
investigação — pode ser pesquisa ambígua ainda não reconciliada, uso da conta fora do B2B ON ou virada de ciclo do provedor. Nada é ajustado
automaticamente."""

import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento.config import agora_utc
from app.models.enriquecimento_creditos import EnriquecimentoMovimento, EnriquecimentoUsoProvedor
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.services import auditoria_service
from app.services.errors import PesquisaBloqueada

logger = logging.getLogger("b2bon.enriquecimento")


def _leitura(provider: ContactEnrichmentProvider):
    try:
        return provider.consultar_uso()
    except NotImplementedError:
        raise PesquisaBloqueada("Este provedor não informa o próprio uso, então não há como conciliar automaticamente.",
                                "provedor_sem_consulta_de_uso") from None
    except Exception:  # noqa: BLE001 — a mensagem do provedor/da rede pode conter detalhes; o log guarda o rastro
        logger.exception("ENRIQUECIMENTO_FALHA_CONSULTA_USO provedor=%s", provider.nome_provedor)
        raise PesquisaBloqueada("Não foi possível consultar o uso no provedor agora. Tente novamente em instantes.",
                                "falha_consulta_uso_provedor") from None


def tarifas_do_provedor(provider: ContactEnrichmentProvider) -> dict:
    """Tarifas por ação, como o PRÓPRIO provedor publica, para o administrador conferir antes de aprovar a política. Só leitura: nada é gravado."""
    uso = _leitura(provider)
    return {"provedor": provider.nome_provedor, "tarifas": uso.tarifas}


def conciliar(db: Session, provider: ContactEnrichmentProvider, ator_id: str | None, tenant_auditoria: str, agora: datetime | None = None) -> dict:
    agora = agora or agora_utc()
    uso = _leitura(provider)
    anterior = (
        db.query(EnriquecimentoUsoProvedor).filter_by(provedor=provider.nome_provedor).order_by(EnriquecimentoUsoProvedor.id.desc()).first()
    )
    delta_provedor = delta_razao = divergencia = None
    if anterior is not None and anterior.creditos_usados is not None and uso.creditos_usados is not None:
        delta_provedor = uso.creditos_usados - anterior.creditos_usados
        delta_razao = int(db.query(func.coalesce(func.sum(EnriquecimentoMovimento.provedor_delta_consumido), 0)).filter(
            EnriquecimentoMovimento.provedor == provider.nome_provedor, EnriquecimentoMovimento.criado_em > anterior.lido_em,
            EnriquecimentoMovimento.criado_em <= agora).scalar() or 0)
        divergencia = delta_provedor - delta_razao
    leitura = EnriquecimentoUsoProvedor(
        provedor=provider.nome_provedor, lido_em=agora, lido_por=ator_id, creditos_total=uso.creditos_total, creditos_usados=uso.creditos_usados,
        creditos_restantes=uso.creditos_restantes, anterior_id=anterior.id if anterior else None, delta_provedor=delta_provedor, delta_razao=delta_razao,
        divergencia=divergencia,
    )
    db.add(leitura)
    db.flush()
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_conciliacao_provedor", "enriquecimento_uso_provedor", leitura.id, ator_id,
                                {"provedor": provider.nome_provedor, "usados": uso.creditos_usados, "delta_provedor": delta_provedor,
                                 "delta_razao": delta_razao, "divergencia": divergencia})
    db.commit()
    if divergencia:
        logger.error("ENRIQUECIMENTO_DIVERGENCIA_PROVEDOR provedor=%s delta_provedor=%s delta_razao=%s divergencia=%s", provider.nome_provedor,
                     delta_provedor, delta_razao, divergencia)
    return serializar(leitura)


def serializar(leitura: EnriquecimentoUsoProvedor) -> dict:
    explicacao = None
    if leitura.divergencia is None:
        explicacao = "Primeira leitura (ou sem leitura anterior comparável): sem base de comparação ainda."
    elif leitura.divergencia == 0:
        explicacao = "O uso informado pelo provedor bate com o razão desde a leitura anterior."
    elif leitura.delta_provedor is not None and leitura.delta_provedor < 0:
        explicacao = "O uso do provedor diminuiu: provável virada de ciclo da conta. Confira antes de concluir que há divergência."
    else:
        explicacao = ("Divergência: investigue pesquisas ambíguas ainda não reconciliadas, uso da conta fora do B2B ON ou consumo não lançado "
                      "no razão. Nada foi ajustado automaticamente.")
    return {
        "id": leitura.id, "provedor": leitura.provedor, "lido_em": leitura.lido_em, "creditos_total": leitura.creditos_total,
        "creditos_usados": leitura.creditos_usados, "creditos_restantes": leitura.creditos_restantes, "delta_provedor": leitura.delta_provedor,
        "delta_razao": leitura.delta_razao, "divergencia": leitura.divergencia, "explicacao": explicacao,
    }


def listar(db: Session, provedor: str, limite: int = 20) -> list[dict]:
    leituras = (
        db.query(EnriquecimentoUsoProvedor).filter_by(provedor=provedor).order_by(EnriquecimentoUsoProvedor.id.desc()).limit(min(max(limite, 1), 100)).all()
    )
    return [serializar(leitura) for leitura in leituras]
