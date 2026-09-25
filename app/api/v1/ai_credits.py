"""B2B ON AI Credits — visão do cliente (Fase 15).

- Público: pacotes de top-up vigentes (fonte única de preço: catálogo
  versionado; o frontend nunca tem preço fixo no código).
- Tenant: carteira (disponível, incluído, comprado, a vencer, uso do
  mês, dias estimados), extrato, execuções, estimativa, compras,
  recarga automática (com consentimento), orçamento/limites, alertas e
  valor de negócio. O cliente vê créditos, nunca custo em USD.
"""

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_payment_provider, get_usuario_atual
from app.contexts.finops import contract as finops
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import ExecucaoIa, LoteCreditos
from app.models.usuario import Usuario
from app.providers.payment.base import PaymentProvider
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

router = APIRouter(prefix="/ai-credits", tags=["ai-credits"])
_admin = [Depends(exigir_papel("admin", "super_admin"))]


def _f(valor) -> float:
    return float(valor or 0)


# --- Público -------------------------------------------------------------------------
@router.get("/pacotes")
def pacotes(db: Session = Depends(get_db)) -> dict:
    """Pacotes vigentes + regras públicas (validade, franquias por módulo)."""
    itens = [finops.catalogos.pacote_dict(p) for p in finops.catalogos.pacotes_vigentes(db)]
    db.commit()  # semente lazy do catálogo
    return {
        "pacotes": itens,
        "franquias": finops.comercial.franquias_publicas(),
        "regras": {
            "consumo": finops.comercial.POLITICA_CONSUMO,
            "franquia_mensal_acumula": False,
            "validade_topup_meses": finops.comercial.validade_topup_meses(),
            "limiar_confirmacao_creditos": finops.comercial.limiar_confirmacao(),
            "limiares_alerta_percentual": list(finops.comercial.LIMIARES_USO),
        },
    }


@router.get("/workloads")
def workloads(db: Session = Depends(get_db)) -> dict:
    """Tabela pública de consumo por operação (catálogo ativo). Sem custo."""
    catalogo = finops.catalogos.catalogo_ativo(db)
    itens = []
    for w in finops.catalogos.workloads(db, catalogo):
        if not w.ativo:
            continue
        d = finops.catalogos.workload_dict(w)
        itens.append({k: d[k] for k in ("codigo", "modulo", "nome", "classe", "creditos_base", "creditos_min", "creditos_max",
                                        "variavel", "requer_aprovacao") if k in d})
    db.commit()
    return {"catalogo_versao": catalogo.versao, "workloads": itens}


