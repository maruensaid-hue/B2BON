from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ColetaSiteConta(Base):
    """Uma execução do enriquecimento de site de uma conta: o histórico persistido (nunca sobrescrito).

    Reprocessar cria uma NOVA linha (`reprocesso_de_id` aponta a original); resultados anteriores continuam consultáveis."""

    __tablename__ = "coleta_site_conta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    dominio: Mapped[str | None] = mapped_column(String, nullable=True)
    disparo: Mapped[str] = mapped_column(String, default="manual")  # manual | fila | reprocesso
    reprocesso_de_id: Mapped[int | None] = mapped_column(ForeignKey("coleta_site_conta.id"), index=True, nullable=True)
    # em_andamento | concluida | concluida_sem_ia (coleta salva, análise pendente) | falhou
    estado: Mapped[str] = mapped_column(String, default="em_andamento")
    iniciada_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    fontes: Mapped[list] = mapped_column(JSON, default=list)  # URLs efetivamente pesquisadas
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)  # saída da IA, quando houve
    erro: Mapped[str | None] = mapped_column(String, nullable=True)
    avisos: Mapped[list] = mapped_column(JSON, default=list)
    # Confirmação do domínio (determinística): origem do domínio, situação, pontuação, evidências e limitações.
    dominio_origem: Mapped[str | None] = mapped_column(String, nullable=True)  # cadastrado | descoberto_busca
    dominio_situacao: Mapped[str | None] = mapped_column(String, nullable=True)
    # confirmado | provavel | inconclusivo | divergente | confirmado_manualmente
    dominio_pontuacao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dominio_evidencias: Mapped[list] = mapped_column(JSON, default=list)
    dominio_limitacoes: Mapped[list] = mapped_column(JSON, default=list)
    dominio_validado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    dominio_validado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # encontrados | nao_encontrado: ausência de dado é "não encontrado", nunca resultado negativo.
    financeiro_estado: Mapped[str | None] = mapped_column(String, nullable=True)


class IndicadorFinanceiroConta(Base):
    """Indicador financeiro público com a origem: publicado (texto da fonte) ou derivado (fórmula + origens)."""

    __tablename__ = "indicador_financeiro_conta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    coleta_id: Mapped[int] = mapped_column(ForeignKey("coleta_site_conta.id"), index=True)
    nome: Mapped[str] = mapped_column(String)
    tipo: Mapped[str] = mapped_column(String, default="publicado")  # publicado | derivado
    valor: Mapped[float] = mapped_column(Float)
    moeda: Mapped[str] = mapped_column(String)  # BRL | USD | %
    escala: Mapped[str] = mapped_column(String)  # unidade | mil | milhoes | bilhoes | trilhoes | percentual
    valor_original: Mapped[str] = mapped_column(String)  # como estava escrito na fonte
    periodo: Mapped[str | None] = mapped_column(String, nullable=True)  # 2025 | 2025-T3 | 2025-S1 | None (não identificado)
    url_fonte: Mapped[str] = mapped_column(String)
    trecho: Mapped[str] = mapped_column(Text)
    data_publicacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # não informada pelas páginas coletadas
    metodo_extracao: Mapped[str] = mapped_column(String)
    confianca: Mapped[str] = mapped_column(String)  # alta | baixa
    estado_validacao: Mapped[str] = mapped_column(String, default="extraido_automaticamente")
    formula: Mapped[str | None] = mapped_column(String, nullable=True)
    origens: Mapped[list] = mapped_column(JSON, default=list)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
