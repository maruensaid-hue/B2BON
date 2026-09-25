"""B2B ON Intelligence (Fase 4): Corporate Brain, perfis consolidados,
aprendizado, auditoria de uso de IA e registro de agentes. JWT; escopo
sempre o tenant do usuário logado."""

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db, get_llm_provider, get_plan_limits_provider, get_usuario_atual, limitar_ia_por_tenant
from app.contexts.intelligence import contract as intel
from app.contexts.shared.entitlements import Entitlements
from app.llm.base import LLMProvider
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.usuario import Usuario
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services import auditoria_service

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


# --- B2B ON Intelligence Agent (Fase 12) ------------------------------------------


class PerguntaAgente(BaseModel):
    pergunta: str = Field(min_length=3, max_length=1000)


def _contexto_agente(usuario: Usuario, plan_limits: PlanLimitsProvider):
    entitlements = Entitlements(plan_limits, usuario.tenant_id)
    ctx = intel.ContextoFerramenta(tenant_id=usuario.tenant_id, usuario_id=usuario.id, papel=usuario.papel)
    return ctx, entitlements.has_module


@router.get("/agente/ferramentas")
def ferramentas_do_agente(usuario: Usuario = Depends(get_usuario_atual),
                          plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider)) -> list[dict]:
    """Só o que ESTE usuário pode usar (plano, papel, agente autorizado)."""
    ctx, tem_modulo = _contexto_agente(usuario, plan_limits)
    return intel.orquestrador.catalogo(ctx, tem_modulo)


@router.post("/agente", dependencies=[Depends(limitar_ia_por_tenant())])
def perguntar_ao_agente(
    dados: PerguntaAgente,
    usuario: Usuario = Depends(get_usuario_atual),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> dict:
    """B2B ON Intelligence Agent: escolhe o agente e a ferramenta; lê, propõe ou recusa."""
    ctx, tem_modulo = _contexto_agente(usuario, plan_limits)
    resposta = intel.orquestrador.perguntar(db, llm, ctx, dados.pergunta, tem_modulo)
    auditoria_service.registrar(db, usuario.tenant_id, "intelligence_agent_consulta", "usuario", usuario.id, str(usuario.id),
                                {"ferramenta": resposta["ferramenta"], "status": resposta["status"], "roteamento": resposta["roteamento"]})
    db.commit()
    return resposta
