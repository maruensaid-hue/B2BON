"""Validação do modelo canônico pela prática (Fase 2, GATE "modelo validado").

O mesmo cálculo do MAP (economia de cliente, saúde de conta, funil) roda
sobre duas fontes: o CRM interno (`CrmInternoMapDataSource`) e o modelo
canônico via `B2BOnCrmAdapter` (`CanonicalMapDataSource`). Se o
mapeamento canônico perder ou distorcer algum dado relevante, os números
divergem.
"""

from datetime import UTC, datetime, timedelta

from app.contexts.crm import contract as crm_contract
from app.contexts.integrations.adapters.b2bon_crm import B2BOnCrmAdapter, cid
from app.contexts.map import contract as map_contract
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.interacao_conta import InteracaoConta
from app.models.pesquisa_nps import PesquisaNps
from app.services import crm_service

TENANT = "tenant-paridade"


def _cenario(db):
    agora = datetime.now(UTC)
    estagios = {e.tipo: e for e in crm_service.garantir_estagios_padrao(db, TENANT)}
    contas = []
    for i, (valor, destino) in enumerate([(1000.0, "ganho"), (2500.0, "ganho"), (800.0, "aberto"), (400.0, "perdido")]):
        conta = Conta(tenant_id=TENANT, nome=f"Conta {i}", status="prospectada", criado_em=agora - timedelta(days=40))
        db.add(conta)
        db.commit()
        decisor = Decisor(tenant_id=TENANT, conta_id=conta.id, nome=f"D{i}")
        db.add(decisor)
        db.commit()
        negocio = crm_service.criar_negocio(db, TENANT, None, conta.id, decisor.id, f"N{i}", valor=valor)
        if destino == "ganho":
            crm_service.mover_estagio(db, TENANT, None, negocio.id, estagios["ganho"].id)
        elif destino == "perdido":
            crm_service.mover_estagio(db, TENANT, None, negocio.id, estagios["perdido"].id, motivo_perda="preço")
        db.add(PesquisaNps(tenant_id=TENANT, conta_id=conta.id, decisor_id=decisor.id, marco="m", nota=6 + i, enviada_em=agora))
        contas.append(conta)
    db.add(InteracaoConta(tenant_id=TENANT, conta_id=contas[0].id, tipo="reclamacao", criado_em=agora - timedelta(days=2)))
    db.add(InteracaoConta(tenant_id=TENANT, conta_id=contas[0].id, tipo="mencionou_concorrente", criado_em=agora - timedelta(days=1)))
    db.add(InteracaoConta(tenant_id=TENANT, conta_id=contas[1].id, tipo="feedback_positivo", criado_em=agora - timedelta(days=3)))
    db.commit()
    periodo = agora.strftime("%Y-%m")
    crm_service.definir_custo_aquisicao(db, TENANT, None, periodo, 3000.0)
    return contas, periodo


def _fonte_canonica(db):
    return map_contract.CanonicalMapDataSource(
        B2BOnCrmAdapter(db), custo_aquisicao=lambda tenant_id, periodo: crm_contract.custo_aquisicao(db, tenant_id, periodo)
    )


def test_economia_do_map_e_identica_pelo_modelo_canonico(db_session):
    _, periodo = _cenario(db_session)

    interno = map_contract.economia(db_session, TENANT, periodo)
    canonico = map_contract.economia(db_session, TENANT, periodo, fonte=_fonte_canonica(db_session))

    assert interno["ltv_medio"] is not None and interno["cac"] is not None
    assert canonico == interno


def test_score_de_risco_por_conta_e_identico_pelo_modelo_canonico(db_session):
    contas, _ = _cenario(db_session)
    fonte = _fonte_canonica(db_session)
    refs = {ref.id: ref for ref in fonte.contas(TENANT)}

    for conta in contas:
        interno = map_contract.score_risco_conta(db_session, conta)
        canonico = map_contract.saude.score_risco(fonte, refs[cid("account", conta.id)])
        assert (canonico["score"], canonico["classificacao"], canonico["sinais"]) == (
            interno["score"], interno["classificacao"], interno["sinais"],
        ), conta.nome


def test_funil_pelo_modelo_canonico_tem_as_mesmas_contagens_e_valores(db_session):
    _cenario(db_session)
    interno = map_contract.funil(db_session, TENANT)
    canonico = map_contract.funil(db_session, TENANT, fonte=_fonte_canonica(db_session))

    def resumo(funil):
        return [(e["nome"], e["tipo"], e["quantidade"], e["valor_total"]) for e in funil["estagios"]]

    assert resumo(canonico) == resumo(interno)
    assert canonico["taxa_conversao"] == interno["taxa_conversao"]
