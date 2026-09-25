"""AI FinOps & Credits (Fase 5; B2B ON AI Credits na Fase 15).

- Plataforma (super_admin): dashboard cross-tenant em USD, tabela de
  custo por modelo, ajustes/promoções de crédito, excedente Enterprise,
  estorno, reconciliação, economia (receita, custo, margem), catálogos
  versionados de workloads e de pacotes (mudança = nova versão auditada).
- Tenant (admin/super_admin): o próprio consumo em chamadas e créditos,
  saldo, extrato e orçamentos. Custo do provedor em USD NÃO é exposto ao
  tenant (é custo interno da B2B ON)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_usuario_atual
from app.contexts.finops import contract as finops
from app.models.creditos_ia import CatalogoCreditos, LoteCreditos, PacoteCreditos
from app.models.preco_modelo_ia import PrecoModeloIa
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, ValidacaoFalhou

router = APIRouter(prefix="/finops", tags=["finops"])
_super = [Depends(exigir_papel("super_admin"))]
_gestor = [Depends(exigir_papel("admin", "super_admin"))]


def _janela(inicio: datetime | None, fim: datetime | None) -> tuple[datetime, datetime]:
    agora = datetime.now(UTC).replace(tzinfo=None)
    fim = fim or agora + timedelta(seconds=1)
    inicio = inicio or datetime(fim.year, fim.month, 1)
    if inicio >= fim:
        raise ValidacaoFalhou("inicio deve ser anterior a fim.")
    return inicio, fim


class OrcamentoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    escopo: str = "tenant"
    alvo: str | None = None
    limite_custo_usd: float | None = Field(default=None, gt=0)
    limite_chamadas: int | None = Field(default=None, gt=0)
    acao: str = "ALERTAR"
    percentual_alerta: int = Field(default=80, ge=1, le=100)


# --- Plataforma --------------------------------------------------------------------
@router.get("/resumo", dependencies=_super)
def resumo_plataforma(inicio: datetime | None = None, fim: datetime | None = None, db: Session = Depends(get_db)) -> dict:
    return finops.dashboard.resumo(db, *_janela(inicio, fim))


@router.get("/precos", dependencies=_super)
def precos(db: Session = Depends(get_db)) -> list[dict]:
    linhas = db.query(PrecoModeloIa).order_by(PrecoModeloIa.modelo, PrecoModeloIa.vigente_desde.desc()).all()
    return [
        {"modelo": p.modelo, "provider": p.provider, "vigente_desde": p.vigente_desde.isoformat(), "entrada_usd_mtok": float(p.entrada_usd_mtok),
         "saida_usd_mtok": float(p.saida_usd_mtok), "cache_escrita_usd_mtok": float(p.cache_escrita_usd_mtok),
         "cache_leitura_usd_mtok": float(p.cache_leitura_usd_mtok), "fonte": p.fonte}
        for p in linhas
    ]


def _politica_dict(politica) -> dict | None:
    if politica is None:
        return None
    return {"status": politica.status, "creditos_por_usd": float(politica.creditos_por_usd) if politica.creditos_por_usd is not None else None,
            "permite_excedente": politica.permite_excedente, "exige_saldo": politica.exige_saldo, "observacao": politica.observacao,
            "legado": True}


@router.get("/politica-creditos", dependencies=_super)
def obter_politica(db: Session = Depends(get_db)) -> dict | None:
    """Legado (Fase 5): conversão custo→créditos. Desde a Fase 15 o crédito
    vem do peso do workload (catálogo versionado); ver /finops/catalogo."""
    return _politica_dict(finops.creditos.politica_vigente(db))


class AjusteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantidade: float = Field(description="Positivo concede; negativo debita.")
    motivo: str = Field(min_length=3, max_length=300)
    tipo: str = Field(default="ADJUSTMENT", pattern="^(ADJUSTMENT|PROMOTIONAL)$")
    validade_dias: int | None = Field(default=None, gt=0, le=3650)


@router.post("/tenants/{tenant_id}/creditos", dependencies=_super)
def ajustar_creditos(tenant_id: str, dados: AjusteRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Concessão, promoção ou débito administrativo — auditado com valor anterior e novo."""
    expira = finops.carteira.agora_utc() + timedelta(days=dados.validade_dias) if dados.validade_dias else None
    resultado = finops.carteira.ajustar(db, tenant_id, Decimal(str(dados.quantidade)), dados.motivo, ator_id,
                                        tipo=finops.comercial.TipoLote(dados.tipo), expira_em=expira)
    return {"tenant_id": tenant_id, **resultado}


class ExcedenteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ativo: bool
    orcamento_mensal: int | None = Field(default=None, gt=0)
    limite_suave: int | None = Field(default=None, gt=0)
    limite_rigido: int | None = Field(default=None, gt=0)
    franquia_personalizada: int | None = Field(default=None, ge=0, description="Enterprise: pool mensal por contrato.")
    motivo: str = Field(min_length=3, max_length=300)


