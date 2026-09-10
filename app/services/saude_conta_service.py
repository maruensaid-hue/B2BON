from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.interacao_conta import InteracaoConta
from app.models.negocio import Negocio
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auditoria_service, llm_helpers, metricas_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

_TIPOS_VALIDOS = {
    "contato",
    "ticket_suporte",
    "reclamacao",
    "feedback_positivo",
    "reuniao_remarcada",
    "mencionou_concorrente",
}
_TIPOS_CONTATO = {"contato", "feedback_positivo"}
_JANELA_SINAIS_DIAS = 30


def _tenant_ids_no_escopo(db: Session, usuario: Usuario, tenant_id_selecionado: str | None) -> list[str]:
    """Mesmo espírito de `relatorio_service._tenant_ids_visiveis`: `user`
    só vê o próprio tenant; admin/super_admin veem a própria subárvore
    (ou tudo, se super_admin) e podem "dar zoom" num tenant específico
    dessa subárvore via `tenant_id_selecionado` (raio-X 2026-09-10 — MAP
    hoje não enxergava sub-tenants, só o tenant do próprio usuário)."""
    from app.services import tenant_service

    if usuario.papel == "user":
        return [usuario.tenant_id]
    visiveis = {t.id for t in tenant_service.listar_tenants_visiveis(db, usuario)}
    if tenant_id_selecionado is not None:
        if tenant_id_selecionado not in visiveis:
            raise NaoAutorizado("Você não tem permissão para ver esse tenant.")
        return [t.id for t in tenant_service.listar_subarvore(db, tenant_id_selecionado)]
    return list(visiveis)


def _obter_conta(db: Session, usuario: Usuario, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id).one_or_none()
    if conta is None or conta.tenant_id not in _tenant_ids_no_escopo(db, usuario, None):
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
    return (
        db.query(InteracaoConta)
        .filter_by(tenant_id=tenant_id, conta_id=conta_id)
        .order_by(InteracaoConta.criado_em.desc())
        .all()
    )


def _classificar(score: float) -> str:
    if score >= settings.limiar_risco_critico_conta:
        return "critico"
    if score >= settings.limiar_risco_atencao_conta:
        return "atencao"
    return "saudavel"


def calcular_score_risco(db: Session, usuario: Usuario, conta_id: int) -> dict:
    """Mesma metodologia de `motor_service.calcular_score_risco`, agora
    sobre uma conta (cliente/prospect) em vez de um tenant assinante."""
    conta = _obter_conta(db, usuario, conta_id)
    return calcular_score_risco_da_conta(db, conta)


