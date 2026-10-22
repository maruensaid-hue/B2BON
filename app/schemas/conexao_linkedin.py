from datetime import datetime

from pydantic import BaseModel


class ImportarConexoesLinkedinRequestSchema(BaseModel):
    conteudo_csv: str


class VariacaoUnificadaSchema(BaseModel):
    empresa: str
    variacoes: list[str]


class ImportarConexoesLinkedinResponseSchema(BaseModel):
    total_importado: int
    # Contatos e empresas criados a partir das conexões (lista "Importação LinkedIn")
    lista_id: int | None = None
    lista_nome: str | None = None
    contas_criadas: int = 0
    contas_reaproveitadas: int = 0
    contatos_criados: int = 0
    contatos_atualizados: int = 0
    contatos_com_email: int = 0
    conexoes_sem_empresa: int = 0
    # Verificação por IA de nomes de empresa parecidos
    ia_disponivel: bool = True
    grupos_analisados: int = 0
    grupos_sem_analise: int = 0
    homonimos_mantidos_separados: int = 0
    variacoes_unificadas: list[VariacaoUnificadaSchema] = []


class StatusConexoesLinkedinSchema(BaseModel):
    total: int
    atualizado_em: datetime | None
