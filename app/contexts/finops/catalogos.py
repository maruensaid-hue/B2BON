"""Catálogos versionados dos AI Credits (Fase 15).

- Pacotes de top-up (`pacote_credito`): versão, moeda, créditos, preço,
  validade e vigência. Preço efetivo por 1.000 créditos é CALCULADO.
- Catálogo de workloads (`catalogo_credito` + `workload_ia`): pesos em
  créditos por operação, com versão (CREDIT_CATALOG_V1, V2…). Toda
  execução grava a versão usada, então o histórico é reproduzível.

As sementes abaixo são a ÚNICA cópia dos valores iniciais no código; o
banco passa a ser a fonte depois de semeado. Mudança de preço ou peso é
nova versão, feita por administrador autorizado e auditada (valor
anterior, novo, ator, motivo). Nada aqui muda preço ou peso sozinho.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.creditos_ia import CatalogoCreditos, PacoteCreditos, WorkloadIa
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

# --- Sementes (valores do prompt da Fase 15) -------------------------------------------
# (codigo, nome, créditos, preço BRL, status)
SEMENTE_PACOTES = (
    ("AI_START", "AI Start", 5_000, Decimal("99"), "ATIVO"),
    ("AI_15K", "AI 15K", 15_000, Decimal("249"), "ATIVO"),
    ("AI_30K", "AI 30K", 30_000, Decimal("449"), "ATIVO"),
    ("AI_75K", "AI 75K", 75_000, Decimal("899"), "ATIVO"),
    ("AI_150K", "AI 150K", 150_000, Decimal("1499"), "ATIVO"),
    ("AI_350K", "AI 350K", 350_000, Decimal("2999"), "ATIVO"),
    ("AI_1M", "AI 1M", 1_000_000, Decimal("6990"), "ATIVO"),
    ("ENTERPRISE", "Enterprise", None, None, "CONTACT_SALES"),
)
VALIDADE_TOPUP_SEMENTE = 12

# Guardas internas de custo por chamada (USD), por classe. Calibráveis; não são preço.
CUSTO_MAX_USD = {"C0": None, "C1": Decimal("0.05"), "C2": Decimal("0.50"), "C3": Decimal("5.00")}

# (codigo, módulo, nome, classe, base, min, max, política variável, requer aprovação)
SEMENTE_WORKLOADS_V1 = (
    ("classification_simple", "intelligence", "Classificação simples", "C1", 1, None, None, None, False),
    ("short_summary", "plataforma", "Resumo curto", "C1", 1, None, None, None, False),
    ("basic_company_analysis", "predator", "Análise básica de empresa", "C2", 2, None, None, None, False),
    ("icp_fit", "network", "Aderência ao ICP", "C1", 2, None, None, None, False),
    ("website_analysis", "predator", "Análise de site", "C2", 3, None, None, None, False),
    ("prospecting_message", "predator", "Mensagem de prospecção", "C2", 2, None, None, None, False),
    ("prospect_personalization", "predator", "Personalização de prospect", "C2", 2, None, None, None, False),
    ("commercial_response", "network", "Resposta comercial", "C2", 3, None, None, None, False),
    ("objection_analysis", "crm", "Análise de objeção", "C2", 3, None, None, None, False),
    ("cadence_generation", "predator", "Geração de cadência", "C2", 8, None, None, None, False),
    ("decision_maker_analysis", "predator", "Análise de decisores", "C2", 5, None, None, None, False),
    ("meeting_summary", "predator", "Resumo de reunião", "C2", 5, None, None, None, False),
    ("meeting_intelligence", "crm", "Meeting Intelligence", "C2", 10, None, None, None, False),
    ("next_best_action", "crm", "Next Best Action", "C2", 5, None, None, None, False),
    ("next_best_offer", "crm", "Next Best Offer", "C2", 8, None, None, None, False),
    ("opportunity_intelligence", "crm", "Opportunity Intelligence", "C2", 15, None, None, None, False),
    ("churn_prediction", "map", "Previsão de churn", "C2", 10, None, None, None, False),
    ("churn_remediation", "map", "Remediação de churn", "C2", 15, None, None, None, False),
    ("white_space_analysis", "crm", "White Space", "C2", 15, None, None, None, False),
    ("simple_rfp_analysis", "bids", "Análise de RFP simples", "C2", 25, None, None, None, False),
    ("tender_analysis", "bids", "Análise de edital", "C3", 50, None, None, None, False),
    ("tender_terms_of_reference", "bids", "Edital + Termo de Referência", "C3", 75, None, None, None, False),
    ("compliance_matrix", "bids", "Matriz de conformidade", "C3", 75, None, None, None, False),
    ("full_go_no_go", "bids", "Go/No-Go completo", "C3", 100, None, None, None, False),
    ("complex_multi_document_analysis", "intelligence", "Análise complexa multi-documento", "C3", 150, 150, 300,
     {"por_documento_extra": 25, "por_pagina": 0.5, "por_pagina_ocr": 0.5}, True),
    # Public Procurement (§45): ações determinísticas não consomem créditos.
    ("procurement_deterministic", "procurement", "Operação determinística de compras", "C0", 0, None, None, None, False),
    ("procurement_document_intelligence", "procurement", "Document Intelligence de compras", "C3", 25, 25, 300,
     {"por_pagina": 1, "por_pagina_ocr": 0.5}, False),
    ("supplier_intelligence", "procurement", "Supplier Intelligence", "C2", 10, None, None, None, False),
    ("contract_intelligence", "procurement", "Contract Intelligence", "C2", 15, None, None, None, False),
    ("procurement_risk_analysis", "procurement", "Análise de risco de compras", "C2", 10, None, None, None, False),
    ("procurement_next_best_action", "procurement", "Próxima ação de compras", "C2", 5, None, None, None, False),
    ("procurement_complex_comparison", "procurement", "Comparação complexa de propostas", "C3", 75, None, None, None, False),
)
VERSAO_V1 = "CREDIT_CATALOG_V1"


def garantir_semente(db: Session) -> None:
    """Idempotente: semeia pacotes e o catálogo V1 se ainda não existirem.
    Dois primeiros acessos simultâneos: um semeia, o outro bate na
    unicidade dentro do savepoint e segue com a semente do primeiro."""
    if db.query(PacoteCreditos.id).first() is not None and db.query(CatalogoCreditos.id).first() is not None:
        return
    try:
        with db.begin_nested():
            _semear(db)
    except IntegrityError:
        pass


def _semear(db: Session) -> None:
    if db.query(PacoteCreditos.id).first() is None:
        for ordem, (codigo, nome, creditos, preco, status) in enumerate(SEMENTE_PACOTES):
            db.add(PacoteCreditos(codigo=codigo, nome=nome, versao=1, moeda="BRL", creditos=creditos, preco=preco,
                                  status=status, validade_meses=VALIDADE_TOPUP_SEMENTE if creditos else None, ordem=ordem))
    if db.query(CatalogoCreditos.id).first() is None:
        catalogo = CatalogoCreditos(versao=VERSAO_V1, numero=1, status="ATIVO", motivo="Catálogo inicial (Fase 15)",
                                    vigente_desde=datetime.now(UTC))
        db.add(catalogo)
        db.flush()
        for codigo, modulo, nome, classe, base, minimo, maximo, variavel, aprovacao in SEMENTE_WORKLOADS_V1:
            db.add(WorkloadIa(catalogo_id=catalogo.id, codigo=codigo, modulo=modulo, nome=nome, classe=classe,
                              creditos_base=Decimal(base), creditos_min=minimo, creditos_max=maximo, politica_variavel=variavel,
                              politica_modelo={"classe_minima": classe}, custo_max_usd=CUSTO_MAX_USD[classe],
                              requer_aprovacao=aprovacao, ativo=True))
    db.flush()


# --- Pacotes ------------------------------------------------------------------------------


def preco_efetivo_1k(pacote: PacoteCreditos) -> Decimal | None:
    if not pacote.creditos or pacote.preco is None:
        return None
    return (Decimal(str(pacote.preco)) * 1000 / pacote.creditos).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def receita_por_credito(pacote: PacoteCreditos) -> Decimal:
    return Decimal(str(pacote.preco)) / pacote.creditos


def pacotes_vigentes(db: Session) -> list[PacoteCreditos]:
    garantir_semente(db)
    return (db.query(PacoteCreditos).filter(PacoteCreditos.valido_ate.is_(None), PacoteCreditos.status != "INATIVO")
            .order_by(PacoteCreditos.ordem).all())


def pacote_dict(pacote: PacoteCreditos) -> dict:
    efetivo = preco_efetivo_1k(pacote)
    return {
        "codigo": pacote.codigo, "nome": pacote.nome, "versao": pacote.versao, "moeda": pacote.moeda,
        "creditos": pacote.creditos, "preco": float(pacote.preco) if pacote.preco is not None else None,
        "preco_efetivo_por_1000": float(efetivo) if efetivo is not None else None,
        "validade_meses": pacote.validade_meses, "status": pacote.status,
        "valido_de": pacote.valido_de.isoformat() if pacote.valido_de else None,
    }


def obter_pacote(db: Session, codigo: str) -> PacoteCreditos:
    pacote = next((p for p in pacotes_vigentes(db) if p.codigo == codigo), None)
    if pacote is None:
        raise NaoEncontrado(f"Pacote {codigo} não encontrado.")
    return pacote


def nova_versao_pacote(db: Session, codigo: str, preco: Decimal, creditos: int, validade_meses: int | None,
                       ator_id: str | None, motivo: str) -> PacoteCreditos:
    """Mudança de preço = nova versão; compras antigas guardam a versão paga."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo da alteração de preço.")
    if preco <= 0 or creditos <= 0:
        raise ValidacaoFalhou("Preço e créditos devem ser positivos.")
    atual = obter_pacote(db, codigo)
    agora = datetime.now(UTC)
    atual.valido_ate = agora
    novo = PacoteCreditos(codigo=codigo, nome=atual.nome, versao=atual.versao + 1, moeda=atual.moeda, creditos=creditos,
                          preco=preco, status="ATIVO", validade_meses=validade_meses, ordem=atual.ordem, valido_de=agora)
    db.add(novo)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "pacote_credito_alterado", "pacote_credito", novo.id, ator_id, {
        "codigo": codigo, "motivo": motivo,
        "anterior": {"versao": atual.versao, "preco": float(atual.preco) if atual.preco is not None else None,
                     "creditos": atual.creditos, "validade_meses": atual.validade_meses},
        "novo": {"versao": novo.versao, "preco": float(preco), "creditos": creditos, "validade_meses": validade_meses},
    })
    db.commit()
    return novo


