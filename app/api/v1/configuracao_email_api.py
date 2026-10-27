import re

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import (
    exigir_papel,
    get_ator_id,
    get_db,
    get_email_provider_do_tenant,
    get_tenant_id,
    get_usuario_atual,
)
from app.core.config import settings
from app.models.configuracao_email_api import ConfiguracaoEmailApi
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.schemas.configuracao_email_api import ConfiguracaoEmailApiSchema, ConfiguracaoEmailApiUpsertSchema
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

router = APIRouter(prefix="/configuracao-email-api", tags=["configuracao-email-api"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PAPEIS = Depends(exigir_papel("super_admin", "admin"))


def _para_schema(config: ConfiguracaoEmailApi) -> ConfiguracaoEmailApiSchema:
    sufixo = config.chave_api[-4:] if len(config.chave_api) >= 4 else config.chave_api
    return ConfiguracaoEmailApiSchema(
        id=config.id,
        tenant_id=config.tenant_id,
        remetente_email=config.remetente_email,
        remetente_nome=config.remetente_nome,
        chave_mascarada=f"••••{sufixo}",
        tem_chave_webhook=bool(config.chave_webhook),
        url_webhook=f"{settings.url_base_api}/webhooks/envio/eventos",
        criado_em=config.criado_em,
        atualizado_em=config.atualizado_em,
    )


@router.get("", response_model=ConfiguracaoEmailApiSchema | None, dependencies=[_PAPEIS])
def obter_configuracao_email_api(
    tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)
) -> ConfiguracaoEmailApiSchema | None:
    config = db.query(ConfiguracaoEmailApi).filter_by(tenant_id=tenant_id).one_or_none()
    return _para_schema(config) if config else None


@router.put("", response_model=ConfiguracaoEmailApiSchema, dependencies=[_PAPEIS])
def salvar_configuracao_email_api(
    dados: ConfiguracaoEmailApiUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoEmailApiSchema:
    """Envio por API do próprio cliente. Nunca devolve a chave em texto puro depois de salva (só o sufixo): numa edição sem trocar a chave, `chave_api` vem
    vazia e o valor salvo é mantido. Existência e escrita passam por `select`/`update` de baixo nível, sem decifrar a linha antiga (mesmo cuidado de
    `configuracao_email_smtp`: uma chave cifrada com outra chave de criptografia não pode impedir a regravação)."""
    remetente_email = dados.remetente_email.strip()
    if not _EMAIL.match(remetente_email):
        raise ValidacaoFalhou("Informe um e-mail de remetente válido (o mesmo verificado no seu serviço de envio).")
    chave_api = (dados.chave_api or "").strip() or None
    chave_webhook = (dados.chave_webhook or "").strip() or None
    remetente_nome = (dados.remetente_nome or "").strip() or None

    linha_existente = db.execute(
        select(ConfiguracaoEmailApi.id).where(ConfiguracaoEmailApi.tenant_id == tenant_id)
    ).one_or_none()
    if linha_existente is None:
        if not chave_api:
            raise ValidacaoFalhou("A chave de API é obrigatória na primeira configuração.")
        config = ConfiguracaoEmailApi(
            tenant_id=tenant_id,
            chave_api=chave_api,
            remetente_email=remetente_email,
            remetente_nome=remetente_nome,
            chave_webhook=chave_webhook,
        )
        db.add(config)
        db.flush()
        config_id = config.id
    else:
        config_id = linha_existente.id
        valores: dict = {"remetente_email": remetente_email, "remetente_nome": remetente_nome}
        if chave_api:
            valores["chave_api"] = chave_api
        if chave_webhook:
            valores["chave_webhook"] = chave_webhook
        db.execute(update(ConfiguracaoEmailApi).where(ConfiguracaoEmailApi.id == config_id).values(**valores))

    auditoria_service.registrar(db, tenant_id, "configuracao_email_api_salva", "configuracao_email_api", config_id, ator_id, {})
    db.commit()
    return _para_schema(db.get(ConfiguracaoEmailApi, config_id))


@router.delete("", dependencies=[_PAPEIS])
def remover_configuracao_email_api(
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> dict:
    """Volta a valer a conta SMTP (se houver). Não apaga o histórico de envios nem de entregas já registrados."""
    removidas = db.query(ConfiguracaoEmailApi).filter_by(tenant_id=tenant_id).delete()
    if removidas:
        auditoria_service.registrar(db, tenant_id, "configuracao_email_api_removida", "configuracao_email_api", 0, ator_id, {})
    db.commit()
    return {"removida": bool(removidas)}


@router.post("/testar", dependencies=[_PAPEIS])
def testar_configuracao_email_api(
    usuario: Usuario = Depends(get_usuario_atual),
    tenant_id: str = Depends(get_tenant_id),
    email: EmailProvider = Depends(get_email_provider_do_tenant),
    db: Session = Depends(get_db),
) -> dict:
    """Manda um e-mail de teste para o próprio usuário logado, pelo envio por API salvo. A falha volta com o motivo real do serviço (ex.: remetente não
    verificado ou chave inválida), sem o nome do fornecedor."""
    if db.execute(select(ConfiguracaoEmailApi.id).where(ConfiguracaoEmailApi.tenant_id == tenant_id)).one_or_none() is None:
        raise ValidacaoFalhou("Salve o envio por API antes de enviar um teste.")

    resultado = email.enviar(
        usuario.email,
        "Teste de envio — B2B ON",
        "Este é um e-mail de teste da B2B ON. Se você recebeu esta mensagem, o envio por API cadastrado em Configuração está funcionando.",
        usuario.nome,
        usuario.email,
        tenant_id,
    )
    if not resultado.sucesso:
        return {"sucesso": False, "mensagem": resultado.motivo_falha or "Falha ao enviar o e-mail de teste."}
    return {"sucesso": True, "mensagem": f"E-mail de teste enviado para {usuario.email}."}
