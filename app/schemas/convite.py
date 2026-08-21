from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConviteCadastroSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    codigo: str
    papel_concedido: str
    status: str
    validade_em: datetime | None
    usado_por_usuario_id: int | None
    criado_em: datetime


class GerarConviteRequestSchema(BaseModel):
    papel_concedido: str = "user"
    validade_horas: int | None = 168


class ConviteVitrineSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id_origem: str
    codigo: str
    status: str
    validade_em: datetime | None
    tenant_id_gerado: str | None
    gratuito: bool
    criado_em: datetime


class GerarConviteVitrineRequestSchema(BaseModel):
    validade_horas: int | None = 168
    email_destinatario: str | None = None
    # Só admin/super_admin pode marcar True — validado na rota, não aqui
    # (ver app/api/v1/convites.py). Concede o plano "Teste" sem checkout.
    gratuito: bool = False


class ConviteVitrineCriadoSchema(ConviteVitrineSchema):
    # None quando nenhum e-mail foi solicitado; True/False quando foi
    # (StubEmailProvider sempre reportava sucesso mesmo sem SMTP
    # configurado — sem este campo, o convite parecia enviado quando não
    # saía nada de verdade em produção).
    email_enviado: bool | None = None


class ConviteVitrineInfoSchema(BaseModel):
    """Info pública mínima pra tela de cadastro decidir o que renderizar
    antes de aceitar o convite — não expõe tenant_id_origem/quem criou."""

    model_config = ConfigDict(from_attributes=True)

    status: str
    gratuito: bool
