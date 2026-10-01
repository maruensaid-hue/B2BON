"""B2B ON Government (D-072). Operação comercial (contratos, recebimentos, comissões, pipeline, métricas):
só super_admin. O cliente vê o próprio contrato em `/governo/meu-contrato`, sem comissões."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id
from app.contexts.governo import contract as governo
from app.schemas.governo import (
    ComponenteAdicionalSchema,
    CriarContratoGovernoSchema,
    MotivoSchema,
    OportunidadeGovernoSchema,
    OverrideComissaoSchema,
    PoliticaComissaoSchema,
    PropostaGovernoSchema,
    RecebimentoGovernoSchema,
    RenovarContratoGovernoSchema,
    TemplateComercialSchema,
    TransferenciaComissaoSchema,
)
from app.models.contrato_governo import ContratoGoverno

router = APIRouter(prefix="/governo", tags=["governo"])
admin = APIRouter(prefix="/governo", tags=["governo"], dependencies=[Depends(exigir_papel("super_admin"))])


@router.get("/meu-contrato")
def meu_contrato(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return {"contrato": governo.contratos.do_tenant(db, tenant_id)}


@admin.get("/planos")
def planos(db: Session = Depends(get_db)) -> list[dict]:
    return [governo.ofertas.oferta(p) for p in governo.ofertas.planos(db)]


@admin.post("/planos/{plano_id}/proposta")
def proposta(plano_id: int, dados: PropostaGovernoSchema, db: Session = Depends(get_db)) -> dict:
    valores = {k: v for k, v in (dados.valores.model_dump() if dados.valores else {}).items() if v is not None}
    return governo.ofertas.proposta(db, governo.ofertas.obter_plano(db, plano_id), dados.entidade_governamental, dados.referencia, valores)


@admin.get("/politica-comissao")
def politica(db: Session = Depends(get_db)) -> dict:
    vigente = governo.politicas.politica_vigente(db)
    db.commit()
    return {"versao": vigente.versao, "regras": vigente.regras, "motivo": vigente.motivo}


@admin.post("/politica-comissao", status_code=201)
def nova_politica(dados: PoliticaComissaoSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    nova = governo.politicas.nova_politica(db, dados.regras, dados.motivo, ator_id)
    return {"versao": nova.versao, "regras": nova.regras}


@admin.get("/template-proposta")
def template(db: Session = Depends(get_db)) -> dict:
    vigente = governo.politicas.template_vigente(db)
    db.commit()
    return {"versao": vigente.versao, "corpo": vigente.corpo, "marcadores": list(governo.tipos.MARCADORES_TEMPLATE)}


@admin.post("/template-proposta", status_code=201)
def novo_template(dados: TemplateComercialSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    novo = governo.politicas.novo_template(db, dados.corpo, dados.motivo, ator_id)
    return {"versao": novo.versao, "corpo": novo.corpo}


@admin.get("/oportunidades")
def oportunidades(db: Session = Depends(get_db)) -> dict:
    return {"estagios": list(governo.tipos.ESTAGIOS), "itens": governo.pipeline.listar(db), "resumo": governo.pipeline.resumo(db)}


@admin.post("/oportunidades", status_code=201)
def criar_oportunidade(dados: OportunidadeGovernoSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return governo.pipeline.oportunidade_dict(db, governo.pipeline.criar(db, dados.model_dump(exclude_none=True), ator_id))


@admin.patch("/oportunidades/{oportunidade_id}")
def atualizar_oportunidade(oportunidade_id: int, dados: OportunidadeGovernoSchema, ator_id: str | None = Depends(get_ator_id),
                           db: Session = Depends(get_db)) -> dict:
    return governo.pipeline.oportunidade_dict(db, governo.pipeline.atualizar(db, oportunidade_id, dados.model_dump(exclude_none=True), ator_id))


@admin.get("/contratos")
def contratos(db: Session = Depends(get_db)) -> list[dict]:
    return [governo.contratos.resumo(db, c, com_comissoes=True)
            for c in db.query(ContratoGoverno).order_by(ContratoGoverno.assinado_em.desc(), ContratoGoverno.id.desc()).all()]


@admin.post("/contratos", status_code=201)
def criar_contrato(dados: CriarContratoGovernoSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    valores = {k: v for k, v in (dados.valores.model_dump() if dados.valores else {}).items() if v is not None}
    contrato = governo.contratos.criar(
        db, tenant_id=dados.tenant_id, plano_id=dados.plano_id, modelo=dados.modelo_cobranca, referencia_contrato=dados.referencia_contrato,
        entidade_governamental=dados.entidade_governamental, assinado_em=dados.assinado_em, inicio=dados.inicio,
        representante_id=dados.representante_id, divisao_comissao=[d.model_dump() for d in dados.divisao_comissao or []] or None,
        oportunidade_id=dados.oportunidade_id, valores=valores, motivo_valores=dados.motivo_valores, regra_reajuste=dados.regra_reajuste,
        ator_id=ator_id,
    )
    return governo.contratos.resumo(db, contrato, com_comissoes=True)


@admin.get("/contratos/{contrato_id}")
def contrato(contrato_id: int, db: Session = Depends(get_db)) -> dict:
    return governo.contratos.resumo(db, governo.contratos.obter(db, contrato_id), com_comissoes=True)


@admin.post("/contratos/{contrato_id}/renovacoes", status_code=201)
def renovar(contrato_id: int, dados: RenovarContratoGovernoSchema, ator_id: str | None = Depends(get_ator_id),
            db: Session = Depends(get_db)) -> dict:
    governo.contratos.renovar(db, contrato_id, valor_assinatura=dados.valor_assinatura, motivo_reajuste=dados.motivo_reajuste, ator_id=ator_id)
    return governo.contratos.resumo(db, governo.contratos.obter(db, contrato_id), com_comissoes=True)


@admin.post("/contratos/{contrato_id}/componentes", status_code=201)
def adicionar_componente(contrato_id: int, dados: ComponenteAdicionalSchema, ator_id: str | None = Depends(get_ator_id),
                         db: Session = Depends(get_db)) -> dict:
    governo.contratos.adicionar_componente(db, contrato_id, tipo=dados.tipo, valor=dados.valor, descricao=dados.descricao,
                                           creditos=dados.creditos, tipo_receita=dados.tipo_receita, ator_id=ator_id)
    return governo.contratos.resumo(db, governo.contratos.obter(db, contrato_id), com_comissoes=True)


@admin.post("/contratos/{contrato_id}/cancelamento")
def cancelar(contrato_id: int, dados: MotivoSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return governo.contratos.resumo(db, governo.contratos.cancelar(db, contrato_id, dados.motivo, ator_id), com_comissoes=True)


@admin.get("/contratos/{contrato_id}/recebimentos")
def recebimentos(contrato_id: int, db: Session = Depends(get_db)) -> list[dict]:
    governo.contratos.obter(db, contrato_id)
    return governo.recebimentos.listar(db, contrato_id)


@admin.post("/contratos/{contrato_id}/recebimentos", status_code=201)
def registrar_recebimento(contrato_id: int, dados: RecebimentoGovernoSchema, ator_id: str | None = Depends(get_ator_id),
                          db: Session = Depends(get_db)) -> dict:
    recebimento = governo.recebimentos.registrar(db, contrato_id, componente_id=dados.componente_id, valor=dados.valor,
                                                 recebido_em=dados.recebido_em, referencia=dados.referencia,
                                                 idempotency_key=dados.idempotency_key, ator_id=ator_id)
    return {"id": recebimento.id, "valor": float(recebimento.valor), "comissoes": governo.comissoes.listar(db, contrato_id)}


@admin.post("/recebimentos/{recebimento_id}/estorno")
def estornar(recebimento_id: int, dados: MotivoSchema, ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return governo.recebimentos.estornar(db, recebimento_id, dados.motivo, ator_id)


@admin.get("/comissoes")
def comissoes(contrato_id: int | None = None, representante_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    return governo.comissoes.listar(db, contrato_id, representante_id)


@admin.patch("/componentes/{componente_id}/comissao")
def override_comissao(componente_id: int, dados: OverrideComissaoSchema, ator_id: str | None = Depends(get_ator_id),
                      db: Session = Depends(get_db)) -> dict:
    componente = governo.comissoes.alterar_componente(db, componente_id, comissionavel=dados.comissionavel, taxa=dados.taxa,
                                                      motivo=dados.motivo, aprovado_por=dados.aprovado_por, ator_id=ator_id)
    return {"id": componente.id, "comissionavel": componente.comissionavel, "taxa_comissao": componente.taxa_comissao}


@admin.post("/contratos/{contrato_id}/transferencia-comissao")
def transferir(contrato_id: int, dados: TransferenciaComissaoSchema, ator_id: str | None = Depends(get_ator_id),
               db: Session = Depends(get_db)) -> dict:
    contrato = governo.comissoes.transferir(db, contrato_id, representante_id=dados.representante_id,
                                            divisao=[d.model_dump() for d in dados.divisao or []] or None, motivo=dados.motivo,
                                            aprovado_por=dados.aprovado_por, ator_id=ator_id)
    return governo.contratos.resumo(db, contrato, com_comissoes=True)


@admin.get("/metricas")
def metricas(inicio: date | None = None, fim: date | None = None, db: Session = Depends(get_db)) -> dict:
    return governo.analytics.metricas(db, inicio, fim)


@admin.get("/tenants/{tenant_id}/margem-contribuicao")
def margem(tenant_id: str, inicio: date, fim: date, db: Session = Depends(get_db)) -> dict:
    return governo.analytics.margem_contribuicao(db, tenant_id, inicio, fim)
