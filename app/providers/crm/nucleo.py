from sqlalchemy.orm import Session

from app.models.atividade import Atividade
from app.models.negocio import Negocio
from app.providers.crm.base import CrmProvider
from app.services import crm_service


class NucleoCrmProvider(CrmProvider):
    """Implementação real da porta de CRM — grava no núcleo B2B ON, na
    mesma base do PREDATOR (Onda B). Fecha a porta que o PREDATOR já
    tinha desenhado desde a Onda 3 (`reuniao_service.confirmar`,
    `dossie_service.montar_e_anexar`) — nenhuma mudança é necessária
    nesses serviços."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def criar_ou_atualizar_oportunidade(self, tenant_id: str, conta_id: int, dados: dict) -> str:
        negocio = (
            self._db.query(Negocio)
            .filter_by(tenant_id=tenant_id, conta_id=conta_id, origem="predator_reuniao")
            .one_or_none()
        )
        if negocio is None:
            estagios = crm_service.garantir_estagios_padrao(self._db, tenant_id)
            primeiro_aberto = next((e for e in estagios if e.tipo == "aberto"), estagios[0])
            negocio = Negocio(
                tenant_id=tenant_id,
                conta_id=conta_id,
                nome=f"Oportunidade — conta {conta_id}",
                estagio_id=primeiro_aberto.id,
                origem="predator_reuniao",
            )
            self._db.add(negocio)
            self._db.flush()
            self._db.add(
                Atividade(
                    tenant_id=tenant_id,
                    negocio_id=negocio.id,
                    usuario_id=None,
                    tipo="sistema",
                    descricao=f"Oportunidade criada automaticamente pelo PREDATOR ao confirmar reunião. Dados: {dados}",
                )
            )
        self._db.commit()
        self._db.refresh(negocio)
        return str(negocio.id)

    def anexar_nota(self, tenant_id: str, oportunidade_id: str, texto: str) -> None:
        self._db.add(
            Atividade(
                tenant_id=tenant_id,
                negocio_id=int(oportunidade_id),
                usuario_id=None,
                tipo="nota",
                descricao=texto,
            )
        )
        self._db.commit()
