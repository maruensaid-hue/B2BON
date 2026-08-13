from sqlalchemy.orm import Session

from app.models.atividade import Atividade
from app.services.errors import ValidacaoFalhou


def registrar(
    db: Session,
    tenant_id: str,
    *,
    conta_id: int | None = None,
    negocio_id: int | None = None,
    tipo: str,
    descricao: str,
    ator_id: str | None = None,
) -> Atividade:
    """Registra um evento na timeline — de uma conta, de um negócio, ou dos
    dois. Só `add`+`flush` de propósito: é chamado de dentro da transação
    de quem já vai comitar (mapear_decisores, mover_estagio etc.), nunca
    comita sozinho.

    `usuario_id=None` (quando `ator_id` não é passado) marca um evento sem
    humano nenhum por trás (ex.: disparo de cadência/campanha via cron);
    quando um vendedor clicou em algo — mesmo que quem tenha feito o
    trabalho pesado seja a IA, como "Mapear decisores" — `ator_id` vem
    preenchido e conta para a métrica de atividade por vendedor."""
    if conta_id is None and negocio_id is None:
        raise ValidacaoFalhou("Atividade precisa estar ligada a uma conta e/ou a um negócio.")

    atividade = Atividade(
        tenant_id=tenant_id,
        conta_id=conta_id,
        negocio_id=negocio_id,
        usuario_id=int(ator_id) if ator_id else None,
        tipo=tipo,
        descricao=descricao,
    )
    db.add(atividade)
    db.flush()
    return atividade


def listar_por_conta(db: Session, tenant_id: str, conta_id: int) -> list[Atividade]:
    # Desempate por id: `criado_em` tem granularidade de segundo em alguns
    # bancos, então duas atividades da mesma leva (ex.: reuniao confirmada
    # + negócio criado, ambas no mesmo request) podem empatar no timestamp.
    return (
        db.query(Atividade)
        .filter_by(tenant_id=tenant_id, conta_id=conta_id)
        .order_by(Atividade.criado_em.desc(), Atividade.id.desc())
        .all()
    )
