from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id
from app.models.configuracao_email_smtp import ConfiguracaoEmailSmtp
from app.schemas.configuracao_email_smtp import ConfiguracaoEmailSmtpSchema, ConfiguracaoEmailSmtpUpsertSchema
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

router = APIRouter(prefix="/configuracao-email-smtp", tags=["configuracao-email-smtp"])


def _para_schema(config: ConfiguracaoEmailSmtp) -> ConfiguracaoEmailSmtpSchema:
    sufixo = config.senha[-4:] if len(config.senha) >= 4 else config.senha
    return ConfiguracaoEmailSmtpSchema(
        id=config.id,
        tenant_id=config.tenant_id,
        host=config.host,
        porta=config.porta,
        usuario=config.usuario,
        usar_tls=config.usar_tls,
        senha_mascarada=f"••••{sufixo}",
        criado_em=config.criado_em,
        atualizado_em=config.atualizado_em,
    )


@router.get("", response_model=ConfiguracaoEmailSmtpSchema | None, dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def obter_configuracao_email_smtp(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoEmailSmtpSchema | None:
    config = db.query(ConfiguracaoEmailSmtp).filter_by(tenant_id=tenant_id).one_or_none()
    return _para_schema(config) if config else None


@router.put("", response_model=ConfiguracaoEmailSmtpSchema, dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def salvar_configuracao_email_smtp(
    dados: ConfiguracaoEmailSmtpUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoEmailSmtpSchema:
    """Conta SMTP própria do tenant — nunca devolve a senha em texto puro
    depois de salva (só o sufixo mascarado), então numa edição posterior
    sem trocar a senha, `senha` vem vazia e mantemos o valor já salvo.

    Checagem de existência e escrita passam por `select`/`update` de
    baixo nível, nunca carregando a entidade ORM inteira — mesmo raio-X
    de hoje (2026-08-27) que corrigiu `configuracao_whatsapp.py`: se a
    senha já salva foi cifrada com uma chave de criptografia diferente
    da atual, um `db.query(...).one_or_none()` comum decifra a coluna na
    hora de montar a linha e estoura `cryptography.fernet.InvalidToken`
    — mesmo numa edição que ia sobrescrever a senha quebrada por uma
    nova válida. Selecionar só a coluna sem tipo criptografado evita
    tocar o valor antigo por completo."""
    linha_existente = db.execute(
        select(ConfiguracaoEmailSmtp.id).where(ConfiguracaoEmailSmtp.tenant_id == tenant_id)
    ).one_or_none()

    if linha_existente is None:
        if not dados.senha:
            raise ValidacaoFalhou("Senha é obrigatória na primeira configuração.")
        config = ConfiguracaoEmailSmtp(
            tenant_id=tenant_id,
            host=dados.host,
            porta=dados.porta,
            usuario=dados.usuario,
            senha=dados.senha,
            usar_tls=dados.usar_tls,
        )
        db.add(config)
        db.flush()
        config_id = config.id
    else:
        config_id = linha_existente.id
        valores = {
            "host": dados.host,
            "porta": dados.porta,
            "usuario": dados.usuario,
            "usar_tls": dados.usar_tls,
        }
        if dados.senha:
            valores["senha"] = dados.senha
        db.execute(update(ConfiguracaoEmailSmtp).where(ConfiguracaoEmailSmtp.id == config_id).values(**valores))

    auditoria_service.registrar(
        db, tenant_id, "configuracao_email_smtp_salva", "configuracao_email_smtp", config_id, ator_id, {}
    )
    db.commit()
    config = db.get(ConfiguracaoEmailSmtp, config_id)
    return _para_schema(config)