@router.put("/tenants/{tenant_id}/excedente", dependencies=_super)
def configurar_excedente(tenant_id: str, dados: ExcedenteRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Enterprise: excedente pós-pago (consumo faturável) e pool próprio."""
    config = finops.carteira.configuracao(db, tenant_id)
    anterior = {"ativo": config.excedente_ativo, "orcamento_mensal": config.excedente_orcamento_mensal,
                "limite_suave": config.excedente_limite_suave, "limite_rigido": config.excedente_limite_rigido,
                "franquia_personalizada": config.franquia_personalizada}
    config.excedente_ativo = dados.ativo
    config.excedente_orcamento_mensal, config.excedente_limite_suave = dados.orcamento_mensal, dados.limite_suave
    config.excedente_limite_rigido, config.franquia_personalizada = dados.limite_rigido, dados.franquia_personalizada
    config.excedente_aprovado_por = ator_id if dados.ativo else None
    novo = {k: v for k, v in dados.model_dump().items() if k != "motivo"}
    auditoria_service.registrar(db, tenant_id, "excedente_ia_configurado", "configuracao_credito_tenant", config.id, ator_id,
                                {"valor_anterior": anterior, "valor_novo": novo, "motivo": dados.motivo})
    db.commit()
    return {"tenant_id": tenant_id, **novo, "excedente_no_mes": float(finops.carteira.excedente_no_mes(db, tenant_id))}


class EstornoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=3, max_length=300)


@router.post("/execucoes/{execucao_id}/estorno", dependencies=_super)
def estornar_execucao(execucao_id: str, dados: EstornoRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    execucao = finops.execucoes.estornar(db, execucao_id, dados.motivo, ator_id)
    return {"execucao_id": execucao.id, "status": execucao.status}


@router.get("/reconciliacao", dependencies=_super)
def reconciliacao(tenant_id: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    """Extrato × lotes × reservas por tenant (inclui saldos migrados da Fase 5)."""
    tenants = [tenant_id] if tenant_id else [t for (t,) in db.query(LoteCreditos.tenant_id).distinct().all()]
    return [finops.carteira.reconciliar(db, t) for t in tenants]


# --- Economia dos AI Credits (Fase 15) ------------------------------------------
def _dias(dias: int) -> tuple[datetime, datetime]:
    if dias not in (7, 30, 90, 1, 365):
        raise ValidacaoFalhou("dias deve ser 1, 7, 30, 90 ou 365.")
    return finops.economia.janela(dias)


@router.get("/economia", dependencies=_super)
def economia(dias: int = 30, db: Session = Depends(get_db)) -> dict:
    return finops.economia.kpis(db, *_dias(dias))


@router.get("/margens", dependencies=_super)
def margens(dimensao: str = "modulo", dias: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    if dimensao not in finops.economia.DIMENSOES:
        raise ValidacaoFalhou(f"dimensao deve ser uma de {finops.economia.DIMENSOES}")
    return finops.economia.margens(db, dimensao, *_dias(dias))


@router.get("/matriz-rentabilidade", dependencies=_super)
def matriz(dias: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    return finops.economia.matriz_rentabilidade(db, *_dias(dias))


@router.get("/alertas-margem", dependencies=_super)
def alertas_margem(db: Session = Depends(get_db)) -> list[dict]:
    return finops.economia.alertas_margem(db)


@router.get("/recomendacoes-peso", dependencies=_super)
def recomendacoes_peso(dias: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    _dias(dias)
    return finops.economia.recomendacoes_peso(db, dias)


@router.get("/economia-unitaria", dependencies=_super)
def economia_unitaria(dias: int = 30, db: Session = Depends(get_db)) -> dict:
    return finops.economia.economia_unitaria(db, *_dias(dias))


@router.get("/relatorio-calibracao", dependencies=_super)
def relatorio_calibracao(dias: int = 30, db: Session = Depends(get_db)) -> dict:
    if dias not in (7, 30, 90):
        raise ValidacaoFalhou("Relatório de calibração: 7, 30 ou 90 dias.")
    return finops.economia.relatorio_calibracao(db, dias)


# --- Catálogos versionados ----------------------------------------------------------
@router.get("/catalogo", dependencies=_super)
def catalogo(versao: str | None = None, db: Session = Depends(get_db)) -> dict:
    ativo = finops.catalogos.catalogo_ativo(db)
    alvo = finops.catalogos.obter_catalogo(db, versao) if versao else ativo
    versoes = db.query(CatalogoCreditos).order_by(CatalogoCreditos.numero).all()
    return {
        "ativo": ativo.versao, "versao": alvo.versao, "status": alvo.status,
        "versoes": [{"versao": c.versao, "status": c.status, "motivo": c.motivo, "criado_por": c.criado_por,
                     "aprovado_por": c.aprovado_por, "vigente_desde": c.vigente_desde.isoformat() if c.vigente_desde else None}
                    for c in versoes],
        "workloads": [finops.catalogos.workload_dict(w) for w in finops.catalogos.workloads(db, alvo)],
    }


class RascunhoCatalogoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mudancas: dict[str, dict]
    motivo: str = Field(min_length=3, max_length=500)


@router.post("/catalogo/rascunhos", status_code=201, dependencies=_super)
def criar_rascunho(dados: RascunhoCatalogoRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    rascunho = finops.catalogos.criar_rascunho(db, dados.mudancas, ator_id, dados.motivo)
    return {"versao": rascunho.versao, "status": rascunho.status}


class MotivoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=3, max_length=500)


@router.post("/catalogo/{versao}/ativar", dependencies=_super)
def ativar_catalogo(versao: str, dados: MotivoRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    ativo = finops.catalogos.ativar(db, versao, ator_id, dados.motivo)
    return {"versao": ativo.versao, "status": ativo.status}


@router.get("/pacotes", dependencies=_super)
def pacotes_historico(db: Session = Depends(get_db)) -> list[dict]:
    finops.catalogos.garantir_semente(db)
    return [{**finops.catalogos.pacote_dict(p), "valido_ate": p.valido_ate.isoformat() if p.valido_ate else None}
            for p in db.query(PacoteCreditos).order_by(PacoteCreditos.ordem, PacoteCreditos.versao).all()]


class VersaoPacoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preco: float = Field(gt=0)
    creditos: int = Field(gt=0)
    validade_meses: int | None = Field(default=None, gt=0, le=60)
    motivo: str = Field(min_length=3, max_length=500)


@router.post("/pacotes/{codigo}/versoes", status_code=201, dependencies=_super)
def nova_versao_pacote(codigo: str, dados: VersaoPacoteRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Mudança de preço é decisão humana explícita: nova versão auditada."""
    pacote = finops.catalogos.nova_versao_pacote(db, codigo, Decimal(str(dados.preco)), dados.creditos, dados.validade_meses, ator_id, dados.motivo)
    return finops.catalogos.pacote_dict(pacote)


# --- Tenant -------------------------------------------------------------------------
@router.get("/meu-uso", dependencies=_gestor)
def meu_uso(inicio: datetime | None = None, fim: datetime | None = None, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    completo = finops.dashboard.resumo(db, *_janela(inicio, fim), tenant_id=usuario.tenant_id)
    totais = completo["totais"]
    return {
        "periodo": completo["periodo"],
        "politica_creditos": completo["politica_creditos"],
        "chamadas": totais["chamadas"],
        "por_status": totais["por_status"],
        "creditos_consumidos": totais["creditos_consumidos"],
        "saldo_creditos": float(finops.carteira.disponivel(db, usuario.tenant_id)),
        "por_modulo": [{"modulo": i["chave"], "chamadas": i["chamadas"], "creditos": i["creditos"]} for i in completo["por_modulo"]],
        "por_feature": [{"feature": i["chave"], "chamadas": i["chamadas"], "creditos": i["creditos"]} for i in completo["por_feature"]],
    }


@router.get("/extrato", dependencies=_gestor)
def extrato(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"id": m.id, "tipo": m.tipo, "quantidade": float(m.quantidade), "saldo_apos": float(m.saldo_apos), "descricao": m.descricao,
         "criado_em": m.criado_em.isoformat() if m.criado_em else None}
        for m in finops.creditos.extrato(db, usuario.tenant_id)
    ]


@router.get("/orcamentos", dependencies=_gestor)
def listar_orcamentos(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    ve_custo = usuario.papel == "super_admin"
    resultado = []
    for estado in finops.orcamentos.estados(db, usuario.tenant_id):
        item = {**estado.__dict__}
        item["custo_usd"] = float(estado.custo_usd) if ve_custo else None
        item["limite_custo_usd"] = float(estado.limite_custo_usd) if ve_custo and estado.limite_custo_usd is not None else None
        resultado.append(item)
    return resultado


@router.post("/orcamentos", status_code=201, dependencies=_gestor)
def criar_orcamento(dados: OrcamentoRequest, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    """Admin do tenant limita por número de chamadas; limite em USD (custo
    interno da B2B ON) só o super_admin define."""
    if dados.limite_custo_usd is not None and usuario.papel != "super_admin":
        raise NaoAutorizado("Limite por custo em USD é definido pela operação da B2B ON; use limite_chamadas.")
    orcamento = finops.orcamentos.criar(db, usuario.tenant_id, dados.model_dump())
    return {"id": orcamento.id}
