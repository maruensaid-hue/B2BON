"""Gerenciador de recursos de enriquecimento: cascata gratuita antes do provedor pago, cobrança de 1 crédito por decisor novo achado de graça,
cota técnica da fonte, cache por empresa, disjuntor e proteção contra cobrança dupla. Fontes SEMPRE simuladas: nenhuma chamada de rede real."""

from datetime import timedelta

import pytest

from app.contexts.enriquecimento import execucao, gerenciador, ledger
from app.contexts.enriquecimento.config import agora_utc
from app.core.config import settings
from app.models.decisor import Decisor
from app.models.enriquecimento_creditos import EnriquecimentoMovimento, PesquisaDecisoresEmpresa
from app.models.enriquecimento_fontes import EnriquecimentoConsulta, EnriquecimentoFonte
from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, ResultadoBuscaContatos
from app.providers.email_validation.dominio import DominioEmailVerificationProvider, TEM_MX
from tests.integration.test_pesquisa_decisores_governanca import (  # noqa: F401 — fixtures e auxiliares do teste de governança
    A,
    ProvedorPago,
    cenario,
    contas,
    eu,
    invariantes,
    ok,
)


class FonteGratuita(ContactEnrichmentProvider):
    """Duplo do Hunter: sem custo para o cliente, devolve o que o roteiro mandar (ou N pessoas) e mede 1 crédito do fornecedor por consulta."""

    nome_provedor = "hunter"
    pago = False
    max_contatos_por_consulta = 10

    def __init__(self, roteiro=None, pessoas=2):
        self.chamadas, self.roteiro, self.pessoas = [], list(roteiro or []), pessoas

    def buscar_contatos(self, filtro):  # pragma: no cover — só o caminho governado é usado
        raise AssertionError("caminho legado chamado")

    def buscar_contatos_governado(self, filtro):
        self.chamadas.append(filtro)
        if self.roteiro:
            proximo = self.roteiro.pop(0)
            if isinstance(proximo, Exception):
                raise proximo
            return proximo
        n = min(self.pessoas, filtro.limite_contatos or self.pessoas)
        contatos = [ContatoCandidato(nome=f"Gratis {filtro.nome_empresa} {i}", cargo="Diretor", email=f"g{i}@{filtro.dominio}", fonte="hunter",
                                     email_status="verificado") for i in range(n)]
        return ResultadoBuscaContatos(estado="ok" if contatos else "sem_resultados", contatos=contatos, creditos_provedor=1)


def erro(detalhe):
    return ResultadoBuscaContatos(estado="erro_seguro", detalhe=detalhe)


@pytest.fixture(autouse=True)
def dns_sem_rede(monkeypatch):
    """Nenhum teste consulta DNS de verdade: todo domínio recebe e-mail, a menos que o teste diga o contrário."""
    from app.providers.email_validation import dominio

    monkeypatch.setattr(dominio, "consultar_dns", lambda _dominio: TEM_MX)


@pytest.fixture()
def ligado(monkeypatch, db_session):
    """Gerenciador ligado e a fonte `hunter` ativa (o padrão de produção é desligado)."""
    monkeypatch.setattr(settings, "enriquecimento_gerenciador_ativo", True)
    gerenciador.garantir_padrao(db_session)
    fonte = db_session.query(EnriquecimentoFonte).filter_by(codigo="hunter").one()
    fonte.ativo = True
    db_session.commit()
    return fonte


def rodar_com(db, graph, solic, cs, pago, gratis, d=None, chave="chave-de-teste-1"):
    from tests.integration.test_pesquisa_decisores_governanca import confirmar, previa

    p = confirmar(db, solic, previa(db, solic, cs, pago, d), pago, chave)
    return execucao.executar(db, tenant_id=solic.tenant_id, pesquisa_id=p.id, provider=pago, graph=graph, ator_id=str(solic.id), gratuitos=gratis)


def movimentos(db, tipo=None):
    consulta = db.query(EnriquecimentoMovimento).filter_by(tenant_id=A)
    return consulta.filter_by(tipo=tipo).all() if tipo else consulta.all()


# ============================================================ desligado: nada muda ===================================================


