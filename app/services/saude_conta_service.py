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
from app.models.usuario import Usuario
from app.services import auditoria_service, llm_helpers
from app.services.errors import NaoEncontrado, ValidacaoFalhou

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


def _obter_conta(db: Session, tenant_id: str, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return conta


def registrar_interacao(
    db: Session, tenant_id: str, ator_id: str | None, conta_id: int, tipo: str, descricao: str | None = None
) -> InteracaoConta:
    if tipo not in _TIPOS_VALIDOS:
        raise ValidacaoFalhou(f"Tipo de interação inválido: {tipo}")
    _obter_conta(db, tenant_id, conta_id)

    interacao = InteracaoConta(
        tenant_id=tenant_id,
        conta_id=conta_id,
        tipo=tipo,
        descricao=descricao,
        criado_por_usuario_id=int(ator_id) if ator_id else None,
    )
    db.add(interacao)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "interacao_conta_registrada", "interacao_conta", interacao.id, ator_id, {"tipo": tipo},
        conta_id=conta_id,
    )
    db.commit()
    db.refresh(interacao)
    return interacao


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


def calcular_score_risco(db: Session, tenant_id: str, conta_id: int) -> dict:
    """Mesma metodologia de `motor_service.calcular_score_risco`, agora
    sobre uma conta (cliente/prospect) em vez de um tenant assinante."""
    conta = _obter_conta(db, tenant_id, conta_id)
    interacoes = listar_interacoes(db, tenant_id, conta_id)
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


def _contas_visiveis(db: Session, tenant_id: str, usuario: Usuario, vendedor_usuario_id: int | None) -> list[Conta]:
    """Escopo por papel: user só vê as contas em que é o vendedor
    responsável; admin/super_admin veem todas as contas do tenant e podem
    filtrar por vendedor. Um `user` pedindo o filtro de outra pessoa é
    ignorado — a query já trava nele mesmo, não é um 403 (a intenção não
    é maliciosa, é só a tela não ter essa opção pra esse papel)."""
    query = db.query(Conta).filter_by(tenant_id=tenant_id)
    if usuario.papel == "user":
        query = query.filter_by(vendedor_usuario_id=usuario.id)
    elif vendedor_usuario_id is not None:
        query = query.filter_by(vendedor_usuario_id=vendedor_usuario_id)
    return query.order_by(Conta.id).all()


def ranking_saude_contas(
    db: Session, tenant_id: str, usuario: Usuario, vendedor_usuario_id: int | None = None
) -> list[dict]:
    contas = _contas_visiveis(db, tenant_id, usuario, vendedor_usuario_id)
    resultado = []
    for conta in contas:
        risco = calcular_score_risco(db, tenant_id, conta.id)
        vendedor = db.query(Usuario).filter_by(id=conta.vendedor_usuario_id).one_or_none() if conta.vendedor_usuario_id else None
        soma_pipeline_aberto = _valor_pipeline_aberto(db, tenant_id, conta.id)
        resultado.append(
            {
                "conta_id": conta.id,
                "nome": conta.nome,
                "nome_fantasia": conta.nome_fantasia,
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
    db: Session, tenant_id: str, usuario: Usuario, vendedor_usuario_id: int | None = None
) -> dict:
    ranking = ranking_saude_contas(db, tenant_id, usuario, vendedor_usuario_id)
    total = len(ranking)
    return {
        "score_medio": (sum(item["score"] for item in ranking) / total) if total else None,
        "total_contas": total,
        "criticas": sum(1 for item in ranking if item["classificacao"] == "critico"),
        "atencao": sum(1 for item in ranking if item["classificacao"] == "atencao"),
        "saudaveis": sum(1 for item in ranking if item["classificacao"] == "saudavel"),
        "valor_total_em_risco": sum(
            item["valor_pipeline_aberto"] for item in ranking if item["classificacao"] != "saudavel"
        ),
    }


def gerar_script_resgate(db: Session, tenant_id: str, conta_id: int, llm: LLMProvider) -> dict:
    conta = _obter_conta(db, tenant_id, conta_id)
    risco = calcular_score_risco(db, tenant_id, conta_id)
    interacoes = listar_interacoes(db, tenant_id, conta_id)[:5]
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
    db: Session, tenant_id: str, ator_id: str | None, conta_id: int, vendedor_usuario_id: int | None
) -> Conta:
    conta = _obter_conta(db, tenant_id, conta_id)
    if vendedor_usuario_id is not None:
        vendedor = db.query(Usuario).filter_by(id=vendedor_usuario_id, tenant_id=tenant_id).one_or_none()
        if vendedor is None:
            raise NaoEncontrado(f"Usuário {vendedor_usuario_id} não encontrado neste tenant")

    conta.vendedor_usuario_id = vendedor_usuario_id
    auditoria_service.registrar(
        db, tenant_id, "conta_vendedor_atribuido", "conta", conta.id, ator_id,
        {"vendedor_usuario_id": vendedor_usuario_id}, conta_id=conta.id,
    )
    db.commit()
    db.refresh(conta)
    return conta
