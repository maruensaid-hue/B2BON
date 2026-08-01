from sqlalchemy.orm import Session

from app.models.faq_item import FaqItem


def criar(db: Session, tenant_id: str, pergunta: str, resposta: str) -> FaqItem:
    item = FaqItem(tenant_id=tenant_id, pergunta=pergunta, resposta=resposta)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def listar(db: Session, tenant_id: str) -> list[FaqItem]:
    return db.query(FaqItem).filter_by(tenant_id=tenant_id).order_by(FaqItem.id).all()
