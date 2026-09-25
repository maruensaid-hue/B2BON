from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.intelligence import contract as intel
from app.contexts.map import contract as map_contract
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.interacao_conta import InteracaoConta
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auditoria_service, tenant_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

_TIPOS_VALIDOS = map_contract.TIPOS_INTERACAO_VALIDOS


def _obter_conta(db: Session, usuario: Usuario, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id).one_or_none()
    if conta is None or conta.tenant_id not in tenant_service.tenant_ids_no_escopo(db, usuario, None):
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return conta


def registrar_interacao(
    db: Session, usuario: Usuario, ator_id: str | None, conta_id: int, tipo: str, descricao: str | None = None
) -> InteracaoConta:
    if tipo not in _TIPOS_VALIDOS:
        raise ValidacaoFalhou(f"Tipo de interação inválido: {tipo}")
    conta = _obter_conta(db, usuario, conta_id)

    interacao = InteracaoConta(
        tenant_id=conta.tenant_id,
        conta_id=conta_id,
        tipo=tipo,
        descricao=descricao,
        criado_por_usuario_id=int(ator_id) if ator_id else None,
    )
    db.add(interacao)
    db.flush()

    auditoria_service.registrar(
        db, conta.tenant_id, "interacao_conta_registrada", "interacao_conta", interacao.id, ator_id, {"tipo": tipo},
        conta_id=conta_id,
    )
    db.commit()
    db.refresh(interacao)
    return interacao


def listar_interacoes_da_conta(db: Session, usuario: Usuario, conta_id: int) -> list[InteracaoConta]:
    conta = _obter_conta(db, usuario, conta_id)
    return listar_interacoes(db, conta.tenant_id, conta_id)


def listar_interacoes(db: Session, tenant_id: str, conta_id: int) -> list[InteracaoConta]:
    return map_contract.listar_interacoes(db, tenant_id, conta_id)


def calcular_score_risco(db: Session, usuario: Usuario, conta_id: int) -> dict:
    """Mesma metodologia de `motor_service.calcular_score_risco`, agora
    sobre uma conta (cliente/prospect) em vez de um tenant assinante."""
    conta = _obter_conta(db, usuario, conta_id)
    return calcular_score_risco_da_conta(db, conta)


def calcular_score_risco_da_conta(db: Session, conta: Conta) -> dict:
    """Núcleo do cálculo — no contexto MAP desde a Fase 1
    (`app/contexts/map/saude.py`)."""
    return map_contract.score_risco_conta(db, conta)


def _contas_visiveis(
    db: Session, usuario: Usuario, vendedor_usuario_id: int | None, tenant_id_selecionado: str | None = None
) -> list[Conta]:
    """Escopo por papel: user só vê as contas em que é o vendedor
    responsável (só no próprio tenant); admin/super_admin veem todas as
    contas da própria subárvore de tenants (raio-X 2026-09-10 — antes só
    do próprio tenant) e podem filtrar por vendedor ou "dar zoom" num
    tenant específico dessa subárvore. Um `user` pedindo o filtro de
    outra pessoa é ignorado — a query já trava nele mesmo, não é um 403
    (a intenção não é maliciosa, é só a tela não ter essa opção pra esse
    papel)."""
    tenant_ids = tenant_service.tenant_ids_no_escopo(db, usuario, tenant_id_selecionado)
    query = db.query(Conta).filter(Conta.tenant_id.in_(tenant_ids))
    if usuario.papel == "user":
        query = query.filter_by(vendedor_usuario_id=usuario.id)
    elif vendedor_usuario_id is not None:
        query = query.filter_by(vendedor_usuario_id=vendedor_usuario_id)
    return query.order_by(Conta.id).all()