# --- Tenant --------------------------------------------------------------------------
@router.get("/carteira")
def carteira(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    tenant_id = usuario.tenant_id
    finops.carteira.preparar(db, tenant_id)
    db.commit()
    agora = finops.carteira.agora_utc()
    lotes = finops.carteira.lotes_fefo(db, tenant_id)
    por_tipo: dict[str, Decimal] = {}
    for lote in lotes:
        por_tipo[lote.tipo] = por_tipo.get(lote.tipo, Decimal(0)) + Decimal(str(lote.quantidade_restante))
    limite_vencimento = agora + timedelta(days=30)
    a_vencer = [
        {"tipo": lote.tipo, "quantidade": _f(lote.quantidade_restante), "expira_em": lote.expira_em.isoformat()}
        for lote in lotes if lote.expira_em is not None and lote.expira_em <= limite_vencimento
    ]
    franquia, detalhe_franquia = finops.carteira.franquia_do_tenant(db, tenant_id)
    uso = finops.limites.uso_do_periodo(db, tenant_id, agora)
    return {
        "disponivel": _f(finops.carteira.disponivel(db, tenant_id)),
        "reservado": _f(finops.carteira.reservado(db, tenant_id)),
        "incluido_no_plano": _f(por_tipo.get("SUBSCRIPTION")),
        "comprado": _f(por_tipo.get("TOPUP")),
        "promocional": _f(por_tipo.get("PROMOTIONAL")),
        "ajustes": _f(por_tipo.get("ADJUSTMENT")),
        "a_vencer_30_dias": a_vencer,
        "franquia_mensal": franquia,
        "franquia_detalhe": detalhe_franquia,
        "uso_do_mes": uso,
        "modo": finops.comercial.modo_cobranca(),
        "lotes": [
            {"id": lote.id, "tipo": lote.tipo, "origem": lote.origem, "restante": _f(lote.quantidade_restante),
             "original": _f(lote.quantidade_original), "expira_em": lote.expira_em.isoformat() if lote.expira_em else None}
            for lote in lotes
        ],
    }


@router.get("/consumo")
def consumo(dias: int = 30, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    """Consumo por módulo, feature/workload e agente (créditos, sem custo)."""
    if dias not in (7, 30, 90):
        raise ValidacaoFalhou("dias deve ser 7, 30 ou 90.")
    desde = finops.carteira.agora_utc() - timedelta(days=dias)
    base = db.query(ExecucaoIa).filter(ExecucaoIa.tenant_id == usuario.tenant_id, ExecucaoIa.status == "LIQUIDADA",
                                       ExecucaoIa.criado_em >= desde)

    def agrupar(coluna) -> list[dict]:
        linhas = (base.with_entities(coluna, func.count(ExecucaoIa.id), func.sum(ExecucaoIa.creditos_liquidados))
                  .group_by(coluna).order_by(func.sum(ExecucaoIa.creditos_liquidados).desc()).all())
        return [{"chave": chave or "—", "execucoes": n, "creditos": _f(c)} for chave, n, c in linhas]

    return {"dias": dias, "por_modulo": agrupar(ExecucaoIa.modulo), "por_workload": agrupar(ExecucaoIa.workload_codigo)[:10],
            "por_agente": agrupar(ExecucaoIa.agente), "por_gatilho": agrupar(ExecucaoIa.gatilho)}


@router.get("/extrato", dependencies=_admin)
def extrato(limite: int = 100, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    movimentos = (db.query(MovimentoCredito).filter(MovimentoCredito.tenant_id == usuario.tenant_id)
                  .order_by(MovimentoCredito.id.desc()).limit(min(max(limite, 1), 500)).all())
    return [
        {"id": m.id, "tipo": m.tipo, "quantidade": _f(m.quantidade), "saldo_apos": _f(m.saldo_apos), "descricao": m.descricao,
         "execucao_id": m.execucao_id, "lote_id": m.lote_id, "faturavel": m.faturavel,
         "catalogo_versao": m.catalogo_versao, "criado_em": m.criado_em.isoformat() if m.criado_em else None}
        for m in movimentos
    ]


@router.get("/execucoes", dependencies=_admin)
def execucoes(limite: int = 50, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    linhas = (db.query(ExecucaoIa).filter(ExecucaoIa.tenant_id == usuario.tenant_id)
              .order_by(ExecucaoIa.criado_em.desc()).limit(min(max(limite, 1), 200)).all())
    return [
        {"id": e.id, "workload": e.workload_codigo, "modulo": e.modulo, "feature": e.feature, "agente": e.agente, "gatilho": e.gatilho,
         "status": e.status, "catalogo_versao": e.catalogo_versao, "creditos_estimados": _f(e.creditos_estimados),
         "creditos_liquidados": _f(e.creditos_liquidados), "creditos_excedente": _f(e.creditos_excedente),
         "motivo_estorno": e.motivo_estorno, "criado_em": e.criado_em.isoformat() if e.criado_em else None}
        for e in linhas
    ]


class EstimativaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workload: str
    parametros: dict = Field(default_factory=dict)


@router.post("/estimativas")
def estimar(dados: EstimativaRequest, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    estimativa = finops.execucoes.estimar(db, dados.workload, dados.parametros)
    finops.carteira.preparar(db, usuario.tenant_id)
    db.commit()
    return {**estimativa, "disponivel": _f(finops.carteira.disponivel(db, usuario.tenant_id))}


# --- Compra de créditos ---------------------------------------------------------------
class CompraRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pacote: str


@router.post("/compras", status_code=201, dependencies=_admin)
def comprar(dados: CompraRequest, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id),
            payment_provider: PaymentProvider = Depends(get_payment_provider), db: Session = Depends(get_db)) -> dict:
    """Cria o pedido e o checkout. Créditos só entram pelo webhook assinado."""
    compra = finops.compras.iniciar(db, usuario.tenant_id, dados.pacote, payment_provider, usuario.email, ator_id)
    return finops.compras.compra_dict(compra)


@router.get("/compras", dependencies=_admin)
def listar_compras(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    return [finops.compras.compra_dict(c) for c in finops.compras.listar(db, usuario.tenant_id)]


@router.post("/compras/{compra_id}/checkout", dependencies=_admin)
def checkout(compra_id: int, usuario: Usuario = Depends(get_usuario_atual),
             payment_provider: PaymentProvider = Depends(get_payment_provider), db: Session = Depends(get_db)) -> dict:
    """Gera (ou devolve) o link de pagamento de um pedido pendente — inclusive
    o criado pela recarga automática."""
    compra = finops.compras.obter(db, usuario.tenant_id, compra_id)
    return finops.compras.compra_dict(finops.compras.gerar_checkout(db, compra, payment_provider, usuario.email))


class RecargaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ativa: bool
    limiar: int | None = Field(default=None, gt=0)
    pacote: str | None = None
    consentimento: bool = False


@router.get("/recarga-automatica", dependencies=_admin)
def obter_recarga(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return finops.compras.recarga_dict(finops.carteira.configuracao(db, usuario.tenant_id))


@router.put("/recarga-automatica", dependencies=_admin)
def configurar_recarga(dados: RecargaRequest, usuario: Usuario = Depends(get_usuario_atual), ator_id: str | None = Depends(get_ator_id),
                       db: Session = Depends(get_db)) -> dict:
    return finops.compras.configurar_recarga(db, usuario.tenant_id, dados.ativa, dados.limiar, dados.pacote, dados.consentimento, ator_id)


# --- Orçamento e limites (budget guard) -----------------------------------------------
class OrcamentoCreditosRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orcamento_mensal_creditos: int | None = Field(default=None, gt=0)
    limite_diario_creditos: int | None = Field(default=None, gt=0)
    limite_usuario_creditos: int | None = Field(default=None, gt=0)
    limite_api_creditos: int | None = Field(default=None, gt=0)
    limites_modulo_percentual: dict[str, float] | None = None
    limites_agente_creditos: dict[str, int] | None = None
    percentual_alerta: int = Field(default=80, ge=1, le=100)
    parada_rigida: bool = True


_CAMPOS_ORCAMENTO = tuple(OrcamentoCreditosRequest.model_fields)


def _orcamento_dict(config) -> dict:
    return {campo: getattr(config, campo) for campo in _CAMPOS_ORCAMENTO}


@router.get("/orcamento", dependencies=_admin)
def obter_orcamento(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    return _orcamento_dict(finops.carteira.configuracao(db, usuario.tenant_id))


@router.put("/orcamento", dependencies=_admin)
def definir_orcamento(dados: OrcamentoCreditosRequest, usuario: Usuario = Depends(get_usuario_atual),
                      ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Ex.: PREDATOR no máximo 40% → limites_modulo_percentual={"predator": 0.4}."""
    for modulo, percentual in (dados.limites_modulo_percentual or {}).items():
        if not 0 < percentual <= 1:
            raise ValidacaoFalhou(f"Percentual do módulo {modulo} deve estar entre 0 e 1.")
    for agente, limite in (dados.limites_agente_creditos or {}).items():
        if limite <= 0:
            raise ValidacaoFalhou(f"Limite do agente {agente} deve ser positivo.")
    config = finops.carteira.configuracao(db, usuario.tenant_id)
    anterior = _orcamento_dict(config)
    for campo, valor in dados.model_dump().items():
        setattr(config, campo, valor)
    auditoria_service.registrar(db, usuario.tenant_id, "orcamento_creditos_ia_definido", "configuracao_credito_tenant", config.id, ator_id,
                                {"valor_anterior": anterior, "valor_novo": dados.model_dump()})
    db.commit()
    return _orcamento_dict(config)


@router.get("/alertas", dependencies=_admin)
def alertas(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> list[dict]:
    return finops.limites.alertas(db, usuario.tenant_id)


@router.get("/valor-de-negocio", dependencies=_admin)
def valor_de_negocio(dias: int = 30, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    if dias not in (30, 90):
        raise ValidacaoFalhou("dias deve ser 30 ou 90.")
    return finops.economia.valor_de_negocio(db, usuario.tenant_id, *finops.economia.janela(dias))


@router.get("/lotes/{lote_id}", dependencies=_admin)
def lote(lote_id: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    item = db.query(LoteCreditos).filter_by(id=lote_id, tenant_id=usuario.tenant_id).one_or_none()
    if item is None:
        raise NaoEncontrado("Lote não encontrado.")
    return {"id": item.id, "tipo": item.tipo, "origem": item.origem, "referencia": item.referencia, "status": item.status,
            "original": _f(item.quantidade_original), "restante": _f(item.quantidade_restante),
            "concedido_em": item.concedido_em.isoformat() if item.concedido_em else None,
            "expira_em": item.expira_em.isoformat() if item.expira_em else None}
