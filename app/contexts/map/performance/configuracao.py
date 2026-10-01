"""Configuração versionada do MAP Performance (D-080): políticas (`politica_comissao`) e quotas (`quota_comercial`).

Toda mudança cria uma versão nova (a anterior fica inativa, nunca é apagada) e é auditada com antes/depois e motivo.
Bancos sem a migração (testes, E2E) recebem a versão inicial na primeira leitura.
"""

import re
from copy import deepcopy

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.map.performance.tipos import (
    CAMPANHA_VERAO_INICIAL,
    CODIGO_CAMPANHA_VERAO,
    CODIGO_POLITICA_COMISSAO_PRIVADA,
    CODIGO_POLITICA_PERFORMANCE,
    POLITICA_COMISSAO_PRIVADA_INICIAL,
    POLITICA_PERFORMANCE_INICIAL,
    PREFIXO_CAMPANHA,
    QUOTAS_INICIAIS,
    Familia,
    Metrica,
    Velocidade,
)
from app.models.contrato_governo import PoliticaComissao
from app.models.quota_comercial import QuotaComercial
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

INICIAIS = {
    CODIGO_POLITICA_PERFORMANCE: POLITICA_PERFORMANCE_INICIAL,
    CODIGO_POLITICA_COMISSAO_PRIVADA: POLITICA_COMISSAO_PRIVADA_INICIAL,
    PREFIXO_CAMPANHA + CODIGO_CAMPANHA_VERAO: CAMPANHA_VERAO_INICIAL,
}
COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
FAMILIAS = {f.value for f in Familia}


def politica(db: Session, codigo: str) -> PoliticaComissao | None:
    """Versão ativa; cria a inicial se o código é conhecido e ainda não existe."""
    atual = db.query(PoliticaComissao).filter_by(codigo=codigo, ativa=True).order_by(PoliticaComissao.versao.desc()).first()
    if atual is None and codigo in INICIAIS:
        try:  # duas requisições simultâneas num banco sem a migração: a segunda relê a versão que a primeira gravou
            with db.begin_nested():
                atual = PoliticaComissao(codigo=codigo, versao=1, regras=deepcopy(INICIAIS[codigo]), ativa=True,
                                         motivo="Versão inicial (D-080)", criado_por="semente")
                db.add(atual)
        except IntegrityError:
            atual = db.query(PoliticaComissao).filter_by(codigo=codigo, ativa=True).order_by(PoliticaComissao.versao.desc()).first()
    return atual


def performance(db: Session) -> dict:
    return politica(db, CODIGO_POLITICA_PERFORMANCE).regras


def comissao_privada(db: Session) -> dict:
    return politica(db, CODIGO_POLITICA_COMISSAO_PRIVADA).regras


def campanhas(db: Session) -> list[PoliticaComissao]:
    politica(db, PREFIXO_CAMPANHA + CODIGO_CAMPANHA_VERAO)
    return (db.query(PoliticaComissao).filter(PoliticaComissao.codigo.like(PREFIXO_CAMPANHA + "%"), PoliticaComissao.ativa.is_(True))
            .order_by(PoliticaComissao.codigo).all())


def _fracao(valor, nome: str) -> None:
    if not isinstance(valor, int | float) or not 0 <= valor <= 1:
        raise ValidacaoFalhou(f"{nome}: fração entre 0 e 1.")


def _positivo(valor, nome: str) -> None:
    if not isinstance(valor, int | float) or valor <= 0:
        raise ValidacaoFalhou(f"{nome}: número positivo.")


