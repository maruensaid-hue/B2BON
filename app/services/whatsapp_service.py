from sqlalchemy.orm import Session

from app.models.template_whatsapp import TemplateWhatsApp
from app.providers.channels.whatsapp.base import WhatsAppProvider


def sincronizar_templates(db: Session, tenant_id: str, provider: WhatsAppProvider) -> list[TemplateWhatsApp]:
    """Status de aprovação visível (E3-H2): sincroniza os templates do
    provedor para o cache local."""
    resultado: list[TemplateWhatsApp] = []
    for info in provider.listar_templates():
        existente = db.query(TemplateWhatsApp).filter_by(tenant_id=tenant_id, nome=info.nome).one_or_none()
        if existente is None:
            existente = TemplateWhatsApp(tenant_id=tenant_id, nome=info.nome, corpo=info.corpo, status=info.status)
            db.add(existente)
        else:
            existente.corpo = info.corpo
            existente.status = info.status
        resultado.append(existente)

    db.commit()
    for template in resultado:
        db.refresh(template)
    return resultado
