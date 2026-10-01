"""Política de comissão e templates comerciais versionados (D-072).

Mudar a política ou o template cria uma versão nova, auditada; contratos guardam a cópia da
versão em que nasceram, então uma mudança vale só para contratos novos.
"""

from sqlalchemy.orm import Session

from app.contexts.governo.tipos import (
    CODIGO_POLITICA,
    CODIGO_TEMPLATE_PROPOSTA,
    MARCADORES_TEMPLATE,
    POLITICA_ATUAL,
    TEMPLATE_PROPOSTA_INICIAL,
    Componente,
    Gatilho,
)
from app.models.contrato_governo import PoliticaComissao, TemplateDocumentoComercial
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou


def semear(db: Session) -> None:
    """Garante a versão 1 da política e do template (bancos criados sem a migração: testes, E2E)."""
    if db.query(PoliticaComissao).filter_by(codigo=CODIGO_POLITICA).first() is None:
        db.add(PoliticaComissao(codigo=CODIGO_POLITICA, versao=1, regras=POLITICA_ATUAL, ativa=True,
                                motivo="Política comercial do PO (D-072, D-073)", criado_por="semente"))
    if db.query(TemplateDocumentoComercial).filter_by(codigo=CODIGO_TEMPLATE_PROPOSTA).first() is None:
        db.add(TemplateDocumentoComercial(codigo=CODIGO_TEMPLATE_PROPOSTA, versao=1, corpo=TEMPLATE_PROPOSTA_INICIAL, ativo=True,
                                          criado_por="semente"))
    db.flush()


def politica_vigente(db: Session) -> PoliticaComissao:
    semear(db)
    return (db.query(PoliticaComissao).filter_by(codigo=CODIGO_POLITICA, ativa=True)
            .order_by(PoliticaComissao.versao.desc()).first())


def _validar_regras(regras: dict) -> None:
    gatilhos = {g.value for g in Gatilho}
    if regras.get("gatilho") not in gatilhos:
        raise ValidacaoFalhou(f"gatilho deve ser um de {sorted(gatilhos)} (emissão de nota fiscal ainda não existe na plataforma).")
    componentes = regras.get("componentes") or {}
    desconhecidos = set(componentes) - {c.value for c in Componente}
    if desconhecidos:
        raise ValidacaoFalhou(f"Componentes desconhecidos: {sorted(desconhecidos)}")
    for tipo, regra in componentes.items():
        taxa = regra.get("taxa")
        if regra.get("comissionavel") and (taxa is None or not 0 < taxa <= 1):
            raise ValidacaoFalhou(f"{tipo}: componente comissionável precisa de taxa entre 0 e 1.")


def nova_politica(db: Session, regras: dict, motivo: str, ator_id: str | None) -> PoliticaComissao:
    """Nova versão da política (ex.: tornar a implantação comissionável), sem mudança de código."""
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo da mudança de política.")
    _validar_regras(regras)
    anterior = politica_vigente(db)
    anterior.ativa = False
    nova = PoliticaComissao(codigo=CODIGO_POLITICA, versao=anterior.versao + 1, regras=regras, ativa=True, motivo=motivo,
                            criado_por=ator_id)
    db.add(nova)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "politica_comissao_alterada", "politica_comissao", nova.id,
                                ator_id, {"antes": anterior.regras, "depois": regras, "versao_anterior": anterior.versao,
                                          "versao": nova.versao, "motivo": motivo, "origem": "admin"})
    db.commit()
    return nova


def template_vigente(db: Session, codigo: str = CODIGO_TEMPLATE_PROPOSTA) -> TemplateDocumentoComercial:
    semear(db)
    return (db.query(TemplateDocumentoComercial).filter_by(codigo=codigo, ativo=True)
            .order_by(TemplateDocumentoComercial.versao.desc()).first())


def novo_template(db: Session, corpo: str, motivo: str, ator_id: str | None) -> TemplateDocumentoComercial:
    try:
        corpo.format(**dict.fromkeys(MARCADORES_TEMPLATE, ""))
    except (KeyError, IndexError, ValueError) as erro:
        raise ValidacaoFalhou(f"Marcador inválido no template: {erro}. Use só {', '.join(MARCADORES_TEMPLATE)}.") from erro
    anterior = template_vigente(db)
    anterior.ativo = False
    novo = TemplateDocumentoComercial(codigo=anterior.codigo, versao=anterior.versao + 1, corpo=corpo, ativo=True, criado_por=ator_id)
    db.add(novo)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "template_comercial_alterado", "template_documento_comercial",
                                novo.id, ator_id, {"versao": novo.versao, "motivo": motivo, "origem": "admin"})
    db.commit()
    return novo
