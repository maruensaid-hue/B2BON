from datetime import UTC, date, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.custo_aquisicao import CustoAquisicao
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.usuario import Usuario
from app.services import auditoria_service, panel_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

# Padrão recomendado, não decisão comercial fechada — configurável depois
# via definir_estagio (mesma regra de sempre para o que é do negócio do
# assinante, não do PREDATOR).
_ESTAGIOS_PADRAO = [
    ("Descoberta", 1, "aberto"),
    ("Proposta", 2, "aberto"),
    ("Negociação", 3, "aberto"),
    ("Ganho", 4, "ganho"),
    ("Perdido", 5, "perdido"),
]
_TIPOS_ESTAGIO_VALIDOS = {"aberto", "ganho", "perdido"}
_PERIODO_PADRAO_DIAS = 30


def garantir_estagios_padrao(db: Session, tenant_id: str) -> list[EstagioFunil]:
    """Semeia o funil padrão na primeira vez que o tenant usa o CRM (Onda B).

    Duas chamadas concorrentes (duas abas abrindo o CRM ao mesmo tempo no
    primeiro uso) podem ambas ver a tabela vazia e tentar inserir — a
    UniqueConstraint(tenant_id, ordem) do modelo garante que só uma
    vence; a outra recua e relê o que já foi gravado, em vez de duplicar.
    """
    estagios = db.query(EstagioFunil).filter_by(tenant_id=tenant_id).order_by(EstagioFunil.ordem).all()
    if estagios:
        return estagios
    for nome, ordem, tipo in _ESTAGIOS_PADRAO:
        db.add(EstagioFunil(tenant_id=tenant_id, nome=nome, ordem=ordem, tipo=tipo))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return db.query(EstagioFunil).filter_by(tenant_id=tenant_id).order_by(EstagioFunil.ordem).all()


def listar_estagios(db: Session, tenant_id: str) -> list[EstagioFunil]:
    return garantir_estagios_padrao(db, tenant_id)


def definir_estagio(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    estagio_id: int,
    nome: str | None = None,
    ordem: int | None = None,
    tipo: str | None = None,
) -> EstagioFunil:
    estagio = db.query(EstagioFunil).filter_by(id=estagio_id, tenant_id=tenant_id).one_or_none()
    if estagio is None:
        raise NaoEncontrado(f"Estágio {estagio_id} não encontrado")

    if nome is not None:
        estagio.nome = nome
    if ordem is not None:
        estagio.ordem = ordem
    if tipo is not None:
        if tipo not in _TIPOS_ESTAGIO_VALIDOS:
            raise ValidacaoFalhou(f"Tipo de estágio inválido: {tipo}")
        estagio.tipo = tipo

    auditoria_service.registrar(db, tenant_id, "estagio_funil_atualizado", "estagio_funil", estagio.id, ator_id, {})
    db.commit()
    db.refresh(estagio)
    return estagio


def obter_negocio(db: Session, tenant_id: str, negocio_id: int) -> Negocio:
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")
    return negocio


def listar_negocios(
    db: Session, tenant_id: str, estagio_id: int | None = None, vendedor_usuario_id: int | None = None
) -> list[Negocio]:
    query = db.query(Negocio).filter_by(tenant_id=tenant_id)
    if estagio_id is not None:
        query = query.filter_by(estagio_id=estagio_id)
    if vendedor_usuario_id is not None:
        query = query.filter_by(vendedor_usuario_id=vendedor_usuario_id)
    return query.order_by(Negocio.id.desc()).all()


