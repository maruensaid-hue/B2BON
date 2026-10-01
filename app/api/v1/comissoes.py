"""Commission Engine (D-074): parâmetros financeiros e memória de cálculo. Só super_admin."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db
from app.contexts.comissoes import contract as comissoes
from app.contexts.governo import contract as governo
from app.models.apuracao_comissao import ApuracaoComissao, ModeloCustoInfra, PerfilTributario
from app.schemas.comissoes import ModeloCustoInfraSchema, PerfilTributarioSchema, RecalculoSchema

router = APIRouter(prefix="/comissoes", tags=["comissoes"], dependencies=[Depends(exigir_papel("super_admin"))])


@router.get("/parametros")
def parametros(db: Session = Depends(get_db)) -> dict:
    hoje = date.today()
    perfis = db.query(PerfilTributario).order_by(PerfilTributario.vigente_de.desc(), PerfilTributario.id.desc()).all()
    modelos = db.query(ModeloCustoInfra).order_by(ModeloCustoInfra.vigente_de.desc(), ModeloCustoInfra.id.desc()).all()
    vigente = governo.politicas.politica_vigente(db)
    db.commit()
    return {
        "perfis_tributarios": [comissoes.tributos.como_dict(p) for p in perfis],
        "modelos_custo_infra": [comissoes.infraestrutura.como_dict(m) for m in modelos],
        "modelo_vigente_id": (m.id if (m := comissoes.infraestrutura.aplicavel(db, hoje)) else None),
        "componentes_infra": list(comissoes.tipos.COMPONENTES_INFRA),
        "tipos_receita": sorted(set(comissoes.tipos.TIPO_RECEITA_POR_COMPONENTE.values()) | {comissoes.tipos.QUALQUER}),
        "politica_governo": {"versao": vigente.versao, "regras": vigente.regras},
        "politica_privada": "% de comissão de cada representante (Admin → Representantes), sobre a Margem Comissionável Líquida",
    }


@router.post("/perfis-tributarios", status_code=201)
def criar_perfil(dados: PerfilTributarioSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    perfil = comissoes.tributos.criar(db, {**dados.model_dump(), "componentes": [c.model_dump() for c in dados.componentes]}, ator_id)
    calculadas = comissoes.motor.recalcular_aguardando(db)
    db.commit()
    return {"perfil": comissoes.tributos.como_dict(perfil), "aguardando_calculadas": calculadas}


@router.post("/modelos-custo-infra", status_code=201)
def criar_modelo(dados: ModeloCustoInfraSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    modelo = comissoes.infraestrutura.criar(db, dados.model_dump(), ator_id)
    calculadas = comissoes.motor.recalcular_aguardando(db)
    db.commit()
    return {"modelo": comissoes.infraestrutura.como_dict(modelo), "aguardando_calculadas": calculadas}


@router.post("/recalculo")
def recalcular(dados: RecalculoSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Recálculo explícito (auditado) das apurações ainda não pagas. Comissões pagas nunca mudam."""
    return comissoes.motor.recalcular_nao_pagas(db, dados.motivo, ator_id)


@router.get("/apuracoes")
def apuracoes(status: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    consulta = db.query(ApuracaoComissao).order_by(ApuracaoComissao.recebido_em.desc(), ApuracaoComissao.id.desc())
    if status:
        consulta = consulta.filter_by(status=status)
    return [comissoes.motor.apuracao_dict(a) for a in consulta.limit(500).all()]


@router.get("/waterfall")
def waterfall(agrupar: str = "tenant", inicio: date | None = None, fim: date | None = None, tenant_id: str | None = None,
              db: Session = Depends(get_db)) -> dict:
    return comissoes.waterfall.calcular(db, agrupar, inicio, fim, tenant_id)
