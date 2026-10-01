from datetime import date

from pydantic import BaseModel, Field


class DivisaoComissaoSchema(BaseModel):
    representante_id: int
    fracao: float = Field(gt=0, le=1)


class ValoresContratoSchema(BaseModel):
    licenca: float | None = None
    implantacao: float | None = None
    assinatura_anual: float | None = None
    creditos_ia_anuais: int | None = None


class CriarContratoGovernoSchema(BaseModel):
    tenant_id: str
    plano_id: int
    modelo_cobranca: str = "GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION"
    referencia_contrato: str = Field(min_length=1)
    entidade_governamental: str = Field(min_length=1)
    assinado_em: date
    inicio: date | None = None
    representante_id: int | None = None
    divisao_comissao: list[DivisaoComissaoSchema] | None = None
    oportunidade_id: int | None = None
    valores: ValoresContratoSchema | None = None
    motivo_valores: str | None = None
    regra_reajuste: dict | None = None


class RenovarContratoGovernoSchema(BaseModel):
    valor_assinatura: float | None = None
    motivo_reajuste: str | None = None


class ComponenteAdicionalSchema(BaseModel):
    tipo: str
    valor: float
    descricao: str | None = None
    creditos: int | None = None
    tipo_receita: str | None = None  # D-076: classificação fiscal do serviço adicional


class MotivoSchema(BaseModel):
    motivo: str = Field(min_length=1)


class RecebimentoGovernoSchema(BaseModel):
    componente_id: int
    valor: float
    recebido_em: date
    referencia: str | None = None
    idempotency_key: str | None = None


class OverrideComissaoSchema(BaseModel):
    comissionavel: bool | None = None
    taxa: float | None = None
    motivo: str = Field(min_length=1)
    aprovado_por: str = Field(min_length=1)


class TransferenciaComissaoSchema(BaseModel):
    representante_id: int | None = None
    divisao: list[DivisaoComissaoSchema] | None = None
    motivo: str = Field(min_length=1)
    aprovado_por: str = Field(min_length=1)


class PoliticaComissaoSchema(BaseModel):
    regras: dict
    motivo: str = Field(min_length=1)


class TemplateComercialSchema(BaseModel):
    corpo: str = Field(min_length=1)
    motivo: str = Field(min_length=1)


class PropostaGovernoSchema(BaseModel):
    entidade_governamental: str = Field(min_length=1)
    referencia: str | None = None
    valores: ValoresContratoSchema | None = None


class OportunidadeGovernoSchema(BaseModel):
    titulo: str | None = None
    entidade_governamental: str | None = None
    estagio: str | None = None
    referencia_processo: str | None = None
    origem: str | None = None
    data_prevista_fechamento: date | None = None
    valor_estimado_licenca: float | None = None
    valor_estimado_assinatura: float | None = None
    valor_estimado_servicos: float | None = None
    probabilidade: float | None = None
    plano_id: int | None = None
    representante_id: int | None = None
    tenant_id: str | None = None
