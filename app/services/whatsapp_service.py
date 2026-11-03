from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contexts.predator import contract as predator_contract
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.models.template_whatsapp import TemplateWhatsApp
from app.providers.channels.whatsapp.base import ResultadoEnvio, WhatsAppProvider
from app.services import auditoria_service


def sincronizar_templates(db: Session, tenant_id: str, provider: WhatsAppProvider) -> list[TemplateWhatsApp]:
    """Status de aprovação visível (E3-H2): sincroniza os templates do
    provedor para o cache local."""
    resultado: list[TemplateWhatsApp] = []
    for info in provider.listar_templates():
        existente = db.query(TemplateWhatsApp).filter_by(tenant_id=tenant_id, nome=info.nome).one_or_none()
        if existente is None:
            existente = TemplateWhatsApp(tenant_id=tenant_id, nome=info.nome, corpo=info.corpo, status=info.status)
            db.add(existente)
        else:
            existente.corpo = info.corpo
            existente.status = info.status
        resultado.append(existente)

    db.commit()
    for template in resultado:
        db.refresh(template)
    return resultado


# --- Direct Send (envio sem template, categoria utilidade) -------------------------------------------------------------------

def _config(db: Session, tenant_id: str):
    # Só colunas sem criptografia: ler a linha inteira decifraria o token (ver `configuracao_whatsapp.salvar_configuracao_whatsapp`).
    return db.execute(
        select(ConfiguracaoWhatsApp.id, ConfiguracaoWhatsApp.direct_send_habilitado).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)
    ).one_or_none()


def direct_send_disponivel(db: Session, tenant_id: str) -> bool:
    linha = _config(db, tenant_id)
    return bool(linha and linha.direct_send_habilitado)


def recusa_de_direct_send(resultado: ResultadoEnvio) -> bool:
    """A Meta disse que a conta não tem (ou perdeu) o Direct Send: erro 100 citando o recurso, ou bloqueio do recurso."""
    motivo = (resultado.motivo_falha or "").lower()
    return not resultado.sucesso and ("direct send" in motivo or (resultado.codigo_erro == 100 and "category" in motivo))


def desligar_direct_send(db: Session, tenant_id: str, motivo: str) -> None:
    """Desliga na hora para o tenant inteiro (nenhuma mensagem seguinte tenta de novo) e registra; quem liga de novo é um admin."""
    db.execute(
        update(ConfiguracaoWhatsApp).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)
        .values(direct_send_habilitado=False, direct_send_motivo_desligado=motivo[:500])
    )
    auditoria_service.registrar(db, tenant_id, "whatsapp_direct_send_desligado", "configuracao_whatsapp", 0, None, {"motivo": motivo[:300]})


def enviar_direct_send(db: Session, tenant_id: str, provider: WhatsAppProvider, telefone: str, texto: str) -> ResultadoEnvio | None:
    """Direct Send com as travas: só com a conta habilitada e sem texto promocional. `None` = não tentou (quem chama decide o que
    fazer: adiar, devolver para revisão, cair para texto livre). Recusa da conta pela Meta desliga o recurso no tenant."""
    if not direct_send_disponivel(db, tenant_id):
        return None
    if predator_contract.portao_envio.termos_promocionais(texto):
        return None
    resultado = provider.enviar_direct_send(telefone, texto, "utility")
    if recusa_de_direct_send(resultado):
        desligar_direct_send(db, tenant_id, resultado.motivo_falha or "Meta recusou o Direct Send.")
    return resultado


def enviar_aviso(db: Session, tenant_id: str, provider: WhatsAppProvider, telefone: str, texto: str) -> ResultadoEnvio:
    """Avisos de utilidade da plataforma (lembrete de reunião, pesquisa NPS, aviso ao vendedor): saem por Direct Send quando a conta
    está habilitada (funcionam fora da janela de 24 h); senão, texto livre, como sempre foi (só chega se a janela estiver aberta)."""
    resultado = enviar_direct_send(db, tenant_id, provider, telefone, texto)
    if resultado is not None and resultado.sucesso:
        return resultado
    return provider.enviar_texto_livre(telefone, texto)
