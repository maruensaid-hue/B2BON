"""Repositório nativo do modelo unificado (Phase E, D-065) — parte neutra.

Fluxos novos (Enterprise Strategic Sourcing) não têm tabela antiga: gravam
direto em `*_sourcing`. Só o núcleo toca essas tabelas (barreira); cada lado
chama estas funções com o **seu** lado, e toda leitura filtra por tenant e
lado — um lado nunca lê linha do outro, nem por id.

Processo, requisito, contrato e evento, que também recebem o espelho das
tabelas antigas, são marcados com `origem_tabela = "nativo"` (o backfill e a
leitura dupla só olham as origens antigas, então nunca os tocam).
"""

import secrets

from sqlalchemy.orm import Session

from app.contexts.sourcing.tipos import Lado
from app.models.sourcing import (
    AnexoSourcing,
    AvaliacaoSourcing,
    ContratoSourcing,
    EsclarecimentoSourcing,
    EventoSourcing,
    ItemSourcing,
    ParticipanteSourcing,
    ProcessoSourcing,
    PropostaItemSourcing,
    PropostaSourcing,
    RequisitoSourcing,
)
from app.services.errors import NaoEncontrado

ORIGEM = "nativo"
MODELOS = {
    "processo": ProcessoSourcing, "requisito": RequisitoSourcing, "contrato": ContratoSourcing, "evento": EventoSourcing,
    "participante": ParticipanteSourcing, "item": ItemSourcing, "proposta": PropostaSourcing,
    "proposta_item": PropostaItemSourcing, "avaliacao": AvaliacaoSourcing, "esclarecimento": EsclarecimentoSourcing,
    "anexo": AnexoSourcing,
}
_COM_ORIGEM = {"processo", "requisito", "contrato", "evento"}
_NOMES = {"processo": "Processo", "requisito": "Requisito", "participante": "Participante", "item": "Item", "proposta": "Proposta",
          "contrato": "Contrato", "evento": "Evento", "proposta_item": "Item da proposta", "avaliacao": "Avaliação",
          "esclarecimento": "Esclarecimento", "anexo": "Anexo"}


def criar(db: Session, entidade: str, lado: Lado, tenant_id: str, **campos):
    modelo = MODELOS[entidade]
    registro = modelo(tenant_id=tenant_id, lado=lado.value, **campos)
    if entidade in _COM_ORIGEM:
        # provisório único e negativo (nunca colide com id real nem com outra inserção concorrente, que
        # esperaria no índice único); o definitivo é o próprio id, logo abaixo
        registro.origem_tabela, registro.origem_id = ORIGEM, -secrets.randbelow(2**31 - 1) - 1
    db.add(registro)
    db.flush()
    if entidade in _COM_ORIGEM:
        registro.origem_id = registro.id
        db.flush()
    return registro


def _consulta(db: Session, entidade: str, lado: Lado, tenant_id: str):
    modelo = MODELOS[entidade]
    consulta = db.query(modelo).filter(modelo.tenant_id == tenant_id, modelo.lado == lado.value)
    if entidade in _COM_ORIGEM:
        consulta = consulta.filter(modelo.origem_tabela == ORIGEM)
    return consulta


def obter(db: Session, entidade: str, lado: Lado, tenant_id: str, registro_id: int):
    registro = _consulta(db, entidade, lado, tenant_id).filter(MODELOS[entidade].id == registro_id).one_or_none()
    if registro is None:
        raise NaoEncontrado(f"{_NOMES[entidade]} {registro_id} não encontrado(a)")
    return registro


def listar(db: Session, entidade: str, lado: Lado, tenant_id: str, ordem: str = "id", limite: int | None = None, **filtros) -> list:
    modelo = MODELOS[entidade]
    consulta = _consulta(db, entidade, lado, tenant_id)
    for campo, valor in filtros.items():
        coluna = getattr(modelo, campo)
        consulta = consulta.filter(coluna.in_(valor) if isinstance(valor, list | tuple | set) else coluna == valor)
    consulta = consulta.order_by(getattr(modelo, ordem.lstrip("-")).desc() if ordem.startswith("-") else getattr(modelo, ordem))
    return consulta.limit(limite).all() if limite else consulta.all()


def atualizar(db: Session, registro, **campos):
    for campo, valor in campos.items():
        setattr(registro, campo, valor)
    db.flush()
    return registro


def apagar(db: Session, registro) -> None:
    db.delete(registro)
    db.flush()


def participante_por_token(db: Session, lado: Lado, token_hash: str) -> ParticipanteSourcing | None:
    """Acesso do fornecedor pelo link (Phase F): o tenant vem da própria linha, achada só pelo hash do segredo."""
    return db.query(ParticipanteSourcing).filter(ParticipanteSourcing.token_hash == token_hash,
                                                 ParticipanteSourcing.lado == lado.value).one_or_none()


def participantes_da_empresa(db: Session, lado: Lado, empresa_rede_tenant_id: str) -> list[ParticipanteSourcing]:
    """Convites recebidos por uma empresa da rede, de qualquer comprador (Phase F): só as linhas em que ela é o participante."""
    return (db.query(ParticipanteSourcing)
            .filter(ParticipanteSourcing.empresa_rede_tenant_id == empresa_rede_tenant_id, ParticipanteSourcing.lado == lado.value)
            .order_by(ParticipanteSourcing.id.desc()).all())
