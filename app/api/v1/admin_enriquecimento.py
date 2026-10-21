"""Administração dos créditos de enriquecimento (somente super_admin): configuração por plano/tenant, política do provedor (tarifas, preço), lotes de
compra, orçamento global, aprovações, conciliação com o provedor, ajustes, estornos e reconciliação. Toda alteração é auditada e exige motivo.
Criar ou alterar gera uma versão PENDENTE; ela só passa a valer depois de aprovada (`.../aprovar`). Nenhuma credencial do provedor passa por aqui."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_contact_enrichment_provider, get_db, get_fiscal_provider
from app.contexts.enriquecimento.contract import conciliacao, config, custo, estornos, execucao, ledger, matriz, pacotes, painel, poc, vendas
from app.models.enriquecimento_creditos import (
    EnriquecimentoCompra,
    EnriquecimentoCustoProvedor,
    EnriquecimentoConfigPlano,
    EnriquecimentoPacote,
    EnriquecimentoPoliticaProvedor,
)
from app.models.usuario import Usuario
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.providers.fiscal.base import FiscalProvider
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
    modo: str | None = Field(default=None, description="franquia_fixa (padrão) | poc_autorizada")
    limite_creditos_pesquisa: int | None = Field(default=None, ge=1)
    limite_pesquisas_periodo: int | None = Field(default=None, ge=0)
    limite_empresas_periodo: int | None = Field(default=None, ge=0)
    limite_contatos_periodo: int | None = Field(default=None, ge=0)
    motivo: str = Field(min_length=3, max_length=300)


class CustoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str = Field(default="lusha", min_length=2, max_length=50)
    custo_mensal_usd: str = Field(min_length=1, max_length=20, description="Decimal em texto, ex.: 600")
    creditos_anuais: int = Field(gt=0)
    cambio_planejamento_brl: str = Field(min_length=1, max_length=20, description="Câmbio de PLANEJAMENTO (precificação), decimal em texto, ex.: 6.00")
    motivo: str = Field(min_length=3, max_length=300)


class PagamentoProvedorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str = Field(default="lusha", min_length=2, max_length=50)
    referencia: str = Field(min_length=3, max_length=120)
    periodo: str = Field(pattern=r"^\d{4}-\d{2}$")
    valor_usd: str = Field(min_length=1, max_length=20)
    taxa_cambio_efetiva: str = Field(min_length=1, max_length=20, description="Taxa EFETIVAMENTE aplicada no pagamento")
    encargos_brl: str = Field(default="0", max_length=20, description="Encargos efetivamente cobrados, em reais (nunca estimados)")
    pago_em: datetime
    observacao: str | None = Field(default=None, max_length=300)


class EstornoSolicitacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str
    creditos: int = Field(gt=0)
    justificativa: str = Field(min_length=10, max_length=500)
    evidencia: str = Field(min_length=5, max_length=500)


class EstornoDecisaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aprovar: bool
    motivo: str = Field(min_length=5, max_length=300)


class MatrizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapeamento: dict[str, int] = Field(default_factory=dict, description="Linha da matriz (ex.: Starter) → id do plano que a recebe")


class PacoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(min_length=3, max_length=60)
    nome: str = Field(min_length=2, max_length=100)
    quantidade_creditos: int | None = Field(default=None, gt=0)
    preco_unitario_brl: str | None = Field(default=None, max_length=30, description="Decimal em texto, ex.: 1.35")
    preco_total_brl: str | None = Field(default=None, max_length=30, description="Decimal em texto; deve ser créditos × unitário em centavos")
    status: str = "ATIVO"
    ordem: int = 0
    motivo: str = Field(min_length=3, max_length=300)


class PocTetoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str = Field(default="lusha", min_length=2, max_length=50)
    empresas: int = Field(gt=0)
    decisores_por_empresa: int = Field(default=1, ge=1)


class PocAutorizacaoRequest(PocTetoRequest):
    tenant_id: str = Field(min_length=1, max_length=100)
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
            "limite_periodo_creditos": c.limite_periodo_creditos, "modo": c.modo, "limite_creditos_pesquisa": c.limite_creditos_pesquisa,
            "limite_pesquisas_periodo": c.limite_pesquisas_periodo, "limite_empresas_periodo": c.limite_empresas_periodo,
            "limite_contatos_periodo": c.limite_contatos_periodo, "valido_de": c.valido_de, "valido_ate": c.valido_ate, "motivo": c.motivo,
            "aprovada": c.aprovado_em is not None, "aprovado_por": c.aprovado_por, "aprovado_em": c.aprovado_em,
            "faltando": [campo for campo in config.CAMPOS_OBRIGATORIOS_POR_MODO[c.modo or "franquia_fixa"] if getattr(c, campo) is None]}


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


# ------------------------------------------------------------------------------------------------------------------- matriz de franquias


@router.get("/matriz", dependencies=[_super])
def situacao_da_matriz(db: Session = Depends(get_db)) -> list[dict]:
    """Cada linha da matriz comercial (POC, Teste, Starter, Professional, Business, Corporate, Enterprise): existe plano correspondente? A configuração
    aprovada bate com a matriz? Nada é adivinhado: linha sem plano de mesmo nome aparece como `plano_inexistente` até o administrador mapear."""
    return matriz.status(db)


@router.post("/matriz/aplicar")
def aplicar_matriz(dados: MatrizRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Aplica a matriz aprovada pelo PO aos planos que existem (por nome exato ou pelo `mapeamento` informado). Idempotente e versionada: quem já
    bate não ganha versão nova. Plano ausente não é criado."""
    return matriz.aplicar(db, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id, mapeamento=dados.mapeamento or None)


