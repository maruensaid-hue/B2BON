import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.configuracao_agente_corporativo import ConfiguracaoAgenteCorporativo
from app.models.faq_item import FaqItem
from app.models.oferta import Oferta
from app.models.perfil_empresa import PerfilEmpresa
from app.models.pergunta_agente_corporativo import PerguntaAgenteCorporativo
from app.services import auditoria_service, llm_helpers, rede_social_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

_MODOS_VALIDOS = {"disabled", "interno", "assistido"}

_PALAVRAS_IGNORADAS = {
    "de", "da", "do", "das", "dos", "para", "com", "sem", "por", "que", "uma", "um",
    "uns", "umas", "não", "nao", "mais", "menos", "the", "and", "for", "seu", "sua",
}

_RESPOSTA_SEM_EVIDENCIA = (
    "Não há informação suficiente cadastrada por esta empresa para responder essa pergunta."
)


def _tokenizar(texto: str) -> set[str]:
    return {
        palavra
        for palavra in re.findall(r"[a-zà-ú0-9]+", texto.lower())
        if len(palavra) >= 3 and palavra not in _PALAVRAS_IGNORADAS
    }


def obter_modo(db: Session, tenant_id: str) -> str:
    configuracao = db.query(ConfiguracaoAgenteCorporativo).filter_by(tenant_id=tenant_id).one_or_none()
    return configuracao.modo if configuracao is not None else "disabled"


def definir_modo(db: Session, tenant_id: str, ator_id: str | None, modo: str) -> ConfiguracaoAgenteCorporativo:
    if modo not in _MODOS_VALIDOS:
        raise ValidacaoFalhou(f"Modo de agente corporativo inválido: {modo}")

    configuracao = db.query(ConfiguracaoAgenteCorporativo).filter_by(tenant_id=tenant_id).one_or_none()
    if configuracao is None:
        configuracao = ConfiguracaoAgenteCorporativo(tenant_id=tenant_id, modo=modo)
        db.add(configuracao)
    else:
        configuracao.modo = modo

    auditoria_service.registrar(
        db, tenant_id, "agente_corporativo_modo_definido", "configuracao_agente_corporativo", 0, ator_id, {"modo": modo}
    )
    db.commit()
    db.refresh(configuracao)
    return configuracao


def _buscar_conhecimento(db: Session, tenant_id: str, pergunta: str) -> list[dict]:
    """"Advanced RAG" (master prompt §57) implementado como retrieval
    estruturado por palavra-chave, mesmo raciocínio de `_tokenizar` já
    usado em `sinal_oportunidade_service.py` — sem embeddings/vector
    search (mesma decisão de escopo da Fase 3C). Fontes: Oferta ativa,
    PerfilEmpresa e FaqItem do tenant perguntado."""
    palavras_pergunta = _tokenizar(pergunta)
    if not palavras_pergunta:
        return []

    evidencias: list[dict] = []

    for oferta in db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).all():
        texto = " ".join(
            filter(None, [oferta.nome, oferta.descricao, *oferta.diferenciais, *oferta.provas_sociais])
        )
        if palavras_pergunta & _tokenizar(texto):
            evidencias.append({"tipo": "oferta", "id": oferta.id, "trecho": f"{oferta.nome}: {oferta.descricao}"})

    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    if perfil is not None:
        texto = " ".join(
            filter(
                None,
                [perfil.descricao, *perfil.produtos_servicos, *perfil.mercados, *perfil.tecnologias, *perfil.certificacoes],
            )
        )
        if palavras_pergunta & _tokenizar(texto):
            evidencias.append({"tipo": "perfil", "id": perfil.id, "trecho": texto[:300]})

    for faq in db.query(FaqItem).filter_by(tenant_id=tenant_id).all():
        if palavras_pergunta & _tokenizar(f"{faq.pergunta} {faq.resposta}"):
            evidencias.append({"tipo": "faq", "id": faq.id, "trecho": f"{faq.pergunta}: {faq.resposta}"})

    return evidencias


def testar_internamente(db: Session, tenant_id: str, pergunta: str, llm: LLMProvider) -> dict:
    """Dono testa o próprio agente sem persistir nada — funciona em
    qualquer modo exceto "disabled", já que é só validação interna."""
    modo = obter_modo(db, tenant_id)
    if modo == "disabled":
        raise RegraNegocioViolada("Ative o agente corporativo (modo interno ou assistido) antes de testá-lo.")

    evidencias = _buscar_conhecimento(db, tenant_id, pergunta)
    resposta = _gerar_resposta(pergunta, evidencias, llm)
    return {"resposta": resposta, "evidencias": evidencias}