def _validar_performance(regras: dict) -> None:
    faltando = set(POLITICA_PERFORMANCE_INICIAL) - set(regras)
    if faltando:
        raise ValidacaoFalhou(f"Política de performance incompleta: {', '.join(sorted(faltando))}.")
    if regras["fonte_new_mrr"] != "FIRST_PAYMENT":
        raise ValidacaoFalhou("fonte_new_mrr: FIRST_PAYMENT (1ª mensalidade efetivamente paga).")
    _positivo(regras["cobertura"].get("multiplo_padrao"), "cobertura.multiplo_padrao")
    for etapa, taxa in regras["funil_baseline"].items():
        (_positivo if etapa == "contas_trabalhadas" else _fracao)(taxa, f"funil_baseline.{etapa}")
    mix = regras["mix"]
    if set(mix["alvo"]) - FAMILIAS or abs(sum(mix["alvo"].values()) - 1) > 0.001:
        raise ValidacaoFalhou("mix.alvo: famílias conhecidas somando 100%.")
    _fracao(mix["alto_valor_minimo"], "mix.alto_valor_minimo")
    for regra in regras["classificacao_planos"]:
        if regra.get("familia") not in FAMILIAS or not set(regra) - {"familia"} <= {"categoria", "modulo", "segmento"}:
            raise ValidacaoFalhou("classificacao_planos: família conhecida + categoria, módulo ou segmento.")
    if set(regras["familia_por_oferta"].values()) - FAMILIAS:
        raise ValidacaoFalhou("familia_por_oferta: famílias conhecidas.")
    velocidades = {v.value for v in Velocidade}
    if set(regras["velocidade"]["por_familia"].values()) - velocidades or set(regras["velocidade"]["dias"]) != velocidades:
        raise ValidacaoFalhou("velocidade: FAST, CORE e STRATEGIC, com dias para cada classe.")
    if regras["governo"].get("conta_na_quota_privada"):
        raise ValidacaoFalhou("Pipeline governamental não compensa a quota privada (Government Bookings ≠ New MRR).")
    _positivo(regras["ticket_medio_baseline"], "ticket_medio_baseline")


def _validar_comissao(regras: dict) -> None:
    _fracao(regras.get("taxa"), "taxa")
    if regras.get("gatilho") != "PAYMENT_RECEIVED" or regras.get("base") != "NET_COMMISSIONABLE_MARGIN":
        raise ValidacaoFalhou("Comissão privada: gatilho PAYMENT_RECEIVED e base NET_COMMISSIONABLE_MARGIN (D-074).")
    if (regras.get("inadimplencia") or {}).get("acao") not in ("HOLD", "NONE"):
        raise ValidacaoFalhou("inadimplencia.acao: HOLD (retém a comissão a pagar) ou NONE.")
    if (regras.get("cancelamento") or {}).get("acao") != "STOP_FUTURE":
        raise ValidacaoFalhou("cancelamento.acao: STOP_FUTURE (sem mensalidade paga, sem comissão).")
    for nome in ("ciclo_dias", "tolerancia_dias"):
        if not isinstance(regras["inadimplencia"].get(nome), int) or regras["inadimplencia"][nome] < 0:
            raise ValidacaoFalhou(f"inadimplencia.{nome}: inteiro ≥ 0.")


def _validar_campanha(regras: dict) -> None:
    if not regras.get("inicio") or not regras.get("fim") or regras["fim"] <= regras["inicio"]:
        raise ValidacaoFalhou("Campanha: início e fim (AAAA-MM-DD), fim depois do início.")
    _positivo(regras.get("meta_individual"), "meta_individual")
    faixas = regras.get("faixas") or []
    limites = [f.get("de") for f in faixas]
    if not faixas or limites != sorted(limites) or limites[0] != 0 or any(not 0 <= f.get("bonus", -1) <= 5 for f in faixas):
        raise ValidacaoFalhou("faixas: crescentes a partir de 0, cada uma com bônus (fração da comissão).")
    if regras.get("base_bonus") != "COMMISSION_OF_NEW_SALES":
        raise ValidacaoFalhou("base_bonus: COMMISSION_OF_NEW_SALES (nunca a carteira histórica).")


def nova_politica(db: Session, codigo: str, regras: dict, motivo: str, ator_id: str | None) -> PoliticaComissao:
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo da mudança.")
    if codigo == CODIGO_POLITICA_PERFORMANCE:
        _validar_performance(regras)
    elif codigo == CODIGO_POLITICA_COMISSAO_PRIVADA:
        _validar_comissao(regras)
    elif codigo.startswith(PREFIXO_CAMPANHA) and len(codigo) > len(PREFIXO_CAMPANHA):
        _validar_campanha(regras)
    else:
        raise ValidacaoFalhou("Política desconhecida.")
    anterior = politica(db, codigo)
    if anterior is not None:
        anterior.ativa = False
    nova = PoliticaComissao(codigo=codigo, versao=(anterior.versao + 1) if anterior else 1, regras=regras, ativa=True,
                            motivo=motivo, criado_por=ator_id)
    db.add(nova)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "politica_map_alterada", "politica_comissao", nova.id, ator_id,
                                {"codigo": codigo, "antes": anterior.regras if anterior else None, "depois": regras,
                                 "versao": nova.versao, "motivo": motivo})
    return nova


