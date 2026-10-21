"""Administração dos créditos de enriquecimento (somente super_admin): configuração por plano/tenant, política do provedor (tarifas, preço), lotes de
compra, orçamento global, aprovações, conciliação com o provedor, ajustes, estornos e reconciliação. Toda alteração é auditada e exige motivo.
Criar ou alterar gera uma versão PENDENTE; ela só passa a valer depois de aprovada (`.../aprovar`). Nenhuma credencial do provedor passa por aqui."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_contact_enrichment_provider, get_db
from app.contexts.enriquecimento.contract import conciliacao, config, execucao, ledger, painel
from app.models.enriquecimento_creditos import EnriquecimentoConfigPlano, EnriquecimentoPoliticaProvedor
from app.models.usuario import Usuario
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.services.errors import ValidacaoFalhou

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


class LoteCompraRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str = Field(min_length=2, max_length=50)
    referencia: str = Field(min_length=3, max_length=120)
    quantidade_creditos: int = Field(gt=0)
    custo_total_brl: str = Field(min_length=1, max_length=30, description="Decimal em texto, ex.: 269.94 (nunca float)")
    comprado_em: datetime
    observacao: str | None = Field(default=None, max_length=300)


class PoliticaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str = Field(min_length=2, max_length=50)
    creditos_busca_por_resultado: int | None = Field(default=None, ge=0)
    creditos_email: int | None = Field(default=None, ge=0)
    creditos_telefone: int | None = Field(default=None, ge=0)
    revelar_emails: bool = False
    revelar_telefones: bool = False
    tamanho_pagina_busca: int | None = None
    creditos_cliente_por_credito_provedor: int | None = Field(default=None, ge=1)
    markup_percentual: str = Field(min_length=1, max_length=20, description="Decimal em texto, ex.: 100")
    metodo_custo: str
    lote_compra_id: int | None = None
    casas_exibicao: int = Field(default=2, ge=0, le=6)
    fonte_tarifas: str = Field(default="manual", pattern="^(manual|provedor_usage)$")
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
    provedor_devolvidos: int = Field(default=0, ge=0)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class ReconciliacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creditos_provedor_consumidos: int = Field(ge=0)
    motivo: str = Field(min_length=3, max_length=300)


class EncerrarReconciliacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=3, max_length=300)


def _linha_config(c: EnriquecimentoConfigPlano) -> dict:
    return {"id": c.id, "plano_id": c.plano_id, "tenant_id": c.tenant_id, "versao": c.versao, "franquia_creditos": c.franquia_creditos,
            "periodicidade": c.periodicidade, "decisores_por_empresa_padrao": c.decisores_por_empresa_padrao,
            "decisores_por_empresa_max": c.decisores_por_empresa_max, "itens_por_lote_max": c.itens_por_lote_max,
            "limite_periodo_creditos": c.limite_periodo_creditos, "valido_de": c.valido_de, "valido_ate": c.valido_ate, "motivo": c.motivo,
            "aprovada": c.aprovado_em is not None, "aprovado_por": c.aprovado_por, "aprovado_em": c.aprovado_em,
            "faltando": [campo for campo in config.CAMPOS_OBRIGATORIOS if getattr(c, campo) is None]}


def _linha_politica(p: EnriquecimentoPoliticaProvedor) -> dict:
    return {"id": p.id, "provedor": p.provedor, "versao": p.versao, "creditos_busca_por_resultado": p.creditos_busca_por_resultado,
            "creditos_email": p.creditos_email, "creditos_telefone": p.creditos_telefone, "revelar_emails": p.revelar_emails,
            "revelar_telefones": p.revelar_telefones, "tamanho_pagina_busca": p.tamanho_pagina_busca,
            "creditos_cliente_por_credito_provedor": p.creditos_cliente_por_credito_provedor, "markup_percentual": str(p.markup_percentual),
            "metodo_custo": p.metodo_custo, "lote_compra_id": p.lote_compra_id, "custo_unitario_brl": str(p.custo_unitario_brl),
            "preco_unitario_brl": str(p.preco_unitario_brl), "casas_exibicao": p.casas_exibicao, "fonte_tarifas": p.fonte_tarifas,
            "aprovada": p.aprovado_em is not None, "aprovado_por": p.aprovado_por, "aprovado_em": p.aprovado_em, "motivo": p.motivo}


# ---------------------------------------------------------------------------------------------------------------------------------- planos


@router.get("/planos", dependencies=[_super])
def situacao_dos_planos(db: Session = Depends(get_db)) -> list[dict]:
    """Por plano: configuração de enriquecimento aprovada, pendente ou ausente (o que libera ou mantém bloqueada a Lusha para os clientes dele)."""
    return painel.planos_status(db)


@router.get("/config", dependencies=[_super])
def listar_configuracoes(plano_id: int | None = None, tenant_id: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    consulta = db.query(EnriquecimentoConfigPlano)
    if plano_id is not None:
        consulta = consulta.filter(EnriquecimentoConfigPlano.plano_id == plano_id)
    if tenant_id is not None:
        consulta = consulta.filter(EnriquecimentoConfigPlano.tenant_id == tenant_id)
    return [_linha_config(c) for c in consulta.order_by(EnriquecimentoConfigPlano.id.desc()).limit(200).all()]


@router.put("/config")
def definir_configuracao(dados: ConfigRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Nova versão PENDENTE da configuração de um plano OU de um tenant. Campo nulo = não definido (a pesquisa fica bloqueada até aprovar uma versão completa)."""
    campos = dados.model_dump(exclude={"plano_id", "tenant_id", "motivo"})
    nova = config.definir_config(db, plano_id=dados.plano_id, tenant_id=dados.tenant_id, campos=campos, ator_id=str(admin.id),
                                 tenant_auditoria=admin.tenant_id, motivo=dados.motivo)
    return _linha_config(nova)


