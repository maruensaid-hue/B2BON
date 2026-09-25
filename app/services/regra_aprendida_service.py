from sqlalchemy.orm import Session

from app.contexts.intelligence import contract as intel
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.aprovacao import Aprovacao
from app.models.auditoria import AuditLog
from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.mensagem import Mensagem
from app.models.regra_aprendida import RegraAprendida
from app.schemas.regra_aprendida import RegraAprendidaCreateSchema
from app.services import auditoria_service
from app.services.errors import NaoEncontrado

# Correções recentes (raio-X 2026-09-17, Peça 2 do loop de aprendizado)
# — só esses dois eventos de AuditLog documentam uma correção humana
# de conteúdo gerado por IA (ver aprovacao_service.editar_mensagem/
# rejeitar); "aprovacao_rejeitada" mira o rejeitado, mas o conteúdo
# em si pode ter sido reaproveitado sem edição, então não expomos
# conteudo_anterior/novo pra rejeição, só o motivo.
_EVENTOS_CORRECAO = ("mensagem_editada", "aprovacao_rejeitada")
_LIMITE_CORRECOES = 50


def listar(db: Session, tenant_id: str) -> list[RegraAprendida]:
    return db.query(RegraAprendida).filter_by(tenant_id=tenant_id).order_by(RegraAprendida.criado_em.desc()).all()


def _obter(db: Session, tenant_id: str, regra_id: int) -> RegraAprendida:
    regra = db.query(RegraAprendida).filter_by(id=regra_id, tenant_id=tenant_id).one_or_none()
    if regra is None:
        raise NaoEncontrado(f"Regra aprendida {regra_id} não encontrada")
    return regra


def criar(db: Session, tenant_id: str, ator_id: str | None, dados: RegraAprendidaCreateSchema) -> RegraAprendida:
    regra = RegraAprendida(
        tenant_id=tenant_id,
        icp_id=dados.icp_id,
        oferta_id=dados.oferta_id,
        canal=dados.canal,
        regra=dados.regra,
        ativa=True,
    )
    db.add(regra)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_criada", "regra_aprendida", regra.id, ator_id, {"regra": regra.regra})
    db.commit()
    db.refresh(regra)
    return regra


def atualizar(
    db: Session, tenant_id: str, ator_id: str | None, regra_id: int, dados: RegraAprendidaCreateSchema
) -> RegraAprendida:
    regra = _obter(db, tenant_id, regra_id)
    regra.icp_id = dados.icp_id
    regra.oferta_id = dados.oferta_id
    regra.canal = dados.canal
    regra.regra = dados.regra

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_atualizada", "regra_aprendida", regra.id, ator_id, {"regra": regra.regra})
    db.commit()
    db.refresh(regra)
    return regra


def ativar(db: Session, tenant_id: str, ator_id: str | None, regra_id: int) -> RegraAprendida:
    regra = _obter(db, tenant_id, regra_id)
    regra.ativa = True

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_ativada", "regra_aprendida", regra.id, ator_id, {})
    db.commit()
    db.refresh(regra)
    return regra


def desativar(db: Session, tenant_id: str, ator_id: str | None, regra_id: int) -> RegraAprendida:
    regra = _obter(db, tenant_id, regra_id)
    regra.ativa = False

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_desativada", "regra_aprendida", regra.id, ator_id, {})
    db.commit()
    db.refresh(regra)
    return regra


def excluir(db: Session, tenant_id: str, ator_id: str | None, regra_id: int) -> None:
    regra = _obter(db, tenant_id, regra_id)

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_excluida", "regra_aprendida", regra.id, ator_id, {"regra": regra.regra})
    db.delete(regra)
    db.commit()


def regras_aplicaveis_texto(db: Session, tenant_id: str, icp_id: int | None, oferta_id: int | None, canal: str) -> str:
    """Loop de aprendizado (master prompt seções 13/14) — regras escritas
    por um humano depois de observar edição/rejeição repetida, injetadas
    no prompt de geração de toque. Escopo nulo = aplica a todos (mais
    amplo, não mais específico); sem ordenação de prioridade porque um
    texto curto por linha já basta pro volume esperado por tenant."""
    regras = (
        db.query(RegraAprendida)
        .filter(
            RegraAprendida.tenant_id == tenant_id,
            RegraAprendida.ativa.is_(True),
            (RegraAprendida.icp_id.is_(None)) | (RegraAprendida.icp_id == icp_id),
            (RegraAprendida.oferta_id.is_(None)) | (RegraAprendida.oferta_id == oferta_id),
            (RegraAprendida.canal.is_(None)) | (RegraAprendida.canal == canal),
        )
        .all()
    )
    if not regras:
        return ""
    return " Regras aprendidas com este cliente (respeite ao escrever): " + "; ".join(r.regra for r in regras) + "."