# --- Catálogo de workloads -------------------------------------------------------------------


@dataclass(frozen=True)
class Estimativa:
    workload: str
    catalogo_versao: str
    classe: str
    creditos: Decimal
    minimo: Decimal | None
    maximo: Decimal | None
    variavel: bool
    detalhe: dict


def catalogo_ativo(db: Session) -> CatalogoCreditos:
    garantir_semente(db)
    return db.query(CatalogoCreditos).filter_by(status="ATIVO").one()


def obter_catalogo(db: Session, versao: str) -> CatalogoCreditos:
    catalogo = db.query(CatalogoCreditos).filter_by(versao=versao).one_or_none()
    if catalogo is None:
        raise NaoEncontrado(f"Catálogo {versao} não encontrado.")
    return catalogo


def workloads(db: Session, catalogo: CatalogoCreditos | None = None) -> list[WorkloadIa]:
    catalogo = catalogo or catalogo_ativo(db)
    return db.query(WorkloadIa).filter_by(catalogo_id=catalogo.id).order_by(WorkloadIa.modulo, WorkloadIa.codigo).all()


def obter_workload(db: Session, codigo: str, catalogo: CatalogoCreditos | None = None) -> WorkloadIa:
    catalogo = catalogo or catalogo_ativo(db)
    workload = db.query(WorkloadIa).filter_by(catalogo_id=catalogo.id, codigo=codigo).one_or_none()
    if workload is None or not workload.ativo:
        raise NaoEncontrado(f"Workload {codigo} não existe no catálogo {catalogo.versao}.")
    return workload