@router.post("/config/{config_id}/aprovar")
def aprovar_configuracao(config_id: int, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    return _linha_config(config.aprovar_config(db, config_id, str(admin.id), admin.tenant_id))


# ---------------------------------------------------------------------------------------------------------------------------------- provedor


@router.get("/orcamento-global", dependencies=[_super])
def ver_orcamento_global(provedor: str = "lusha", db: Session = Depends(get_db)) -> dict:
    """Visão administrativa do provedor: orçamento global (todos os tenants), política (tarifas, custo, markup, preço, margem), resultado financeiro,
    lotes, leituras de uso, aprovações pendentes e pesquisas aguardando reconciliação. Só aqui; nunca na visão do tenant."""
    return painel.visao_administrativa(db, provedor)


@router.put("/orcamento-global")
def definir_orcamento_global(dados: OrcamentoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Nova versão PENDENTE do orçamento global (créditos do provedor por mês). Só vale depois de aprovada."""
    nova = config.definir_orcamento_global(db, provedor=dados.provedor, limite_creditos=dados.limite_creditos,
                                           alerta_percentual=dados.alerta_percentual, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id,
                                           motivo=dados.motivo)
    return {"id": nova.id, "provedor": nova.provedor, "versao": nova.versao, "limite_creditos": nova.limite_creditos,
            "alerta_percentual": nova.alerta_percentual, "aprovado": False}


@router.post("/orcamento-global/{orcamento_id}/aprovar")
def aprovar_orcamento_global(orcamento_id: int, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    linha = config.aprovar_orcamento_global(db, orcamento_id, str(admin.id), admin.tenant_id)
    return {"id": linha.id, "provedor": linha.provedor, "versao": linha.versao, "limite_creditos": linha.limite_creditos, "aprovado": True}


@router.post("/lotes-compra", status_code=201)
def registrar_lote_compra(dados: LoteCompraRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Novo aporte de créditos do provedor (custo, quantidade, data e referência próprios). Não altera o preço vigente: isso exige publicar e aprovar
    uma nova política."""
    try:
        custo = config.precos.dec(dados.custo_total_brl)
    except Exception:  # noqa: BLE001 — texto que não é número decimal
        raise ValidacaoFalhou("custo_total_brl deve ser um número decimal, ex.: 269.94.") from None
    lote = config.registrar_lote_compra(db, provedor=dados.provedor, referencia=dados.referencia, quantidade_creditos=dados.quantidade_creditos,
                                        custo_total_brl=custo, comprado_em=dados.comprado_em, ator_id=str(admin.id),
                                        tenant_auditoria=admin.tenant_id, observacao=dados.observacao)
    return {"id": lote.id, "referencia": lote.referencia, "quantidade_creditos": lote.quantidade_creditos, "custo_total_brl": str(lote.custo_total_brl),
            "custo_unitario_brl": str(lote.custo_unitario_brl)}


@router.get("/politica", dependencies=[_super])
def listar_politicas(provedor: str = "lusha", db: Session = Depends(get_db)) -> list[dict]:
    linhas = db.query(EnriquecimentoPoliticaProvedor).filter_by(provedor=provedor).order_by(EnriquecimentoPoliticaProvedor.versao.desc()).all()
    return [_linha_politica(p) for p in linhas]


@router.put("/politica")
def definir_politica(dados: PoliticaRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db),
                     provider: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider)) -> dict:
    """Nova versão PENDENTE da política do provedor (tarifas, relação com o crédito do cliente, markup, método de custo). O custo unitário e o preço
    de venda são calculados na publicação e gravados como foto. Só vale depois de aprovada."""
    try:
        markup = config.precos.dec(dados.markup_percentual)
    except Exception:  # noqa: BLE001
        raise ValidacaoFalhou("markup_percentual deve ser um número decimal, ex.: 100.") from None
    mesmo = provider.nome_provedor == dados.provedor
    nova = config.definir_politica(
        db, provedor=dados.provedor, creditos_busca_por_resultado=dados.creditos_busca_por_resultado, creditos_email=dados.creditos_email,
        creditos_telefone=dados.creditos_telefone, revelar_emails=dados.revelar_emails, revelar_telefones=dados.revelar_telefones,
        tamanho_pagina_busca=dados.tamanho_pagina_busca, creditos_cliente_por_credito_provedor=dados.creditos_cliente_por_credito_provedor,
        markup_percentual=markup, metodo_custo=dados.metodo_custo, lote_compra_id=dados.lote_compra_id, casas_exibicao=dados.casas_exibicao,
        fonte_tarifas=dados.fonte_tarifas, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id, motivo=dados.motivo,
        tamanho_pagina_minimo=provider.tamanho_pagina_minimo if mesmo else None, tamanho_pagina_maximo=provider.max_contatos_por_consulta if mesmo else None,
    )
    return _linha_politica(nova)


