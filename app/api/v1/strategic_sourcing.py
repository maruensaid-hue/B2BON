"""API do Enterprise Strategic Sourcing (Phase E, D-065) — lado comprador privado.

Gate: módulo "sourcing" (B2B ON Strategic Sourcing). Recursos compartilhados
sob `/sourcing` (§30). Só o próprio tenant; nenhuma resposta vai para o lado
vendedor, para a rede ou para a IA.
"""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id, get_usuario_atual
from app.contexts.procurement import contract as compras
from app.models.usuario import Usuario

router = APIRouter(prefix="/sourcing", tags=["strategic-sourcing"])
estrategico = compras.estrategico

TipoProcesso = Literal[compras.fluxo.TIPOS_EMPRESA]  # type: ignore[valid-type]
Categoria = Literal[compras.estrategico.CATEGORIAS]  # type: ignore[valid-type]


def _usuario_id(ator_id: str | None) -> int | None:
    return int(ator_id) if ator_id and ator_id.isdigit() else None


class ProcessoEntrada(BaseModel):
    tipo_processo: TipoProcesso
    titulo: str = Field(min_length=3, max_length=300)
    descricao: str | None = None
    prazo: datetime | None = None
    valor_estimado: float | None = Field(default=None, ge=0)
    moeda: str | None = Field(default=None, min_length=3, max_length=3)


class StatusEntrada(BaseModel):
    status: str


class RequisitoEntrada(BaseModel):
    categoria: Categoria
    texto: str = Field(min_length=3, max_length=1000)
    obrigatorio: bool | None = None
    peso: float | None = None


class ItemEntrada(BaseModel):
    descricao: str = Field(min_length=2, max_length=300)
    quantidade: float
    unidade: str | None = None
    especificacao: str | None = None


class DescobertaEntrada(BaseModel):
    necessidade: str | None = None
    ufs: list[str] = []
    certificacoes: list[str] = []


class ConviteEntrada(BaseModel):
    fornecedor_id: int | None = None
    empresa_rede_tenant_id: str | None = None
    nome: str | None = None
    cnpj: str | None = None


class SituacaoEntrada(BaseModel):
    status: Literal["QUALIFICADO", "DESQUALIFICADO", "DECLINOU", "SHORTLIST"]
    motivo: str | None = None


class PrecoItem(BaseModel):
    item_id: int
    preco_unitario: float = Field(ge=0)


class RespostaRequisito(BaseModel):
    requisito_id: int
    resposta: str | None = Field(default=None, max_length=5000)


class PropostaEntrada(BaseModel):
    participante_id: int
    valor_total: float | None = Field(default=None, ge=0)
    moeda: str | None = None
    prazo_entrega_dias: int | None = Field(default=None, ge=0)
    condicoes_pagamento: str | None = None
    impostos_inclusos: bool | None = None
    validade: date | None = None
    observacoes: str | None = None
    itens: list[PrecoItem] = []
    respostas: list[RespostaRequisito] = []


class AvaliacaoEntrada(BaseModel):
    requisito_id: int
    status: Literal[compras.estrategico.tipos.STATUS_CONFORMIDADE]  # type: ignore[valid-type]
    nota: float | None = None
    justificativa: str | None = None


class AprovacaoPedido(BaseModel):
    participante_id: int
    justificativa: str


class AprovacaoDecisao(BaseModel):
    aprovar: bool
    motivo: str | None = None


class ContratoEntrada(BaseModel):
    numero: str | None = None
    objeto: str | None = None
    valor: float | None = Field(default=None, ge=0)
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None
    sla: str | None = None
    garantia: str | None = None