def _icp_e_oferta_da_mensagem(db: Session, mensagem_id: int | None) -> tuple[int | None, int | None]:
    if mensagem_id is None:
        return None, None
    mensagem = db.query(Mensagem).filter_by(id=mensagem_id).one_or_none()
    if mensagem is None or mensagem.cadencia_id is None:
        return None, None
    cadencia = db.query(Cadencia).filter_by(id=mensagem.cadencia_id).one_or_none()
    if cadencia is None:
        return None, None
    return cadencia.icp_id, cadencia.oferta_id


def listar_correcoes_recentes(db: Session, tenant_id: str) -> list[dict]:
    """Correções humanas (edição/rejeição) que hoje ficam órfãs dentro do
    `AuditLog` — nenhuma tela expõe `conteudo_anterior`/`conteudo_novo`/
    `motivo` (raio-X 2026-09-17). Serve pro humano decidir se aquele
    padrão merece virar uma `RegraAprendida` durável."""
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant_id, AuditLog.evento_tipo.in_(_EVENTOS_CORRECAO))
        .order_by(AuditLog.criado_em.desc())
        .limit(_LIMITE_CORRECOES)
        .all()
    )

    resultado = []
    for log in logs:
        if log.entidade_tipo == "mensagem":
            mensagem_id = log.entidade_id
        else:
            aprovacao = db.query(Aprovacao).filter_by(id=log.entidade_id).one_or_none()
            mensagem_id = aprovacao.mensagem_id if aprovacao is not None else None

        icp_id, oferta_id = _icp_e_oferta_da_mensagem(db, mensagem_id)
        conta = db.query(Conta).filter_by(id=log.conta_id).one_or_none() if log.conta_id is not None else None

        resultado.append(
            {
                "id": log.id,
                "tipo": "edicao" if log.evento_tipo == "mensagem_editada" else "rejeicao",
                "conta_nome": (conta.nome_fantasia or conta.nome) if conta is not None else None,
                "canal": log.canal,
                "icp_id": icp_id,
                "oferta_id": oferta_id,
                "conteudo_anterior": log.detalhes.get("conteudo_anterior"),
                "conteudo_novo": log.detalhes.get("conteudo_novo"),
                "motivo": log.detalhes.get("motivo"),
                "criado_em": log.criado_em,
            }
        )
    return resultado