def ranking_saude_contas(
    db: Session,
    usuario: Usuario,
    vendedor_usuario_id: int | None = None,
    tenant_id_selecionado: str | None = None,
) -> list[dict]:
    contas = _contas_visiveis(db, usuario, vendedor_usuario_id, tenant_id_selecionado)
    # Lote (Fase 7B, hardening) — antes buscava um `Usuario` por conta
    # dentro do loop; `tenant_nomes` já memoizava do jeito certo duas
    # linhas abaixo, só o vendedor tinha ficado de fora.
    ids_vendedores = {conta.vendedor_usuario_id for conta in contas if conta.vendedor_usuario_id is not None}
    vendedores_por_id = {
        usuario_vendedor.id: usuario_vendedor
        for usuario_vendedor in db.query(Usuario).filter(Usuario.id.in_(ids_vendedores)).all()
    } if ids_vendedores else {}
    tenant_nomes: dict[str, str] = {}
    resultado = []
    for conta in contas:
        risco = calcular_score_risco_da_conta(db, conta)
        vendedor = vendedores_por_id.get(conta.vendedor_usuario_id) if conta.vendedor_usuario_id else None
        soma_pipeline_aberto = _valor_pipeline_aberto(db, conta.tenant_id, conta.id)
        if conta.tenant_id not in tenant_nomes:
            tenant = db.query(Tenant).filter_by(id=conta.tenant_id).one_or_none()
            tenant_nomes[conta.tenant_id] = tenant.razao_social if tenant else conta.tenant_id
        resultado.append(
            {
                "conta_id": conta.id,
                "nome": conta.nome,
                "nome_fantasia": conta.nome_fantasia,
                "tenant_id": conta.tenant_id,
                "tenant_nome": tenant_nomes[conta.tenant_id],
                "vendedor_usuario_id": conta.vendedor_usuario_id,
                "vendedor_nome": vendedor.nome if vendedor else None,
                "score": risco["score"],
                "classificacao": risco["classificacao"],
                "valor_pipeline_aberto": soma_pipeline_aberto,
            }
        )
    resultado.sort(key=lambda item: item["score"], reverse=True)
    return resultado


def _valor_pipeline_aberto(db: Session, tenant_id: str, conta_id: int) -> float:
    return map_contract.valor_pipeline_aberto(db, tenant_id, conta_id)


def dashboard_saude_contas(
    db: Session,
    usuario: Usuario,
    vendedor_usuario_id: int | None = None,
    tenant_id_selecionado: str | None = None,
) -> dict:
    ranking = ranking_saude_contas(db, usuario, vendedor_usuario_id, tenant_id_selecionado)
    total = len(ranking)

    # CS Score/ROI ficam escopados a um único tenant (o selecionado, ou o
    # do próprio usuário sem seleção) — `map_contract.cs_score`
    # e a economia do MAP são inerentemente de um tenant só
    # (NPS e negócios não têm por que ser somados entre tenants
    # diferentes da hierarquia); só as contagens de `ranking` acima é que
    # de fato agregam a subárvore inteira.
    tenant_id_metricas = tenant_id_selecionado or usuario.tenant_id
    cs = map_contract.cs_score(
        db,
        tenant_id_metricas,
        conta_ids=[item["conta_id"] for item in ranking if item["tenant_id"] == tenant_id_metricas],
        scores_risco=[item["score"] for item in ranking if item["tenant_id"] == tenant_id_metricas],
    )

    periodo_atual = datetime.now(UTC).strftime("%Y-%m")
    roi = map_contract.economia(db, tenant_id_metricas, periodo_atual).get("roi")

    return {
        "score_medio": (sum(item["score"] for item in ranking) / total) if total else None,
        "total_contas": total,
        "criticas": sum(1 for item in ranking if item["classificacao"] == "critico"),
        "atencao": sum(1 for item in ranking if item["classificacao"] == "atencao"),
        "saudaveis": sum(1 for item in ranking if item["classificacao"] == "saudavel"),
        "valor_total_em_risco": sum(
            item["valor_pipeline_aberto"] for item in ranking if item["classificacao"] != "saudavel"
        ),
        "roi": roi,
        "cs_score": cs["cs_score"],
        "nps_medio": cs["nps_medio"],
    }