# ------------------------------------------------------------------------------------------------------------------- pacotes adicionais


@router.get("/pacotes", dependencies=[_super])
def listar_pacotes(db: Session = Depends(get_db)) -> list[dict]:
    """Todas as versões de pacote (aprovadas e pendentes)."""
    return [{"id": p.id, "codigo": p.codigo, "versao": p.versao, "nome": p.nome, "creditos": p.quantidade_creditos, "status": p.status,
             "preco_unitario_brl": str(p.preco_unitario_brl) if p.preco_unitario_brl is not None else None,
             "preco_total_brl": str(p.preco_total_brl) if p.preco_total_brl is not None else None, "ordem": p.ordem,
             "aprovado": p.aprovado_em is not None, "aprovado_por": p.aprovado_por, "valido_ate": p.valido_ate, "motivo": p.motivo}
            for p in db.query(EnriquecimentoPacote).order_by(EnriquecimentoPacote.ordem, EnriquecimentoPacote.codigo, EnriquecimentoPacote.versao.desc()).all()]


@router.put("/pacotes")
def definir_pacote(dados: PacoteRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Nova versão PENDENTE de um pacote (preço nunca é editado no lugar). Total divergente de créditos × unitário é recusado."""
    novo = pacotes.definir_pacote(db, codigo=dados.codigo, nome=dados.nome, quantidade_creditos=dados.quantidade_creditos,
                                  preco_unitario_brl=dados.preco_unitario_brl, preco_total_brl=dados.preco_total_brl, status=dados.status,
                                  ordem=dados.ordem, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id, motivo=dados.motivo)
    return {"id": novo.id, "codigo": novo.codigo, "versao": novo.versao, "status": novo.status, "pendente_aprovacao": True}


@router.post("/pacotes/{pacote_id}/aprovar")
def aprovar_pacote(pacote_id: int, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    aprovado = pacotes.aprovar_pacote(db, pacote_id, str(admin.id), admin.tenant_id)
    return {"id": aprovado.id, "codigo": aprovado.codigo, "versao": aprovado.versao, "status": aprovado.status, "aprovado": True}


@router.get("/pacotes/rentabilidade", dependencies=[_super])
def rentabilidade_dos_pacotes(provedor: str = "lusha", db: Session = Depends(get_db)) -> dict:
    """Margem de cada pacote com o custo CONTRATUAL vigente (USD 600 ÷ 6.800 créditos × câmbio de planejamento). Recalculada a cada leitura."""
    return pacotes.rentabilidade(db, provedor)


@router.get("/compras", dependencies=[_super])
def listar_compras(tenant_id: str | None = None, limite: int = 100, db: Session = Depends(get_db)) -> list[dict]:
    consulta = db.query(EnriquecimentoCompra)
    if tenant_id:
        consulta = consulta.filter(EnriquecimentoCompra.tenant_id == tenant_id)
    return [{**pacotes.serializar_compra(c), "tenant_id": c.tenant_id}
            for c in consulta.order_by(EnriquecimentoCompra.id.desc()).limit(max(1, min(limite, 500))).all()]  # com nota e conciliação: GET /vendas


# --------------------------------------------------------------------------------------------------------------- custo contratual do provedor


def _linha_custo(c: EnriquecimentoCustoProvedor) -> dict:
    return {"id": c.id, "provedor": c.provedor, "versao": c.versao, "custo_mensal_usd": str(c.custo_mensal_usd), "creditos_anuais": c.creditos_anuais,
            "creditos_mensais": c.creditos_mensais, "cambio_planejamento_brl": str(c.cambio_planejamento_brl),
            "custo_unitario_usd": str(c.custo_unitario_usd), "custo_unitario_brl": str(c.custo_unitario_brl), "custo_mensal_brl": str(c.custo_mensal_brl),
            "aprovada": c.aprovado_em is not None, "aprovado_por": c.aprovado_por, "vigente": c.aprovado_em is not None and c.valido_ate is None,
            "motivo": c.motivo}


@router.get("/custo", dependencies=[_super])
def listar_custos(provedor: str = "lusha", db: Session = Depends(get_db)) -> dict:
    """Versões do custo contratual do provedor e o custo efetivo por crédito consumido no mês."""
    linhas = db.query(EnriquecimentoCustoProvedor).filter_by(provedor=provedor).order_by(EnriquecimentoCustoProvedor.versao.desc()).all()
    return {"versoes": [_linha_custo(c) for c in linhas], "efetivo_no_mes": custo.custo_efetivo(db, provedor, config.periodo_de(config.agora_utc()))}


@router.put("/custo")
def definir_custo(dados: CustoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Nova versão PENDENTE do custo contratual (os derivados são calculados no servidor). Só vale depois de aprovada."""
    nova = custo.definir_custo(db, provedor=dados.provedor, custo_mensal_usd=dados.custo_mensal_usd, creditos_anuais=dados.creditos_anuais,
                               cambio_planejamento_brl=dados.cambio_planejamento_brl, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id, motivo=dados.motivo)
    return _linha_custo(nova)


@router.post("/custo/{custo_id}/aprovar")
def aprovar_custo(custo_id: int, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    return _linha_custo(custo.aprovar_custo(db, custo_id, str(admin.id), admin.tenant_id))


@router.get("/custo/efetivo", dependencies=[_super])
def custo_efetivo(provedor: str = "lusha", periodo: str | None = None, db: Session = Depends(get_db)) -> dict:
    return custo.custo_efetivo(db, provedor, periodo or config.periodo_de(config.agora_utc()))


@router.post("/pagamentos-provedor", status_code=201)
def registrar_pagamento_provedor(dados: PagamentoProvedorRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Pagamento efetivo ao provedor (USD, taxa de câmbio efetivamente aplicada e encargos efetivamente cobrados). Base do custo contábil do ciclo."""
    p = custo.registrar_pagamento(db, provedor=dados.provedor, referencia=dados.referencia, periodo=dados.periodo, valor_usd=dados.valor_usd,
                                  taxa_cambio_efetiva=dados.taxa_cambio_efetiva, encargos_brl=dados.encargos_brl, pago_em=dados.pago_em,
                                  observacao=dados.observacao, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id)
    return {"id": p.id, "referencia": p.referencia, "periodo": p.periodo, "valor_usd": str(p.valor_usd), "taxa_cambio_efetiva": str(p.taxa_cambio_efetiva),
            "encargos_brl": str(p.encargos_brl), "valor_brl_total": str(p.valor_brl_total)}


# --------------------------------------------------------------------------------------------- vendas, nota fiscal, conciliação e estorno manual


@router.get("/vendas", dependencies=[_super])
def vendas_e_conciliacao(tenant_id: str | None = None, limite: int = 100, db: Session = Depends(get_db)) -> dict:
    """Vendas de pacotes com a nota fiscal e a situação de conciliação de cada uma, mais o resumo (bruto, tarifas e líquido informados pelo provedor de pagamento)."""
    return {"resumo": vendas.resumo_conciliacao(db), "vendas": vendas.listar_vendas(db, tenant_id, limite)}


@router.post("/compras/{compra_id}/emitir-nota")
def emitir_nota(compra_id: int, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db),
                fiscal: FiscalProvider = Depends(get_fiscal_provider)) -> dict:
    """Emite (ou reemite, se falhou) a nota da compra pelo emissor configurado. Sem emissor configurado a nota fica com falha, nunca simulada."""
    nota = vendas.emitir_nota(db, compra_id, fiscal, ator_id=str(admin.id))
    return {"compra_id": compra_id, "status": nota.status, "numero": nota.numero, "erro": nota.erro, "tentativas": nota.tentativas}


@router.get("/estornos", dependencies=[_super])
def listar_estornos(status: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    return estornos.listar(db, status)


@router.post("/compras/{compra_id}/estornos", status_code=201)
def solicitar_estorno(compra_id: int, dados: EstornoSolicitacaoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Pedido MANUAL de estorno/chargeback/cancelamento/ajuste de créditos de um pacote. Nada é revertido até a decisão de OUTRO administrador."""
    return estornos.serializar(estornos.solicitar(db, compra_id, tipo=dados.tipo, creditos=dados.creditos, justificativa=dados.justificativa,
                                                  evidencia=dados.evidencia, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id))


@router.post("/estornos/{estorno_id}/decidir")
def decidir_estorno(estorno_id: int, dados: EstornoDecisaoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Aprova (e executa, com lançamento compensatório no razão) ou rejeita. Quem solicitou não decide. Idempotente."""
    return estornos.serializar(estornos.decidir(db, estorno_id, aprovar=dados.aprovar, motivo=dados.motivo, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id))


# ------------------------------------------------------------------------------------------------------------------------------------- POC


@router.post("/poc/teto", dependencies=[_super])
def calcular_teto_poc(dados: PocTetoRequest, db: Session = Depends(get_db)) -> dict:
    """Teto de créditos de uma operação de POC, calculado só com as tarifas confirmadas (política aprovada). Não grava nada."""
    return poc.calcular_teto(db, dados.provedor, dados.empresas, dados.decisores_por_empresa)


@router.post("/poc/autorizar")
def autorizar_poc(dados: PocAutorizacaoRequest, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db)) -> dict:
    """Cria a autorização (configuração do tenant, PENDENTE de aprovação) da operação de POC com o teto calculado."""
    return poc.autorizar(db, dados.tenant_id, provedor=dados.provedor, empresas=dados.empresas, decisores_por_empresa=dados.decisores_por_empresa,
                         ator_id=str(admin.id), tenant_auditoria=admin.tenant_id, motivo=dados.motivo)


# ------------------------------------------------------------------------------------------------------------------------------- auditoria


@router.get("/auditoria", dependencies=[_super])
def auditoria(tenant_id: str | None = None, limite: int = 100, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    """Trilha de auditoria de enriquecimento: configuração, matriz, pacotes, política, orçamento, lotes, ajustes, estornos, compras."""
    return painel.auditoria_administrativa(db, tenant_id=tenant_id, limite=limite, offset=offset)


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


@router.post("/provedores/{provedor}/sincronizar-politica")
def sincronizar_politica(provedor: str, admin: Usuario = Depends(exigir_papel("super_admin")), db: Session = Depends(get_db),
                         provider: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider)) -> dict:
    """Publica (e já aprova) a política do provedor a partir das tarifas que ele próprio informa (`pricing` de `GET /v3/account/usage`), do custo contratual
    e do menor pacote ativo. Idempotente. Sem a tarifa da busca ou do e-mail (ou com fração) o retorno é um bloqueio técnico descrito, sem inventar valor."""
    if provider.nome_provedor != provedor:
        raise ValidacaoFalhou("O provedor configurado neste ambiente é outro.")
    return conciliacao.sincronizar_politica(db, provider, ator_id=str(admin.id), tenant_auditoria=admin.tenant_id)


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
