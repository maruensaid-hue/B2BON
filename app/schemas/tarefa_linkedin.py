from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TarefaLinkedinSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    mensagem_id: int
    decisor_id: int
    texto: str
    link_perfil: str | None
    status: str
    criado_em: datetime
    atualizado_em: datetime
    # Quem é o contato e de qual empresa, para a pessoa saber a quem está enviando sem abrir outra tela.
    decisor_nome: str | None = None
    decisor_cargo: str | None = None
    conta_id: int | None = None
    conta_nome: str | None = None


class ContagemTarefasLinkedinSchema(BaseModel):
    pendentes: int


class MarcarTarefaLinkedinRequestSchema(BaseModel):
    executada: bool