def gerar_script_resgate(db: Session, usuario: Usuario, conta_id: int, llm: LLMProvider) -> dict:
    conta = _obter_conta(db, usuario, conta_id)
    risco = calcular_score_risco_da_conta(db, conta)
    interacoes = listar_interacoes(db, conta.tenant_id, conta_id)[:5]
    decisor = db.query(Decisor).filter_by(conta_id=conta_id).order_by(Decisor.id).first()

    resumo_sinais = ", ".join(f"{tipo}: +{pontos}" for tipo, pontos in risco["sinais"].items()) or "nenhum sinal negativo recente"
    historico = "\n".join(f"- {i.tipo} ({i.criado_em:%Y-%m-%d}): {i.descricao or ''}" for i in interacoes) or "sem interações registradas"
    contexto_decisor = f" O contato principal é {decisor.nome} ({decisor.cargo or 'decisor'})." if decisor else ""

    resposta = intel.gerar(
        db,
        llm,
        intel.ContextoIA(tenant_id=conta.tenant_id, feature="map.script_resgate_conta", usuario_id=usuario.id, entidade_tipo="conta", entidade_id=conta.id),
        LLMRequest(
            prompt=(
                f"A conta '{conta.nome_fantasia or conta.nome}' está classificada como "
                f"'{risco['classificacao']}' (score de risco {risco['score']}/100) na carteira de um vendedor."
                f"{contexto_decisor} Sinais que elevaram o score: {resumo_sinais}. "
                f"Dias sem contato: {risco['dias_sem_contato']}. "
                f"Últimas interações registradas:\n{historico}\n\n"
                "Escreva uma mensagem curta e direta que o vendedor possa enviar a este cliente para "
                "reengajar e reduzir o risco de perder o negócio."
            ),
            system="Você ajuda um vendedor B2B a redigir mensagens de resgate de clientes/negócios em risco.",
        ),
    )

    return {
        "conta_id": conta_id,
        "script": resposta.content,
        "justificativa": f"Classificação '{risco['classificacao']}' com sinais: {resumo_sinais}.",
    }


def listar_vendedores_disponiveis(db: Session, usuario: Usuario, conta_id: int) -> list[Usuario]:
    """Vendedores atribuíveis a esta conta: qualquer usuário ativo da
    subárvore de tenants visível a quem chama, não só do tenant exato da
    conta (raio-X 2026-09-11: pra este uso da hierarquia, os sub-tenants
    são estrutura interna do próprio time do Admin — matriz/filial —, não
    clientes pagantes separados, então um vendedor de qualquer tenant
    dessa subárvore deve poder ser atribuído a uma conta de outro tenant
    da mesma subárvore; antes o campo "Vendedor responsável" usava
    `GET /usuarios`, escopado só ao tenant do chamador, e nem achava
    vendedores de outros tenants da própria subárvore). `_obter_conta` já
    garante que a conta está dentro desse escopo."""
    _obter_conta(db, usuario, conta_id)
    tenant_ids = tenant_service.tenant_ids_no_escopo(db, usuario, None)
    return (
        db.query(Usuario)
        .filter(Usuario.tenant_id.in_(tenant_ids), Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
        .all()
    )


def atribuir_vendedor(
    db: Session, usuario: Usuario, ator_id: str | None, conta_id: int, vendedor_usuario_id: int | None
) -> Conta:
    conta = _obter_conta(db, usuario, conta_id)
    if vendedor_usuario_id is not None:
        # Qualquer tenant da subárvore visível a quem chama, não só o
        # tenant exato da conta (raio-X 2026-09-11, mesmo motivo de
        # `listar_vendedores_disponiveis` acima).
        tenant_ids = tenant_service.tenant_ids_no_escopo(db, usuario, None)
        vendedor = (
            db.query(Usuario)
            .filter(Usuario.id == vendedor_usuario_id, Usuario.tenant_id.in_(tenant_ids))
            .one_or_none()
        )
        if vendedor is None:
            raise NaoEncontrado(f"Usuário {vendedor_usuario_id} não encontrado neste tenant")

    conta.vendedor_usuario_id = vendedor_usuario_id
    auditoria_service.registrar(
        db, conta.tenant_id, "conta_vendedor_atribuido", "conta", conta.id, ator_id,
        {"vendedor_usuario_id": vendedor_usuario_id}, conta_id=conta.id,
    )
    db.commit()
    db.refresh(conta)
    return conta
