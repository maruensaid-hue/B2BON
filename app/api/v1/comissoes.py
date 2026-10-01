"""Commission Engine (D-074–D-076): parâmetros financeiros (Tax Profile, Infrastructure Cost Pool, capacidade, câmbio PTAX,
Commission Policies) e memória de cálculo. Só super_admin."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db
from app.contexts.comissoes import contract as comissoes
from app.contexts.finops import contract as finops
from app.contexts.governo import contract as governo
from app.models.apuracao_comissao import ApuracaoComissao, PerfilTributario, PeriodoStatusTributario
from app.models.cotacao_cambio import CotacaoCambio
from app.models.custo_infraestrutura import ComponenteInfra
from app.schemas.comissoes import (
    AtualizarComponenteInfraSchema,
    ComponenteInfraSchema,
    CotacaoCambioSchema,
    EnvelopeCapacidadeSchema,
    CustoDiretoSchema,
    DecisaoAlertaSchema,
    PerfilTributarioSchema,
    PoliticaInfraSchema,
    PoliticaMargemSchema,
    RecalculoSchema,
    StatusTributarioSchema,
    UsoCapacidadeSchema,
)

router = APIRouter(prefix="/comissoes", tags=["comissoes"], dependencies=[Depends(exigir_papel("super_admin"))])


@router.get("/parametros")
def parametros(db: Session = Depends(get_db)) -> dict:
    hoje = date.today()
    perfis = db.query(PerfilTributario).order_by(PerfilTributario.vigente_de.desc(), PerfilTributario.id.desc()).all()
    cotacoes = db.query(CotacaoCambio).order_by(CotacaoCambio.vigente_em.desc(), CotacaoCambio.id.desc()).limit(50).all()
    vigente = governo.politicas.politica_vigente(db)
    margem, infra = comissoes.politica.vigente(db), comissoes.politica.vigente_infra(db)
    cambio = finops.cambio.aplicavel(db)
    resposta = {
        "perfis_tributarios": [comissoes.tributos.como_dict(p) for p in perfis],
        "cotacoes_cambio": [finops.cambio.como_dict(c) for c in cotacoes],
        "cotacao_vigente": finops.cambio.como_dict(cambio) if cambio else None, "politica_cambio": finops.cambio.POLITICA,
        "tributos": [t.value for t in comissoes.tipos.Tributo], "bases_tributo": [b.value for b in comissoes.tipos.BaseTributo],
        "situacoes_reforma": [s.value for s in comissoes.tipos.SituacaoReforma],
        "tipos_receita": [*comissoes.tipos.TIPOS_RECEITA, comissoes.tipos.QUALQUER],
        "politica_governo": {"versao": vigente.versao, "regras": vigente.regras},
        "politica_margem": {"versao": margem.versao, "regras": margem.regras},
        "politica_infraestrutura": {"versao": infra.versao, "regras": infra.regras},
        "politica_privada": "% de comissão de cada representante (Admin → Representantes), sobre a Margem Comissionável Líquida",
        "status_tributario": [comissoes.tributos.status_periodo_dict(p) for p in
                              db.query(PeriodoStatusTributario).order_by(PeriodoStatusTributario.vigente_de.desc()).all()],
        "status_tributario_vigente": (comissoes.tributos.status_periodo_dict(v) if (v := comissoes.tributos.status_vigente(db, hoje))
                                      else None),
        "pendentes": _pendentes(db, hoje, cambio, margem.regras),
    }
    db.commit()
    return resposta


def _pendentes(db: Session, hoje: date, cambio, regras_margem: dict) -> list[str]:
    """O que ainda impede as comissões de saírem de AWAITING (mostrado na tela e no relatório ao PO)."""
    faltam = []
    for tipo in comissoes.tipos.TIPOS_RECEITA:
        perfil = comissoes.tributos.aplicavel(db, tipo, hoje)
        if perfil is None:
            faltam.append(f"Tax Profile vigente para {tipo}")
        else:
            faltam += [f"Tax Profile {tipo}: {item}" for item in comissoes.tributos.pendencias(perfil)]
    regras_infra = comissoes.politica.vigente_infra(db).regras
    pools = regras_infra.get("pools_comissao") or ["INFRASTRUCTURE", "DATA_PROVIDER"]
    componentes = comissoes.infraestrutura.aplicaveis(db, hoje, pools)
    if not componentes:
        faltam.append("Infrastructure Cost Pool: fornecedores e planos de referência com valores")
    for componente in componentes:
        custos = comissoes.infraestrutura.custos_mensais(db, componente, hoje)
        nome = f"{componente.fornecedor} · {componente.servico}"
        if componente.status_arquitetura == comissoes.tipos.StatusArquitetura.APLICAVEL_A_CONFIRMAR.value:
            faltam.append(f"Confirmar uso na arquitetura: {nome}")
        if custos["faltante"] == comissoes.tipos.Faltante.CUSTO_INFRA.value:
            faltam.append(f"Capacity envelope: {nome}" if componente.modelo_preco == comissoes.tipos.ModeloPreco.USO.value
                          else f"Valor do plano de referência: {nome}")
        elif custos["faltante"] == comissoes.tipos.Faltante.CAMBIO.value:
            faltam.append(f"Cotação PTAX {componente.moeda}/BRL: {nome}")
    for componente in comissoes.infraestrutura.vigentes(db, hoje):
        if componente.proxima_revisao_em and componente.proxima_revisao_em <= hoje:
            faltam.append(f"Revisar preço: {componente.fornecedor} · {componente.servico} (desde {componente.proxima_revisao_em})")
    _, _, sem_peso = comissoes.infraestrutura.unidades_ponderadas(db, regras_infra["pesos"])
    faltam += [f"Tier de infraestrutura do plano {plano}" for plano in sem_peso]
    if cambio is None and regras_margem.get("deduzir_custo_ia"):
        faltam.append("Cotação USD/BRL (a política deduz custo de IA)")
    return faltam


@router.post("/perfis-tributarios", status_code=201)
def criar_perfil(dados: PerfilTributarioSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    perfil = comissoes.tributos.criar(db, dados.model_dump(), ator_id)
    calculadas = comissoes.motor.recalcular_aguardando(db)
    db.commit()
    return {"perfil": comissoes.tributos.como_dict(perfil), "aguardando_calculadas": calculadas}


@router.get("/infraestrutura")
def infraestrutura(db: Session = Depends(get_db)) -> dict:
    """Infrastructure Cost Pool, Provider Economics, capacidade, alertas e projeção."""
    componentes = db.query(ComponenteInfra).order_by(ComponenteInfra.fornecedor, ComponenteInfra.id).all()
    resposta = {"componentes": [comissoes.infraestrutura.como_dict(c) for c in componentes],
                "modelos_preco": [m.value for m in comissoes.tipos.ModeloPreco],
                "status_arquitetura": [s.value for s in comissoes.tipos.StatusArquitetura],
                "tipos_fonte": [t.value for t in comissoes.tipos.TipoFonte],
                "economia": comissoes.capacidade.economia_fornecedores(db), "categorias": list(comissoes.tipos.CATEGORIAS_INFRA),
                "ciclos": list(comissoes.tipos.CICLOS_COBRANCA), "politica": comissoes.politica.vigente_infra(db).regras}
    db.commit()
    return resposta


def _recalcular(db: Session) -> int:
    calculadas = comissoes.motor.recalcular_aguardando(db)
    db.commit()
    return calculadas


@router.post("/infraestrutura/componentes", status_code=201)
def criar_componente(dados: ComponenteInfraSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    componente = comissoes.infraestrutura.criar(db, dados.model_dump(), ator_id)
    return {"componente": comissoes.infraestrutura.como_dict(componente), "aguardando_calculadas": _recalcular(db)}


@router.patch("/infraestrutura/componentes/{componente_id}")
def atualizar_componente(componente_id: int, dados: AtualizarComponenteInfraSchema, ator_id: str | None = Depends(get_ator_id),
                         db: Session = Depends(get_db)) -> dict:
    """Plano, custo, capacidade ou alocação. Comissões calculadas guardam o snapshot; só o recálculo explícito muda as não pagas."""
    valores = dict(dados.dados)
    for campo in ("vigente_de", "vigente_ate", "verificado_em", "proxima_revisao_em"):
        if isinstance(valores.get(campo), str):
            valores[campo] = date.fromisoformat(valores[campo])
    componente = comissoes.infraestrutura.atualizar(db, componente_id, valores, dados.motivo, ator_id)
    return {"componente": comissoes.infraestrutura.como_dict(componente), "aguardando_calculadas": _recalcular(db)}


@router.post("/infraestrutura/componentes/{componente_id}/envelopes", status_code=201)
def criar_envelope(componente_id: int, dados: EnvelopeCapacidadeSchema, ator_id: str | None = Depends(get_ator_id),
                   db: Session = Depends(get_db)) -> dict:
    """Capacity Envelope de fornecedor por uso (ex.: Neon). Benchmark do fornecedor fica só como referência."""
    valores = {k: v for k, v in dados.model_dump().items() if v is not None or k == "benchmark_only"}
    envelope = comissoes.infraestrutura.criar_envelope(db, componente_id, valores, ator_id)
    return {"envelope": comissoes.infraestrutura.envelope_dict(envelope), "aguardando_calculadas": _recalcular(db)}


@router.post("/infraestrutura/componentes/{componente_id}/uso")
def registrar_uso(componente_id: int, dados: UsoCapacidadeSchema, ator_id: str | None = Depends(get_ator_id),
                  db: Session = Depends(get_db)) -> dict:
    """Uso medido → status e alerta de capacidade. Nenhum upgrade ou contratação acontece sozinho."""
    resultado = comissoes.capacidade.registrar_uso(db, componente_id, dados.uso, ator_id, dados.fonte, dados.medido_em)
    db.commit()
    return resultado


@router.post("/infraestrutura/custos-diretos", status_code=201)
def registrar_custo_direto(dados: CustoDiretoSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    linha = comissoes.infraestrutura.registrar_custo_direto(db, dados.model_dump(), ator_id)
    return {"id": linha.id, "aguardando_calculadas": _recalcular(db)}


@router.post("/infraestrutura/alertas/{alerta_id}/decisao")
def decidir_alerta(alerta_id: int, dados: DecisaoAlertaSchema, ator_id: str | None = Depends(get_ator_id),
                   db: Session = Depends(get_db)) -> dict:
    alerta = comissoes.capacidade.decidir_alerta(db, alerta_id, dados.decisao, ator_id)
    db.commit()
    return comissoes.capacidade.alerta_dict(alerta)


@router.post("/politica-infraestrutura", status_code=201)
def alterar_politica_infra(dados: PoliticaInfraSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    """Pesos por tier, limiares de capacidade e base de custo da comissão: nova versão auditada."""
    politica = comissoes.politica.nova_infra(db, {"pesos": dados.pesos, "limiares": dados.limiares,
                                                  "custo_comissao": dados.custo_comissao}, dados.motivo, ator_id)
    db.commit()
    return {"versao": politica.versao, "regras": politica.regras}


@router.post("/cotacoes-cambio/sincronizar")
def sincronizar_ptax(db: Session = Depends(get_db)) -> dict:
    """PTAX de fechamento do Banco Central dos últimos dias úteis (a mesma rotina do cron horário)."""
    resultado = finops.cambio.sincronizar_ptax(db)
    return {**resultado, "aguardando_calculadas": _recalcular(db)}


@router.post("/status-tributario", status_code=201)
def criar_status_tributario(dados: StatusTributarioSchema, ator_id: str | None = Depends(get_ator_id),
                            db: Session = Depends(get_db)) -> dict:
    """TaxStatusPeriod (D-078): nova vigência da situação de CBS/IBS. Histórico e comissões fixadas não mudam; apurações
    ainda aguardando são refeitas."""
    periodo = comissoes.tributos.criar_status_periodo(db, dados.model_dump(), ator_id)
    return {"periodo": comissoes.tributos.status_periodo_dict(periodo), "aguardando_calculadas": _recalcular(db)}


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
