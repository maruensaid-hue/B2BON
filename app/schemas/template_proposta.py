from pydantic import BaseModel, ConfigDict


class TemplatePropostaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    texto_introdutorio: str | None
    logo_tipo_mime: str | None
    termo_aceite: str | None
    mostrar_tabela_produtos: bool
    mostrar_tabela_servicos: bool


class AtualizarTemplatePropostaRequestSchema(BaseModel):
    texto_introdutorio: str | None = None
    termo_aceite: str | None = None
    mostrar_tabela_produtos: bool = True
    mostrar_tabela_servicos: bool = True


class ItemTemplatePropostaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    ordem: int
    descricao: str
    valor: float | None


class CriarItemTemplatePropostaRequestSchema(BaseModel):
    tipo: str
    descricao: str
    valor: float | None = None


class AtualizarItemTemplatePropostaRequestSchema(BaseModel):
    descricao: str
    valor: float | None = None


class ItemPropostaSchema(BaseModel):
    descricao: str
    valor: float | None = None


class GerarPropostaRequestSchema(BaseModel):
    itens_produtos: list[ItemPropostaSchema] | None = None
    itens_servicos: list[ItemPropostaSchema] | None = None
