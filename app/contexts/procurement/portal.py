"""Acesso do fornecedor ao processo do comprador privado (Phase F, D-066).

Supplier Guest: o fornecedor responde **sem ocupar assento** do comprador,
por um link secreto (só o hash fica guardado; gerar de novo revoga o anterior)
ou, se for empresa da Business Network, pela própria conta B2B ON.

Visibilidade controlada (§17, §23): o fornecedor vê só o convite, os
requisitos (sem peso), os itens, os esclarecimentos respondidos (sem dizer
quem perguntou), as próprias perguntas, propostas e situação. Nunca vê
outros participantes, avaliações, notas, valor estimado, a aprovação ou a
comparação. Não há vitrine pública de processos na rede. Nada disso passa
por IA nem entra no CRM, no Bid Intelligence ou no Corporate Brain de quem
responde.
"""

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.procurement import estrategico
from app.contexts.shared.documentos import sha256, validar
from app.contexts.sourcing.contract import nativo
from app.models.tenant import Tenant
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

LADO = estrategico.LADO
NAO_ENCONTRADO = "Convite não encontrado."
ABERTOS = ("PUBLICADO", "RECEBENDO_PROPOSTAS", "RECEBENDO_RESPOSTAS")
RECEBENDO = ("RECEBENDO_PROPOSTAS", "RECEBENDO_RESPOSTAS", "EM_NEGOCIACAO")
MAXIMO_ANEXOS = 10


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- Lado comprador: gerar o acesso e responder esclarecimentos -----------------------------
def gerar_acesso(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, participante_id: int,
                 email: str | None = None) -> str:
    """Devolve o link secreto **uma vez**; gerar de novo invalida o anterior."""
    processo = estrategico.obter(db, tenant_id, processo_id)
    participante = estrategico._participante(db, tenant_id, processo, participante_id)
    if processo.status in ("CANCELADO",) or participante.status in ("DECLINOU", "DESQUALIFICADO"):
        raise RegraNegocioViolada("Este participante não pode mais responder.")
    token = secrets.token_urlsafe(32)
    nativo.atualizar(db, participante, token_hash=_hash(token), token_gerado_em=_agora(),
                     email=(email or participante.email or None))
    auditoria_service.registrar(db, tenant_id, "sourcing_acesso_fornecedor_gerado", "processo_sourcing", processo.id,
                                str(usuario_id) if usuario_id else None, {"participante_id": participante.id})  # nunca o token
    db.commit()
    return token


def responder_esclarecimento(db: Session, tenant_id: str, usuario_id: int | None, esclarecimento_id: int, resposta: str):
    esclarecimento = nativo.obter(db, "esclarecimento", LADO, tenant_id, esclarecimento_id)
    if not resposta or not resposta.strip():
        raise ValidacaoFalhou("Informe a resposta.")
    nativo.atualizar(db, esclarecimento, resposta=resposta.strip()[:5000], revisado_por_usuario_id=usuario_id, respondido_em=_agora())
    db.commit()
    return esclarecimento


def baixar_anexo(db: Session, tenant_id: str, anexo_id: int):
    return nativo.obter(db, "anexo", LADO, tenant_id, anexo_id)


# --- Lado fornecedor: quem está falando ----------------------------------------------------
def por_token(db: Session, token: str):
    participante = nativo.participante_por_token(db, LADO, _hash(token)) if token else None
    if participante is None:  # link inválido ou revogado: não diz qual
        raise NaoEncontrado(NAO_ENCONTRADO)
    return participante


def por_empresa(db: Session, empresa_tenant_id: str, participante_id: int):
    participante = next((p for p in nativo.participantes_da_empresa(db, LADO, empresa_tenant_id) if p.id == participante_id), None)
    if participante is None:
        raise NaoEncontrado(NAO_ENCONTRADO)
    return participante


def _processo(db: Session, participante):
    processo = nativo.obter(db, "processo", LADO, participante.tenant_id, participante.processo_id)
    if processo.status == "RASCUNHO":  # antes de publicar, o convite não existe para o fornecedor
        raise NaoEncontrado(NAO_ENCONTRADO)
    return processo


def _situacao_publica(processo, participante) -> str:
    if processo.status in ABERTOS:
        return "ABERTO"
    if processo.status == "EM_NEGOCIACAO":
        return "EM_NEGOCIACAO" if participante.status == "SHORTLIST" or processo.tipo_processo == "RFQ" else "EM_ANALISE"
    if processo.status in ("ADJUDICADO", "CONTRATADO", "ENCERRADO"):
        return "ENCERRADO"
    if processo.status == "CANCELADO":
        return "CANCELADO"
    return "EM_ANALISE"


def _pode_enviar(processo, participante) -> bool:
    if processo.status not in RECEBENDO or participante.status in ("DECLINOU", "DESQUALIFICADO"):
        return False
    return processo.status != "EM_NEGOCIACAO" or participante.status == "SHORTLIST" or processo.tipo_processo == "RFQ"


