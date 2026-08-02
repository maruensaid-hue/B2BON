from sqlalchemy.orm import Session

from app.models.licenca import Licenca
from app.models.plano import Plano
from app.providers.plan_limits.base import PlanLimitsProvider


class NucleoPlanLimitsProvider(PlanLimitsProvider):
    """Implementação real da porta de franquia — lê a licença ativa e o
    plano do próprio núcleo B2B ON (Onda A), agora que ambos existem na
    mesma base do PREDATOR (regra de fronteira encerrada para esta porta)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def obter_franquia_contas_mes(self, tenant_id: str) -> int:
        licenca = self._db.query(Licenca).filter_by(tenant_id=tenant_id, status="ativa").one_or_none()
        if licenca is None:
            return 0
        plano = self._db.query(Plano).filter_by(id=licenca.plano_id).one_or_none()
        return plano.franquia_contas_mes if plano else 0