def test_desligado_o_fluxo_e_o_de_sempre_e_a_fonte_gratuita_nao_e_chamada(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    pago, gratis = ProvedorPago(), FonteGratuita()

    p = rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])

    assert gratis.chamadas == [] and [f.limite_contatos for f in pago.chamadas] == [2]
    assert (p.estado, p.creditos_consumidos) == ("concluida", 2)
    assert db_session.query(EnriquecimentoConsulta).count() == 0
    invariantes(db_session)


# ============================================================ cascata: o cadastro vem primeiro ======================================


def test_decisores_ja_cadastrados_atendem_sem_chamar_ninguem_e_sem_cobrar(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    [conta] = contas(db_session, 1)
    for i in range(2):  # chegaram por importação/site: já fazem parte do cadastro do cliente
        db_session.add(Decisor(tenant_id=A, conta_id=conta.id, nome=f"Já Tenho {i}", cargo="CEO", email=f"j{i}@x.com.br", email_status="publicado", origem="site_institucional"))
    db_session.commit()
    pago, gratis = ProvedorPago(), FonteGratuita()

    p = rodar_com(db_session, fake_graph, eu(db_session), [conta], pago, [gratis])

    assert pago.chamadas == [] and gratis.chamadas == []
    assert (p.estado, p.creditos_consumidos, p.provedor_consumidos) == ("concluida", 0, 0)
    assert ledger.disponivel(db_session, A) == 10 and ledger.reservado(db_session, A) == 0  # a reserva inteira voltou
    assert movimentos(db_session, "CONSUMO") == []
    item = db_session.query(PesquisaDecisoresEmpresa).one()
    assert (item.estado, item.decisores_retornados) == ("concluido", 2)
    invariantes(db_session)


def test_email_deduzido_do_cadastro_nao_conta_como_decisor_valido(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    [conta] = contas(db_session, 1)
    db_session.add(Decisor(tenant_id=A, conta_id=conta.id, nome="Deduzido", cargo="CEO", email="d@x.com.br", email_status="inferido", origem="site_institucional"))
    db_session.commit()
    pago = ProvedorPago()

    rodar_com(db_session, fake_graph, eu(db_session), [conta], pago, [])

    assert [f.limite_contatos for f in pago.chamadas] == [2]  # o palpite não reduz a necessidade


# ============================================================ cobrança do que a fonte gratuita achou ================================


def test_decisores_novos_de_fonte_gratuita_custam_um_credito_cada_e_o_pago_nao_e_chamado(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    pago, gratis = ProvedorPago(), FonteGratuita(pessoas=2)

    p = rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])

    assert pago.chamadas == [] and len(gratis.chamadas) == 1
    assert (p.estado, p.creditos_consumidos, p.provedor_consumidos) == ("concluida", 2, 0)
    assert ledger.disponivel(db_session, A) == 8 and ledger.reservado(db_session, A) == 0
    [consumo] = movimentos(db_session, "CONSUMO")
    assert (consumo.delta_saldo, consumo.origem, consumo.provedor_delta_consumido) == (-2, "fonte_gratuita", 0)
    assert str(consumo.custo_total_brl) == "0" or float(consumo.custo_total_brl) == 0.0  # a fonte não custou nada: o custo de aquisição é zero
    assert float(consumo.valor_venda_brl) > 0  # mas o crédito do cliente foi consumido e tem valor de venda
    assert db_session.query(Decisor).filter_by(tenant_id=A, origem="hunter").count() == 2
    invariantes(db_session)


def test_resultado_parcial_cobra_o_gratuito_e_o_pago_so_busca_o_que_faltou(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    pago = ProvedorPago([ok(1, prefixo="Pago")])
    gratis = FonteGratuita(pessoas=1)

    p = rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])

    assert [f.limite_contatos for f in pago.chamadas] == [1]  # pediu 2, a gratuita cobriu 1
    assert (p.estado, p.creditos_consumidos, p.provedor_consumidos) == ("concluida", 2, 1)  # 1 do gratuito + 1 medido do pago
    assert ledger.disponivel(db_session, A) == 8
    item = db_session.query(PesquisaDecisoresEmpresa).one()
    assert (item.creditos_consumidos, item.decisores_retornados) == (2, 2)
    invariantes(db_session)