def _garantir_quotas(db: Session) -> None:
    if db.query(QuotaComercial.id).first() is None:  # bancos sem a migração
        db.add_all([QuotaComercial(representante_id=None, metrica=Metrica.NEW_MRR.value, competencia=c, valor=v, multiplo_cobertura=3.0,
                                   pipeline_alvo=p, versao=1, ativa=True, motivo="Quota do PO (D-080)", criado_por="semente")
                    for c, v, p in QUOTAS_INICIAIS])
        db.flush()


def quotas(db: Session, competencias: list[str], representante_ids: list[int]) -> dict[tuple[int, str], QuotaComercial | None]:
    """Quota efetiva por (representante, competência): a específica do representante prevalece sobre a padrão."""
    _garantir_quotas(db)
    linhas = (db.query(QuotaComercial).filter(QuotaComercial.ativa.is_(True), QuotaComercial.metrica == Metrica.NEW_MRR.value,
                                              QuotaComercial.competencia.in_(competencias),
                                              or_(QuotaComercial.representante_id.is_(None),
                                                  QuotaComercial.representante_id.in_(representante_ids or [-1])))
              .all())
    padrao = {q.competencia: q for q in linhas if q.representante_id is None}
    proprias = {(q.representante_id, q.competencia): q for q in linhas if q.representante_id is not None}
    return {(r, c): proprias.get((r, c)) or padrao.get(c) for r in representante_ids for c in competencias}


def listar_quotas(db: Session) -> list[QuotaComercial]:
    _garantir_quotas(db)
    ativas = (db.query(QuotaComercial).filter(QuotaComercial.ativa.is_(True))
              .order_by(QuotaComercial.competencia, QuotaComercial.representante_id, QuotaComercial.id).all())
    return list({(q.representante_id, q.competencia): q for q in ativas}.values())  # uma por escopo (a mais recente)


def definir_quota(db: Session, dados: dict, motivo: str, ator_id: str | None) -> QuotaComercial:
    """Nova versão da quota (padrão ou de um representante) para uma competência."""
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo da quota.")
    competencia = dados.get("competencia") or ""
    if not COMPETENCIA.match(competencia):
        raise ValidacaoFalhou("Competência no formato AAAA-MM.")
    _positivo(dados.get("valor"), "valor")
    for campo in ("multiplo_cobertura", "pipeline_alvo"):
        if dados.get(campo) is not None:
            _positivo(dados[campo], campo)
    _garantir_quotas(db)
    representante_id = dados.get("representante_id")
    anterior = (db.query(QuotaComercial).filter_by(representante_id=representante_id, metrica=Metrica.NEW_MRR.value,
                                                   competencia=competencia, ativa=True).one_or_none())
    versao = (db.query(QuotaComercial.versao).filter_by(representante_id=representante_id, metrica=Metrica.NEW_MRR.value,
                                                        competencia=competencia).order_by(QuotaComercial.versao.desc()).first())
    if anterior is not None:
        anterior.ativa = False
    quota = QuotaComercial(representante_id=representante_id, metrica=Metrica.NEW_MRR.value, competencia=competencia,
                           valor=float(dados["valor"]), multiplo_cobertura=dados.get("multiplo_cobertura"),
                           pipeline_alvo=dados.get("pipeline_alvo"), versao=(versao[0] + 1) if versao else 1, ativa=True,
                           motivo=motivo, criado_por=ator_id)
    db.add(quota)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "quota_comercial_definida", "quota_comercial", quota.id, ator_id,
                                {"antes": quota_dict(anterior) if anterior else None, "depois": quota_dict(quota), "motivo": motivo})
    return quota


def quota_dict(quota: QuotaComercial) -> dict:
    return {"id": quota.id, "representante_id": quota.representante_id, "metrica": quota.metrica, "competencia": quota.competencia,
            "valor": quota.valor, "multiplo_cobertura": quota.multiplo_cobertura, "pipeline_alvo": quota.pipeline_alvo,
            "versao": quota.versao, "motivo": quota.motivo}
