"""Poda diária dos históricos: remove o antigo, preserva o que o produto ainda usa e é idempotente."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models.coleta_fonte import ExecucaoColetaFonte
from app.models.coleta_site import ColetaSiteConta, IndicadorFinanceiroConta
from app.models.conta import Conta
from app.models.creditos_ia import CacheRespostaIa
from app.models.tenant import Tenant
from app.services import retencao_historicos_service as retencao

TENANT = "tenant-retencao"
AGORA = datetime(2026, 10, 20, 12, 0)


def _dias(n: int) -> datetime:
    return AGORA - timedelta(days=n)


@pytest.fixture()
def base(db_session):
    db_session.add(Tenant(id=TENANT, razao_social="Retenção"))
    conta = Conta(tenant_id=TENANT, nome="Alpha", dominio="alpha.com.br", status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def _coleta(db, conta, dias, estado="concluida", situacao=None, reprocesso_de=None, dominio="alpha.com.br") -> SimpleNamespace:
    c = ColetaSiteConta(tenant_id=TENANT, conta_id=conta.id, dominio=dominio, estado=estado, iniciada_em=_dias(dias), fontes=[], avisos=[],
                        dominio_evidencias=[], dominio_limitacoes=[], dominio_situacao=situacao, reprocesso_de_id=reprocesso_de)
    db.add(c)
    db.commit()
    return SimpleNamespace(id=c.id)  # só o id: a linha pode ser apagada pela poda e o objeto ORM ficaria inválido


def _execucao(db, dias, estado="concluida", tenant=TENANT) -> SimpleNamespace:
    e = ExecucaoColetaFonte(tenant_id=tenant, fonte="PNCP", estado=estado, iniciada_em=_dias(dias))
    db.add(e)
    db.commit()
    return SimpleNamespace(id=e.id)


def _ids(db, modelo, **filtro):
    db.expire_all()
    return sorted(i for (i,) in db.query(modelo.id).filter_by(**filtro))


# --- Cache de IA -------------------------------------------------------------------------------------------------------------------------


def test_cache_de_ia_vencido_e_apagado_e_o_valido_fica(db_session, base):
    for chave, expira in (("vencido", AGORA - timedelta(hours=1)), ("valido", AGORA + timedelta(hours=1))):
        db_session.add(CacheRespostaIa(chave=chave, tenant_id=TENANT, feature="f", modelo="m", conteudo="resposta", custo_original_usd=0,
                                       tokens_entrada=1, tokens_saida=1, hits=0, expira_em=expira))
    db_session.commit()

    resultado = retencao.podar(db_session, AGORA)

    assert resultado["cache_ia_expirado"] == 1
    assert [c.chave for c in db_session.query(CacheRespostaIa)] == ["valido"]


# --- Execuções da coleta de fonte pública ---------------------------------------------------------------------------------------------


def test_execucoes_antigas_saem_mas_a_ultima_concluida_que_guarda_o_cursor_nunca(db_session, base):
    velha_falha = _execucao(db_session, 200, "falhou")
    velha_concluida_1 = _execucao(db_session, 150, "concluida")
    ultima_concluida = _execucao(db_session, 120, "concluida")  # a mais recente concluída está FORA da retenção: mesmo assim fica
    nova_falha = _execucao(db_session, 10, "falhou")
    em_andamento_antiga = _execucao(db_session, 300, "em_andamento")

    resultado = retencao.podar(db_session, AGORA)

    assert resultado["execucoes_coleta_fonte"] == 2
    assert _ids(db_session, ExecucaoColetaFonte) == sorted([ultima_concluida.id, nova_falha.id, em_andamento_antiga.id])
    assert velha_falha.id not in _ids(db_session, ExecucaoColetaFonte) and velha_concluida_1.id not in _ids(db_session, ExecucaoColetaFonte)


def test_a_protecao_do_cursor_e_por_tenant_e_fonte(db_session, base):
    db_session.add(Tenant(id="outro-ret", razao_social="Outro"))
    db_session.commit()
    a = _execucao(db_session, 400, "concluida")
    b = _execucao(db_session, 400, "concluida", tenant="outro-ret")
    _execucao(db_session, 399, "falhou")

    retencao.podar(db_session, AGORA)

    assert {a.id, b.id} <= set(_ids(db_session, ExecucaoColetaFonte))  # cada tenant mantém a sua última concluída


# --- Coletas de site -------------------------------------------------------------------------------------------------------------------


def test_coletas_de_site_antigas_saem_com_os_indicadores_e_preservam_as_que_o_produto_usa(db_session, base):
    antiga_comum = _coleta(db_session, base, 400, "falhou")
    antiga_sucesso_substituida = _coleta(db_session, base, 380, "concluida")
    manual = _coleta(db_session, base, 300, "concluida", situacao="confirmado_manualmente")
    ultima_sucesso = _coleta(db_session, base, 250, "concluida_sem_ia")  # fora da retenção, mas é a última bem-sucedida: fica
    recente_falha = _coleta(db_session, base, 5, "falhou")  # a mais recente da conta: fica
    for coleta in (antiga_comum, antiga_sucesso_substituida, manual):
        db_session.add(IndicadorFinanceiroConta(tenant_id=TENANT, conta_id=base.id, coleta_id=coleta.id, nome="receita_liquida", tipo="publicado",
                                                valor=1.0, moeda="BRL", escala="unidade", valor_original="R$ 1", url_fonte="https://x", trecho="t",
                                                metodo_extracao="m", confianca="alta", origens=[]))
    db_session.commit()

    resultado = retencao.podar(db_session, AGORA)

    assert resultado["coletas_de_site"] == {"coletas": 2, "indicadores": 2}
    assert _ids(db_session, ColetaSiteConta) == sorted([manual.id, ultima_sucesso.id, recente_falha.id])
    assert [i.coleta_id for i in db_session.query(IndicadorFinanceiroConta)] == [manual.id]


def test_reprocesso_que_sobrevive_perde_a_ligacao_com_a_original_apagada_sem_violar_fk(db_session, base):
    original = _coleta(db_session, base, 400, "falhou")
    reprocesso_recente = _coleta(db_session, base, 3, "concluida", reprocesso_de=original.id)

    retencao.podar(db_session, AGORA)

    db_session.expire_all()
    assert db_session.get(ColetaSiteConta, original.id) is None
    assert db_session.get(ColetaSiteConta, reprocesso_recente.id).reprocesso_de_id is None


def test_em_andamento_nunca_e_podada_e_a_poda_e_idempotente(db_session, base):
    andamento = _coleta(db_session, base, 500, "em_andamento")
    _coleta(db_session, base, 10, "concluida")

    primeira = retencao.podar(db_session, AGORA)
    segunda = retencao.podar(db_session, AGORA)

    assert andamento.id in _ids(db_session, ColetaSiteConta)
    assert primeira["coletas_de_site"] == {"coletas": 0, "indicadores": 0} and segunda == primeira


def test_retencao_respeita_a_configuracao(db_session, base, monkeypatch):
    _coleta(db_session, base, 100, "falhou")
    _coleta(db_session, base, 50, "concluida")
    monkeypatch.setattr(settings, "retencao_coleta_site_dias", 30)

    assert retencao.podar(db_session, AGORA)["coletas_de_site"]["coletas"] == 1


def test_cada_conta_e_avaliada_separadamente(db_session, base):
    outra = Conta(tenant_id=TENANT, nome="Beta", dominio="beta.com.br", status="prospectada")
    db_session.add(outra)
    db_session.commit()
    unica_da_outra = _coleta(db_session, outra, 500, "concluida", dominio="beta.com.br")
    _coleta(db_session, base, 500, "falhou")
    _coleta(db_session, base, 2, "concluida")

    retencao.podar(db_session, AGORA)

    # a única coleta da conta Beta é a mais recente E a última bem-sucedida dela: nunca some só por ser antiga
    assert unica_da_outra.id in _ids(db_session, ColetaSiteConta)


def test_rota_de_cron_exige_segredo_e_executa(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "segredo-retencao")
    assert client.post("/api/v1/cron/podar-historicos").status_code == 403
    resposta = client.post("/api/v1/cron/podar-historicos", headers={"X-Cron-Secret": "segredo-retencao"})
    assert resposta.status_code == 200 and set(resposta.json()) == {"cache_ia_expirado", "execucoes_coleta_fonte", "coletas_de_site"}