def estimar(workload: WorkloadIa, versao: str, parametros: dict | None = None) -> Estimativa:
    """Créditos da operação ANTES de executar. Fixo = peso; variável = peso
    + política (documentos, páginas, OCR), limitado entre mínimo e máximo."""
    parametros = parametros or {}
    base = Decimal(str(workload.creditos_base))
    politica = workload.politica_variavel or {}
    detalhe: dict = {"base": float(base)}
    total = base
    if politica:
        paginas = max(int(parametros.get("paginas") or 0), 0)
        documentos = max(int(parametros.get("documentos") or 1), 1)
        ocr = bool(parametros.get("ocr"))
        adicionais = {
            "documentos": Decimal(str(politica.get("por_documento_extra", 0))) * (documentos - 1),
            "paginas": Decimal(str(politica.get("por_pagina", 0))) * paginas,
            "ocr": Decimal(str(politica.get("por_pagina_ocr", 0))) * paginas if ocr else Decimal(0),
        }
        detalhe.update({k: float(v) for k, v in adicionais.items() if v})
        total = base + sum(adicionais.values())
    minimo = Decimal(str(workload.creditos_min)) if workload.creditos_min is not None else None
    maximo = Decimal(str(workload.creditos_max)) if workload.creditos_max is not None else None
    if minimo is not None:
        total = max(total, minimo)
    if maximo is not None:
        total = min(total, maximo)
    return Estimativa(workload.codigo, versao, workload.classe, total.quantize(Decimal("0.01")), minimo, maximo,
                      bool(politica), detalhe)