@router.get("/processos")
def listar(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return [estrategico.como_dict(p) for p in estrategico.listar(db, tenant_id)]


@router.post("/processos", status_code=201)
def criar(dados: ProcessoEntrada, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
          db: Session = Depends(get_db)) -> dict:
    return estrategico.como_dict(estrategico.criar_processo(db, tenant_id, _usuario_id(ator_id), dados.model_dump()))


@router.get("/processos/{processo_id}/workspace")
def workspace(processo_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return estrategico.workspace(db, tenant_id, processo_id)


@router.post("/processos/{processo_id}/status")
def mudar_status(processo_id: int, dados: StatusEntrada, tenant_id: str = Depends(get_tenant_id),
                 ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return estrategico.como_dict(estrategico.mudar_status(db, tenant_id, _usuario_id(ator_id), processo_id, dados.status))


@router.post("/processos/{processo_id}/requisitos", status_code=201)
def adicionar_requisito(processo_id: int, dados: RequisitoEntrada, tenant_id: str = Depends(get_tenant_id),
                        ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    requisito = estrategico.adicionar_requisito(db, tenant_id, _usuario_id(ator_id), processo_id, dados.model_dump())
    return estrategico.serializar(requisito, estrategico.CAMPOS_REQUISITO)


@router.post("/processos/{processo_id}/itens", status_code=201)
def adicionar_item(processo_id: int, dados: ItemEntrada, tenant_id: str = Depends(get_tenant_id),
                   ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return estrategico.serializar(estrategico.adicionar_item(db, tenant_id, _usuario_id(ator_id), processo_id, dados.model_dump()),
                             estrategico.CAMPOS_ITEM)


@router.post("/processos/{processo_id}/descoberta")
def descobrir(processo_id: int, dados: DescobertaEntrada, tenant_id: str = Depends(get_tenant_id),
              db: Session = Depends(get_db)) -> dict:
    return estrategico.descobrir(db, tenant_id, processo_id, dados.necessidade, dados.ufs, dados.certificacoes)


@router.post("/processos/{processo_id}/participantes", status_code=201)
def convidar(processo_id: int, dados: ConviteEntrada, tenant_id: str = Depends(get_tenant_id),
             ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return estrategico.serializar(estrategico.convidar(db, tenant_id, _usuario_id(ator_id), processo_id, dados.model_dump()),
                             estrategico.CAMPOS_PARTICIPANTE)


@router.put("/processos/{processo_id}/participantes/{participante_id}")
def definir_participante(processo_id: int, participante_id: int, dados: SituacaoEntrada, tenant_id: str = Depends(get_tenant_id),
                         ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    participante = estrategico.definir_participante(db, tenant_id, _usuario_id(ator_id), processo_id, participante_id, dados.status,
                                                    dados.motivo)
    return estrategico.serializar(participante, estrategico.CAMPOS_PARTICIPANTE)


@router.post("/processos/{processo_id}/propostas", status_code=201)
def registrar_proposta(processo_id: int, dados: PropostaEntrada, tenant_id: str = Depends(get_tenant_id),
                       ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    proposta = estrategico.registrar_proposta(db, tenant_id, _usuario_id(ator_id), processo_id, dados.model_dump())
    return estrategico.serializar(proposta, estrategico.CAMPOS_PROPOSTA)


@router.put("/propostas/{proposta_id}/avaliacoes")
def avaliar(proposta_id: int, dados: AvaliacaoEntrada, tenant_id: str = Depends(get_tenant_id),
            ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    avaliacao = estrategico.avaliar(db, tenant_id, _usuario_id(ator_id), proposta_id, dados.requisito_id, dados.status, dados.nota,
                                    dados.justificativa)
    return {"proposta_id": avaliacao.proposta_id, "requisito_id": avaliacao.requisito_id, "status": avaliacao.status,
            "nota": float(avaliacao.nota) if avaliacao.nota is not None else None, "justificativa": avaliacao.justificativa}


@router.get("/processos/{processo_id}/comparacao")
def comparar(processo_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return estrategico.comparar(db, tenant_id, processo_id)


@router.post("/processos/{processo_id}/aprovacao")
def solicitar_aprovacao(processo_id: int, dados: AprovacaoPedido, tenant_id: str = Depends(get_tenant_id),
                        ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return estrategico.como_dict(estrategico.solicitar_aprovacao(db, tenant_id, _usuario_id(ator_id), processo_id,
                                                                 dados.participante_id, dados.justificativa))


@router.put("/processos/{processo_id}/aprovacao")
def decidir_aprovacao(processo_id: int, dados: AprovacaoDecisao, tenant_id: str = Depends(get_tenant_id),
                      usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return estrategico.como_dict(estrategico.decidir_aprovacao(db, tenant_id, usuario, processo_id, dados.aprovar, dados.motivo))


@router.post("/processos/{processo_id}/contrato", status_code=201)
def contratar(processo_id: int, dados: ContratoEntrada, tenant_id: str = Depends(get_tenant_id),
              ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return estrategico.serializar(estrategico.contratar(db, tenant_id, _usuario_id(ator_id), processo_id, dados.model_dump()),
                             estrategico.CAMPOS_CONTRATO)