def criar_negocio(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    nome: str,
    valor: float = 0.0,
    probabilidade: int = 50,
    vendedor_usuario_id: int | None = None,
    estagio_id: int | None = None,
) -> Negocio:
    """Cadastro manual de negócio (origem="manual") — direto pelo vendedor,
    sem passar pelo PREDATOR (Onda B)."""
    if db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")

    if estagio_id is None:
        estagios = garantir_estagios_padrao(db, tenant_id)
        primeiro_aberto = next((e for e in estagios if e.tipo == "aberto"), estagios[0])
        estagio_id = primeiro_aberto.id
    elif db.query(EstagioFunil).filter_by(id=estagio_id, tenant_id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Estágio {estagio_id} não encontrado")

    negocio = Negocio(
        tenant_id=tenant_id,
        conta_id=conta_id,
        nome=nome,
        valor=valor,
        probabilidade=probabilidade,
        vendedor_usuario_id=vendedor_usuario_id,
        estagio_id=estagio_id,
        origem="manual",
    )
    db.add(negocio)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "negocio_criado", "negocio", negocio.id, ator_id, {"conta_id": conta_id}, conta_id=conta_id
    )
    db.commit()
    db.refresh(negocio)
    return negocio


def atualizar_negocio(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    negocio_id: int,
    nome: str,
    valor: float,
    probabilidade: int,
) -> Negocio:
    """Edição pós-criação (nome/valor/probabilidade) — não havia como
    corrigir um negócio depois de cadastrado, só mover de estágio."""
    negocio = obter_negocio(db, tenant_id, negocio_id)
    negocio.nome = nome
    negocio.valor = valor
    negocio.probabilidade = probabilidade

    auditoria_service.registrar(
        db, tenant_id, "negocio_atualizado", "negocio", negocio.id, ator_id, {"nome": nome}, conta_id=negocio.conta_id
    )
    db.commit()
    db.refresh(negocio)
    return negocio


def mover_estagio(
    db: Session, tenant_id: str, ator_id: str | None, negocio_id: int, novo_estagio_id: int, motivo_perda: str | None = None
) -> Negocio:
    """"Arrastar no kanban" (Onda B): ao entrar num estágio tipo "ganho",
    marca a conta como cliente (só na primeira vez); ao entrar em
    "perdido", grava o motivo."""
    negocio = obter_negocio(db, tenant_id, negocio_id)
    novo_estagio = db.query(EstagioFunil).filter_by(id=novo_estagio_id, tenant_id=tenant_id).one_or_none()
    if novo_estagio is None:
        raise NaoEncontrado(f"Estágio {novo_estagio_id} não encontrado")

    negocio.estagio_id = novo_estagio.id

    if novo_estagio.tipo == "ganho":
        if negocio.ganho_em is None:
            negocio.ganho_em = datetime.now(UTC)
        conta = db.query(Conta).filter_by(id=negocio.conta_id).one()
        if conta.cliente_desde is None:
            conta.cliente_desde = datetime.now(UTC)
    elif novo_estagio.tipo == "perdido":
        if negocio.perdido_em is None:
            negocio.perdido_em = datetime.now(UTC)
        negocio.motivo_perda = motivo_perda

    auditoria_service.registrar(
        db,
        tenant_id,
        "negocio_estagio_alterado",
        "negocio",
        negocio.id,
        ator_id,
        {"novo_estagio": novo_estagio.nome, "tipo": novo_estagio.tipo},
        conta_id=negocio.conta_id,
    )
    db.commit()
    db.refresh(negocio)
    return negocio


def registrar_atividade(
    db: Session, tenant_id: str, ator_id: str | None, negocio_id: int, tipo: str, descricao: str
) -> Atividade:
    negocio = obter_negocio(db, tenant_id, negocio_id)
    atividade = Atividade(
        tenant_id=tenant_id,
        negocio_id=negocio.id,
        usuario_id=int(ator_id) if ator_id else None,
        tipo=tipo,
        descricao=descricao,
    )
    db.add(atividade)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "atividade_registrada", "atividade", atividade.id, ator_id, {"tipo": tipo}, conta_id=negocio.conta_id
    )
    db.commit()
    db.refresh(atividade)
    return atividade