def workload_dict(workload: WorkloadIa) -> dict:
    return {
        "codigo": workload.codigo, "modulo": workload.modulo, "nome": workload.nome, "descricao": workload.descricao,
        "classe": workload.classe, "creditos_base": float(workload.creditos_base),
        "creditos_min": float(workload.creditos_min) if workload.creditos_min is not None else None,
        "creditos_max": float(workload.creditos_max) if workload.creditos_max is not None else None,
        "politica_variavel": workload.politica_variavel, "politica_modelo": workload.politica_modelo,
        "custo_max_usd": float(workload.custo_max_usd) if workload.custo_max_usd is not None else None,
        "requer_aprovacao": workload.requer_aprovacao, "ativo": workload.ativo,
    }


_CAMPOS_EDITAVEIS = {"creditos_base", "creditos_min", "creditos_max", "politica_variavel", "custo_max_usd",
                     "requer_aprovacao", "ativo", "margem_alvo"}


def criar_rascunho(db: Session, mudancas: dict[str, dict], ator_id: str | None, motivo: str) -> CatalogoCreditos:
    """Nova versão em RASCUNHO copiando a ativa, com as mudanças de peso.
    Não afeta cobrança até ser ativada."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo da nova versão do catálogo.")
    ativo = catalogo_ativo(db)
    atuais = {w.codigo: w for w in workloads(db, ativo)}
    desconhecidos = set(mudancas) - set(atuais)
    if desconhecidos:
        raise ValidacaoFalhou(f"Workloads inexistentes: {sorted(desconhecidos)}")
    for codigo, campos in mudancas.items():
        invalidos = set(campos) - _CAMPOS_EDITAVEIS
        if invalidos:
            raise ValidacaoFalhou(f"Campos não editáveis em {codigo}: {sorted(invalidos)}")
        if "creditos_base" in campos and Decimal(str(campos["creditos_base"])) < 0:
            raise ValidacaoFalhou("Peso não pode ser negativo.")
    numero = (db.query(CatalogoCreditos.numero).order_by(CatalogoCreditos.numero.desc()).first() or (0,))[0] + 1
    rascunho = CatalogoCreditos(versao=f"CREDIT_CATALOG_V{numero}", numero=numero, status="RASCUNHO", motivo=motivo, criado_por=ator_id)
    db.add(rascunho)
    db.flush()
    for codigo, original in atuais.items():
        campos = {c: getattr(original, c) for c in ("modulo", "nome", "descricao", "classe", "creditos_base", "creditos_min",
                                                   "creditos_max", "politica_variavel", "politica_modelo", "custo_max_usd",
                                                   "margem_alvo", "requer_aprovacao", "ativo")}
        campos.update(mudancas.get(codigo, {}))
        db.add(WorkloadIa(catalogo_id=rascunho.id, codigo=codigo, **campos))
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "catalogo_credito_rascunho", "catalogo_credito", rascunho.id,
                                ator_id, {"versao": rascunho.versao, "base": ativo.versao, "motivo": motivo, "mudancas": {
                                    codigo: {"anterior": {c: _json(getattr(atuais[codigo], c)) for c in campos},
                                             "novo": {c: _json(v) for c, v in campos.items()}}
                                    for codigo, campos in mudancas.items()}})
    db.commit()
    return rascunho


def ativar(db: Session, versao: str, ator_id: str | None, motivo: str) -> CatalogoCreditos:
    """Aprovação administrativa: a versão passa a valer para NOVAS execuções;
    as já registradas mantêm a versão com que foram cobradas."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo da ativação.")
    novo = obter_catalogo(db, versao)
    if novo.status != "RASCUNHO":
        raise ValidacaoFalhou("Só um rascunho pode ser ativado.")
    anterior = catalogo_ativo(db)
    anterior.status = "ARQUIVADO"
    novo.status = "ATIVO"
    novo.aprovado_por = ator_id
    novo.vigente_desde = datetime.now(UTC)
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "catalogo_credito_ativado", "catalogo_credito", novo.id, ator_id,
                                {"anterior": anterior.versao, "novo": novo.versao, "motivo": motivo})
    db.commit()
    return novo


def _json(valor):
    return float(valor) if isinstance(valor, Decimal) else valor
