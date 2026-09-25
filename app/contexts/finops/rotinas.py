"""Rotina horária dos AI Credits (Fase 15), chamada por `/cron/creditos-ia`."""

import logging

from sqlalchemy.orm import Session

from app.contexts.finops import carteira, economia, execucoes, limites
from app.models.creditos_ia import LoteCreditos
from app.models.licenca import Licenca

logger = logging.getLogger("b2bon.creditos")


def creditos_ia_rotina(db: Session) -> dict:
    """Idempotente: rodar duas vezes na mesma hora não concede nem expira em dobro."""
    orfas = execucoes.liberar_reservas_orfas(db)
    tenants = {t for (t,) in db.query(Licenca.tenant_id).filter(Licenca.status == "ativa").all()}
    tenants |= {t for (t,) in db.query(LoteCreditos.tenant_id).filter(LoteCreditos.status == "ATIVO").distinct().all()}
    alertas_uso, anomalias, falhas = 0, [], 0
    for tenant_id in sorted(tenants):
        try:
            carteira.preparar(db, tenant_id)
            alertas_uso += len(limites.registrar_alertas(db, tenant_id))
            pico = limites.anomalia_de_consumo(db, tenant_id)
            if pico:
                anomalias.append({"tenant_id": tenant_id, **pico})
            db.commit()
        except Exception:  # um tenant com problema não para a rotina dos demais
            db.rollback()
            falhas += 1
            logger.exception("CREDITOS_ROTINA_FALHA tenant=%s", tenant_id)
    margem = economia.alertas_margem(db)
    for alerta in margem:
        logger.warning("CREDITOS_%s janela=%sd %s=%s margem=%s", alerta["alerta"], alerta["janela_dias"], alerta["dimensao"],
                       alerta["chave"], alerta["margem_bruta"])
    return {"tenants": len(tenants), "reservas_orfas_liberadas": orfas, "alertas_uso": alertas_uso, "anomalias": anomalias,
            "alertas_margem": len(margem), "falhas": falhas}