def _gerar_resposta(pergunta: str, evidencias: list[dict], llm: LLMProvider) -> str:
    if not evidencias:
        return _RESPOSTA_SEM_EVIDENCIA

    trechos = "\n".join(f"- {evidencia['trecho']}" for evidencia in evidencias)
    resposta = llm_helpers.gerar(
        llm,
        LLMRequest(
            prompt=(
                f"Pergunta de uma empresa da rede: \"{pergunta}\"\n\n"
                f"Informações JÁ CADASTRADAS por esta empresa (responda usando SÓ o que está aqui, "
                f"nunca invente nenhum dado além destes):\n{trechos}\n\n"
                "Responda a pergunta de forma direta e curta, só com base nas informações acima. "
                "Se as informações não cobrirem a pergunta por completo, diga isso explicitamente."
            ),
            system="Você responde perguntas comerciais em nome de uma empresa, só com base em dados fornecidos.",
        ),
    )
    return resposta.content.strip()


def perguntar(
    db: Session, tenant_id_perguntante: str, ator_id: str | None, tenant_id_alvo: str, pergunta: str, llm: LLMProvider
) -> PerguntaAgenteCorporativo:
    if obter_modo(db, tenant_id_alvo) != "assistido":
        raise RegraNegocioViolada("Esta empresa não tem um agente corporativo disponível para perguntas.")
    if not rede_social_service.conexao_aceita_entre(db, tenant_id_perguntante, tenant_id_alvo):
        raise RegraNegocioViolada("É preciso ter uma conexão aceita com esta empresa para perguntar ao seu agente.")

    evidencias = _buscar_conhecimento(db, tenant_id_alvo, pergunta)
    resposta_rascunho = _gerar_resposta(pergunta, evidencias, llm)

    registro = PerguntaAgenteCorporativo(
        tenant_id_alvo=tenant_id_alvo,
        tenant_id_perguntante=tenant_id_perguntante,
        pergunta=pergunta,
        resposta_rascunho=resposta_rascunho,
        evidencias=evidencias,
        status="pendente_aprovacao",
    )
    db.add(registro)
    db.flush()
    auditoria_service.registrar(
        db, tenant_id_alvo, "pergunta_agente_corporativo_recebida", "pergunta_agente_corporativo", registro.id, ator_id, {}
    )
    db.commit()
    db.refresh(registro)
    return registro


def _obter_pergunta_do_alvo(db: Session, tenant_id: str, pergunta_id: int) -> PerguntaAgenteCorporativo:
    registro = db.query(PerguntaAgenteCorporativo).filter_by(id=pergunta_id, tenant_id_alvo=tenant_id).one_or_none()
    if registro is None:
        raise NaoEncontrado(f"Pergunta {pergunta_id} não encontrada")
    return registro


def listar_pendentes(db: Session, tenant_id: str) -> list[PerguntaAgenteCorporativo]:
    return (
        db.query(PerguntaAgenteCorporativo)
        .filter_by(tenant_id_alvo=tenant_id, status="pendente_aprovacao")
        .order_by(PerguntaAgenteCorporativo.criado_em.desc())
        .all()
    )


def aprovar(
    db: Session, tenant_id: str, ator_id: str | None, pergunta_id: int, resposta_final: str | None = None
) -> PerguntaAgenteCorporativo:
    registro = _obter_pergunta_do_alvo(db, tenant_id, pergunta_id)
    if registro.status != "pendente_aprovacao":
        raise RegraNegocioViolada("Esta pergunta já foi respondida ou recusada.")

    texto_final = resposta_final if resposta_final is not None else registro.resposta_rascunho
    registro.resposta_final = texto_final
    registro.status = "editada" if resposta_final is not None and resposta_final != registro.resposta_rascunho else "aprovada"
    registro.respondido_em = datetime.now(UTC)
    registro.respondido_por = ator_id

    auditoria_service.registrar(
        db, tenant_id, "pergunta_agente_corporativo_aprovada", "pergunta_agente_corporativo", registro.id, ator_id,
        {"status": registro.status},
    )
    db.commit()
    db.refresh(registro)
    return registro


def recusar(db: Session, tenant_id: str, ator_id: str | None, pergunta_id: int, motivo: str | None = None) -> PerguntaAgenteCorporativo:
    registro = _obter_pergunta_do_alvo(db, tenant_id, pergunta_id)
    if registro.status != "pendente_aprovacao":
        raise RegraNegocioViolada("Esta pergunta já foi respondida ou recusada.")

    registro.status = "recusada"
    registro.respondido_em = datetime.now(UTC)
    registro.respondido_por = ator_id

    auditoria_service.registrar(
        db, tenant_id, "pergunta_agente_corporativo_recusada", "pergunta_agente_corporativo", registro.id, ator_id,
        {"motivo": motivo},
    )
    db.commit()
    db.refresh(registro)
    return registro


def listar_minhas_perguntas(db: Session, tenant_id_perguntante: str) -> list[PerguntaAgenteCorporativo]:
    return (
        db.query(PerguntaAgenteCorporativo)
        .filter_by(tenant_id_perguntante=tenant_id_perguntante)
        .order_by(PerguntaAgenteCorporativo.criado_em.desc())
        .all()
    )
