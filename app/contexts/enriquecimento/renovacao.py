"""Renovação mensal das franquias de enriquecimento (rotina agendada).

A franquia também é concedida sob demanda (`ledger.preparar` ao abrir o painel ou pesquisar); esta rotina garante que a renovação e a expiração do mês
aconteçam e fiquem registradas no razão mesmo para quem não abriu nada. É idempotente: rodar de novo no mesmo ciclo não duplica concessão (chave
`franquia:AAAA-MM`) nem expiração (`expiracao:<id>`). Um tenant com defeito não impede os demais."""

import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config, ledger
from app.models.enriquecimento_creditos import EnriquecimentoCarteira, EnriquecimentoMovimento
from app.models.licenca import Licenca

logger = logging.getLogger("b2bon.enriquecimento")


def _franquias_concedidas(db: Session, tenant_id: str) -> int:
    return db.query(func.count(EnriquecimentoMovimento.id)).filter(
        EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.origem == "franquia",
        EnriquecimentoMovimento.tipo.in_(("CONCESSAO", "RENOVACAO"))).scalar() or 0


def renovar_todos(db: Session, agora: datetime | None = None) -> dict:
    """Expira o que venceu e concede a franquia do mês de todo tenant que tem carteira de enriquecimento ou licença ativa com configuração aprovada."""
    agora = agora or config.agora_utc()
    candidatos = {t for (t,) in db.query(EnriquecimentoCarteira.tenant_id).all()}
    candidatos |= {t for (t,) in db.query(Licenca.tenant_id).filter(Licenca.status == "ativa").all()}
    resumo = {"tenants": 0, "franquias_concedidas": 0, "creditos_expirados": 0, "sem_configuracao": 0, "erros": 0}
    for tenant_id in sorted(candidatos):
        try:
            cfg, _ = config.config_vigente(db, tenant_id)
            tinha_carteira = db.query(EnriquecimentoCarteira.id).filter_by(tenant_id=tenant_id).first() is not None
            if cfg is None and not tinha_carteira:
                resumo["sem_configuracao"] += 1
                continue
            ledger.travar_carteira(db, tenant_id)
            franquias_antes = _franquias_concedidas(db, tenant_id)
            expirados = ledger.expirar_vencidos(db, tenant_id, agora)
            if cfg is not None and cfg.utilizavel:
                ledger.garantir_franquia(db, tenant_id, cfg, agora)
            db.commit()
            resumo["tenants"] += 1
            resumo["creditos_expirados"] += expirados
            resumo["franquias_concedidas"] += _franquias_concedidas(db, tenant_id) - franquias_antes
        except Exception:  # noqa: BLE001 - um tenant com defeito não pode travar a renovação dos demais
            db.rollback()
            resumo["erros"] += 1
            logger.exception("ENRIQUECIMENTO_RENOVACAO_FALHOU tenant=%s", tenant_id)
    return resumo
