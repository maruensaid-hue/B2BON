from pydantic import BaseModel, ConfigDict


class RotuloTipoTenantSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tipo: str
    rotulo: str


class AtualizarRotulosHierarquiaRequestSchema(BaseModel):
    rotulo_distribuidor: str
    rotulo_revendedor: str
    rotulo_cliente: str