def calcular_performance_ia(db: Session, tenant_id: str) -> dict:
    """AI Performance metrics (master prompt §77, Fase 6D) — só o que já
    é medível de verdade a partir do `AuditLog` que os pontos de
    aprovação/edição/envio/resposta já gravam, sem inventar nenhum
    sinal novo. `AI_to_meeting_rate`/`recommendation_conversion` ficam
    de fora — não existe hoje nenhuma ligação rastreável entre uma
    mensagem e uma reunião resultante.

    Bug real corrigido 2026-09-20: "aceita sem edição" era calculado só
    como `total - editadas`, sem nunca descontar as rejeitadas — uma
    mensagem rejeitada sem ter sido editada antes contava como
    "aceita" ao mesmo tempo que contava como "rejeitada", fazendo as
    três taxas somarem mais que 100% (achado pelo usuário: 100% de
    aceitação + 3% de rejeição na mesma tela). `aprovacao_rejeitada`
    grava `entidade_id` da `Aprovacao`, não da `Mensagem` — resolve via
    `Aprovacao.mensagem_id` pra comparar no mesmo espaço de IDs de
    `mensagem_proposta`/`mensagem_editada`. Quando a mesma mensagem foi
    editada E depois rejeitada (permitido — `rejeitar` não bloqueia uma
    `Aprovacao` já editada), o desfecho final (rejeitada) prevalece
    sobre a edição, pra cada mensagem proposta cair em exatamente uma
    das três categorias."""

    def _ids_distintos(evento_tipo: str) -> set[int]:
        linhas = (
            db.query(AuditLog.entidade_id)
            .filter_by(tenant_id=tenant_id, evento_tipo=evento_tipo)
            .distinct()
            .all()
        )
        return {id_ for (id_,) in linhas}

    def _taxa(numerador: int, denominador: int) -> float:
        return round(numerador / denominador, 4) if denominador else 0.0

    mensagens_propostas_ids = _ids_distintos("mensagem_proposta")
    mensagens_editadas_ids = _ids_distintos("mensagem_editada")
    aprovacoes_rejeitadas_ids = _ids_distintos("aprovacao_rejeitada")

    mensagens_rejeitadas_ids: set[int] = set()
    if aprovacoes_rejeitadas_ids:
        linhas = db.query(Aprovacao.mensagem_id).filter(Aprovacao.id.in_(aprovacoes_rejeitadas_ids)).distinct().all()
        mensagens_rejeitadas_ids = {mid for (mid,) in linhas}

    total_propostas = len(mensagens_propostas_ids)
    rejeitadas = len(mensagens_rejeitadas_ids)
    editadas_nao_rejeitadas = len(mensagens_editadas_ids - mensagens_rejeitadas_ids)
    aceitas_sem_edicao = max(total_propostas - editadas_nao_rejeitadas - rejeitadas, 0)

    mensagens_enviadas = len(_ids_distintos("mensagem_enviada"))
    respostas_detectadas = len(_ids_distintos("resposta_detectada"))

    return {
        "total_propostas": total_propostas,
        "mensagens_editadas": len(mensagens_editadas_ids),
        "aprovacoes_rejeitadas": rejeitadas,
        "mensagens_enviadas": mensagens_enviadas,
        "respostas_detectadas": respostas_detectadas,
        "taxa_aceitacao": _taxa(aceitas_sem_edicao, total_propostas),
        "taxa_edicao": _taxa(editadas_nao_rejeitadas, total_propostas),
        "taxa_rejeicao": _taxa(rejeitadas, total_propostas),
        "taxa_resposta": _taxa(respostas_detectadas, mensagens_enviadas),
    }


def sugerir_regra_com_ia(db: Session, tenant_id: str, correcao_log_id: int, llm: LLMProvider) -> str:
    """Peça 3 do loop de aprendizado (raio-X 2026-09-17) — primeira
    chamada de IA nova do loop, deliberadamente pequena: sugere só o
    TEXTO da regra a partir de uma única correção, nunca cria a
    `RegraAprendida` diretamente. Quem chama decide se usa, edita ou
    descarta antes de salvar (mesma cautela das Peças 1/2 — nenhuma
    regra passa a valer sem um humano confirmar)."""
    log = db.query(AuditLog).filter_by(id=correcao_log_id, tenant_id=tenant_id).one_or_none()
    if log is None or log.evento_tipo not in _EVENTOS_CORRECAO:
        raise NaoEncontrado(f"Correção {correcao_log_id} não encontrada")

    if log.evento_tipo == "mensagem_editada":
        prompt = (
            "Um vendedor editou manualmente uma mensagem de prospecção gerada por IA.\n"
            f"Texto original: \"{log.detalhes.get('conteudo_anterior')}\"\n"
            f"Texto editado pelo vendedor: \"{log.detalhes.get('conteudo_novo')}\"\n"
            "Em uma frase curta e objetiva, escreva uma regra reutilizável de estilo/conteúdo "
            "que evite o problema do texto original nas próximas mensagens geradas. "
            "Responda só com a regra, sem explicações nem aspas."
        )
    else:
        prompt = (
            "Um vendedor rejeitou uma mensagem de prospecção gerada por IA.\n"
            f"Motivo da rejeição: \"{log.detalhes.get('motivo')}\"\n"
            "Em uma frase curta e objetiva, escreva uma regra reutilizável que ajude a evitar esse "
            "motivo nas próximas mensagens geradas. Responda só com a regra, sem explicações nem aspas."
        )

    resposta = intel.gerar(
        db, llm,
        intel.ContextoIA(tenant_id=tenant_id, feature="predator.sugerir_regra", entidade_tipo="audit_log", entidade_id=correcao_log_id),
        LLMRequest(prompt=prompt, max_tokens=200),
    )
    return resposta.content.strip()