def test_so_o_decisor_novo_e_cobrado_quem_ja_existia_com_o_mesmo_nome_nao(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    [conta] = contas(db_session, 1)
    db_session.add(Decisor(tenant_id=A, conta_id=conta.id, nome=f"Gratis {conta.nome} 0", cargo="Diretor", email=None, origem="qsa_receita_federal"))
    db_session.commit()
    pago, gratis = ProvedorPago([ok(1, prefixo="Pago")]), FonteGratuita(pessoas=2)

    p = rodar_com(db_session, fake_graph, eu(db_session), [conta], pago, [gratis])

    # A fonte devolveu 2: um já estava no cadastro (só ganha o e-mail que faltava) e não é cobrado; o outro é novo e custa 1.
    assert db_session.query(EnriquecimentoConsulta).filter_by(fonte="hunter", estado="ok").one().novos == 1
    assert movimentos(db_session, "CONSUMO")[0].delta_saldo == -1
    assert p.estado == "concluida"
    invariantes(db_session)


def test_cobranca_nunca_e_dupla_a_mesma_empresa_nao_e_cobrada_duas_vezes(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    solic, [conta] = eu(db_session), contas(db_session, 1)
    pago, gratis = ProvedorPago(), FonteGratuita(pessoas=2)
    p = rodar_com(db_session, fake_graph, solic, [conta], pago, [gratis])
    item = db_session.query(PesquisaDecisoresEmpresa).one()

    # Repetição da etapa para a MESMA empresa (retentativa, reprocessamento): não cobra, não mexe na reserva, não consulta de novo.
    reservado_antes = item.provedor_reservados
    repetida = execucao._etapa_gratuita(db_session, p, item, conta, execucao.obter_politica(db_session, p.politica_id), fake_graph, None, agora_utc(), [gratis])

    assert repetida is None and len(gratis.chamadas) == 1
    assert item.provedor_reservados == reservado_antes
    assert len(movimentos(db_session, "CONSUMO")) == 1 and ledger.disponivel(db_session, A) == 8


def test_segunda_pesquisa_da_mesma_empresa_usa_o_cadastro_e_nao_cobra_de_novo(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    solic, [conta] = eu(db_session), contas(db_session, 1)
    pago, gratis = ProvedorPago(), FonteGratuita(pessoas=2)
    rodar_com(db_session, fake_graph, solic, [conta], pago, [gratis], chave="chave-de-teste-1")
    assert ledger.disponivel(db_session, A) == 8

    segunda = rodar_com(db_session, fake_graph, solic, [conta], pago, [gratis], chave="chave-de-teste-2")

    assert len(gratis.chamadas) == 1 and pago.chamadas == []  # mesma empresa, mesmo cliente: já é dele
    assert segunda.creditos_consumidos == 0 and ledger.disponivel(db_session, A) == 8  # 0 crédito (regra: mesmo tenant + empresa + decisor válido)
    invariantes(db_session)


def test_fator_de_conversao_diferente_de_1_desliga_a_etapa_e_o_fluxo_e_o_de_sempre(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=20, fator=2)
    pago, gratis = ProvedorPago(), FonteGratuita()

    p = rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])

    assert gratis.chamadas == [] and [f.limite_contatos for f in pago.chamadas] == [2]
    assert p.creditos_consumidos == 4  # 2 créditos do provedor × fator 2
    invariantes(db_session)


# ============================================================ filtros de qualidade ==================================================


def test_email_deduzido_e_dominio_inexistente_vindos_da_fonte_nao_viram_decisor_nem_sao_cobrados(client, db_session, fake_graph, ligado, monkeypatch):
    monkeypatch.setattr(gerenciador, "DominioEmailVerificationProvider",
                        lambda: DominioEmailVerificationProvider(lambda dominio: "inexistente" if dominio.startswith("morto") else TEM_MX))
    cenario(db_session, franquia=10)
    [conta] = contas(db_session, 1)
    candidatos = [
        ContatoCandidato(nome="Palpite", cargo="CEO", email=f"p@{conta.dominio}", fonte="hunter", email_status="inferido"),
        ContatoCandidato(nome="Domínio Morto", cargo="CEO", email="x@morto.com.br", fonte="hunter", email_status="publicado"),
        ContatoCandidato(nome="Sem Cargo", cargo="", email=f"s@{conta.dominio}", fonte="hunter", email_status="publicado"),
        ContatoCandidato(nome="Boa Pessoa", cargo="CFO", email=f"b@{conta.dominio}", fonte="hunter", email_status="verificado"),
    ]
    gratis = FonteGratuita([ResultadoBuscaContatos(estado="ok", contatos=candidatos, creditos_provedor=1)])
    pago = ProvedorPago([ok(1, prefixo="Pago")])

    rodar_com(db_session, fake_graph, eu(db_session), [conta], pago, [gratis])

    assert [d.nome for d in db_session.query(Decisor).filter_by(tenant_id=A, origem="hunter").all()] == ["Boa Pessoa"]
    assert movimentos(db_session, "CONSUMO")[0].delta_saldo == -1  # só 1 válido


def test_pesquisa_que_pede_telefone_nao_usa_fonte_que_nao_entrega_telefone(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=30, email=1, telefone=5, revelar_telefones=True)
    pago, gratis = ProvedorPago([ok(2)]), FonteGratuita()

    from tests.integration.test_pesquisa_decisores_governanca import confirmar, previa

    solic = eu(db_session)
    p = confirmar(db_session, solic, previa(db_session, solic, contas(db_session, 1), pago, revelar_telefones=True), pago)
    execucao.executar(db_session, tenant_id=A, pesquisa_id=p.id, provider=pago, graph=fake_graph, ator_id=str(solic.id), gratuitos=[gratis])

    assert gratis.chamadas == [] and len(pago.chamadas) == 1
    assert db_session.query(EnriquecimentoConsulta).filter_by(fonte="hunter").one().motivo == "exige_telefone"


# ============================================================ cota técnica, cache e disjuntor =======================================


def test_cota_esgotada_pula_a_fonte_e_o_pago_cobre_tudo(client, db_session, fake_graph, ligado):
    ligado.limite_mensal, ligado.consumido_periodo, ligado.periodo = 50, 50, agora_utc().strftime("%Y-%m")
    db_session.commit()
    cenario(db_session, franquia=10)
    pago, gratis = ProvedorPago(), FonteGratuita()

    p = rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])

    assert gratis.chamadas == [] and [f.limite_contatos for f in pago.chamadas] == [2] and p.creditos_consumidos == 2
    assert db_session.query(EnriquecimentoConsulta).filter_by(fonte="hunter").one().motivo == "cota_esgotada"


