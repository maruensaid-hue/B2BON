"""Organization / Person — Shared Kernel (Master Prompt §12).

`Conta` e `Decisor` são escritos por CRM, PREDATOR e Shoal e lidos por
todos os módulos. Este é o contrato de LEITURA que os outros contextos
(MAP primeiro) usam em vez de consultar o ORM do CRM direto. Os DTOs
são imutáveis e não carregam sessão: quem recebe não consegue alterar a
linha por acidente.
"""

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.services.errors import NaoEncontrado


class OrganizationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    # `int` no CRM interno; `str` (id canônico) quando vem de um `CrmAdapter`.
    id: int | str
    tenant_id: str
    nome: str
    nome_fantasia: str | None = None
    cnpj: str | None = None
    dominio: str | None = None
    vendedor_usuario_id: int | str | None = None
    cliente_desde: datetime | None = None
    cliente_cancelado_em: datetime | None = None
    criado_em: datetime | None = None


class PersonRef(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    tenant_id: str
    conta_id: int
    nome: str
    cargo: str | None = None


def listar_organizacoes(
    db: Session, tenant_id: str, vendedor_usuario_id: int | None = None, apenas_com_vendedor: bool = False
) -> list[OrganizationRef]:
    query = db.query(Conta).filter(Conta.tenant_id == tenant_id)
    if vendedor_usuario_id is not None:
        query = query.filter(Conta.vendedor_usuario_id == vendedor_usuario_id)
    elif apenas_com_vendedor:
        query = query.filter(Conta.vendedor_usuario_id.isnot(None))
    return [OrganizationRef.model_validate(conta) for conta in query.order_by(Conta.id).all()]


def contato_principal(db: Session, tenant_id: str, conta_id: int) -> PersonRef | None:
    decisor = (
        db.query(Decisor).filter_by(tenant_id=tenant_id, conta_id=conta_id).order_by(Decisor.id).first()
    )
    return PersonRef.model_validate(decisor) if decisor else None


# --- Escrita / validação (movido de `conta_service` na Fase 1) ---------------
# Usado por qualquer contexto que precise da linha ORM de uma conta do
# próprio tenant antes de alterá-la (CRM, PREDATOR).


def obter_conta(db: Session, tenant_id: str, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return conta


def decisores_da_conta(db: Session, conta_id: int) -> list[Decisor]:
    """Sem filtro de tenant: quem chama já validou a conta com
    `obter_conta` (mesmo contrato de antes da Fase 1)."""
    return db.query(Decisor).filter_by(conta_id=conta_id).all()


def normalizar_dominio(dominio: str | None) -> str | None:
    """Aceita o que a pessoa colar (com ou sem `https://`, com ou sem
    caminho/barra final) e guarda só o host — `site_fetcher` monta a URL
    como `https://{dominio}`, então um valor como `https://empresa.com`
    salvo ao pé da letra virava `https://https://empresa.com` e quebrava
    a busca com erro de DNS (bug real reportado em produção)."""
    if not dominio:
        return None
    texto = dominio.strip()
    if not texto:
        return None
    if "://" not in texto:
        texto = f"//{texto}"
    netloc = urlparse(texto).netloc
    return (netloc or texto.lstrip("/")).rstrip("/") or None