def calcular_score_risco_da_conta(db: Session, conta: Conta) -> dict:
    """Núcleo do cálculo, separado de `calcular_score_risco` pra
    `ranking_saude_contas` não repetir a checagem de escopo (e a busca da
    subárvore de tenants) uma vez por conta já visível na listagem."""
    conta_id = conta.id
    interacoes = listar_interacoes(db, conta.tenant_id, conta_id)
    agora = datetime.now(UTC)

    ultimo_contato_em = next((i.criado_em for i in interacoes if i.tipo in _TIPOS_CONTATO), None)
    if ultimo_contato_em is None:
        ultimo_contato_em = conta.criado_em

    dias_sem_contato = (agora - ultimo_contato_em.replace(tzinfo=UTC)).days

    score = 10.0
    sinais: dict[str, int] = {}

    if dias_sem_contato > 30:
        score += 30
        sinais["dias_sem_contato"] = 30
    elif dias_sem_contato > 14:
        score += 20
        sinais["dias_sem_contato"] = 20
    elif dias_sem_contato > 7:
        score += 10
        sinais["dias_sem_contato"] = 10

    corte = agora - timedelta(days=_JANELA_SINAIS_DIAS)

    reclamacoes_recentes = sum(
        1 for i in interacoes if i.tipo == "reclamacao" and i.criado_em.replace(tzinfo=UTC) >= corte
    )
    if reclamacoes_recentes:
        pontos = min(reclamacoes_recentes * 15, 45)
        score += pontos
        sinais["reclamacoes"] = pontos

    if any(i.tipo == "mencionou_concorrente" and i.criado_em.replace(tzinfo=UTC) >= corte for i in interacoes):
        score += 20
        sinais["mencionou_concorrente"] = 20

    if any(i.tipo == "reuniao_remarcada" and i.criado_em.replace(tzinfo=UTC) >= corte for i in interacoes):
        score += 15
        sinais["reuniao_remarcada"] = 15

    if any(i.tipo == "feedback_positivo" and i.criado_em.replace(tzinfo=UTC) >= corte for i in interacoes):
        score -= 20
        sinais["feedback_positivo"] = -20

    score = max(0.0, min(100.0, score))

    return {
        "conta_id": conta_id,
        "score": score,
        "classificacao": _classificar(score),
        "dias_sem_contato": dias_sem_contato,
        "sinais": sinais,
    }


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
    tenant_ids = _tenant_ids_no_escopo(db, usuario, tenant_id_selecionado)
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
    tenant_nomes: dict[str, str] = {}
    resultado = []
    for conta in contas:
        risco = calcular_score_risco_da_conta(db, conta)
        vendedor = db.query(Usuario).filter_by(id=conta.vendedor_usuario_id).one_or_none() if conta.vendedor_usuario_id else None
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
    negocios = (
        db.query(Negocio)
        .join(EstagioFunil, Negocio.estagio_id == EstagioFunil.id)
        .filter(Negocio.tenant_id == tenant_id, Negocio.conta_id == conta_id, EstagioFunil.tipo == "aberto")
        .all()
    )
    return sum(n.valor for n in negocios)


def dashboard_saude_contas(
    db: Session,
    usuario: Usuario,
    vendedor_usuario_id: int | None = None,
    tenant_id_selecionado: str | None = None,
) -> dict:
    ranking = ranking_saude_contas(db, usuario, vendedor_usuario_id, tenant_id_selecionado)
    total = len(ranking)

    # CS Score/ROI ficam escopados a um único tenant (o selecionado, ou o
    # do próprio usuário sem seleção) — `metricas_service.calcular_cs_score`
    # e `crm_service.dashboard_economia` são inerentemente de um tenant só
    # (NPS e negócios não têm por que ser somados entre tenants
    # diferentes da hierarquia); só as contagens de `ranking` acima é que
    # de fato agregam a subárvore inteira.
    tenant_id_metricas = tenant_id_selecionado or usuario.tenant_id
    cs = metricas_service.calcular_cs_score(
        db,
        tenant_id_metricas,
        conta_ids=[item["conta_id"] for item in ranking if item["tenant_id"] == tenant_id_metricas],
        scores_risco=[item["score"] for item in ranking if item["tenant_id"] == tenant_id_metricas],
    )

    # Import local (não no topo do arquivo) pra evitar dependência
    # circular: `crm_service` também importa este módulo (pro CS do
    # Dashboard) — por enquanto do ponto de vista de import, os dois só
    # se enxergam dentro da chamada de função, nunca no carregamento do
    # módulo em si.
    from app.services import crm_service

    periodo_atual = datetime.now(UTC).strftime("%Y-%m")
    roi = crm_service.dashboard_economia(db, tenant_id_metricas, periodo_atual).get("roi")

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

    resposta = llm_helpers.gerar(
        llm,
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


def atribuir_vendedor(
    db: Session, usuario: Usuario, ator_id: str | None, conta_id: int, vendedor_usuario_id: int | None
) -> Conta:
    conta = _obter_conta(db, usuario, conta_id)
    if vendedor_usuario_id is not None:
        # Sempre o tenant DA CONTA, não o do chamador (raio-X 2026-09-10)
        # — um admin de distribuidor pode estar atribuindo vendedor numa
        # conta de um tenant "cliente" abaixo dele, e o vendedor mora lá,
        # não no tenant do distribuidor.
        vendedor = db.query(Usuario).filter_by(id=vendedor_usuario_id, tenant_id=conta.tenant_id).one_or_none()
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
