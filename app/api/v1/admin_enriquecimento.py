"""Administração dos créditos de enriquecimento (somente super_admin): configuração versionada por plano/tenant, orçamento global do provedor,
ajustes, estornos e reconciliação. Toda alteração é auditada e exige motivo. Nenhuma credencial do provedor passa por aqui."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db
from app.contexts.enriquecimento.contract import config, execucao, ledger, painel
from app.models.enriquecimento_creditos import EnriquecimentoConfigPlano
from app.models.usuario import Usuario

router = APIRouter(prefix="/admin/enriquecimento", tags=["admin"])
_super = Depends(exigir_papel("super_admin"))


class ConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plano_id: int | None = None
    tenant_id: str | None = Field(default=None, max_length=100)
    franquia_creditos: int | None = Field(default=None, ge=0)
    periodicidade: str | None = None
    decisores_por_empresa_padrao: int | None = Field(default=None, ge=1)
    decisores_por_empresa_max: int | None = Field(default=None, ge=1)
    itens_por_lote_max: int | None = Field(default=None, ge=1)
    limite_periodo_creditos: int | None = Field(default=None, ge=0)
    motivo: str = Field(min_length=3, max_length=300)


class OrcamentoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str = Field(min_length=2, max_length=50)
    limite_creditos: int | None = Field(default=None, ge=0)
    alerta_percentual: int = Field(default=80, ge=1, le=100)
    motivo: str = Field(min_length=3, max_length=300)


class AjusteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantidade: int
    motivo: str = Field(min_length=3, max_length=300)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class EstornoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantidade: int = Field(gt=0)
    motivo: str = Field(min_length=3, max_length=300)
    pesquisa_id: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class ReconciliacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creditos_consumidos: int = Field(ge=0)
    motivo: str = Field(min_length=3, max_length=300)


class EncerrarReconciliacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=3, max_length=300)


def _linha(c: EnriquecimentoConfigPlano) -> dict:
    return {"id": c.id, "plano_id": c.plano_id, "tenant_id": c.tenant_id, "versao": c.versao, "franquia_creditos": c.franquia_creditos,
            "periodicidade": c.periodicidade, "decisores_por_empresa_padrao": c.decisores_por_empresa_padrao,
            "decisores_por_empresa_max": c.decisores_por_empresa_max, "itens_por_lote_max": c.itens_por_lote_max,
            "limite_periodo_creditos": c.limite_periodo_creditos, "valido_de": c.valido_de, "valido_ate": c.valido_ate, "motivo": c.motivo,
            "faltando": [campo for campo in config.CAMPOS_OBRIGATORIOS if getattr(c, campo) is None]}


@router.get("/config", dependencies=[_super])
def listar_configuracoes(plano_id: int | None = None, tenant_id: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    consulta = db.query(EnriquecimentoConfigPlano)
    if plano_id is not None:
        consulta = consulta.filter(EnriquecimentoConfigPlano.plano_id == plano_id)
    if tenant_id is not None:
        consulta = consulta.filter(EnriquecimentoConfigPlano.tenant_id == tenant_id)
    return [_linha(c) for c in consulta.order_by(EnriquecimentoConfigPlano.id.desc()).limit(200).all()]


@router.put("/config")
def definir_configuracao(dados: ConfigRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Nova versão da configuração de um plano OU de um tenant. Campo nulo = não definido (a pesquisa continua bloqueada para quem depende dele)."""
    campos = dados.model_dump(exclude={"plano_id", "tenant_id", "motivo"})
    nova = config.definir_config(db, plano_id=dados.plano_id, tenant_id=dados.tenant_id, campos=campos, ator_id=str(admin.id),
                                 tenant_auditoria=admin.tenant_id, motivo=dados.motivo)
    return _linha(nova)


@router.get("/orcamento-global", dependencies=[_super])
def ver_orcamento_global(provedor: str = "lusha", db: Session = Depends(get_db)) -> dict:
    """Uso do orçamento global do provedor (todos os tenants somados) e pesquisas aguardando reconciliação. Só aqui; nunca na visão do tenant."""
    return painel.visao_administrativa(db, provedor)


@router.put("/orcamento-global")
def definir_orcamento_global(dados: OrcamentoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    nova = config.definir_orcamento_global(db, provedor=dados.provedor, limite_creditos=dados.limite_creditos,
                                           alerta_percentual=dados.alerta_percentual, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id,
                                           motivo=dados.motivo)
    return {"provedor": nova.provedor, "versao": nova.versao, "limite_creditos": nova.limite_creditos, "alerta_percentual": nova.alerta_percentual}


@router.post("/tenants/{tenant_id}/ajustes")
def ajustar_creditos(tenant_id: str, dados: AjusteRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    movimento = ledger.ajustar(db, tenant_id, dados.quantidade, dados.motivo, str(admin.id), admin.tenant_id, idempotency_key=dados.idempotency_key)
    return {"movimento_id": movimento.id, "disponivel": ledger.disponivel(db, tenant_id)}


@router.post("/tenants/{tenant_id}/estornos")
def estornar_creditos(tenant_id: str, dados: EstornoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    movimento = ledger.estornar(db, tenant_id, dados.quantidade, dados.motivo, str(admin.id), admin.tenant_id, pesquisa_id=dados.pesquisa_id,
                                idempotency_key=dados.idempotency_key)
    return {"movimento_id": movimento.id, "disponivel": ledger.disponivel(db, tenant_id)}


@router.post("/pesquisas/{pesquisa_id}/itens/{item_id}/reconciliar")
def reconciliar(pesquisa_id: str, item_id: int, dados: ReconciliacaoRequest, admin: Usuario = Depends(exigir_papel("super_admin")),
                db: Session = Depends(get_db)) -> dict:
    """Fecha uma empresa de desfecho ambíguo com o consumo confirmado no relatório do provedor (0 libera toda a reserva)."""
    pesq = execucao.reconciliar_item(db, pesquisa_id=pesquisa_id, item_id=item_id, creditos_consumidos=dados.creditos_consumidos,
                                     motivo=dados.motivo, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id)
    return painel.serializar_pesquisa(db, pesq, com_itens=True, com_transicoes=True)


@router.post("/pesquisas/{pesquisa_id}/encerrar-reconciliacao")
def encerrar_reconciliacao(pesquisa_id: str, dados: EncerrarReconciliacaoRequest, admin: Usuario = Depends(exigir_papel("super_admin")),
                           db: Session = Depends(get_db)) -> dict:
    pesq = execucao.encerrar_reconciliacao(db, pesquisa_id=pesquisa_id, motivo=dados.motivo, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id)
    return painel.serializar_pesquisa(db, pesq, com_itens=True, com_transicoes=True)