@router.post("/politica/{politica_id}/aprovar")
def aprovar_politica(politica_id: int, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    return _linha_politica(config.aprovar_politica(db, politica_id, str(admin.id), admin.tenant_id))


@router.get("/provedores/{provedor}/tarifas-do-provedor", dependencies=[_super])
def tarifas_do_provedor(provedor: str, provider: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider)) -> dict:
    """Tarifas por ação como o PRÓPRIO provedor publica (`GET /v3/account/usage` na Lusha), para conferir ao montar a política. Só leitura."""
    if provider.nome_provedor != provedor:
        raise ValidacaoFalhou("O provedor configurado neste ambiente é outro.")
    return conciliacao.tarifas_do_provedor(provider)


@router.post("/provedores/{provedor}/conciliar")
def conciliar_com_provedor(provedor: str, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db),
                           provider: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider)) -> dict:
    """Lê o uso informado pelo provedor e compara com o razão desde a leitura anterior; divergência vira alerta (nada é ajustado sozinho)."""
    if provider.nome_provedor != provedor:
        raise ValidacaoFalhou("O provedor configurado neste ambiente é outro.")
    return conciliacao.conciliar(db, provider, str(admin.id), admin.tenant_id)


# ---------------------------------------------------------------------------------------------------------------------------------- tenants


@router.post("/tenants/{tenant_id}/ajustes")
def ajustar_creditos(tenant_id: str, dados: AjusteRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    movimento = ledger.ajustar(db, tenant_id, dados.quantidade, dados.motivo, str(admin.id), admin.tenant_id, idempotency_key=dados.idempotency_key)
    return {"movimento_id": movimento.id, "disponivel": ledger.disponivel(db, tenant_id)}


@router.post("/tenants/{tenant_id}/estornos")
def estornar_creditos(tenant_id: str, dados: EstornoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    movimento = ledger.estornar(db, tenant_id, dados.quantidade, dados.motivo, str(admin.id), admin.tenant_id, pesquisa_id=dados.pesquisa_id,
                                idempotency_key=dados.idempotency_key, provedor_devolvidos=dados.provedor_devolvidos,
                                provedor="lusha" if dados.provedor_devolvidos else None)
    return {"movimento_id": movimento.id, "disponivel": ledger.disponivel(db, tenant_id)}


@router.post("/pesquisas/{pesquisa_id}/itens/{item_id}/reconciliar")
def reconciliar(pesquisa_id: str, item_id: int, dados: ReconciliacaoRequest, admin: Usuario = Depends(exigir_papel("super_admin")),
                db: Session = Depends(get_db)) -> dict:
    """Fecha uma empresa de desfecho ambíguo com o consumo, em créditos DO PROVEDOR, confirmado no relatório dele (0 libera toda a reserva)."""
    pesq = execucao.reconciliar_item(db, pesquisa_id=pesquisa_id, item_id=item_id, creditos_provedor_consumidos=dados.creditos_provedor_consumidos,
                                     motivo=dados.motivo, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id)
    return painel.serializar_pesquisa(db, pesq, com_itens=True, com_transicoes=True)


@router.post("/pesquisas/{pesquisa_id}/encerrar-reconciliacao")
def encerrar_reconciliacao(pesquisa_id: str, dados: EncerrarReconciliacaoRequest, admin: Usuario = Depends(exigir_papel("super_admin")),
                           db: Session = Depends(get_db)) -> dict:
    pesq = execucao.encerrar_reconciliacao(db, pesquisa_id=pesquisa_id, motivo=dados.motivo, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id)
    return painel.serializar_pesquisa(db, pesq, com_itens=True, com_transicoes=True)
