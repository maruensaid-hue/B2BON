import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.contexts.predator import contract as predator_contract
from app.models.cadencia import Cadencia
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import atividade_service, auditoria_service, optout_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

# Separador seguro pra local-part de e-mail (raio-X 2026-09-24, Webmail
# — caixa de entrada) — mesma técnica HMAC stateless de
# `optout_service.gerar_token`, só troca ":" por "." porque o token
# vira parte de um endereço de e-mail (`resp+{token}@dominio`), onde
# ":" cru é incomum/arriscado sem aspas RFC 5321.
_SEPARADOR_TOKEN_RESPOSTA = "."


def gerar_token_resposta(tenant_id: str, decisor_id: int) -> str:
    payload = f"{tenant_id}{_SEPARADOR_TOKEN_RESPOSTA}{decisor_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR_TOKEN_RESPOSTA}{assinatura}"


def validar_token_resposta(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR_TOKEN_RESPOSTA)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de resposta inválido.")
    tenant_id, decisor_id_str, assinatura = partes
    try:
        decisor_id = int(decisor_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de resposta inválido.") from erro

    esperado = gerar_token_resposta(tenant_id, decisor_id).rsplit(_SEPARADOR_TOKEN_RESPOSTA, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de resposta inválido.")
    return tenant_id, decisor_id


def marcar_resposta(db: Session, tenant_id: str, decisor_id: int) -> dict:
    """Resposta detectada (E3-H3). Raio-X 2026-09-15: por padrão a resposta
    NÃO interrompe mais a cadência — uma resposta pedindo mais informação
    não é motivo pra parar de nutrir por e-mail/LinkedIn. Só cancela tudo
    se a própria cadência tiver `cancelar_ao_responder=True` (opção
    explícita, desligada por padrão). Mensagem avulsa (sem cadência, ex.:
    pedido de indicação) continua cancelando sempre — não tem flag pra
    checar, e é um pedido pontual mesmo. Cancelamento fino por mensagem
    individual continua disponível via `aprovacao_service.cancelar_mensagem`,
    independente disso."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    decisor.ultima_interacao_em = datetime.now(UTC)

    pendentes = (
        db.query(Mensagem)
        .outerjoin(Cadencia, Mensagem.cadencia_id == Cadencia.id)
        .filter(
            Mensagem.decisor_id == decisor.id,
            Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]),
            or_(Mensagem.cadencia_id.is_(None), Cadencia.cancelar_ao_responder.is_(True)),
        )
        .all()
    )
    for mensagem in pendentes:
        mensagem.status = "cancelado"

    # Colegas da mesma empresa, nas cadências que pedem isso: quem respondeu virou conversa, o resto da empresa para de receber.
    colegas = (
        db.query(Mensagem)
        .join(Cadencia, Mensagem.cadencia_id == Cadencia.id)
        .join(Decisor, Mensagem.decisor_id == Decisor.id)
        .filter(
            Decisor.tenant_id == tenant_id,
            Decisor.conta_id == decisor.conta_id,
            Decisor.id != decisor.id,
            Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]),
            Cadencia.pausar_empresa_ao_responder.is_(True),
        )
        .all()
    )
    for mensagem in colegas:
        mensagem.status = "cancelado"
        mensagem.motivo_falha = f"Pausada: {decisor.nome}, da mesma empresa, respondeu."

    auditoria_service.registrar(
        db,
        tenant_id,
        "resposta_detectada",
        "decisor",
        decisor.id,
        None,
        {"mensagens_canceladas": len(pendentes), "mensagens_da_empresa_pausadas": len(colegas)},
        conta_id=decisor.conta_id,
    )
    db.commit()
    return {"decisor_id": decisor.id, "mensagens_canceladas": len(pendentes), "mensagens_da_empresa_pausadas": len(colegas)}


def ler_resposta(db: Session, tenant_id: str, decisor: Decisor, texto: str, origem: str) -> dict | None:
    """Lê o texto da resposta antes de qualquer automação. Pedido de descadastro escrito ("SAIR", "me tire da lista") vira opt-out
    imediato e permanente, devolvendo o resultado (quem chama não responde nem qualifica). Ameaça jurídica ou reclamação fica registrada
    na conta para um humano e devolve `{"escalar": True}`: quem chama não deixa a IA responder. Resposta comum devolve `None`."""
    leitura = predator_contract.optout_resposta.ler(texto or "")
    if leitura.escalar:
        atividade_service.registrar(
            db, tenant_id, conta_id=decisor.conta_id, tipo="sistema",
            descricao=f"Resposta de {decisor.nome} pede atenção humana (possível reclamação ou menção jurídica): nenhuma resposta automática.",
        )
    if leitura.optout:
        atividade_service.registrar(
            db, tenant_id, conta_id=decisor.conta_id, tipo="sistema",
            descricao=f"{decisor.nome} pediu para não receber mais mensagens ({origem}): \"{(leitura.trecho or '')[:80]}\"",
        )
        resultado = optout_service.processar(db, tenant_id, decisor.id, origem=f"resposta_{origem}")
        return {**resultado, "optout_por_resposta": True, "escalar": leitura.escalar}
    if leitura.escalar:
        # Reclamação não é descadastro, mas nada mais sai para essa pessoa até um humano decidir.
        decisor.ultima_interacao_em = datetime.now(UTC)
        pendentes = db.query(Mensagem).filter(Mensagem.decisor_id == decisor.id, Mensagem.status.in_(["aguardando_aprovacao", "aprovado"])).all()
        for mensagem in pendentes:
            mensagem.status, mensagem.motivo_falha = "cancelado", "Resposta pede atenção humana (possível reclamação)."
        auditoria_service.registrar(db, tenant_id, "resposta_escalada", "decisor", decisor.id, None, {"mensagens_canceladas": len(pendentes)},
                                    conta_id=decisor.conta_id)
        db.commit()
        return {"decisor_id": decisor.id, "escalar": True, "mensagens_canceladas": len(pendentes)}
    return None