def test_a_cota_conta_o_consumo_informado_pelo_fornecedor_e_zera_no_mes_seguinte(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago(), [FonteGratuita()])
    db_session.refresh(ligado)
    assert ligado.consumido_periodo == 1  # reservou 1 e o fornecedor informou 1

    mes_que_vem = agora_utc() + timedelta(days=40)
    assert gerenciador.fonte_liberada(db_session, ligado, mes_que_vem) is None
    assert ligado.consumido_periodo == 0 and ligado.periodo == mes_que_vem.strftime("%Y-%m")


def test_reserva_de_cota_nunca_passa_do_limite(client, db_session, ligado):
    ligado.limite_mensal, ligado.consumido_periodo, ligado.periodo = 2, 0, agora_utc().strftime("%Y-%m")
    db_session.commit()
    agora = agora_utc()

    assert [gerenciador.reservar_cota(db_session, ligado, 1, agora) for _ in range(3)] == [True, True, False]
    assert ligado.consumido_periodo == 2


def test_cache_por_empresa_e_por_tenant_e_vence(client, db_session, ligado):
    agora = agora_utc()
    [conta] = contas(db_session, 1)
    gerenciador.registrar_consulta(db_session, A, conta.id, "hunter", "freemium", "sem_resultados", agora=agora)

    assert gerenciador.consulta_valida_recente(db_session, A, conta.id, "hunter", agora) is True
    assert gerenciador.consulta_valida_recente(db_session, "tenant-outro", conta.id, "hunter", agora) is False  # o cache não atravessa tenants
    assert gerenciador.consulta_valida_recente(db_session, A, conta.id, "hunter", agora + timedelta(days=settings.enriquecimento_cache_dias + 1)) is False