def listar_atividades(db: Session, tenant_id: str, negocio_id: int) -> list[Atividade]:
    obter_negocio(db, tenant_id, negocio_id)  # garante existência/isolamento por tenant
    return (
        db.query(Atividade)
        .filter_by(tenant_id=tenant_id, negocio_id=negocio_id)
        .order_by(Atividade.criado_em)
        .all()
    )


def marcar_cliente_cancelado(db: Session, tenant_id: str, ator_id: str | None, conta_id: int, motivo: str | None) -> Conta:
    """Registra o evento de churn (Onda B)."""
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    if conta.cliente_desde is None:
        raise RegraNegocioViolada("Conta ainda não é cliente (nenhum negócio ganho) — não é possível cancelar.")

    if conta.cliente_cancelado_em is None:
        conta.cliente_cancelado_em = datetime.now(UTC)

    auditoria_service.registrar(
        db, tenant_id, "cliente_cancelado", "conta", conta.id, ator_id, {"motivo": motivo}, conta_id=conta.id
    )
    db.commit()
    db.refresh(conta)
    return conta


def definir_custo_aquisicao(db: Session, tenant_id: str, ator_id: str | None, periodo: str, valor: float) -> CustoAquisicao:
    custo = db.query(CustoAquisicao).filter_by(tenant_id=tenant_id, periodo=periodo).one_or_none()
    if custo is None:
        custo = CustoAquisicao(tenant_id=tenant_id, periodo=periodo, valor=valor)
        db.add(custo)
    else:
        custo.valor = valor

    auditoria_service.registrar(
        db, tenant_id, "custo_aquisicao_definido", "custo_aquisicao", 0, ator_id, {"periodo": periodo, "valor": valor}
    )
    db.commit()
    db.refresh(custo)
    return custo


def obter_custo_aquisicao(db: Session, tenant_id: str, periodo: str) -> CustoAquisicao | None:
    return db.query(CustoAquisicao).filter_by(tenant_id=tenant_id, periodo=periodo).one_or_none()


def _periodo_padrao(data_inicio: date | None, data_fim: date | None) -> tuple[date, date]:
    fim = data_fim or date.today()
    inicio = data_inicio or (fim - timedelta(days=_PERIODO_PADRAO_DIAS))
    return inicio, fim


def _no_periodo(momento: datetime | None, inicio: date, fim: date) -> bool:
    if momento is None:
        return False
    return inicio <= momento.date() <= fim


def dashboard_funil(db: Session, tenant_id: str, data_inicio: date | None = None, data_fim: date | None = None) -> dict:
    """Contagem/valor por estágio e taxa de conversão do período (Onda B)."""
    inicio, fim = _periodo_padrao(data_inicio, data_fim)
    estagios = garantir_estagios_padrao(db, tenant_id)
    negocios = db.query(Negocio).filter_by(tenant_id=tenant_id).all()
    negocios_periodo = [n for n in negocios if _no_periodo(n.criado_em, inicio, fim)]

    resumo = []
    for estagio in estagios:
        do_estagio = [n for n in negocios_periodo if n.estagio_id == estagio.id]
        resumo.append(
            {
                "estagio_id": estagio.id,
                "nome": estagio.nome,
                "tipo": estagio.tipo,
                "quantidade": len(do_estagio),
                "valor_total": sum(n.valor for n in do_estagio),
            }
        )

    ids_ganho = {e.id for e in estagios if e.tipo == "ganho"}
    total = len(negocios_periodo)
    ganhos = sum(1 for n in negocios_periodo if n.estagio_id in ids_ganho)
    taxa_conversao = ganhos / total if total else None

    return {
        "periodo_inicio": inicio.isoformat(),
        "periodo_fim": fim.isoformat(),
        "estagios": resumo,
        "taxa_conversao": taxa_conversao,
    }


