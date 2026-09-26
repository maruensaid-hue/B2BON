"""Portal do fornecedor (Phase F, D-066): responder ao processo do comprador privado.

Dois jeitos de chegar ao mesmo convite:
- `/portal-fornecedor` — link secreto, **sem login e sem assento** (Supplier
  Guest). O segredo vai no cabeçalho `X-Convite-Token`, nunca no caminho (o
  log de acesso registra caminhos).
- `/rede/convites-sourcing` — empresa da Business Network logada vê os
  convites que recebeu e responde pela própria conta.

As duas entradas chamam as mesmas funções (`procurement.portal`); a visão é
sempre restrita ao próprio participante.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_usuario_atual
from app.contexts.procurement import contract as compras
from app.core.rate_limit import limitador_portal
from app.models.usuario import Usuario

portal = compras.portal


def _limitar(request: Request) -> None:
    ip = request.client.host if request.client else "desconhecido"
    limitador_portal.checar(f"portal:{ip}", 120, 60)


router_link = APIRouter(prefix="/portal-fornecedor", tags=["portal-fornecedor"], dependencies=[Depends(_limitar)])
router_rede = APIRouter(prefix="/rede/convites-sourcing", tags=["portal-fornecedor"])


class PerguntaEntrada(BaseModel):
    pergunta: str = Field(min_length=3, max_length=2000)


class PrecoItem(BaseModel):
    item_id: int
    preco_unitario: float = Field(ge=0)


class RespostaRequisito(BaseModel):
    requisito_id: int
    resposta: str | None = Field(default=None, max_length=5000)


class PropostaEntrada(BaseModel):
    valor_total: float | None = Field(default=None, ge=0)
    moeda: str | None = None
    prazo_entrega_dias: int | None = Field(default=None, ge=0)
    condicoes_pagamento: str | None = Field(default=None, max_length=300)
    impostos_inclusos: bool | None = None
    validade: date | None = None
    observacoes: str | None = Field(default=None, max_length=5000)
    itens: list[PrecoItem] = []
    respostas: list[RespostaRequisito] = []


class DeclinioEntrada(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


def _por_link(x_convite_token: str = Header(default=""), db: Session = Depends(get_db)):
    return portal.por_token(db, x_convite_token)


def _proposta_dict(proposta) -> dict:
    return {"id": proposta.id, "rodada": proposta.rodada,
            "valor_total": float(proposta.valor_total) if proposta.valor_total is not None else None}


def _rotas(router: APIRouter, participante_de, prefixo: str) -> None:
    """Mesmas ações nas duas entradas; `participante_de` resolve quem está falando."""

    @router.get(f"{prefixo}")
    def ver(participante=Depends(participante_de), db: Session = Depends(get_db)) -> dict:
        return portal.visao(db, participante)

    @router.post(f"{prefixo}/perguntas", status_code=201)
    def perguntar(dados: PerguntaEntrada, participante=Depends(participante_de), db: Session = Depends(get_db)) -> dict:
        portal.perguntar(db, participante, dados.pergunta)
        return {"ok": True}

    @router.post(f"{prefixo}/propostas", status_code=201)
    def enviar(dados: PropostaEntrada, participante=Depends(participante_de), db: Session = Depends(get_db)) -> dict:
        return _proposta_dict(portal.enviar_proposta(db, participante, dados.model_dump()))

    @router.post(f"{prefixo}/propostas/{{proposta_id}}/anexos", status_code=201)
    async def anexar(proposta_id: int, arquivo: UploadFile = File(...), participante=Depends(participante_de),
                     db: Session = Depends(get_db)) -> dict:
        anexo = portal.anexar(db, participante, proposta_id, arquivo.filename or "anexo", arquivo.content_type or "",
                              await arquivo.read())
        return {"id": anexo.id, "nome_arquivo": anexo.nome_arquivo, "sha256": anexo.sha256}

    @router.post(f"{prefixo}/declinar")
    def declinar(dados: DeclinioEntrada, participante=Depends(participante_de), db: Session = Depends(get_db)) -> dict:
        return {"situacao": portal.declinar(db, participante, dados.motivo).status}


_rotas(router_link, _por_link, "")


@router_rede.get("")
def convites(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    return portal.convites_da_empresa(db, usuario.tenant_id)


def _por_conta(participante_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    return portal.por_empresa(db, usuario.tenant_id, participante_id)


_rotas(router_rede, _por_conta, "/{participante_id}")