def test_erro_nao_vale_como_cache_e_a_fonte_e_consultada_de_novo(client, db_session, ligado):
    agora = agora_utc()
    [conta] = contas(db_session, 1)
    gerenciador.registrar_consulta(db_session, A, conta.id, "hunter", "freemium", "erro", motivo="hunter_http_502", agora=agora)

    assert gerenciador.consulta_valida_recente(db_session, A, conta.id, "hunter", agora) is False


def test_tres_falhas_seguidas_abrem_o_disjuntor_e_um_sucesso_o_fecha(client, db_session, ligado):
    agora = agora_utc()
    for _ in range(gerenciador.FALHAS_PARA_ABRIR_DISJUNTOR):
        gerenciador._registrar_resultado_na_fonte(db_session, ligado, "erro", "hunter_http_502", agora)

    assert ligado.suspensa_ate is not None and gerenciador.fonte_liberada(db_session, ligado, agora) == "suspensa"
    assert gerenciador.fonte_liberada(db_session, ligado, agora + gerenciador.SUSPENSAO_POR_FALHAS + timedelta(seconds=1)) is None
    gerenciador._registrar_resultado_na_fonte(db_session, ligado, "ok", None, agora)
    assert (ligado.falhas_seguidas, ligado.suspensa_ate) == (0, None)


@pytest.mark.parametrize(("detalhe", "dias_minimos"), [("hunter_chave_invalida", 1), ("hunter_sem_creditos", 1)])
def test_chave_recusada_ou_saldo_acabado_suspendem_de_imediato(client, db_session, ligado, detalhe, dias_minimos):
    agora = agora_utc()

    gerenciador._registrar_resultado_na_fonte(db_session, ligado, "erro", detalhe, agora)

    assert ligado.suspensa_ate is not None and ligado.suspensa_ate - agora >= timedelta(hours=1)


def test_falha_da_fonte_gratuita_nunca_derruba_a_pesquisa_paga(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    pago = ProvedorPago()
    gratis = FonteGratuita([RuntimeError("fornecedor fora do ar")])

    p = rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])

    assert (p.estado, p.creditos_consumidos) == ("concluida", 2) and [f.limite_contatos for f in pago.chamadas] == [2]
    consulta = db_session.query(EnriquecimentoConsulta).filter_by(fonte="hunter").one()
    assert (consulta.estado, consulta.motivo) == ("erro", "excecao_no_adaptador")
    invariantes(db_session)


def test_chave_invalida_vira_erro_registrado_suspende_e_o_pago_assume(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=10)
    pago, gratis = ProvedorPago(), FonteGratuita([erro("hunter_chave_invalida")])

    p = rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])

    assert p.creditos_consumidos == 2 and [f.limite_contatos for f in pago.chamadas] == [2]
    db_session.refresh(ligado)
    assert ligado.suspensa_ate is not None


def test_fonte_desativada_ou_sem_uso_comercial_confirmado_nao_e_consultada(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=20)
    ligado.permite_uso_comercial = False  # o administrador conferiu os termos do fornecedor e o uso comercial não é permitido
    db_session.commit()
    pago, gratis = ProvedorPago(), FonteGratuita()

    rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), pago, [gratis])
    assert gratis.chamadas == []
    assert db_session.query(EnriquecimentoConsulta).filter_by(fonte="hunter").one().motivo == "uso_comercial_nao_permitido"

    ligado.permite_uso_comercial, ligado.ativo = None, False
    db_session.commit()
    rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago(), [gratis], chave="chave-de-teste-2")
    assert gratis.chamadas == []


def test_garantir_padrao_e_idempotente_e_a_fonte_paga_nasce_desligada(client, db_session):
    gerenciador.garantir_padrao(db_session)
    gerenciador.garantir_padrao(db_session)

    fontes = {f.codigo: f for f in db_session.query(EnriquecimentoFonte).all()}
    assert set(fontes) == {"banco", "hunter"}
    assert fontes["hunter"].ativo is False and fontes["hunter"].limite_mensal == 50 and fontes["hunter"].permite_uso_comercial is None
    assert fontes["banco"].ativo is True


def test_sem_chave_configurada_nao_ha_fonte_externa_e_a_lista_fica_vazia(monkeypatch):
    monkeypatch.setattr(settings, "hunter_api_key", "")
    assert gerenciador.provedores_gratuitos() == []

    monkeypatch.setattr(settings, "hunter_api_key", "chave-de-teste")
    assert [p.nome_provedor for p in gerenciador.provedores_gratuitos()] == ["hunter"]


