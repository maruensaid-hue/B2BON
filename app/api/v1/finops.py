"""AI FinOps & Credits (Fase 5).

- Plataforma (super_admin): dashboard cross-tenant em USD, tabela de
  custo por modelo, política de créditos, alocação de créditos.
- Tenant (admin/super_admin): o próprio consumo em chamadas e créditos,
  saldo, extrato e orçamentos. Custo do provedor em USD NÃO é exposto ao
  tenant (é custo interno da B2B ON)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_usuario_atual
from app.contexts.finops import contract as finops
from app.models.preco_modelo_ia import PrecoModeloIa
from app.models.usuario import Usuario
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


class PoliticaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    creditos_por_usd: float = Field(gt=0)
    permite_excedente: bool = False
    exige_saldo: bool = False
    observacao: str | None = Field(default=None, max_length=500)


class AlocacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantidade: float = Field(gt=0)
    descricao: str | None = Field(default=None, max_length=300)


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
            "permite_excedente": politica.permite_excedente, "exige_saldo": politica.exige_saldo, "observacao": politica.observacao}


@router.get("/politica-creditos", dependencies=_super)
def obter_politica(db: Session = Depends(get_db)) -> dict | None:
    return _politica_dict(finops.creditos.politica_vigente(db))


@router.post("/politica-creditos", dependencies=_super)
def definir_politica(dados: PoliticaRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict | None:
    return _politica_dict(finops.creditos.definir_politica(db, ator_id, dados.creditos_por_usd, dados.permite_excedente, dados.exige_saldo, dados.observacao))


@router.post("/tenants/{tenant_id}/creditos", dependencies=_super)
def alocar_creditos(tenant_id: str, dados: AlocacaoRequest, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    movimento = finops.creditos.alocar(db, tenant_id, dados.quantidade, ator_id, dados.descricao)
    return {"tenant_id": tenant_id, "saldo": float(movimento.saldo_apos)}


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
        "saldo_creditos": float(finops.creditos.saldo(db, usuario.tenant_id)),
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
