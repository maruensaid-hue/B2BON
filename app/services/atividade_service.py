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


def contexto_recentes_texto(
    db: Session, tenant_id: str, *, conta_id: int | None = None, negocio_id: int | None = None, limite: int = 5
) -> str:
    """Context Engine mínimo (master prompt §18-19, Fase 0.5-A) — mesmo
    bloco "últimas atividades" que `crm_service.gerar_meeting_brief` e
    `conta_service.sugerir_estrategia_venda` reimplementavam cada um do
    zero; parametrizado por `conta_id` OU `negocio_id`."""
    query = db.query(Atividade).filter_by(tenant_id=tenant_id)
    if negocio_id is not None:
        query = query.filter_by(negocio_id=negocio_id)
    if conta_id is not None:
        query = query.filter_by(conta_id=conta_id)
    atividades = query.order_by(Atividade.criado_em.desc()).limit(limite).all()
    return "\n".join(
        f"- {atividade.criado_em:%d/%m/%Y} ({atividade.tipo}): {atividade.descricao}" for atividade in atividades
    ) or "Nenhuma atividade registrada ainda."


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
