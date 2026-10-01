"""MAP Performance Comercial (D-080): quotas, funil, atividade, comissão recorrente, campanhas e Daily Comercial.

Acesso decidido no contexto (`map.contract.performance`): super_admin = gestão comercial da CyberFort; usuário vinculado
a um representante vê só o próprio painel. Sem response_model fixo: os painéis são leituras agregadas versionadas pela
política vigente."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_usuario_atual
from app.contexts.map import contract as map_contract
from app.models.usuario import Usuario

router = APIRouter(prefix="/map/performance", tags=["map-performance"])


class PoliticaSchema(BaseModel):
    codigo: str
    regras: dict
    motivo: str


class QuotaSchema(BaseModel):
    representante_id: int | None = None
    competencia: str
    valor: float
    multiplo_cobertura: float | None = None
    pipeline_alvo: float | None = None
    motivo: str


class VinculoSchema(BaseModel):
    usuario_id: int | None = Field(default=None)


def _hoje(data_referencia: date | None) -> date:
    return data_referencia or datetime.now(UTC).date()


def _competencia(competencia: str | None, hoje: date) -> str:
    return competencia or hoje.strftime("%Y-%m")


@router.get("/acesso")
def acesso(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return map_contract.performance.acesso(db, usuario)


@router.get("/painel")
def painel(representante_id: int | None = None, competencia: str | None = None, data_referencia: date | None = None,
           usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    hoje = _hoje(data_referencia)
    resultado = map_contract.performance.painel_individual(db, usuario, representante_id, _competencia(competencia, hoje), hoje)
    db.commit()  # semente das políticas/quotas na primeira leitura de bancos sem a migração
    return resultado


@router.get("/equipe")
def equipe(competencia: str | None = None, data_referencia: date | None = None, usuario: Usuario = Depends(get_usuario_atual),
           db: Session = Depends(get_db)) -> dict:
    hoje = _hoje(data_referencia)
    resultado = map_contract.performance.painel_equipe(db, usuario, _competencia(competencia, hoje), hoje)
    db.commit()
    return resultado


@router.get("/daily")
def daily(competencia: str | None = None, data_referencia: date | None = None, usuario: Usuario = Depends(get_usuario_atual),
          db: Session = Depends(get_db)) -> dict:
    hoje = _hoje(data_referencia)
    resultado = map_contract.performance.daily_comercial(db, usuario, _competencia(competencia, hoje), hoje)
    db.commit()
    return resultado


@router.get("/configuracao")
def configuracao(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    resultado = map_contract.performance.configuracao_atual(db, usuario)
    db.commit()
    return resultado


@router.post("/politicas", status_code=201)
def nova_politica(dados: PoliticaSchema, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    resultado = map_contract.performance.nova_politica(db, usuario, dados.codigo, dados.regras, dados.motivo)
    db.commit()
    return resultado


@router.post("/quotas", status_code=201)
def definir_quota(dados: QuotaSchema, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    resultado = map_contract.performance.definir_quota(db, usuario, dados.model_dump(exclude={"motivo"}), dados.motivo)
    db.commit()
    return resultado


@router.put("/representantes/{representante_id}/usuario")
def vincular(representante_id: int, dados: VinculoSchema, usuario: Usuario = Depends(get_usuario_atual),
             db: Session = Depends(get_db)) -> dict:
    rep = map_contract.performance.vincular_usuario(db, usuario, representante_id, dados.usuario_id)
    db.commit()
    return {"id": rep.id, "nome": rep.nome, "usuario_id": rep.usuario_id}
