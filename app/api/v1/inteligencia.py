"""B2B ON Intelligence (Fase 4): Corporate Brain, perfis consolidados,
aprendizado, auditoria de uso de IA e registro de agentes. JWT; escopo
sempre o tenant do usuário logado."""

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db, get_usuario_atual
from app.contexts.intelligence import contract as intel
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.usuario import Usuario

router = APIRouter(prefix="/inteligencia", tags=["inteligencia"])


class ConhecimentoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo: str
    titulo: str = Field(min_length=1, max_length=200)
    conteudo: str = Field(min_length=1, max_length=8000)
    visibilidade: str = "interno"
    classificacao: str = "INTERNAL"
    fonte: str | None = Field(default=None, max_length=500)


class ConhecimentoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: str
    titulo: str
    conteudo: str
    origem: str
    classificacao: str
    visibilidade: str
    fonte: str | None
    criado_em: datetime | None


class PerfilSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    escopo: str
    usuario_id: int | None
    dados: dict
    fontes: dict
    versao: int
    atualizado_em: datetime | None


@router.get("/conhecimento/tipos")
def tipos_conhecimento() -> list[str]:
    return sorted(intel.brain.TIPOS)


@router.get("/conhecimento", response_model=list[ConhecimentoSchema])
def listar_conhecimento(tipo: str | None = None, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    return intel.brain.listar(db, usuario.tenant_id, tipo)


@router.post("/conhecimento", response_model=ConhecimentoSchema, status_code=201, dependencies=[Depends(exigir_papel("admin", "super_admin"))])
def criar_conhecimento(dados: ConhecimentoEntrada, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    return intel.brain.criar(db, usuario.tenant_id, usuario.id, dados.model_dump())


@router.delete("/conhecimento/{item_id}", status_code=204, dependencies=[Depends(exigir_papel("admin", "super_admin"))])
def arquivar_conhecimento(item_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> Response:
    intel.brain.arquivar(db, usuario.tenant_id, usuario.id, item_id)
    return Response(status_code=204)


@router.post("/perfil-empresa/consolidar", response_model=PerfilSchema)
def consolidar_perfil_empresa(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    return intel.perfis.consolidar_empresa(db, usuario.tenant_id)


@router.post("/perfil-usuario/consolidar", response_model=PerfilSchema)
def consolidar_perfil_usuario(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    return intel.perfis.consolidar_usuario(db, usuario.tenant_id, usuario.id)


@router.get("/aprendizado")
def resumo_aprendizado(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return intel.aprendizado.resumo(db, usuario.tenant_id)


@router.get("/uso-ia", dependencies=[Depends(exigir_papel("admin", "super_admin"))])
def uso_ia(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    """AI Audit do tenant (§73): chamadas por feature, status e tokens."""
    linhas = (
        db.query(
            RegistroUsoIa.feature, RegistroUsoIa.modulo, RegistroUsoIa.status,
            func.count(RegistroUsoIa.id), func.sum(RegistroUsoIa.tokens_entrada), func.sum(RegistroUsoIa.tokens_saida),
        )
        .filter(RegistroUsoIa.tenant_id == usuario.tenant_id)
        .group_by(RegistroUsoIa.feature, RegistroUsoIa.modulo, RegistroUsoIa.status)
        .all()
    )
    return [
        {"feature": f, "modulo": m, "status": s, "chamadas": c, "tokens_entrada": int(te or 0), "tokens_saida": int(ts or 0)}
        for f, m, s, c, te, ts in linhas
    ]


@router.get("/agentes")
def listar_agentes() -> list[dict]:
    return [
        {"id": a.id, "nome": a.nome, "dominio": a.dominio, "status": a.status.value, "ferramentas": list(a.ferramentas)}
        for a in intel.registro.AGENTES.values()
    ]


@router.get("/features")
def listar_features() -> list[dict]:
    return [
        {"nome": f.nome, "modulo": f.modulo, "agente": f.agente, "classe_modelo": f.classe.value, "gatilho": f.gatilho.value, "descricao": f.descricao}
        for f in intel.registro.FEATURES.values()
    ]
