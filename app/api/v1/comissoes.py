"""Commission Engine (D-074, D-075): parâmetros financeiros (Tax Profile, Infrastructure Cost Model, câmbio, Commission
Policy da margem) e memória de cálculo. Só super_admin."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db
from app.contexts.comissoes import contract as comissoes
from app.contexts.finops import contract as finops
from app.contexts.governo import contract as governo
from app.models.apuracao_comissao import ApuracaoComissao, ModeloCustoInfra, PerfilTributario
from app.models.cotacao_cambio import CotacaoCambio
from app.schemas.comissoes import (
    CotacaoCambioSchema,
    ModeloCustoInfraSchema,
    PerfilTributarioSchema,
    PoliticaMargemSchema,
    RecalculoSchema,
)

router = APIRouter(prefix="/comissoes", tags=["comissoes"], dependencies=[Depends(exigir_papel("super_admin"))])


@router.get("/parametros")
def parametros(db: Session = Depends(get_db)) -> dict:
    hoje = date.today()
    perfis = db.query(PerfilTributario).order_by(PerfilTributario.vigente_de.desc(), PerfilTributario.id.desc()).all()
    modelos = db.query(ModeloCustoInfra).order_by(ModeloCustoInfra.vigente_de.desc(), ModeloCustoInfra.id.desc()).all()
    cotacoes = db.query(CotacaoCambio).order_by(CotacaoCambio.vigente_em.desc(), CotacaoCambio.id.desc()).limit(50).all()
    vigente = governo.politicas.politica_vigente(db)
    margem = comissoes.politica.vigente(db)
    modelo_vigente = comissoes.infraestrutura.aplicavel(db, hoje)
    cambio = finops.cambio.aplicavel(db)
    db.commit()
    return {
        "perfis_tributarios": [comissoes.tributos.como_dict(p) for p in perfis],
        "modelos_custo_infra": [comissoes.infraestrutura.como_dict(m) for m in modelos],
        "modelo_vigente_id": modelo_vigente.id if modelo_vigente else None,
        "cotacoes_cambio": [finops.cambio.como_dict(c) for c in cotacoes],
        "cotacao_vigente": finops.cambio.como_dict(cambio) if cambio else None,
        "tributos": [t.value for t in comissoes.tipos.Tributo], "bases_tributo": [b.value for b in comissoes.tipos.BaseTributo],
        "categorias_infra": list(comissoes.tipos.CATEGORIAS_INFRA), "metodos_infra": comissoes.tipos.METODOS_INFRA,
        "tipos_receita": sorted(set(comissoes.tipos.TIPO_RECEITA_POR_COMPONENTE.values()) | {comissoes.tipos.QUALQUER}),
        "politica_governo": {"versao": vigente.versao, "regras": vigente.regras},
        "politica_margem": {"versao": margem.versao, "regras": margem.regras},
        "politica_privada": "% de comissão de cada representante (Admin → Representantes), sobre a Margem Comissionável Líquida",
        "pendentes": _pendentes(db, hoje, modelo_vigente, cambio, margem.regras),
    }


def _pendentes(db: Session, hoje: date, modelo_vigente, cambio, regras_margem: dict) -> list[str]:
    """O que ainda falta para as comissões de hoje saírem de AWAITING (mostrado na tela e no relatório)."""
    faltam = []
    for tipo in sorted(set(comissoes.tipos.TIPO_RECEITA_POR_COMPONENTE.values())):
        perfil = comissoes.tributos.aplicavel(db, tipo, hoje)
        if perfil is None:
            faltam.append(f"Tax Profile vigente para {tipo}")
        else:
            faltam += [f"Tax Profile {tipo}: {item}" for item in comissoes.tributos.pendencias(perfil)]
    if modelo_vigente is None:
        faltam.append("Infrastructure Cost Model (custos reais de infraestrutura)")
    if cambio is None and regras_margem.get("deduzir_custo_ia"):
        faltam.append("Cotação USD/BRL (a política deduz custo de IA)")
    return faltam


@router.post("/perfis-tributarios", status_code=201)
def criar_perfil(dados: PerfilTributarioSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    perfil = comissoes.tributos.criar(db, dados.model_dump(), ator_id)
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


@router.post("/cotacoes-cambio", status_code=201)
def registrar_cotacao(dados: CotacaoCambioSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """OI-018: cotação com fonte e vigência. Apurações que aguardavam câmbio são refeitas."""
    linha = finops.cambio.registrar(db, dados.model_dump(), ator_id)
    calculadas = comissoes.motor.recalcular_aguardando(db)
    db.commit()
    return {"cotacao": finops.cambio.como_dict(linha), "aguardando_calculadas": calculadas}


@router.post("/politica-margem", status_code=201)
def alterar_politica_margem(dados: PoliticaMargemSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Nova versão da Commission Policy da margem (ex.: passar a deduzir o custo de IA). Vale para apurações novas e para
    o recálculo explícito das não pagas; comissões pagas não mudam."""
    politica = comissoes.politica.nova(db, {"deduzir_custo_ia": dados.deduzir_custo_ia}, dados.motivo, ator_id)
    db.commit()
    return {"versao": politica.versao, "regras": politica.regras}


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