def dashboard_atividade(db: Session, tenant_id: str, data_inicio: date | None = None, data_fim: date | None = None) -> dict:
    """Atividade por vendedor e por equipe (Onda B)."""
    inicio, fim = _periodo_padrao(data_inicio, data_fim)
    atividades = db.query(Atividade).filter_by(tenant_id=tenant_id).all()
    atividades_periodo = [a for a in atividades if _no_periodo(a.criado_em, inicio, fim) and a.usuario_id is not None]

    contagem: dict[int, int] = {}
    for atividade in atividades_periodo:
        contagem[atividade.usuario_id] = contagem.get(atividade.usuario_id, 0) + 1

    por_vendedor = []
    for usuario_id, quantidade in contagem.items():
        usuario = db.query(Usuario).filter_by(id=usuario_id).one_or_none()
        por_vendedor.append(
            {"usuario_id": usuario_id, "nome": usuario.nome if usuario else "Desconhecido", "quantidade": quantidade}
        )
    por_vendedor.sort(key=lambda item: item["quantidade"], reverse=True)

    return {
        "periodo_inicio": inicio.isoformat(),
        "periodo_fim": fim.isoformat(),
        "por_vendedor": por_vendedor,
        "total_equipe": len(atividades_periodo),
    }


def dashboard_economia(db: Session, tenant_id: str, periodo: str) -> dict:
    """LTV médio, CAC e taxa de churn do período "YYYY-MM" (Onda B)."""
    ano, mes = (int(parte) for parte in periodo.split("-"))
    inicio_periodo = date(ano, mes, 1)
    proximo_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    fim_periodo = proximo_mes - timedelta(days=1)

    contas = db.query(Conta).filter_by(tenant_id=tenant_id).all()
    contas_clientes = [conta for conta in contas if conta.cliente_desde is not None]

    estagios = {estagio.id: estagio for estagio in garantir_estagios_padrao(db, tenant_id)}
    negocios = db.query(Negocio).filter_by(tenant_id=tenant_id).all()
    valor_ganho_por_conta: dict[int, float] = {}
    for negocio in negocios:
        estagio = estagios.get(negocio.estagio_id)
        if estagio and estagio.tipo == "ganho":
            valor_ganho_por_conta[negocio.conta_id] = valor_ganho_por_conta.get(negocio.conta_id, 0.0) + negocio.valor
    ltv_medio = (sum(valor_ganho_por_conta.values()) / len(contas_clientes)) if contas_clientes else None

    novos_clientes = [
        conta for conta in contas_clientes if inicio_periodo <= conta.cliente_desde.date() <= fim_periodo
    ]

    custo = obter_custo_aquisicao(db, tenant_id, periodo)
    cac = (custo.valor / len(novos_clientes)) if custo and novos_clientes else None

    ativos_inicio = [
        conta
        for conta in contas_clientes
        if conta.cliente_desde.date() < inicio_periodo
        and (conta.cliente_cancelado_em is None or conta.cliente_cancelado_em.date() >= inicio_periodo)
    ]
    cancelados_periodo = [
        conta
        for conta in contas_clientes
        if conta.cliente_cancelado_em and inicio_periodo <= conta.cliente_cancelado_em.date() <= fim_periodo
    ]
    taxa_churn = (len(cancelados_periodo) / len(ativos_inicio)) if ativos_inicio else None

    return {
        "periodo": periodo,
        "ltv_medio": ltv_medio,
        "cac": cac,
        "taxa_churn": taxa_churn,
        "novos_clientes": len(novos_clientes),
        "clientes_ativos_inicio_periodo": len(ativos_inicio),
        "clientes_cancelados_periodo": len(cancelados_periodo),
    }


def dashboard_flywheel(db: Session, tenant_id: str) -> dict:
    """Ponto de encontro CRM (novo) + PREDATOR (já existente) num único
    payload (Onda B) — a "retroalimentação" pedida."""
    return {
        "metrica_norte": panel_service.metrica_norte(db, tenant_id),
        "indicadores_energia": panel_service.indicadores_energia(db, tenant_id, None, None),
        "indicadores_atrito": panel_service.indicadores_atrito(db, tenant_id, None, None),
        "funil": dashboard_funil(db, tenant_id),
    }