def visao(db: Session, participante) -> dict:
    processo = _processo(db, participante)
    tenant = participante.tenant_id
    comprador = db.get(Tenant, tenant)
    propostas = nativo.listar(db, "proposta", LADO, tenant, processo_id=processo.id, participante_id=participante.id)
    anexos = (nativo.listar(db, "anexo", LADO, tenant, proposta_id=[p.id for p in propostas]) if propostas else [])
    esclarecimentos = nativo.listar(db, "esclarecimento", LADO, tenant, processo_id=processo.id)
    return {
        "comprador": comprador.razao_social if comprador else None,
        "processo": {"titulo": processo.titulo, "descricao": processo.descricao, "tipo_processo": processo.tipo_processo,
                     "prazo": processo.prazo, "moeda": processo.moeda, "situacao": _situacao_publica(processo, participante)},
        "requisitos": [{"id": r.id, "categoria": r.categoria, "texto": r.texto, "obrigatorio": r.obrigatorio}
                       for r in estrategico.requisitos_vigentes(db, tenant, processo.id)],
        "itens": [{"id": i.id, "descricao": i.descricao, "quantidade": float(i.quantidade), "unidade": i.unidade,
                   "especificacao": i.especificacao} for i in nativo.listar(db, "item", LADO, tenant, processo_id=processo.id)],
        "esclarecimentos": [{"pergunta": e.pergunta, "resposta": e.resposta, "respondido_em": e.respondido_em}
                            for e in esclarecimentos if e.resposta],  # publicados sem dizer quem perguntou
        "minhas_perguntas": [{"pergunta": e.pergunta, "resposta": e.resposta} for e in esclarecimentos
                             if e.participante_id == participante.id],
        "participacao": {"nome": participante.nome, "situacao": participante.status,
                         "pode_enviar": _pode_enviar(processo, participante),
                         "pode_perguntar": processo.status in ABERTOS and participante.status not in ("DECLINOU", "DESQUALIFICADO")},
        "minhas_propostas": [{"id": p.id, "rodada": p.rodada, "valor_total": float(p.valor_total) if p.valor_total is not None else None,
                              "prazo_entrega_dias": p.prazo_entrega_dias, "recebida_em": p.recebida_em,
                              "anexos": [a.nome_arquivo for a in anexos if a.proposta_id == p.id]} for p in propostas],
    }


def perguntar(db: Session, participante, pergunta: str):
    processo = _processo(db, participante)
    if processo.status not in ABERTOS or participante.status in ("DECLINOU", "DESQUALIFICADO"):
        raise RegraNegocioViolada("Perguntas só enquanto o processo está aberto.")
    if not pergunta or len(pergunta.strip()) < 3:
        raise ValidacaoFalhou("Escreva a pergunta.")
    esclarecimento = nativo.criar(db, "esclarecimento", LADO, participante.tenant_id, processo_id=processo.id,
                                  participante_id=participante.id, pergunta=pergunta.strip()[:2000])
    db.commit()
    return esclarecimento


def enviar_proposta(db: Session, participante, dados: dict):
    processo = _processo(db, participante)
    if not _pode_enviar(processo, participante):
        raise RegraNegocioViolada("Este processo não está recebendo a sua proposta agora.")
    return estrategico.registrar_proposta(db, participante.tenant_id, None, processo.id,
                                          {**dados, "participante_id": participante.id}, canal="PORTAL")


def anexar(db: Session, participante, proposta_id: int, nome_arquivo: str, tipo_mime: str, conteudo: bytes):
    processo = _processo(db, participante)
    proposta = nativo.obter(db, "proposta", LADO, participante.tenant_id, proposta_id)
    if proposta.participante_id != participante.id:
        raise NaoEncontrado("Proposta não encontrada.")
    if processo.status not in RECEBENDO:
        raise RegraNegocioViolada("O processo não recebe mais anexos.")
    validar(conteudo, tipo_mime)  # PDF ou texto, tamanho máximo do Document Engine
    if len(nativo.listar(db, "anexo", LADO, participante.tenant_id, proposta_id=proposta.id)) >= MAXIMO_ANEXOS:
        raise RegraNegocioViolada(f"Limite de {MAXIMO_ANEXOS} anexos por proposta.")
    anexo = nativo.criar(db, "anexo", LADO, participante.tenant_id, proposta_id=proposta.id, nome_arquivo=nome_arquivo[:255],
                         tipo_mime=tipo_mime, tamanho_bytes=len(conteudo), sha256=sha256(conteudo), conteudo=conteudo)
    db.commit()
    return anexo


def declinar(db: Session, participante, motivo: str | None):
    processo = _processo(db, participante)
    if participante.status in ("ADJUDICADO", "NAO_SELECIONADO", "DESQUALIFICADO") or processo.status in ("CONTRATADO", "CANCELADO"):
        raise RegraNegocioViolada("Não é mais possível declinar.")
    nativo.atualizar(db, participante, status="DECLINOU", motivo=(motivo or "").strip()[:500] or "Declinou pelo portal")
    db.commit()
    return participante


# --- Business Network: convites que a empresa recebeu -------------------------------------
def convites_da_empresa(db: Session, empresa_tenant_id: str) -> list[dict]:
    resultado = []
    for participante in nativo.participantes_da_empresa(db, LADO, empresa_tenant_id):
        processo = nativo.obter(db, "processo", LADO, participante.tenant_id, participante.processo_id)
        if processo.status == "RASCUNHO":
            continue
        comprador = db.get(Tenant, participante.tenant_id)
        resultado.append({"participante_id": participante.id, "comprador": comprador.razao_social if comprador else None,
                          "titulo": processo.titulo, "tipo_processo": processo.tipo_processo, "prazo": processo.prazo,
                          "situacao": _situacao_publica(processo, participante), "minha_situacao": participante.status})
    return resultado