# ============================================================ indicadores e área administrativa =====================================

ADMIN = "/api/v1/admin/enriquecimento"


def test_indicadores_sem_historico_nao_inventam_numero(client, db_session, ligado):
    visao = client.get(f"{ADMIN}/recursos").json()

    assert visao["FREE_RESOURCE_UTILIZATION_RATE"] is None and visao["decisores_entregues"]["total"] == 0
    custo_evitado = visao["PAID_PROVIDER_COST_AVOIDED"]
    assert custo_evitado["valor_brl"] is None and custo_evitado["motivo_sem_valor"] == "nenhum_decisor_atendido_por_fonte_gratuita_no_periodo"
    assert {f["codigo"] for f in visao["fontes"]} == {"banco", "hunter"}


def test_indicadores_calculam_taxa_e_custo_evitado_com_a_media_historica_medida(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=20)
    solic = eu(db_session)
    # 1) só o pago: 2 decisores, 2 créditos medidos => média histórica de 1 crédito por decisor.
    rodar_com(db_session, fake_graph, solic, contas(db_session, 1), ProvedorPago(), [], chave="chave-de-teste-1")
    # 2) só a fonte gratuita: 2 decisores entregues sem o pago.
    rodar_com(db_session, fake_graph, solic, contas(db_session, 1), ProvedorPago(), [FonteGratuita(pessoas=2)], chave="chave-de-teste-2")

    visao = client.get(f"{ADMIN}/recursos").json()

    assert visao["decisores_entregues"] == {"total": 4, "por_fonte_gratuita": 2, "por_provedor_pago": 2}
    assert visao["FREE_RESOURCE_UTILIZATION_RATE"] == 0.5
    evitado = visao["PAID_PROVIDER_COST_AVOIDED"]
    assert evitado["estimativa"] is True and evitado["media_historica_creditos_por_decisor"] == "1.0000" and evitado["creditos_do_provedor_evitados"] == "2.00"
    assert float(evitado["valor_brl"]) == pytest.approx(2 * 0.67485, abs=0.01)  # 2 créditos × custo unitário da política de teste (R$ 0,67485)
    hunter = next(f for f in visao["desempenho_por_fonte"] if f["fonte"] == "hunter")
    assert (hunter["consultas"], hunter["ok"], hunter["novos"], hunter["taxa_sucesso"]) == (1, 1, 2, 1.0)
    assert next(f for f in visao["fontes"] if f["codigo"] == "hunter")["restante_periodo"] == 49


def test_indicadores_nunca_citam_nome_de_fornecedor_de_contatos(client, db_session, fake_graph, ligado):
    cenario(db_session, franquia=20)
    rodar_com(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago(), [])

    texto = str(client.get(f"{ADMIN}/recursos").json()).lower()

    assert "lusha" not in texto


def test_area_de_recursos_so_para_super_admin_e_ligar_fonte_externa_exige_decisao_sobre_uso_comercial(client, db_session, criar_usuario_autenticado):
    comum = criar_usuario_autenticado(A, papel="admin", email="adm-recursos@x.com.br")
    assert client.get(f"{ADMIN}/recursos", headers=comum).status_code == 403
    assert client.put(f"{ADMIN}/recursos/hunter", json={"ativo": True, "motivo": "teste"}, headers=comum).status_code == 403

    recusado = client.put(f"{ADMIN}/recursos/hunter", json={"ativo": True, "motivo": "ligar sem conferir os termos"})
    assert recusado.status_code in (400, 422) and "uso comercial" in str(recusado.json()).lower()
    assert db_session.query(EnriquecimentoFonte).filter_by(codigo="hunter").one().ativo is False

    liberado = client.put(f"{ADMIN}/recursos/hunter", json={"permite_uso_comercial": True, "ativo": True, "motivo": "fornecedor confirmou por escrito"})
    assert liberado.status_code == 200 and liberado.json()["ativo"] is True
    assert client.put(f"{ADMIN}/recursos/inexistente", json={"ativo": False, "motivo": "x x x"}).status_code in (400, 404, 422)
