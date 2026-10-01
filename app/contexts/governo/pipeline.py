"""Pipeline Government da B2B ON (D-072): separado da quota privada de New MRR.

Ciclo comercial (90–180 dias, não fixado) é o que a data prevista disser; a probabilidade é informada por
quem vende. Pipeline ponderado = TCV estimado × probabilidade.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.governo.tipos import ESTAGIOS, ESTAGIOS_FECHADOS
from app.models.contrato_governo import ContratoGoverno, OportunidadeGoverno
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

CAMPOS = ("titulo", "entidade_governamental", "estagio", "referencia_processo", "origem", "data_prevista_fechamento",
          "valor_estimado_licenca", "valor_estimado_assinatura", "valor_estimado_servicos", "probabilidade", "plano_id",
          "representante_id", "tenant_id")


def _validar(dados: dict) -> None:
    if "estagio" in dados and dados["estagio"] not in ESTAGIOS:
        raise ValidacaoFalhou(f"Estágio inválido. Use um de {', '.join(ESTAGIOS)}.")
    if "probabilidade" in dados and not 0 <= float(dados["probabilidade"]) <= 1:
        raise ValidacaoFalhou("Probabilidade entre 0 e 1.")
    for campo in ("valor_estimado_licenca", "valor_estimado_assinatura", "valor_estimado_servicos"):
        if campo in dados and Decimal(str(dados[campo] or 0)) < 0:
            raise ValidacaoFalhou(f"{campo} não pode ser negativo.")


def criar(db: Session, dados: dict, ator_id: str | None) -> OportunidadeGoverno:
    _validar(dados)
    oportunidade = OportunidadeGoverno(**{c: v for c, v in dados.items() if c in CAMPOS})
    db.add(oportunidade)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "oportunidade_governo_criada", "oportunidade_governo",
                                oportunidade.id, ator_id, {"dados": {k: str(v) for k, v in dados.items()}, "origem": "governo"})
    db.commit()
    return oportunidade


def atualizar(db: Session, oportunidade_id: int, dados: dict, ator_id: str | None) -> OportunidadeGoverno:
    oportunidade = db.get(OportunidadeGoverno, oportunidade_id)
    if oportunidade is None:
        raise NaoEncontrado(f"Oportunidade {oportunidade_id} não encontrada")
    _validar(dados)
    antes = {c: str(getattr(oportunidade, c)) for c in dados if c in CAMPOS}
    for campo, valor in dados.items():
        if campo in CAMPOS:
            setattr(oportunidade, campo, valor)
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "oportunidade_governo_atualizada", "oportunidade_governo",
                                oportunidade.id, ator_id, {"antes": antes, "depois": {k: str(v) for k, v in dados.items()}, "origem": "governo"})
    db.commit()
    return oportunidade


def oportunidade_dict(db: Session, oportunidade: OportunidadeGoverno) -> dict:
    tcv = (Decimal(str(oportunidade.valor_estimado_licenca or 0)) + Decimal(str(oportunidade.valor_estimado_assinatura or 0))
           + Decimal(str(oportunidade.valor_estimado_servicos or 0)))
    contrato = db.query(ContratoGoverno.id).filter_by(oportunidade_id=oportunidade.id).first()
    return {
        "id": oportunidade.id, "titulo": oportunidade.titulo, "entidade_governamental": oportunidade.entidade_governamental,
        "estagio": oportunidade.estagio, "procurement_stage": oportunidade.estagio, "referencia_processo": oportunidade.referencia_processo,
        "origem": oportunidade.origem,
        "data_prevista_fechamento": oportunidade.data_prevista_fechamento.isoformat() if oportunidade.data_prevista_fechamento else None,
        "valor_estimado_licenca": float(oportunidade.valor_estimado_licenca or 0),
        "valor_estimado_assinatura": float(oportunidade.valor_estimado_assinatura or 0),
        "valor_estimado_servicos": float(oportunidade.valor_estimado_servicos or 0), "tcv_estimado": float(tcv),
        "probabilidade": oportunidade.probabilidade, "pipeline_ponderado": float(tcv * Decimal(str(oportunidade.probabilidade or 0))),
        "plano_id": oportunidade.plano_id, "representante_id": oportunidade.representante_id, "tenant_id": oportunidade.tenant_id,
        "contrato_id": contrato[0] if contrato else None, "aberta": oportunidade.estagio not in ESTAGIOS_FECHADOS,
    }


def listar(db: Session) -> list[dict]:
    return [oportunidade_dict(db, o) for o in db.query(OportunidadeGoverno).order_by(OportunidadeGoverno.data_prevista_fechamento,
                                                                                     OportunidadeGoverno.id).all()]


def resumo(db: Session, ate: date | None = None) -> dict:
    abertas = [o for o in listar(db) if o["aberta"] and (ate is None or not o["data_prevista_fechamento"]
                                                         or o["data_prevista_fechamento"] <= ate.isoformat())]
    return {"oportunidades_abertas": len(abertas), "tcv_estimado": sum(o["tcv_estimado"] for o in abertas),
            "pipeline_ponderado": sum(o["pipeline_ponderado"] for o in abertas)}
