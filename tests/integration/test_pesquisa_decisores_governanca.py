"""Governança de créditos de enriquecimento: configuração e política aprovadas, seleção explícita, decisores por empresa, estimativa e confirmação,
reserva atômica e idempotente, consumo MEDIDO pelo provedor, custo/markup/preço, falhas/ambiguidade/reconciliação, deduplicação, orçamento global,
separação IA × enriquecimento, QSA sem Lusha, isolamento de tenant e permissões. Provedor sempre simulado: nenhuma chamada real, nenhum orçamento real."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.api.deps import get_contact_enrichment_provider
from app.contexts.enriquecimento import conciliacao, config, custo, execucao, ledger, painel, pesquisa, precos
from app.contexts.enriquecimento.pesquisa import Solicitante
from app.core.config import settings
from app.main import app
from app.models.carteira_creditos import CarteiraCreditos, MovimentoCredito
from app.models.conta import Conta
from app.models.creditos_ia import ExecucaoIa, LoteCreditos
from app.models.decisor import Decisor
from app.models.enriquecimento_creditos import (
    EnriquecimentoLoteCompra,
    EnriquecimentoMovimento,
    EnriquecimentoUsoProvedor,
    PesquisaDecisores,
    PesquisaDecisoresEmpresa,
)
from app.models.plano import Plano
from app.models.usuario import Usuario
from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, ResultadoBuscaContatos, UsoProvedor
from app.services.errors import NaoEncontrado, PesquisaBloqueada, ValidacaoFalhou

A, B = "tenant-teste", "tenant-outro"
URL = "/api/v1/pesquisas-decisores"
ADMIN = "/api/v1/admin/enriquecimento"


class ProvedorPago(ContactEnrichmentProvider):
    """Duplo do provedor com custo. Sem roteiro, revela `limite_contatos` por empresa e MEDE `custo_busca + n × custo_por_contato` créditos."""

    nome_provedor = "lusha"
    pago = True
    max_contatos_por_consulta = 100
    tamanho_pagina_minimo = 10

    def __init__(self, roteiro=None, *, custo_busca=0, custo_por_contato=1, uso=None):
        self.chamadas = []
        self.roteiro = list(roteiro or [])
        self.custo_busca, self.custo_por_contato = custo_busca, custo_por_contato
        self.uso = uso

    def buscar_contatos(self, filtro):  # o caminho legado nunca pode ser usado por uma pesquisa governada
        raise AssertionError("caminho legado chamado")

    def buscar_contatos_governado(self, filtro):
        self.chamadas.append(filtro)
        if self.roteiro:
            proximo = self.roteiro.pop(0)
            if isinstance(proximo, Exception):
                raise proximo
            return proximo
        n = filtro.limite_contatos
        return ResultadoBuscaContatos(
            estado="ok", ids_provedor=[f"id{i}" for i in range(n)], creditos_busca=self.custo_busca, creditos_revelacao=n * self.custo_por_contato,
            creditos_provedor=self.custo_busca + n * self.custo_por_contato,
            contatos=[ContatoCandidato(nome=f"{filtro.nome_empresa} Pessoa {i}", cargo="CEO", email=f"p{i}@{filtro.dominio}", fonte="lusha") for i in range(n)],
        )

    def consultar_uso(self):
        if self.uso is None:
            raise NotImplementedError
        return self.uso


def ok(n, medido=None, prefixo="Fulano"):
    """n contatos revelados; `medido` = créditos do provedor informados na resposta (padrão: n, como na política de teste)."""
    return ResultadoBuscaContatos(estado="ok", ids_provedor=[f"i{k}" for k in range(n)], creditos_provedor=n if medido is None else medido,
                                  contatos=[ContatoCandidato(nome=f"{prefixo} {k}", cargo="CEO", fonte="lusha") for k in range(n)])


def erro_seguro(cobrado_pela_busca=None):
    return ResultadoBuscaContatos(estado="erro_seguro", detalhe="revelacao_rejeitada", creditos_provedor=cobrado_pela_busca)


def ambiguo():
    return ResultadoBuscaContatos(estado="ambiguo", detalhe="revelacao_timeout", ids_provedor=["x1"], creditos_busca=0)


def sem_resultados(medido=0):
    return ResultadoBuscaContatos(estado="sem_resultados", creditos_provedor=medido)


def plano_id(db):
    return db.query(Plano).filter_by(nome="Plano Padrão Teste").one().id


def lote(db, referencia="APORTE-TESTE-1", quantidade=400, custo="269.94"):
    existente = db.query(EnriquecimentoLoteCompra).filter_by(provedor="lusha", referencia=referencia).one_or_none()
    return existente or config.registrar_lote_compra(db, provedor="lusha", referencia=referencia, quantidade_creditos=quantidade,
                                                     custo_total_brl=Decimal(custo), comprado_em=datetime(2026, 10, 21), ator_id="1", tenant_auditoria=A)


def politica(db, *, busca=0, email=1, telefone=None, revelar_telefones=False, pagina=10, fator=1, markup="100", aprovar=True, metodo="lote_referencia"):
    return config.definir_politica(
        db, provedor="lusha", creditos_busca_por_resultado=busca, creditos_email=email, creditos_telefone=telefone, revelar_emails=True,
        revelar_telefones=revelar_telefones, tamanho_pagina_busca=pagina, creditos_cliente_por_credito_provedor=fator, markup_percentual=Decimal(markup),
        metodo_custo=metodo, lote_compra_id=lote(db).id if metodo == "lote_referencia" else None, casas_exibicao=2, fonte_tarifas="manual",
        ator_id="1", tenant_auditoria=A, motivo="teste", tamanho_pagina_minimo=10, tamanho_pagina_maximo=100, aprovar=aprovar)


def custo_contratual(db, provedor="lusha", *, aprovar=True):
    """Custo contratual (USD 600/mês, 81.600 créditos/ano, câmbio de planejamento R$ 6,00): decisão comercial já aprovada pelo PO."""
    return custo.definir_custo(db, provedor=provedor, custo_mensal_usd="600", creditos_anuais=81600, cambio_planejamento_brl="6.00", ator_id="1",
                               tenant_auditoria=A, motivo="teste", aprovar=aprovar)


def cenario(db, *, franquia=10, itens=10, padrao=2, maximo=5, limite_periodo=None, orcamento=1000, periodicidade="mensal", com_politica=True,
            limite_pesquisa=100_000, contrato=True, **kw_politica):
    """Plano, política do provedor e orçamento global APROVADOS. Tarifas de teste: busca 0, e-mail 1 (só e-mail), página 10, fator 1 — então o teto de
    uma empresa é igual ao nº de decisores pedidos. Cada parâmetro pode ser desligado/alterado por teste."""
    if contrato:
        custo_contratual(db)
    config.definir_config(db, plano_id=plano_id(db), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="teste", aprovar=True, campos=dict(
        franquia_creditos=franquia, periodicidade=periodicidade, decisores_por_empresa_padrao=padrao, decisores_por_empresa_max=maximo,
        itens_por_lote_max=itens, limite_periodo_creditos=limite_periodo, limite_creditos_pesquisa=limite_pesquisa))
    if com_politica:
        politica(db, **kw_politica)
    if orcamento is not None:
        config.definir_orcamento_global(db, provedor="lusha", limite_creditos=orcamento, alerta_percentual=80, ator_id="1", tenant_auditoria=A,
                                        motivo="teste", aprovar=True)


def contas(db, n, tenant=A, prefixo="Empresa"):
    criadas = []
    existentes = db.query(Conta).count()
    for i in range(n):
        k = existentes + i + 1
        c = Conta(tenant_id=tenant, nome=f"{prefixo} {tenant} {k}", dominio=f"emp{tenant}{k}.com.br", cnpj=f"{k:014d}", status="prospectada")
        db.add(c)
        criadas.append(c)
    db.commit()
    return criadas


def eu(db, tenant=A, papel="super_admin"):
    usuario = db.query(Usuario).filter_by(tenant_id=tenant, papel=papel).first()
    if usuario is None:
        usuario = Usuario(tenant_id=tenant, nome=f"{papel} {tenant}", email=f"{papel}@{tenant}.com.br", papel=papel, ativo=True)
        db.add(usuario)
        db.commit()
    return Solicitante(id=usuario.id, papel=usuario.papel, tenant_id=tenant)


def preparar_tenant_b(db):
    from app.models.licenca import Licenca
    from app.models.tenant import Tenant

    if db.query(Tenant).filter_by(id=B).one_or_none() is None:
        db.add(Tenant(id=B, razao_social="Outra"))
        db.flush()
        db.add(Licenca(tenant_id=B, plano_id=plano_id(db), status="ativa"))
        db.commit()


@pytest.fixture()
def prov_api(client):
    """O provedor que as rotas HTTP enxergam (a fixture `client` injeta um fake sem custo por padrão)."""
    provedor = ProvedorPago()
    app.dependency_overrides[get_contact_enrichment_provider] = lambda: provedor
    return provedor


def previa(db, solic, ids, prov, d=None, agora=None, **dados):
    return pesquisa.estimar(db, solicitante=solic, conta_ids=[c.id if hasattr(c, "id") else c for c in ids], decisores_por_empresa=d, provider=prov, agora=agora, **dados)


def confirmar(db, solic, p, prov, chave="chave-de-teste-1", agora=None):
    return pesquisa.confirmar(db, solicitante=solic, pesquisa_id=p.id, selecao_hash=p.selecao_hash, idempotency_key=chave, provider=prov, agora=agora)


def rodar(db, graph, solic, ids, prov, d=None, chave="chave-de-teste-1", **dados):
    p = previa(db, solic, ids, prov, d, **dados)
    p = confirmar(db, solic, p, prov, chave)
    return execucao.executar(db, tenant_id=solic.tenant_id, pesquisa_id=p.id, provider=prov, graph=graph, ator_id=str(solic.id))


def esperar_bloqueio(codigo, funcao):
    with pytest.raises(PesquisaBloqueada) as erro:
        funcao()
    assert erro.value.codigo == codigo, (erro.value.codigo, str(erro.value))
    return erro.value


def invariantes(db, tenant=A, permite_negativo=False):
    """Saldo e reservado são somas do razão; o reservado (do cliente e do provedor) é exatamente o que as empresas em aberto seguram."""
    movs = db.query(EnriquecimentoMovimento).filter_by(tenant_id=tenant).all()
    assert ledger.saldo(db, tenant) == sum(m.delta_saldo for m in movs)
    assert ledger.reservado(db, tenant) == sum(m.delta_reservado for m in movs)
    abertos = [i for i in db.query(PesquisaDecisoresEmpresa).filter_by(tenant_id=tenant).all() if i.estado in ("pendente", "enviado", "ambiguo")]
    assert ledger.reservado(db, tenant) == sum(i.creditos_reservados for i in abertos)
    assert sum(m.provedor_delta_reservado for m in movs) == sum(i.provedor_reservados for i in abertos)
    if not permite_negativo:
        assert ledger.disponivel(db, tenant) >= 0


def tipos(db, tenant=A):
    return [m.tipo for m in db.query(EnriquecimentoMovimento).filter_by(tenant_id=tenant).order_by(EnriquecimentoMovimento.id).all()]


# =================================================== configuração e aprovação ========================================================


def test_sem_configuracao_do_plano_a_previa_e_bloqueada_e_nada_e_chamado(client, db_session):
    prov, cs = ProvedorPago(), contas(db_session, 1)
    e = esperar_bloqueio("plano_sem_configuracao", lambda: previa(db_session, eu(db_session), cs, prov))
    assert "comercial" in str(e)
    assert prov.chamadas == [] and db_session.query(PesquisaDecisores).count() == 0


def test_configuracao_pendente_de_aprovacao_nao_libera(client, db_session):
    config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="rascunho", campos=dict(
        franquia_creditos=5, periodicidade="mensal", decisores_por_empresa_padrao=2, decisores_por_empresa_max=4, itens_por_lote_max=5))
    politica(db_session)
    esperar_bloqueio("plano_config_pendente_aprovacao", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago()))


def test_aprovar_libera_e_uma_nova_versao_pendente_nao_derruba_a_aprovada(client, db_session):
    cenario(db_session, franquia=10)
    nova = config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="mais franquia",
                                 campos=dict(franquia_creditos=99, periodicidade="mensal", decisores_por_empresa_padrao=2, decisores_por_empresa_max=5,
                                             itens_por_lote_max=10, limite_creditos_pesquisa=100_000))
    vigente, _ = config.config_vigente(db_session, A)
    assert vigente.franquia_creditos == 10 and vigente.versao == 1  # a pendente ainda não vale
    config.aprovar_config(db_session, nova.id, "1", A)
    vigente, _ = config.config_vigente(db_session, A)
    assert vigente.franquia_creditos == 99 and vigente.versao == 2
    with pytest.raises(ValidacaoFalhou, match="já foi aprovada"):
        config.aprovar_config(db_session, nova.id, "1", A)


def test_configuracao_incompleta_nao_pode_ser_aprovada_e_bloqueia_com_o_que_falta(client, db_session):
    incompleta = config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="rascunho",
                                       campos=dict(franquia_creditos=5, periodicidade="mensal"))
    with pytest.raises(ValidacaoFalhou, match="decisores_por_empresa_max"):
        config.aprovar_config(db_session, incompleta.id, "1", A)
    vigente, motivo = config.config_vigente(db_session, A)
    assert vigente is None and motivo == "plano_config_pendente_aprovacao"


@pytest.mark.parametrize("campos,trecho", [
    (dict(decisores_por_empresa_padrao=6, decisores_por_empresa_max=3), "não pode ser maior"),
    (dict(franquia_creditos=-1), "negativo"),
    (dict(itens_por_lote_max=0), "mínimo 1"),
    (dict(periodicidade="semanal"), "periodicidade"),
    (dict(franquia_creditos=True), "inteiro"),
    (dict(limite_periodo_creditos=2.5), "inteiro"),
])
def test_validacao_da_configuracao_recusa_valores_incoerentes(client, db_session, campos, trecho):
    with pytest.raises(ValidacaoFalhou, match=trecho):
        config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="x", campos=campos)


def test_configuracao_e_versionada_e_a_do_tenant_prevalece_sobre_a_do_plano(client, db_session):
    cenario(db_session, franquia=10, maximo=5)
    config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="v2", aprovar=True, campos=dict(
        franquia_creditos=20, periodicidade="mensal", decisores_por_empresa_padrao=2, decisores_por_empresa_max=5, itens_por_lote_max=10,
        limite_creditos_pesquisa=100_000))
    vigente, _ = config.config_vigente(db_session, A)
    assert vigente.versao == 2 and vigente.franquia_creditos == 20 and vigente.origem == "plano"
    config.definir_config(db_session, plano_id=None, tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="contrato Corporate", aprovar=True, campos=dict(
        franquia_creditos=500, periodicidade="mensal", decisores_por_empresa_padrao=3, decisores_por_empresa_max=10, itens_por_lote_max=50,
        limite_creditos_pesquisa=100_000))
    do_tenant, _ = config.config_vigente(db_session, A)
    assert do_tenant.origem == "tenant" and do_tenant.franquia_creditos == 500
    with pytest.raises(ValidacaoFalhou):
        config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="x", campos={})  # os dois


def test_sem_plano_ativo_bloqueia(client, db_session):
    preparar_tenant_b(db_session)
    from app.models.licenca import Licenca

    db_session.query(Licenca).filter_by(tenant_id=B).update({"status": "suspensa"})
    db_session.commit()
    cenario(db_session)
    esperar_bloqueio("sem_plano_ativo", lambda: previa(db_session, eu(db_session, B), contas(db_session, 1, B), ProvedorPago()))


def test_sem_politica_do_provedor_a_pesquisa_e_bloqueada(client, db_session):
    cenario(db_session, com_politica=False)
    esperar_bloqueio("politica_provedor_nao_configurada", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago()))


def test_politica_pendente_de_aprovacao_ou_incompleta_nao_libera(client, db_session):
    cenario(db_session, com_politica=False)
    pendente = politica(db_session, aprovar=False)
    esperar_bloqueio("politica_provedor_pendente_aprovacao", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago()))
    config.aprovar_politica(db_session, pendente.id, "1", A)
    assert previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago()).estimativa["viavel"] is True
    sem_tarifa = config.definir_politica(
        db_session, provedor="lusha", creditos_busca_por_resultado=1, creditos_email=None, creditos_telefone=None, revelar_emails=True, revelar_telefones=False,
        tamanho_pagina_busca=10, creditos_cliente_por_credito_provedor=1, markup_percentual=Decimal("100"), metodo_custo="lote_referencia",
        lote_compra_id=lote(db_session).id, casas_exibicao=2, fonte_tarifas="manual", ator_id="1", tenant_auditoria=A, motivo="rascunho")
    with pytest.raises(ValidacaoFalhou, match="creditos_email"):
        config.aprovar_politica(db_session, sem_tarifa.id, "1", A)


def test_orcamento_global_pendente_de_aprovacao_bloqueia(client, db_session):
    cenario(db_session, orcamento=None)
    config.definir_orcamento_global(db_session, provedor="lusha", limite_creditos=500, alerta_percentual=80, ator_id="1", tenant_auditoria=A, motivo="rascunho")
    prov = ProvedorPago()
    p = previa(db_session, eu(db_session), contas(db_session, 1), prov)
    assert p.estimativa["bloqueios"][0]["codigo"] == "orcamento_global_pendente_aprovacao"
    esperar_bloqueio("orcamento_global_pendente_aprovacao", lambda: confirmar(db_session, eu(db_session), p, prov))
    assert prov.chamadas == [] and "RESERVA" not in tipos(db_session)


def test_provedor_nao_configurado_bloqueia_antes_de_qualquer_outra_coisa(client, db_session):
    from app.providers.contact_enrichment.desativado import ContactEnrichmentDesativadoProvider

    esperar_bloqueio("provedor_indisponivel", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ContactEnrichmentDesativadoProvider()))


def test_planos_sem_configuracao_aparecem_na_visao_administrativa(client, db_session, criar_plano):
    cenario(db_session)
    outro = criar_plano(nome="Starter Teste")
    pendente = criar_plano(nome="Business Teste")
    config.definir_config(db_session, plano_id=pendente.id, tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="rascunho",
                          campos=dict(franquia_creditos=1))
    situacao = {p["plano"]: p["situacao"] for p in client.get(f"{ADMIN}/planos").json()}
    assert situacao["Plano Padrão Teste"] == "aprovada" and situacao[outro.nome] == "sem_configuracao" and situacao[pendente.nome] == "pendente_aprovacao"


# =================================================== seleção explícita ================================================================


def test_icp_inteiro_nao_dispara_pesquisa_a_api_so_aceita_lista_explicita(client, db_session, prov_api):
    cenario(db_session)
    for corpo in ({"icp_id": 1}, {"todas": True}, {"conta_ids": [], "decisores_por_empresa": 1}, {"conta_ids": [1], "icp_id": 3}):
        assert client.post(f"{URL}/previa", json=corpo).status_code == 422, corpo
    assert db_session.query(PesquisaDecisores).count() == 0 and prov_api.chamadas == []


def test_mapeamento_avulso_e_fila_automatica_trazem_so_qsa_e_nao_chamam_o_provedor(client, db_session, fake_graph, fake_account_data, fake_plan_limits,
                                                                                    fake_llm, fake_site_fetcher, fake_web_search):
    """Importar planilha/gerar lista/enriquecer enfileira contas, mas só o QSA é consultado: a Lusha exige pesquisa confirmada."""
    from app.contexts.predator import contract as predator
    from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
    from app.providers.account_data.base import DecisorCandidato
    from app.services import enriquecimento_fila_service

    prov = ProvedorPago()
    cenario(db_session)
    conta = contas(db_session, 1)[0]
    fake_account_data.decisores[conta.cnpj] = [DecisorCandidato(cnpj=conta.cnpj, nome="Sócio Um", qualificacao="Sócio-Administrador", fonte="receita_federal")]
    decisores = predator.mapear_decisores(db_session, A, "1", conta.id, fake_account_data, fake_graph, fake_plan_limits)
    assert prov.chamadas == [] and [d.nome for d in decisores] == ["Sócio Um"]

    outra = contas(db_session, 1)[0]
    fake_account_data.decisores[outra.cnpj] = [DecisorCandidato(cnpj=outra.cnpj, nome="Sócia Dois", qualificacao="Sócia", fonte="receita_federal")]
    enriquecimento_fila_service.enfileirar(db_session, A, [outra.id])
    resultado = enriquecimento_fila_service.processar_pendentes(db_session, fake_llm, fake_site_fetcher, fake_web_search, fake_account_data, fake_graph,
                                                                fake_plan_limits)
    assert resultado["processados"] == 1 and prov.chamadas == []
    assert db_session.query(PesquisaDecisores).count() == 0 and "RESERVA" not in tipos(db_session) and "CONSUMO" not in tipos(db_session)
    assert db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=outra.id).one().status in ("concluido", "falhou")
    assert not db_session.query(Decisor).filter(Decisor.origem == "lusha").count()


def test_qsa_funciona_sem_nenhuma_configuracao_de_enriquecimento_e_e_contabilizado_por_fonte(client, db_session, fake_graph, fake_account_data,
                                                                                            fake_plan_limits):
    """Nada de plano, política ou orçamento: o QSA continua e só registra o uso da fonte (sem custo de crédito)."""
    from app.contexts.predator import contract as predator
    from app.providers.account_data.base import DecisorCandidato

    assert config.config_vigente(db_session, A)[0] is None and config.politica_vigente(db_session, "lusha")[0] is None
    conta = contas(db_session, 1)[0]
    fake_account_data.decisores[conta.cnpj] = [DecisorCandidato(cnpj=conta.cnpj, nome="Sócio Um", qualificacao="Sócio", fonte="receita_federal")]
    assert [d.nome for d in predator.mapear_decisores(db_session, A, "1", conta.id, fake_account_data, fake_graph, fake_plan_limits)] == ["Sócio Um"]
    assert ledger.uso_por_fonte(db_session, A, config.periodo_de(config.agora_utc())) == {"receita_qsa": 1}
    assert ledger.saldo(db_session, A) == 0 and ledger.reservado(db_session, A) == 0  # uso sem custo: deltas zero


def test_brasilapi_tambem_e_contabilizada_por_fonte(client, db_session):
    conta = client.post("/api/v1/leads/contas", json={"nome": "Empresa BR", "cnpj": "11222333000181", "dominio": "br.com.br"}).json()
    resposta = client.post(f"/api/v1/contas/{conta['id']}/enriquecer-brasilapi")
    assert resposta.status_code == 200
    assert ledger.uso_por_fonte(db_session, A, config.periodo_de(config.agora_utc())).get("brasilapi") == 1


def test_selecao_de_outro_tenant_ou_inexistente_responde_igual(client, db_session, prov_api):
    cenario(db_session)
    preparar_tenant_b(db_session)
    alheia = contas(db_session, 1, B)[0]
    r1 = client.post(f"{URL}/previa", json={"conta_ids": [alheia.id]})
    r2 = client.post(f"{URL}/previa", json={"conta_ids": [999999]})
    assert r1.status_code == r2.status_code == 404 and r1.json() == r2.json()


def test_vendedor_so_seleciona_empresas_do_proprio_escopo(client, db_session, criar_usuario_autenticado, prov_api):
    cenario(db_session)
    cs = contas(db_session, 1)
    headers = criar_usuario_autenticado(A, papel="user", email="vendedor@x.com.br")
    assert client.post(f"{URL}/previa", json={"conta_ids": [cs[0].id]}, headers=headers).status_code == 403


def test_duplicatas_na_lista_enviada_sao_unificadas_e_a_hash_e_estavel(client, db_session):
    cenario(db_session)
    c = contas(db_session, 2)
    p1 = previa(db_session, eu(db_session), [c[0].id, c[0].id, c[1].id], ProvedorPago())
    p2 = previa(db_session, eu(db_session), [c[1].id, c[0].id], ProvedorPago())
    assert p1.total_empresas == 2 and p1.selecao_hash == p2.selecao_hash


# =================================================== decisores por empresa ============================================================


def test_padrao_do_plano_e_origem_visivel_e_escolha_do_usuario(client, db_session):
    cenario(db_session, padrao=2, maximo=5)
    c = contas(db_session, 1)
    p = previa(db_session, eu(db_session), c, ProvedorPago())
    assert p.decisores_por_empresa == 2 and p.origem_decisores == "padrao_plano" and p.estimativa["origem_decisores"] == "padrao_plano"
    p = previa(db_session, eu(db_session), c, ProvedorPago(), d=4)
    assert p.decisores_por_empresa == 4 and p.origem_decisores == "informado_usuario" and p.total_maximo == 4


@pytest.mark.parametrize("valor,trecho", [(6, "excede o máximo do seu plano"), (0, "maior que zero"), (-1, "maior que zero"), (True, "maior que zero")])
def test_valor_invalido_ou_acima_do_maximo_e_rejeitado_e_nunca_ajustado_em_silencio(client, db_session, valor, trecho):
    cenario(db_session, maximo=5)
    with pytest.raises(ValidacaoFalhou, match=trecho):
        previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=valor)
    assert db_session.query(PesquisaDecisores).count() == 0


def test_valor_acima_da_pagina_da_politica_e_pagina_abaixo_do_minimo_do_provedor_sao_rejeitados(client, db_session):
    cenario(db_session, maximo=200, pagina=10)
    with pytest.raises(ValidacaoFalhou, match="uma consulta ao provedor retorna"):
        previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=11)
    with pytest.raises(ValidacaoFalhou, match="mínimo aceito pelo provedor"):
        politica(db_session, pagina=9)


def test_lote_acima_do_maximo_do_plano_e_rejeitado_sem_truncar(client, db_session):
    cenario(db_session, itens=3)
    with pytest.raises(ValidacaoFalhou, match="máximo por pesquisa"):
        previa(db_session, eu(db_session), contas(db_session, 4), ProvedorPago())


def test_limite_por_empresa_nao_substitui_os_limites_totais(client, db_session):
    cenario(db_session, franquia=5, padrao=2, maximo=5)
    p = previa(db_session, eu(db_session), contas(db_session, 3), ProvedorPago(), d=2)  # teto 6 > 5
    assert p.estimativa["viavel"] is False and p.estimativa["bloqueios"][0]["codigo"] == "saldo_insuficiente"


# =================================================== estimativa e confirmação =========================================================


def test_previa_mostra_estimativa_por_categoria_incertezas_e_nao_reserva_nem_chama(client, db_session):
    cenario(db_session, franquia=10)
    prov = ProvedorPago()
    p = previa(db_session, eu(db_session), contas(db_session, 3), prov)
    e = p.estimativa
    assert (e["creditos_maximos"], e["creditos_provedor_maximos"], e["empresas_selecionadas"], e["empresas_a_consultar"], e["disponivel"], e["viavel"]) == (6, 6, 3, 3, 10, True)
    assert e["limites"]["decisores_por_empresa_max"] == 5 and e["config"] == {"origem": "plano", "versao": 1} and e["politica"] == {"versao": 1}
    assert e["por_categoria"]["ia"]["creditos"] == 0 and e["por_categoria"]["enriquecimento"]["lusha_revelacao"]["creditos_cliente_max"] == 6
    assert e["por_categoria"]["enriquecimento"]["receita_qsa"]["creditos_cliente_max"] == 0
    assert any("TETO" in i and "informado pelo próprio provedor" in i for i in e["incertezas"])
    assert any("cobrada por resultado" in i for i in e["incertezas"]) and any("estimativa de apresentação" in i for i in e["incertezas"])
    assert prov.chamadas == [] and ledger.reservado(db_session, A) == 0 and "RESERVA" not in tipos(db_session)


def test_estimativa_com_as_tarifas_da_lusha_busca_email_e_telefone(client, db_session):
    """Tarifas publicadas pela Lusha: e-mail 1, telefone 5; a busca cobra por resultado devolvido (página inteira)."""
    cenario(db_session, franquia=1000, maximo=5, busca=1, email=1, telefone=5, revelar_telefones=True, pagina=10)
    p = previa(db_session, eu(db_session), contas(db_session, 2), ProvedorPago(), d=2, revelar_telefones=True)
    e = p.estimativa
    # por empresa: 10 resultados × 1 (busca) + 2 contatos × (1 + 5) = 22; duas empresas = 44
    assert e["creditos_provedor_maximos"] == 44 and e["creditos_maximos"] == 44
    assert e["por_categoria"]["enriquecimento"]["lusha_busca"]["creditos_provedor_max"] == 20
    assert e["por_categoria"]["enriquecimento"]["lusha_revelacao"]["creditos_provedor_max"] == 24
    assert e["valor_maximo_brl"] == "59.39" and e["preco_credito_provedor_brl"] == "1.35"  # 44 × 1,3497 = 59,3868 (só a exibição arredonda)


def test_ajustes_sugeridos_usam_so_limites_e_tarifas_conhecidos_e_nao_alteram_a_escolha(client, db_session):
    cenario(db_session, franquia=3, padrao=2, maximo=5, itens=10)
    p = previa(db_session, eu(db_session), contas(db_session, 2), ProvedorPago(), d=2)  # teto 4, há 3
    por_tipo = {s["tipo"]: s for s in p.estimativa["ajustes_sugeridos"]}
    assert por_tipo["reduzir_profundidade"] == {"tipo": "reduzir_profundidade", "decisores_por_empresa": 1, "empresas_cobertas": 2}
    assert por_tipo["ampliar_abrangencia"]["empresas_cobertas"] == 3 and por_tipo["reduzir_selecao"]["empresas_cobertas"] == 1
    assert p.decisores_por_empresa == 2 and p.total_empresas == 2 and "não foi alterada" in p.estimativa["nota_ajustes"]


def test_ajustes_consideram_o_custo_fixo_da_busca_por_empresa(client, db_session):
    """Com a busca cobrando uma página inteira por empresa, 'mais empresas com 1 decisor' não cabe como no cálculo ingênuo de 1 crédito por contato."""
    cenario(db_session, franquia=30, padrao=2, maximo=5, busca=1, email=1, pagina=10)  # empresa com d decisores: 10 + d
    p = previa(db_session, eu(db_session), contas(db_session, 3), ProvedorPago(), d=2)  # 3 × 12 = 36 > 30
    assert p.estimativa["viavel"] is False
    por_tipo = {s["tipo"]: s for s in p.estimativa["ajustes_sugeridos"]}
    assert set(por_tipo) == {"reduzir_selecao"} and por_tipo["reduzir_selecao"]["empresas_cobertas"] == 2  # 3 × 11 = 33 também estoura: só menos empresas


def test_confirmar_com_hash_diferente_e_recusado(client, db_session):
    cenario(db_session)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 1), prov)
    esperar_bloqueio("selecao_alterada", lambda: pesquisa.confirmar(db_session, solicitante=solic, pesquisa_id=p.id, selecao_hash="0" * 64,
                                                                    idempotency_key="chave-12345", provider=prov))
    assert prov.chamadas == [] and ledger.reservado(db_session, A) == 0


def test_previa_expirada_nao_pode_ser_confirmada(client, db_session):
    cenario(db_session)
    prov, solic = ProvedorPago(), eu(db_session)
    agora = config.agora_utc()
    p = previa(db_session, solic, contas(db_session, 1), prov, agora=agora)
    esperar_bloqueio("previa_expirada", lambda: confirmar(db_session, solic, p, prov, agora=agora + timedelta(minutes=settings.enriquecimento_previa_validade_min + 1)))
    assert db_session.get(PesquisaDecisores, p.id).estado == "cancelada" and prov.chamadas == []


def test_mudanca_de_configuracao_depois_da_previa_exige_nova_previa(client, db_session):
    cenario(db_session)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 1), prov)
    config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="v2", aprovar=True, campos=dict(
        franquia_creditos=10, periodicidade="mensal", decisores_por_empresa_padrao=2, decisores_por_empresa_max=5, itens_por_lote_max=10,
        limite_creditos_pesquisa=100_000))
    esperar_bloqueio("estimativa_desatualizada", lambda: confirmar(db_session, solic, p, prov))
    assert ledger.reservado(db_session, A) == 0
    assert db_session.get(PesquisaDecisores, p.id).estado == "criada"  # continua revisável (a recusa deixa rastro, não destrói a prévia)


def test_mudanca_de_tarifa_ou_preco_depois_da_previa_exige_nova_previa(client, db_session):
    cenario(db_session)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 1), prov)
    politica(db_session, markup="120")  # nova versão aprovada: preço de venda diferente
    esperar_bloqueio("estimativa_desatualizada", lambda: confirmar(db_session, solic, p, prov))
    assert "RESERVA" not in tipos(db_session)


def test_decisores_obtidos_entre_a_previa_e_a_confirmacao_invalidam_a_estimativa(client, db_session):
    cenario(db_session)
    prov, solic, cs = ProvedorPago(), eu(db_session), contas(db_session, 1)
    p = previa(db_session, solic, cs, prov)
    db_session.add(Decisor(tenant_id=A, conta_id=cs[0].id, nome="Já veio", email="x@exemplo.com.br", origem="lusha"))
    db_session.commit()
    esperar_bloqueio("estimativa_desatualizada", lambda: confirmar(db_session, solic, p, prov))


def test_valores_do_cliente_nao_alteram_nada_no_servidor(client, db_session, prov_api):
    """Campos extras (plano, saldo, limite, orçamento, estado, preço, créditos) são recusados na prévia e na confirmação."""
    cenario(db_session)
    c = contas(db_session, 1)
    for extra in ({"franquia_creditos": 999}, {"saldo": 999}, {"orcamento": 999}, {"estado": "concluida"}, {"plano_id": 1}, {"preco": 0}):
        assert client.post(f"{URL}/previa", json={"conta_ids": [c[0].id], **extra}).status_code == 422
    p = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id]}).json()
    assert client.post(f"{URL}/{p['id']}/confirmar", json={"selecao_hash": p["selecao_hash"], "idempotency_key": "chave-12345", "creditos": 0}).status_code == 422


# =================================================== fluxo completo, razão, reserva ===================================================


def test_fluxo_feliz_reserva_o_teto_consome_o_medido_e_grava_decisores(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov, solic, cs = ProvedorPago(), eu(db_session), contas(db_session, 2)
    p = rodar(db_session, fake_graph, solic, cs, prov)
    assert p.estado == "concluida" and (p.creditos_reservados, p.creditos_consumidos, p.requer_reconciliacao) == (4, 4, False)
    assert (p.provedor_reservados, p.provedor_consumidos) == (4, 4)
    assert [f.limite_contatos for f in prov.chamadas] == [2, 2]
    assert all(f.tamanho_pagina == 10 and f.revelar == ["emails"] for f in prov.chamadas)  # tudo vem da política aprovada
    assert ledger.disponivel(db_session, A) == 6 and ledger.reservado(db_session, A) == 0
    assert tipos(db_session) == ["CONCESSAO", "RESERVA", "CONSUMO", "CONSUMO"]
    assert db_session.query(Decisor).filter_by(tenant_id=A, origem="lusha").count() == 4
    detalhe = painel.serializar_pesquisa(db_session, p, com_itens=True, com_transicoes=True)
    assert [t["para"] for t in detalhe["transicoes"] if t["item_id"] is None] == ["criada", "validada", "reservada", "enviada", "concluida"]
    assert {i["estado"] for i in detalhe["itens"]} == {"concluido"}
    invariantes(db_session)


def test_o_debito_e_o_consumo_medido_pelo_provedor_e_nao_o_numero_de_contatos(client, db_session, fake_graph):
    """2 contatos revelados mas o provedor mediu 5 créditos (e-mail + telefone): cobra 5, não 2."""
    cenario(db_session, franquia=20, busca=0, email=1, telefone=5, revelar_telefones=True)  # teto da empresa: 2 × 6 = 12
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([ok(2, medido=5)]), revelar_telefones=True)
    assert p.estado == "concluida" and (p.provedor_reservados, p.provedor_consumidos, p.creditos_consumidos) == (12, 5, 5)
    assert ledger.disponivel(db_session, A) == 15 and "LIBERACAO" in tipos(db_session)
    invariantes(db_session)


def test_so_o_medido_e_cobrado_e_o_resto_da_reserva_volta(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 2), ProvedorPago([ok(1), sem_resultados()]))
    assert p.estado == "concluida" and p.creditos_consumidos == 1 and ledger.disponivel(db_session, A) == 9  # reservou 4, o provedor mediu 1
    invariantes(db_session)


def test_busca_sem_resultados_mas_cobrada_debita_o_que_o_provedor_mediu(client, db_session, fake_graph):
    cenario(db_session, franquia=30, busca=1, email=1, pagina=10)  # teto da empresa: 10 + 2 = 12
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([sem_resultados(medido=10)]))
    assert p.provedor_consumidos == 10 and p.creditos_consumidos == 10 and ledger.disponivel(db_session, A) == 20
    invariantes(db_session)


def test_falha_da_revelacao_depois_de_a_busca_ser_cobrada_debita_a_busca(client, db_session, fake_graph):
    cenario(db_session, franquia=30, busca=1, email=1, pagina=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([erro_seguro(cobrado_pela_busca=10)]))
    assert p.estado == "falha" and p.provedor_consumidos == 10 and ledger.disponivel(db_session, A) == 20
    invariantes(db_session)


def test_resposta_sem_medicao_de_provedor_pago_e_ambigua_e_nao_cobra_estimativa(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    sem_medicao = ResultadoBuscaContatos(estado="ok", contatos=[ContatoCandidato(nome="Alguém", cargo="CEO", fonte="lusha")], creditos_provedor=None)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([sem_medicao]))
    assert p.estado == "em_processamento" and p.requer_reconciliacao and "CONSUMO" not in tipos(db_session)
    assert ledger.reservado(db_session, A) == 2 and db_session.query(Decisor).filter_by(origem="lusha").count() == 0  # nada gravado, nada cobrado
    item = db_session.query(PesquisaDecisoresEmpresa).one()
    assert item.estado == "ambiguo" and "medicao_ausente" in item.motivo


def test_custo_de_aquisicao_markup_e_valor_de_venda_ficam_no_razao_sem_arredondar(client, db_session, fake_graph):
    cenario(db_session, franquia=20)  # lote 269,94/400 => custo 0,67485; markup 100% => preço 1,3497
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([ok(2, medido=3)]))
    consumo = db_session.query(EnriquecimentoMovimento).filter_by(tipo="CONSUMO").one()
    assert (consumo.provedor_delta_consumido, consumo.delta_saldo) == (3, -3)
    assert Decimal(str(consumo.custo_unitario_brl)) == Decimal("0.67485") and Decimal(str(consumo.preco_unitario_brl)) == Decimal("1.3497")
    assert Decimal(str(consumo.custo_total_brl)) == Decimal("2.02455") and Decimal(str(consumo.valor_venda_brl)) == Decimal("4.0491")  # 4,0491, não 4,05
    resultado = ledger.resultado_financeiro(db_session, "lusha")
    assert (resultado["custo_brl"], resultado["venda_brl"], resultado["margem_brl"]) == (Decimal("2.02455"), Decimal("4.0491"), Decimal("2.02455"))
    assert resultado["margem_percentual"] == Decimal("50")


def test_credito_do_cliente_nao_e_igual_ao_do_provedor_quando_a_politica_diz_outra_coisa(client, db_session, fake_graph):
    """Política aprovada: 2 créditos do cliente por crédito do provedor. O orçamento global segue em créditos do PROVEDOR."""
    cenario(db_session, franquia=40, fator=2)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([ok(2, medido=3)]))  # teto: 2 do provedor = 4 do cliente
    assert (p.provedor_reservados, p.creditos_reservados, p.provedor_consumidos, p.creditos_consumidos) == (2, 4, 3, 6)  # medido > reservado
    assert p.requer_reconciliacao  # o provedor consumiu acima do reservado: lançado por inteiro e sinalizado
    assert ledger.disponivel(db_session, A) == 34 and ledger.situacao_global(db_session, "lusha")["consumido"] == 3
    invariantes(db_session)


def test_consumo_acima_do_reservado_e_lancado_por_inteiro_e_bloqueia_novas_pesquisas(client, db_session, fake_graph):
    cenario(db_session, franquia=4, padrao=2)
    solic, prov = eu(db_session), ProvedorPago([ok(2, medido=9)])  # reservou 2, o provedor mediu 9
    p = rodar(db_session, fake_graph, solic, contas(db_session, 1), prov)
    assert p.creditos_consumidos == 9 and p.requer_reconciliacao and ledger.disponivel(db_session, A) == -5  # a realidade não é escondida
    invariantes(db_session, permite_negativo=True)
    nova = previa(db_session, solic, contas(db_session, 1), ProvedorPago())
    assert nova.estimativa["viavel"] is False and nova.estimativa["bloqueios"][0]["codigo"] == "saldo_insuficiente"


def test_provedor_sem_creditos_na_conta_dele_libera_a_reserva_e_alerta(client, db_session, fake_graph, caplog):
    cenario(db_session, franquia=10)
    sem_creditos = ResultadoBuscaContatos(estado="erro_seguro", detalhe="busca_sem_creditos")
    with caplog.at_level("ERROR", logger="b2bon.enriquecimento"):
        p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([sem_creditos]))
    assert p.estado == "falha" and ledger.disponivel(db_session, A) == 10
    assert "ENRIQUECIMENTO_PROVEDOR_SEM_CREDITOS" in caplog.text


def test_reserva_atomica_duas_pesquisas_disputando_o_mesmo_saldo(client, db_session, fake_graph):
    cenario(db_session, franquia=4)
    prov, solic = ProvedorPago(), eu(db_session)
    p1, p2 = previa(db_session, solic, contas(db_session, 2), prov), previa(db_session, solic, contas(db_session, 2), prov)
    assert p1.estimativa["viavel"] and p2.estimativa["viavel"]  # na prévia cada uma cabe sozinha
    confirmar(db_session, solic, p1, prov, "chave-numero-1")
    assert ledger.reservado(db_session, A) == 4 and ledger.disponivel(db_session, A) == 0
    esperar_bloqueio("saldo_insuficiente", lambda: confirmar(db_session, solic, p2, prov, "chave-numero-2"))  # a 2ª não ultrapassa o saldo
    assert ledger.reservado(db_session, A) == 4 and db_session.get(PesquisaDecisores, p2.id).estado == "criada"
    invariantes(db_session)


def test_chamada_ao_provedor_so_acontece_depois_da_reserva_gravada(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    visto = {}

    class Espiao(ProvedorPago):
        def buscar_contatos_governado(self, filtro):
            visto["reservado"] = ledger.reservado(db_session, A)
            visto["reservado_provedor"] = ledger.reservado_do_provedor(db_session, "lusha")
            visto["estado_item"] = db_session.query(PesquisaDecisoresEmpresa).filter_by(estado="enviado").count()
            return super().buscar_contatos_governado(filtro)

    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), Espiao())
    assert visto == {"reservado": 2, "reservado_provedor": 2, "estado_item": 1}  # reserva já no razão e empresa já marcada como enviada


def test_qualquer_bloqueio_impede_que_o_provedor_seja_chamado(client, db_session, fake_graph):
    cenario(db_session, franquia=1)
    prov = ProvedorPago()
    p = previa(db_session, eu(db_session), contas(db_session, 2), prov)
    esperar_bloqueio("saldo_insuficiente", lambda: confirmar(db_session, eu(db_session), p, prov))
    assert prov.chamadas == [] and "RESERVA" not in tipos(db_session)


# =================================================== idempotência =====================================================================


def test_repetir_a_confirmacao_com_a_mesma_chave_devolve_o_estado_sem_reservar_nem_chamar_de_novo(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 1), prov)
    primeira = confirmar(db_session, solic, p, prov, "chave-unica-1")
    execucao.executar(db_session, tenant_id=A, pesquisa_id=p.id, provider=prov, graph=fake_graph, ator_id="1")
    repetida = confirmar(db_session, solic, p, prov, "chave-unica-1")
    assert repetida.id == primeira.id and repetida.estado == "concluida"
    assert tipos(db_session).count("RESERVA") == 1 and len(prov.chamadas) == 1
    execucao.executar(db_session, tenant_id=A, pesquisa_id=p.id, provider=prov, graph=fake_graph, ator_id="1")  # executar de novo não envia nada
    assert len(prov.chamadas) == 1
    invariantes(db_session)


def test_outra_chave_numa_pesquisa_ja_processada_e_recusada_e_a_chave_nao_serve_a_duas_pesquisas(client, db_session, fake_graph):
    cenario(db_session, franquia=20)
    prov, solic = ProvedorPago(), eu(db_session)
    p1, p2 = previa(db_session, solic, contas(db_session, 1), prov), previa(db_session, solic, contas(db_session, 1), prov)
    confirmar(db_session, solic, p1, prov, "chave-unica-1")
    esperar_bloqueio("pesquisa_ja_processada", lambda: confirmar(db_session, solic, p1, prov, "chave-diferente"))
    esperar_bloqueio("chave_idempotencia_em_uso", lambda: confirmar(db_session, solic, p2, prov, "chave-unica-1"))
    assert tipos(db_session).count("RESERVA") == 1
    invariantes(db_session)


def test_idempotencia_pela_api_a_segunda_chamada_nao_consome_de_novo(client, db_session, prov_api):
    cenario(db_session, franquia=10)
    c = contas(db_session, 1)
    p = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id]}).json()
    corpo = {"selecao_hash": p["selecao_hash"], "idempotency_key": "chave-api-123"}
    r1, r2 = client.post(f"{URL}/{p['id']}/confirmar", json=corpo), client.post(f"{URL}/{p['id']}/confirmar", json=corpo)
    assert r1.status_code == r2.status_code == 200 and r1.json()["estado"] == "reservada"  # a consulta roda em segundo plano
    assert client.get(f"{URL}/{p['id']}").json()["estado"] == "concluida"
    assert len(prov_api.chamadas) == 1 and tipos(db_session).count("CONSUMO") == 1 and tipos(db_session).count("RESERVA") == 1


# =================================================== falhas, ambiguidade, reconciliação ===============================================


def test_erro_certo_antes_do_consumo_libera_toda_a_reserva(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([erro_seguro()]))
    assert p.estado == "falha" and p.creditos_consumidos == 0 and ledger.disponivel(db_session, A) == 10 and ledger.reservado(db_session, A) == 0
    invariantes(db_session)


def test_resultado_parcial_uma_empresa_ok_outra_falhou(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 2), ProvedorPago([ok(2), erro_seguro()]))
    assert p.estado == "parcial" and p.creditos_consumidos == 2 and ledger.disponivel(db_session, A) == 8
    invariantes(db_session)


def test_desfecho_ambiguo_nao_repete_nao_libera_e_aguarda_reconciliacao(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov, solic = ProvedorPago([ambiguo()]), eu(db_session)
    p = rodar(db_session, fake_graph, solic, contas(db_session, 1), prov)
    assert p.estado == "em_processamento" and p.requer_reconciliacao and p.creditos_consumidos == 0
    assert ledger.reservado(db_session, A) == 2 and ledger.disponivel(db_session, A) == 8  # retido, nem liberado nem cobrado
    p = execucao.retomar(db_session, solicitante=solic, pesquisa_id=p.id, provider=prov, graph=fake_graph)
    assert len(prov.chamadas) == 1 and p.estado == "em_processamento"  # retomar não reenvia
    invariantes(db_session)
    item = db_session.query(PesquisaDecisoresEmpresa).filter_by(pesquisa_id=p.id).one()
    assert item.estado == "ambiguo" and item.ids_provedor == ["x1"] and item.tentativas == 1

    p = execucao.reconciliar_item(db_session, pesquisa_id=p.id, item_id=item.id, creditos_provedor_consumidos=1, motivo="relatório de uso Lusha de 20/10",
                                  ator_id="1", tenant_auditoria=A)
    assert p.estado == "reconciliada" and not p.requer_reconciliacao and p.creditos_consumidos == 1 and p.provedor_consumidos == 1
    assert ledger.reservado(db_session, A) == 0 and ledger.disponivel(db_session, A) == 9
    assert {"CONSUMO", "LIBERACAO", "RECONCILIACAO"} <= set(tipos(db_session))
    invariantes(db_session)


def test_excecao_do_adaptador_depois_do_envio_tambem_e_ambigua(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([RuntimeError("falha inesperada")]))
    assert p.estado == "em_processamento" and p.requer_reconciliacao and ledger.reservado(db_session, A) == 2


def test_empresa_enviada_ha_muito_tempo_sem_desfecho_vira_ambigua_e_nunca_e_reenviada(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov, solic = ProvedorPago(), eu(db_session)
    p = confirmar(db_session, solic, previa(db_session, solic, contas(db_session, 1), prov), prov)
    item = db_session.query(PesquisaDecisoresEmpresa).filter_by(pesquisa_id=p.id).one()
    item.estado, item.enviado_em = "enviado", config.agora_utc() - timedelta(minutes=settings.enriquecimento_item_enviado_stale_min + 1)
    p.estado = "enviada"
    db_session.commit()
    p = execucao.executar(db_session, tenant_id=A, pesquisa_id=p.id, provider=prov, graph=fake_graph, ator_id="1")
    assert prov.chamadas == [] and p.estado == "em_processamento" and p.requer_reconciliacao and ledger.reservado(db_session, A) == 2


def test_falhas_seguidas_pausam_o_envio_e_o_restante_pode_ser_retomado(client, db_session, fake_graph):
    cenario(db_session, franquia=20, itens=10)
    prov, solic = ProvedorPago([erro_seguro(), erro_seguro(), erro_seguro()]), eu(db_session)
    p = rodar(db_session, fake_graph, solic, contas(db_session, 5), prov)
    assert len(prov.chamadas) == 3 and p.estado == "enviada"  # parou de martelar; 2 empresas seguem pendentes
    assert ledger.reservado(db_session, A) == 4
    p = execucao.retomar(db_session, solicitante=solic, pesquisa_id=p.id, provider=prov, graph=fake_graph)
    assert len(prov.chamadas) == 5 and p.estado == "parcial" and p.creditos_consumidos == 4
    invariantes(db_session)


def test_cancelar_previa_e_cancelar_pesquisa_reservada_libera_tudo(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 2), prov)
    assert execucao.cancelar(db_session, solicitante=solic, pesquisa_id=p.id).estado == "cancelada"
    p2 = confirmar(db_session, solic, previa(db_session, solic, contas(db_session, 2), prov), prov)
    assert ledger.reservado(db_session, A) == 4
    assert execucao.cancelar(db_session, solicitante=solic, pesquisa_id=p2.id).estado == "cancelada"
    assert ledger.reservado(db_session, A) == 0 and ledger.disponivel(db_session, A) == 10 and prov.chamadas == []
    invariantes(db_session)


# =================================================== deduplicação =====================================================================


def test_duplicidade_na_selecao_e_decisores_ja_obtidos_ficam_fora_da_consulta(client, db_session, fake_graph):
    cenario(db_session, franquia=20, padrao=2)
    prov, solic = ProvedorPago(), eu(db_session)
    a, b, c = contas(db_session, 3)
    b.cnpj = a.cnpj  # a mesma empresa duas vezes (CNPJ repetido)
    db_session.add_all([Decisor(tenant_id=A, conta_id=c.id, nome="Pessoa X", email="x@exemplo.com.br", origem="lusha"), Decisor(tenant_id=A, conta_id=c.id, nome="Pessoa Y", email="x@exemplo.com.br", origem="lusha")])
    db_session.commit()
    p = previa(db_session, solic, [a, b, c], prov)
    assert p.total_maximo == 2 and p.estimativa["empresas_deduplicadas"] == 2
    assert any("economia não é garantida" in i for i in p.estimativa["incertezas"])
    p = confirmar(db_session, solic, p, prov)
    p = execucao.executar(db_session, tenant_id=A, pesquisa_id=p.id, provider=prov, graph=fake_graph, ator_id="1")
    assert len(prov.chamadas) == 1 and prov.chamadas[0].nome_empresa == a.nome  # só a empresa elegível chegou ao provedor
    motivos = {i.conta_id: i.motivo for i in db_session.query(PesquisaDecisoresEmpresa).filter_by(estado="deduplicada")}
    assert motivos == {b.id: "duplicada_na_selecao", c.id: "decisores_ja_obtidos_do_provedor"}
    assert p.estado == "concluida"


def test_so_o_que_falta_e_pedido_ao_provedor(client, db_session, fake_graph):
    cenario(db_session, franquia=20, padrao=3)
    prov, cs = ProvedorPago(), contas(db_session, 1)
    db_session.add(Decisor(tenant_id=A, conta_id=cs[0].id, nome="Já tenho", email="x@exemplo.com.br", origem="lusha"))
    db_session.commit()
    p = rodar(db_session, fake_graph, eu(db_session), cs, prov)
    assert prov.chamadas[0].limite_contatos == 2 and p.creditos_reservados == 2


def test_nada_a_consultar_conclui_sem_reservar(client, db_session, fake_graph):
    cenario(db_session, franquia=20, padrao=1)
    prov, cs, solic = ProvedorPago(), contas(db_session, 1), eu(db_session)
    db_session.add(Decisor(tenant_id=A, conta_id=cs[0].id, nome="Já tenho", email="x@exemplo.com.br", origem="lusha"))
    db_session.commit()
    p = confirmar(db_session, solic, previa(db_session, solic, cs, prov), prov)
    assert p.estado == "concluida" and "RESERVA" not in tipos(db_session) and prov.chamadas == []


# =================================================== limites: período, orçamento global ==============================================


def test_limite_do_periodo_bloqueia_mesmo_com_saldo(client, db_session, fake_graph):
    cenario(db_session, franquia=100, limite_periodo=3)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 2), prov)  # teto 4 > 3
    assert p.estimativa["bloqueios"][0]["codigo"] == "limite_periodo" and p.estimativa["limite_periodo_restante"] == 3
    esperar_bloqueio("limite_periodo", lambda: confirmar(db_session, solic, p, prov))


def test_sem_orcamento_global_configurado_as_chamadas_ao_provedor_sao_bloqueadas(client, db_session, fake_graph):
    cenario(db_session, franquia=10, orcamento=None)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 1), prov)
    assert p.estimativa["bloqueios"][0]["codigo"] == "orcamento_global_nao_configurado"
    esperar_bloqueio("orcamento_global_nao_configurado", lambda: confirmar(db_session, solic, p, prov))
    assert prov.chamadas == [] and "RESERVA" not in tipos(db_session)


def test_orcamento_global_soma_reservas_e_consumo_medido_de_todos_os_tenants(client, db_session, fake_graph):
    cenario(db_session, franquia=10, orcamento=5)
    preparar_tenant_b(db_session)
    prov = ProvedorPago()
    sa, sb = eu(db_session), eu(db_session, B)
    pa = previa(db_session, sa, contas(db_session, 2), prov)       # teto 4
    pb = previa(db_session, sb, contas(db_session, 2, B), prov)    # teto 4; orçamento 5
    confirmar(db_session, sa, pa, prov, "chave-do-tenant-a")
    esperar_bloqueio("orcamento_global_esgotado", lambda: confirmar(db_session, sb, pb, prov, "chave-do-tenant-b"))  # 4 reservados + 4 > 5
    assert ledger.situacao_global(db_session, "lusha")["reservado"] == 4
    execucao.executar(db_session, tenant_id=A, pesquisa_id=pa.id, provider=prov, graph=fake_graph, ator_id="1")
    esperar_bloqueio("orcamento_global_esgotado", lambda: confirmar(db_session, sb, pb, prov, "chave-do-tenant-b"))  # agora 4 medidos
    g = ledger.situacao_global(db_session, "lusha")
    assert (g["consumido"], g["reservado"], g["restante"], g["nivel"]) == (4, 0, 1, "alerta")
    invariantes(db_session, A)


def test_orcamento_global_e_economia_da_cyberfort_so_aparecem_na_area_administrativa(client, db_session, criar_usuario_autenticado, prov_api):
    cenario(db_session)
    corpo_painel = client.get(f"{URL}/painel").json()
    texto = str(corpo_painel).lower()
    assert "orcamento_global" not in corpo_painel and not any(p in texto for p in ("custo_unitario", "markup", "margem", "custo_total"))
    visao = client.get(f"{ADMIN}/orcamento-global").json()
    assert visao["orcamento_global"]["limite"] == 1000
    assert visao["politica"]["custo_unitario_brl"] == "0.674850000000" and visao["politica"]["preco_unitario_brl"] == "1.349700000000"
    assert visao["politica"]["preco_unitario_exibicao"] == "1.35" and visao["politica"]["margem_bruta_percentual"] == "50.000000000000"
    assert visao["lotes_compra"][0]["custo_total_brl"].startswith("269.94") and visao["lotes_compra"][0]["quantidade_creditos"] == 400
    comum = criar_usuario_autenticado(A, papel="admin", email="adm@x.com.br")
    for rota in (f"{ADMIN}/orcamento-global", f"{ADMIN}/politica", f"{ADMIN}/planos"):
        assert client.get(rota, headers=comum).status_code == 403
    assert client.put(f"{ADMIN}/orcamento-global", json={"provedor": "lusha", "limite_creditos": 9, "motivo": "tentativa"}, headers=comum).status_code == 403


def test_extrato_do_tenant_nao_traz_custo_nem_margem(client, db_session, fake_graph, prov_api):
    cenario(db_session)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    extrato = client.get(f"{URL}/movimentacoes").json()
    assert extrato and not any(k in str(extrato).lower() for k in ("custo", "markup", "margem", "valor_venda", "preco"))


def test_alteracao_do_orcamento_global_e_versionada_aprovada_e_auditada(client, db_session):
    from app.models.auditoria import AuditLog

    cenario(db_session, orcamento=100)
    r = client.put(f"{ADMIN}/orcamento-global", json={"provedor": "lusha", "limite_creditos": 300, "alerta_percentual": 70, "motivo": "contrato ampliado"})
    assert r.status_code == 200 and r.json()["versao"] == 2 and r.json()["aprovado"] is False
    assert config.orcamento_vigente(db_session, "lusha").limite_creditos == 100  # pendente: ainda vale a versão aprovada
    assert client.post(f"{ADMIN}/orcamento-global/{r.json()['id']}/aprovar").json()["aprovado"] is True
    assert config.orcamento_vigente(db_session, "lusha").limite_creditos == 300
    log = db_session.query(AuditLog).filter_by(evento_tipo="enriquecimento_orcamento_global_aprovado").order_by(AuditLog.id.desc()).first()
    assert log.detalhes["limite_anterior"] == 100 and log.detalhes["limite_novo"] == 300
    assert client.put(f"{ADMIN}/orcamento-global", json={"provedor": "lusha", "limite_creditos": 300, "motivo": ""}).status_code == 422


# =================================================== lotes de compra e política =======================================================


def test_lote_de_compra_guarda_custo_quantidade_data_e_referencia_e_nao_sobrescreve(client, db_session):
    primeiro = lote(db_session)
    assert (primeiro.quantidade_creditos, primeiro.referencia) == (400, "APORTE-TESTE-1") and Decimal(str(primeiro.custo_unitario_brl)) == Decimal("0.67485")
    segundo = config.registrar_lote_compra(db_session, provedor="lusha", referencia="APORTE-TESTE-2", quantidade_creditos=1000, custo_total_brl=Decimal("600"),
                                           comprado_em=datetime(2026, 11, 5), ator_id="1", tenant_auditoria=A)
    assert Decimal(str(segundo.custo_unitario_brl)) == Decimal("0.6")
    assert Decimal(str(db_session.get(EnriquecimentoLoteCompra, primeiro.id).custo_unitario_brl)) == Decimal("0.67485")  # o anterior segue intacto
    base = dict(provedor="lusha", referencia="X-1", quantidade_creditos=10, custo_total_brl=Decimal("1"), comprado_em=datetime(2026, 11, 6), ator_id="1", tenant_auditoria=A)
    with pytest.raises(ValidacaoFalhou, match="Já existe um lote"):
        config.registrar_lote_compra(db_session, **{**base, "referencia": "APORTE-TESTE-1"})
    for invalido in (dict(quantidade_creditos=0), dict(custo_total_brl=Decimal("0"))):
        with pytest.raises(ValidacaoFalhou):
            config.registrar_lote_compra(db_session, **{**base, **invalido})


def test_lote_e_historico_append_only(client, db_session):
    primeiro = lote(db_session)
    primeiro.custo_total_brl = Decimal("1")
    with pytest.raises(RuntimeError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_novo_lote_nao_muda_o_preco_vigente_so_uma_nova_politica_aprovada(client, db_session):
    cenario(db_session)
    config.registrar_lote_compra(db_session, provedor="lusha", referencia="APORTE-TESTE-2", quantidade_creditos=600, custo_total_brl=Decimal("480"),
                                 comprado_em=datetime(2026, 11, 5), ator_id="1", tenant_auditoria=A)
    assert config.politica_vigente(db_session, "lusha")[0].preco_unitario_brl == Decimal("1.3497")  # nada mudou sozinho
    nova = politica(db_session, metodo="media_ponderada", markup="100")  # (269,94 + 480) / 1000 = 0,74994; × 2 = 1,49988
    assert Decimal(str(nova.custo_unitario_brl)) == Decimal("0.74994") and config.politica_vigente(db_session, "lusha")[0].preco_unitario_brl == Decimal("1.49988")


def test_politica_valida_os_campos_e_exige_motivo(client, db_session):
    cenario(db_session)
    base = dict(provedor="lusha", creditos_busca_por_resultado=1, creditos_email=1, creditos_telefone=5, revelar_emails=True, revelar_telefones=True,
                tamanho_pagina_busca=10, creditos_cliente_por_credito_provedor=1, markup_percentual=Decimal("100"), metodo_custo="lote_referencia",
                lote_compra_id=lote(db_session).id, casas_exibicao=2, fonte_tarifas="manual", ator_id="1", tenant_auditoria=A, motivo="ok")
    for ajuste, trecho in [(dict(motivo=""), "motivo"), (dict(markup_percentual=None), "markup"), (dict(markup_percentual=Decimal("-1")), "markup"),
                           (dict(metodo_custo="chute"), "metodo_custo"), (dict(lote_compra_id=None), "lote de compra"),
                           (dict(creditos_cliente_por_credito_provedor=0), "maior ou igual a 1"), (dict(creditos_email=-1), "negativo"),
                           (dict(casas_exibicao=9), "casas_exibicao")]:
        with pytest.raises(ValidacaoFalhou, match=trecho):
            config.definir_politica(db_session, **{**base, **ajuste})
    sem_lote = {**base, "metodo_custo": "media_ponderada", "lote_compra_id": None}
    assert config.definir_politica(db_session, **sem_lote).metodo_custo == "media_ponderada"


def test_api_de_politica_lote_e_aprovacao(client, db_session, prov_api):
    r = client.post(f"{ADMIN}/lotes-compra", json={"provedor": "lusha", "referencia": "APORTE-API-1", "quantidade_creditos": 400, "custo_total_brl": "269.94",
                                                   "comprado_em": "2026-10-21T00:00:00"})
    assert r.status_code == 201 and r.json()["custo_unitario_brl"] == "0.674850000000"
    assert client.post(f"{ADMIN}/lotes-compra", json={"provedor": "lusha", "referencia": "APORTE-API-2", "quantidade_creditos": 1, "custo_total_brl": "abc",
                                                      "comprado_em": "2026-10-21T00:00:00"}).status_code == 422
    corpo = {"provedor": "lusha", "creditos_busca_por_resultado": 1, "creditos_email": 1, "creditos_telefone": 5, "revelar_emails": True, "revelar_telefones": True,
             "tamanho_pagina_busca": 10, "creditos_cliente_por_credito_provedor": 1, "markup_percentual": "100", "metodo_custo": "lote_referencia",
             "lote_compra_id": r.json()["id"], "motivo": "tarifas conferidas em account/usage"}
    pendente = client.put(f"{ADMIN}/politica", json=corpo)
    assert pendente.status_code == 200 and pendente.json()["aprovada"] is False and pendente.json()["preco_unitario_brl"] == "1.349700000000"
    assert config.politica_vigente(db_session, "lusha")[0] is None
    aprovada = client.post(f"{ADMIN}/politica/{pendente.json()['id']}/aprovar")
    assert aprovada.status_code == 200 and aprovada.json()["aprovada"] is True and config.politica_vigente(db_session, "lusha")[0].utilizavel
    assert client.put(f"{ADMIN}/politica", json={**corpo, "tamanho_pagina_busca": 5}).status_code == 422  # abaixo do mínimo do provedor


# =================================================== conciliação com o provedor ======================================================


def test_conciliacao_compara_o_uso_do_provedor_com_o_razao(client, db_session, fake_graph):
    cenario(db_session, franquia=20)
    prov = ProvedorPago(uso=UsoProvedor(creditos_total=400, creditos_usados=100, creditos_restantes=300, tarifas={"revealEmail": {"credits": 1, "perQuantity": 1}}))
    primeira = conciliacao.conciliar(db_session, prov, "1", A)
    assert primeira["divergencia"] is None and "Primeira leitura" in primeira["explicacao"]
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 2), prov)  # o razão registra 4 créditos do provedor
    prov.uso = UsoProvedor(creditos_total=400, creditos_usados=104, creditos_restantes=296)
    bateu = conciliacao.conciliar(db_session, prov, "1", A)
    assert (bateu["delta_provedor"], bateu["delta_razao"], bateu["divergencia"]) == (4, 4, 0) and "bate" in bateu["explicacao"]


def test_divergencia_entre_provedor_e_razao_vira_alerta_sem_ajuste_automatico(client, db_session, fake_graph, caplog):
    cenario(db_session, franquia=20)
    prov = ProvedorPago(uso=UsoProvedor(creditos_total=400, creditos_usados=100, creditos_restantes=300))
    conciliacao.conciliar(db_session, prov, "1", A)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), prov)  # razão: 2
    prov.uso = UsoProvedor(creditos_total=400, creditos_usados=109, creditos_restantes=291)  # o provedor diz 9
    saldo_antes = ledger.saldo(db_session, A)
    with caplog.at_level("ERROR", logger="b2bon.enriquecimento"):
        leitura = conciliacao.conciliar(db_session, prov, "1", A)
    assert (leitura["delta_provedor"], leitura["delta_razao"], leitura["divergencia"]) == (9, 2, 7) and "Divergência" in leitura["explicacao"]
    assert "ENRIQUECIMENTO_DIVERGENCIA_PROVEDOR" in caplog.text and ledger.saldo(db_session, A) == saldo_antes  # nada ajustado sozinho
    assert db_session.query(EnriquecimentoUsoProvedor).count() == 2
    assert client_visao_diverge(db_session)


def client_visao_diverge(db):
    return painel.visao_administrativa(db, "lusha")["leituras_de_uso"][0]["divergencia"] == 7


def test_provedor_sem_consulta_de_uso_nao_concilia(client, db_session):
    esperar_bloqueio("provedor_sem_consulta_de_uso", lambda: conciliacao.conciliar(db_session, ProvedorPago(), "1", A))


def test_falha_na_consulta_de_uso_nao_vaza_detalhe(client, db_session):
    class Quebrado(ProvedorPago):
        def consultar_uso(self):
            raise RuntimeError("api_key=segredo-123 falhou")

    erro = esperar_bloqueio("falha_consulta_uso_provedor", lambda: conciliacao.conciliar(db_session, Quebrado(), "1", A))
    assert "segredo" not in str(erro)


def test_api_de_conciliacao_e_tarifas_so_super_admin_e_provedor_certo(client, db_session, criar_usuario_autenticado):
    provedor = ProvedorPago(uso=UsoProvedor(creditos_total=10, creditos_usados=1, creditos_restantes=9, tarifas={"revealPhone": {"credits": 5, "perQuantity": 1}}))
    app.dependency_overrides[get_contact_enrichment_provider] = lambda: provedor
    assert client.get(f"{ADMIN}/provedores/lusha/tarifas-do-provedor").json()["tarifas"]["revealPhone"]["credits"] == 5
    assert client.post(f"{ADMIN}/provedores/lusha/conciliar").status_code == 200
    assert client.post(f"{ADMIN}/provedores/outro/conciliar").status_code == 422
    comum = criar_usuario_autenticado(A, papel="admin", email="adm@x.com.br")
    assert client.post(f"{ADMIN}/provedores/lusha/conciliar", headers=comum).status_code == 403
    assert client.get(f"{ADMIN}/provedores/lusha/tarifas-do-provedor", headers=comum).status_code == 403


# =================================================== razão, franquia, separação =======================================================


def test_razao_e_append_only(client, db_session, fake_graph):
    cenario(db_session)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    mov = db_session.query(EnriquecimentoMovimento).first()
    mov.motivo = "adulterado"
    with pytest.raises(RuntimeError, match="append-only"):
        db_session.commit()
    db_session.rollback()
    db_session.delete(db_session.query(EnriquecimentoMovimento).first())
    with pytest.raises(RuntimeError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_franquia_mensal_e_idempotente_e_renova_sem_duplicar(client, db_session):
    cenario(db_session, franquia=10)
    cfg, _ = config.config_vigente(db_session, A)
    hoje = config.agora_utc()
    ledger.preparar(db_session, A, cfg, hoje)
    ledger.preparar(db_session, A, cfg, hoje)
    db_session.commit()
    assert tipos(db_session) == ["CONCESSAO"] and ledger.disponivel(db_session, A) == 10
    mes_que_vem = (hoje.replace(day=1) + timedelta(days=32)).replace(day=2)
    ledger.preparar(db_session, A, cfg, mes_que_vem)
    db_session.commit()
    assert tipos(db_session) == ["CONCESSAO", "EXPIRACAO", "RENOVACAO"]  # o que não foi usado venceu, sem rollover
    assert ledger.disponivel(db_session, A) == 10
    invariantes(db_session)


def test_franquia_unica_para_poc_e_free_trial_e_concedida_uma_vez(client, db_session):
    cenario(db_session, franquia=5, periodicidade="unica")
    cfg, _ = config.config_vigente(db_session, A)
    for dias in (0, 40, 400):
        ledger.preparar(db_session, A, cfg, config.agora_utc() + timedelta(days=dias))
    db_session.commit()
    assert tipos(db_session) == ["CONCESSAO"] and ledger.disponivel(db_session, A) == 5


def test_expiracao_nao_toca_no_que_esta_reservado(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov, solic = ProvedorPago(), eu(db_session)
    confirmar(db_session, solic, previa(db_session, solic, contas(db_session, 2), prov), prov)  # reserva 4
    cfg, _ = config.config_vigente(db_session, A)
    ledger.preparar(db_session, A, cfg, (config.agora_utc().replace(day=1) + timedelta(days=32)).replace(day=2))
    db_session.commit()
    assert ledger.reservado(db_session, A) == 4 and ledger.disponivel(db_session, A) >= 0
    invariantes(db_session)


def test_ajuste_e_estorno_administrativos_exigem_motivo_e_respeitam_limites(client, db_session, fake_graph, prov_api):
    cenario(db_session, franquia=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    assert client.post(f"{ADMIN}/tenants/{A}/ajustes", json={"quantidade": 5, "motivo": "cortesia comercial"}).status_code == 200
    assert ledger.disponivel(db_session, A) == 13
    assert client.post(f"{ADMIN}/tenants/{A}/ajustes", json={"quantidade": -100, "motivo": "débito grande"}).status_code == 422
    assert client.post(f"{ADMIN}/tenants/{A}/ajustes", json={"quantidade": 0, "motivo": "zero aqui"}).status_code == 422
    assert client.post(f"{ADMIN}/tenants/{A}/estornos", json={"quantidade": 3, "motivo": "crédito do provedor", "pesquisa_id": p.id}).status_code == 422  # só 2 consumidos
    assert client.post(f"{ADMIN}/tenants/{A}/estornos", json={"quantidade": 1, "motivo": "crédito do provedor", "pesquisa_id": p.id,
                                                              "provedor_devolvidos": 1}).status_code == 200
    assert ledger.disponivel(db_session, A) == 14 and ledger.situacao_global(db_session, "lusha")["consumido"] == 1  # o provedor devolveu 1
    invariantes(db_session)


def test_enriquecimento_e_ia_sao_contabilidades_separadas(client, db_session, fake_graph):
    from app.contexts.finops import carteira
    from app.contexts.finops.comercial import TipoLote

    cenario(db_session, franquia=10)
    antes = (db_session.query(CarteiraCreditos).count(), db_session.query(LoteCreditos).count(), db_session.query(MovimentoCredito).count(),
             db_session.query(ExecucaoIa).count())
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    assert (db_session.query(CarteiraCreditos).count(), db_session.query(LoteCreditos).count(), db_session.query(MovimentoCredito).count(),
            db_session.query(ExecucaoIa).count()) == antes  # consumir enriquecimento não toca a carteira de IA
    disponivel_enriquecimento = ledger.disponivel(db_session, A)
    carteira.conceder(db_session, A, TipoLote.PROMOTIONAL, Decimal(500), "teste")
    db_session.commit()
    assert ledger.disponivel(db_session, A) == disponivel_enriquecimento  # e créditos de IA não viram créditos de enriquecimento


# =================================================== isolamento, permissões, painel ===================================================


def test_pesquisa_de_um_tenant_nao_aparece_para_outro(client, db_session, fake_graph, criar_usuario_autenticado, prov_api):
    cenario(db_session)
    preparar_tenant_b(db_session)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    outro = criar_usuario_autenticado(B, papel="admin", email="adm@b.com.br")
    assert client.get(f"{URL}/{p.id}", headers=outro).status_code == 404
    assert client.get(f"{URL}", headers=outro).json() == []
    assert client.post(f"{URL}/{p.id}/cancelar", headers=outro).status_code == 404
    assert client.post(f"{URL}/{p.id}/retomar", headers=outro).status_code == 404
    assert client.get(f"{URL}/movimentacoes", headers=outro).json() == []
    painel_b = client.get(f"{URL}/painel", headers=outro).json()
    assert painel_b["creditos"]["consumido_no_periodo"] == 0 and painel_b["pesquisas_por_estado"] == {}


def test_confirmar_pesquisa_de_outro_tenant_e_negado(client, db_session, criar_usuario_autenticado, prov_api):
    cenario(db_session)
    preparar_tenant_b(db_session)
    p = previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago())
    outro = criar_usuario_autenticado(B, papel="admin", email="adm@b.com.br")
    r = client_post_confirmar(client, p, outro)
    assert r.status_code == 404 and db_session.get(PesquisaDecisores, p.id).estado == "criada"


def client_post_confirmar(client, p, headers):
    return client.post(f"{URL}/{p.id}/confirmar", json={"selecao_hash": p.selecao_hash, "idempotency_key": "chave-roubada-1"}, headers=headers)


def test_vendedor_so_ve_as_proprias_pesquisas_e_nao_ve_o_extrato(client, db_session, fake_graph, criar_usuario_autenticado, prov_api):
    cenario(db_session)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    vendedor = criar_usuario_autenticado(A, papel="user", email="vendedor@x.com.br")
    assert client.get(f"{URL}", headers=vendedor).json() == []
    assert client.get(f"{URL}/movimentacoes", headers=vendedor).status_code == 403
    assert client.get(f"{URL}/painel", headers=vendedor).json()["pesquisas_por_estado"] == {}
    assert len(client.get(f"{URL}").json()) == 1  # o admin (super_admin do teste) vê


def test_so_o_criador_ou_gestor_confirma(client, db_session, criar_usuario_autenticado, prov_api):
    cenario(db_session)
    p = previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago())
    vendedor = criar_usuario_autenticado(A, papel="user", email="vendedor@x.com.br")
    assert client.post(f"{URL}/{p.id}/confirmar", json={"selecao_hash": p.selecao_hash, "idempotency_key": "chave-vendedor"}, headers=vendedor).status_code == 404


def test_rotas_administrativas_exigem_super_admin(client, db_session, criar_usuario_autenticado):
    cenario(db_session)
    comum = criar_usuario_autenticado(A, papel="admin", email="adm@x.com.br")
    for metodo, caminho, corpo in [
        ("put", f"{ADMIN}/config", {"plano_id": 1, "motivo": "tentativa"}),
        ("get", f"{ADMIN}/config", None),
        ("post", f"{ADMIN}/config/1/aprovar", None),
        ("post", f"{ADMIN}/orcamento-global/1/aprovar", None),
        ("post", f"{ADMIN}/politica/1/aprovar", None),
        ("put", f"{ADMIN}/politica", {"provedor": "lusha", "markup_percentual": "100", "metodo_custo": "media_ponderada", "motivo": "tentativa"}),
        ("post", f"{ADMIN}/lotes-compra", {"provedor": "lusha", "referencia": "XXX", "quantidade_creditos": 1, "custo_total_brl": "1", "comprado_em": "2026-10-21T00:00:00"}),
        ("post", f"{ADMIN}/tenants/{A}/ajustes", {"quantidade": 9, "motivo": "tentativa"}),
        ("post", f"{ADMIN}/tenants/{A}/estornos", {"quantidade": 1, "motivo": "tentativa"}),
        ("post", f"{ADMIN}/pesquisas/x/itens/1/reconciliar", {"creditos_provedor_consumidos": 0, "motivo": "tentativa"}),
        ("post", f"{ADMIN}/pesquisas/x/encerrar-reconciliacao", {"motivo": "tentativa"}),
    ]:
        assert getattr(client, metodo)(caminho, headers=comum, **({"json": corpo} if corpo else {})).status_code == 403, caminho


def test_painel_do_tenant_mostra_franquia_saldos_fontes_pesquisas_e_estimado_vs_consumido(client, db_session, fake_graph, prov_api):
    cenario(db_session, franquia=10, limite_periodo=3)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([ok(1)]))
    d = client.get(f"{URL}/painel").json()
    assert d["plano"]["franquia_creditos"] == 10 and d["plano"]["disponivel"] is True and d["lusha"] == {"disponivel": True, "motivos": []}
    assert d["creditos"] == {"disponivel": 9, "reservado": 0, "saldo": 9, "consumido_no_periodo": 1, "expirado_no_periodo": 0, "concedido_no_periodo": 10,
                            "comprado_no_periodo": 0}
    assert d["pesquisas_por_estado"] == {"concluida": 1} and d["estimado_vs_reconciliado"] == {"estimado_maximo": 2, "consumido": 1}
    assert "AI Credits" in d["categorias"]["ia"] and set(d["uso_por_fonte"]) <= {"receita_qsa", "brasilapi", "lusha"}
    extrato = client.get(f"{URL}/movimentacoes", params={"tipo": "CONSUMO"}).json()
    assert [m["delta_saldo"] for m in extrato] == [-1] and extrato[0]["creditos_provedor"] == 1
    assert d["alertas"] == []


@pytest.mark.parametrize("montar,codigo", [
    (lambda db: None, "plano_sem_configuracao"),
    (lambda db: cenario(db, com_politica=False, orcamento=None), "politica_provedor_nao_configurada"),
    (lambda db: cenario(db, orcamento=None), "orcamento_global_nao_configurado"),
])
def test_painel_explica_por_que_a_pesquisa_lusha_esta_indisponivel(client, db_session, prov_api, montar, codigo):
    montar(db_session)
    d = client.get(f"{URL}/painel").json()
    assert d["lusha"]["disponivel"] is False and codigo in [m["codigo"] for m in d["lusha"]["motivos"]]
    assert all(m["mensagem"] for m in d["lusha"]["motivos"]) and d["alertas"][0]["codigo"] == "pesquisa_lusha_indisponivel"


def test_previa_pela_api_traz_estimativa_completa_e_codigos_estaveis_de_bloqueio(client, db_session, prov_api):
    c = contas(db_session, 1)
    r = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id]})
    assert r.status_code == 409 and r.json()["codigo"] == "plano_sem_configuracao" and r.json()["bloqueios"][0]["codigo"] == "plano_sem_configuracao"
    cenario(db_session)
    r = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id], "decisores_por_empresa": 3})
    assert r.status_code == 201 and r.json()["estado"] == "criada" and r.json()["estimativa"]["decisores_por_empresa"] == 3


def test_pesquisa_inexistente_responde_404(client, db_session):
    cenario(db_session)
    with pytest.raises(NaoEncontrado):
        pesquisa.obter(db_session, A, eu(db_session), "nao-existe")


def test_precisao_decimal_de_ponta_a_ponta(client, db_session, fake_graph):
    """Nada passa por float: custo 269,94/400 e markup 100% chegam ao razão exatos."""
    cenario(db_session, franquia=1000)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([ok(2, medido=400)]))
    consumo = db_session.query(EnriquecimentoMovimento).filter_by(tipo="CONSUMO").one()
    assert Decimal(str(consumo.custo_total_brl)) == Decimal("269.94") and Decimal(str(consumo.valor_venda_brl)) == precos.valor(400, "1.3497")


# ============================================================ dados a revelar escolhidos pelo usuário em cada pesquisa ===================


def test_padrao_revela_so_o_email_e_o_provedor_recebe_so_emails(client, db_session, fake_graph):
    cenario(db_session, franquia=100, telefone=5, revelar_telefones=True)  # a política OFERECE telefone, mas o usuário não marcou
    prov = ProvedorPago()
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), prov, d=3)
    assert (p.revelar_emails, p.revelar_telefones) == (True, False) and prov.chamadas[0].revelar == ["emails"]
    assert p.estimativa["creditos_maximos"] == 3 and p.estimativa["dados_a_revelar"]["rotulo"] == "só e-mail"


@pytest.mark.parametrize("emails,telefones,esperado,teto,rotulo", [
    (True, True, ["emails", "phones"], 2 * (1 + 5), "e-mail e telefone"),
    (False, True, ["phones"], 2 * 5, "só telefone"),
    (True, False, ["emails"], 2 * 1, "só e-mail"),
])
def test_cada_combinacao_escolhida_vai_ao_provedor_e_define_o_teto_da_reserva(client, db_session, fake_graph, emails, telefones, esperado, teto, rotulo):
    cenario(db_session, franquia=100, telefone=5, revelar_telefones=True)
    prov = ProvedorPago()
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), prov, d=2, revelar_emails=emails, revelar_telefones=telefones)
    assert prov.chamadas[0].revelar == esperado and p.estimativa["creditos_maximos"] == teto and p.estimativa["dados_a_revelar"]["rotulo"] == rotulo
    assert p.creditos_reservados == 0 or p.estado == "concluida"


def test_a_mesma_selecao_com_dados_diferentes_gera_outro_hash(client, db_session):
    cenario(db_session, franquia=100, telefone=5, revelar_telefones=True)
    cs, solic, prov = contas(db_session, 1), eu(db_session), ProvedorPago()
    so_email = previa(db_session, solic, cs, prov, d=2)
    ambos = previa(db_session, solic, cs, prov, d=2, revelar_telefones=True)
    assert so_email.selecao_hash != ambos.selecao_hash
    with pytest.raises(PesquisaBloqueada):  # confirmar a prévia "só e-mail" com o hash da outra seleção é recusado
        pesquisa.confirmar(db_session, solicitante=solic, pesquisa_id=so_email.id, selecao_hash=ambos.selecao_hash, idempotency_key="chave-de-teste-1", provider=prov)


def test_nenhum_dado_marcado_ou_telefone_nao_oferecido_nao_geram_pesquisa(client, db_session):
    cenario(db_session, franquia=100)  # política sem tarifa de telefone: o provedor não o oferece
    cs, solic, prov = contas(db_session, 1), eu(db_session), ProvedorPago()
    with pytest.raises(ValidacaoFalhou, match="ao menos um dado"):
        previa(db_session, solic, cs, prov, revelar_emails=False, revelar_telefones=False)
    with pytest.raises(ValidacaoFalhou, match="telefone não está disponível"):
        previa(db_session, solic, cs, prov, revelar_telefones=True)
    assert db_session.query(PesquisaDecisores).count() == 0 and prov.chamadas == []


def test_decisor_so_com_email_nao_conta_como_obtido_quando_o_usuario_pede_telefone(client, db_session, fake_graph):
    cenario(db_session, franquia=100, telefone=5, revelar_telefones=True)
    c = contas(db_session, 1)[0]
    db_session.add(Decisor(tenant_id=A, conta_id=c.id, nome="Só e-mail", email="a@exemplo.com.br", origem="lusha"))
    db_session.commit()
    solic, prov = eu(db_session), ProvedorPago()
    assert previa(db_session, solic, [c], prov, d=1).estimativa["empresas_a_consultar"] == 0  # e-mail pedido: já tem
    pedindo_telefone = previa(db_session, solic, [c], prov, d=1, revelar_emails=False, revelar_telefones=True)
    assert pedindo_telefone.estimativa["empresas_a_consultar"] == 1  # telefone pedido: ainda falta


def test_link_do_linkedin_chega_ao_decisor_e_a_contagem_aparece_por_empresa(client, db_session, fake_graph):
    cenario(db_session, franquia=100)
    contatos = [ContatoCandidato(nome="Ana Souza", cargo="CEO", email="ana@x.com.br", linkedin_url="https://www.linkedin.com/in/ana", fonte="lusha"),
                ContatoCandidato(nome="Beto Lima", cargo="CFO", email="beto@x.com.br", fonte="lusha")]
    resultado = ResultadoBuscaContatos(estado="ok", ids_provedor=["1", "2"], creditos_provedor=2, contatos=contatos)
    c = contas(db_session, 1)[0]
    p = rodar(db_session, fake_graph, eu(db_session), [c], ProvedorPago([resultado]), d=2)
    item = pesquisa.itens_de(db_session, p.id)[0]
    assert (item.decisores_retornados, item.decisores_com_linkedin) == (2, 1)
    ana = db_session.query(Decisor).filter_by(conta_id=c.id, nome="Ana Souza").one()
    assert ana.linkedin_url == "https://www.linkedin.com/in/ana" and ana.canal_provavel == "email"


def test_so_telefone_define_o_canal_provavel_como_whatsapp(client, db_session, fake_graph):
    cenario(db_session, franquia=100, telefone=5, revelar_telefones=True)
    resultado = ResultadoBuscaContatos(estado="ok", ids_provedor=["1"], creditos_provedor=5,
                                       contatos=[ContatoCandidato(nome="Carla Dias", cargo="COO", telefone="+5511999990000", fonte="lusha")])
    c = contas(db_session, 1)[0]
    rodar(db_session, fake_graph, eu(db_session), [c], ProvedorPago([resultado]), d=1, revelar_emails=False, revelar_telefones=True)
    assert db_session.query(Decisor).filter_by(conta_id=c.id, nome="Carla Dias").one().canal_provavel == "whatsapp"


def test_api_aceita_os_dados_a_revelar_e_o_painel_informa_o_que_cada_dado_custa(client, db_session, prov_api):
    cenario(db_session, franquia=100, telefone=5, revelar_telefones=True)
    c = contas(db_session, 1)[0]
    r = client.post(f"{URL}/previa", json={"conta_ids": [c.id], "decisores_por_empresa": 2, "revelar_emails": True, "revelar_telefones": True})
    assert r.status_code == 201 and r.json()["estimativa"]["dados_a_revelar"] == {"emails": True, "telefones": True, "rotulo": "e-mail e telefone",
                                                                                 "creditos_por_decisor": 6}
    assert client.get(f"{URL}/{r.json()['id']}").json()["dados_a_revelar"] == {"emails": True, "telefones": True}
    dados = client.get(f"{URL}/painel").json()["dados_a_revelar"]
    assert dados["emails"] == {"disponivel": True, "creditos_por_decisor": 1} and dados["telefones"] == {"disponivel": True, "creditos_por_decisor": 5}
    assert "LinkedIn" in dados["linkedin"]
    assert client.post(f"{URL}/previa", json={"conta_ids": [c.id], "revelar_emails": False, "revelar_telefones": False}).status_code == 422



# ============================================================ pacote adicional muda o limite por pesquisa; super admin sem limites =========

AGORA_PACOTE = datetime(2026, 10, 15, 15, 0)


def comprar_pacote(db, tenant, creditos, agora=AGORA_PACOTE, compra_id=1):
    """Pacote já pago (como o webhook do Mercado Pago o credita): saldo adicional com validade de 30 dias."""
    ledger.travar_carteira(db, tenant)
    ledger.conceder_compra(db, tenant, compra_id, creditos, agora + timedelta(days=ledger.VALIDADE_PACOTE_DIAS), f"ENRIQ_{creditos}", agora)
    db.commit()


def test_pacote_de_3000_faz_o_limite_do_starter_ser_3000_ate_acabar_e_depois_volta_ao_do_plano(client, db_session):
    cenario(db_session, franquia=30, itens=None, maximo=5, limite_pesquisa=30, orcamento=6800)
    solic, prov = eu(db_session), ProvedorPago()
    cs = contas(db_session, 40)
    antes = previa(db_session, solic, cs, prov, d=1, agora=AGORA_PACOTE)  # 40 créditos > 30 do plano
    assert antes.estimativa["viavel"] is False and antes.estimativa["bloqueios"][0]["codigo"] == "limite_por_pesquisa"
    comprar_pacote(db_session, A, 3000)
    com = previa(db_session, solic, cs, prov, d=1, agora=AGORA_PACOTE)
    assert com.estimativa["viavel"] is True
    assert (com.estimativa["limites"]["limite_creditos_pesquisa"], com.estimativa["limites"]["limite_origem"]) == (3000, "pacote")
    assert com.estimativa["limites"]["decisores_por_empresa_max"] == 5  # só o limite de créditos por pesquisa muda
    # consumiu todo o crédito (franquia 30 + pacote 3000): o limite volta ao do plano, mesmo antes dos 30 dias
    ledger.travar_carteira(db_session, A)
    ledger.lancar(db_session, A, "CONSUMO", delta_saldo=-3030, agora=AGORA_PACOTE)
    db_session.commit()
    depois = previa(db_session, solic, cs, prov, d=1, agora=AGORA_PACOTE)
    assert (depois.estimativa["limites"]["limite_creditos_pesquisa"], depois.estimativa["limites"]["limite_origem"]) == (30, "plano")
    assert "limite_por_pesquisa" in [b["codigo"] for b in depois.estimativa["bloqueios"]]


def test_limite_do_pacote_termina_aos_30_dias_mesmo_com_credito_sobrando(client, db_session):
    cenario(db_session, franquia=30, itens=None, maximo=5, limite_pesquisa=30, orcamento=6800)
    solic, prov, cs = eu(db_session), ProvedorPago(), contas(db_session, 40)
    comprar_pacote(db_session, A, 3000)
    dia_29 = previa(db_session, solic, cs, prov, d=1, agora=AGORA_PACOTE + timedelta(days=29))
    assert dia_29.estimativa["limites"]["limite_creditos_pesquisa"] == 3000 and dia_29.estimativa["viavel"] is True
    dia_31 = previa(db_session, solic, cs, prov, d=1, agora=AGORA_PACOTE + timedelta(days=31))
    assert dia_31.estimativa["limites"]["limite_creditos_pesquisa"] == 30 and dia_31.estimativa["viavel"] is False
    assert ledger.composicao(db_session, A, AGORA_PACOTE + timedelta(days=31))["adicional_restante"] == 0  # o saldo do pacote também venceu


def test_pacote_menor_que_o_limite_do_plano_nao_reduz_o_limite(client, db_session):
    cenario(db_session, franquia=500, itens=None, maximo=5, limite_pesquisa=500, orcamento=6800)
    comprar_pacote(db_session, A, 400)
    p = previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=1, agora=AGORA_PACOTE)
    assert (p.estimativa["limites"]["limite_creditos_pesquisa"], p.estimativa["limites"]["limite_origem"]) == (500, "plano")


def test_dois_pacotes_ativos_somam_o_limite(client, db_session):
    cenario(db_session, franquia=30, itens=None, maximo=5, limite_pesquisa=30, orcamento=6800)
    comprar_pacote(db_session, A, 400, compra_id=1)
    comprar_pacote(db_session, A, 660, compra_id=2)
    p = previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=1, agora=AGORA_PACOTE)
    assert p.estimativa["limites"]["limite_creditos_pesquisa"] == 1060


def test_painel_mostra_o_limite_vigente_e_a_validade_dos_pacotes(client, db_session, prov_api):
    cenario(db_session, franquia=30, itens=None, maximo=5, limite_pesquisa=30, orcamento=6800)
    agora = config.agora_utc()
    comprar_pacote(db_session, A, 3000, agora=agora)
    d = client.get(f"{URL}/painel").json()
    assert (d["plano"]["limite_creditos_pesquisa"], d["plano"]["limite_origem"]) == (3000, "pacote")
    assert d["composicao"]["adicional_restante"] == 3000 and d["composicao"]["pacotes_ativos"][0]["creditos"] == 3000
    assert d["composicao"]["adicional_expira_em"] == (agora + timedelta(days=30)).isoformat()


def liberar_super_admin(db, monkeypatch, *, orcamento=6800):
    monkeypatch.setattr(settings, "enriquecimento_super_admin_sem_limites", True)
    custo_contratual(db)
    politica(db)
    config.definir_orcamento_global(db, provedor="lusha", limite_creditos=orcamento, alerta_percentual=80, ator_id="1", tenant_auditoria=A, motivo="teste",
                                    aprovar=True)


def test_super_admin_pesquisa_sem_plano_sem_saldo_e_sem_limites_e_os_demais_continuam_limitados(client, db_session, fake_graph, monkeypatch):
    liberar_super_admin(db_session, monkeypatch)  # nenhum plano configurado, nenhuma franquia, saldo zero
    cs = contas(db_session, 12)
    sa = eu(db_session, papel="super_admin")
    p = rodar(db_session, fake_graph, sa, cs, ProvedorPago(), d=10)  # 12 empresas × 10 decisores: acima de qualquer plano da matriz
    assert p.estado == "concluida" and p.config_origem == "super_admin" and p.estimativa["limites"]["limite_creditos_pesquisa"] is None
    assert p.creditos_consumidos == 120 and ledger.disponivel(db_session, A) == 0
    concessao = db_session.query(EnriquecimentoMovimento).filter_by(origem="super_admin").one()
    assert (concessao.tipo, concessao.delta_saldo) == ("CONCESSAO", 120)  # só o necessário, rastreado
    invariantes(db_session)
    # o mesmo pedido de um admin do tenant (sem plano configurado) é recusado
    with pytest.raises(PesquisaBloqueada) as erro:
        previa(db_session, eu(db_session, papel="admin"), cs, ProvedorPago(), d=2)
    assert erro.value.codigo == "plano_sem_configuracao"


def test_super_admin_ignora_limites_do_plano_mas_vendedor_e_admin_nao(client, db_session, monkeypatch):
    liberar_super_admin(db_session, monkeypatch)
    config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="teste", aprovar=True, campos=dict(
        franquia_creditos=10, periodicidade="mensal", decisores_por_empresa_padrao=2, decisores_por_empresa_max=3, itens_por_lote_max=2,
        limite_periodo_creditos=10, limite_creditos_pesquisa=10, limite_pesquisas_periodo=1, limite_empresas_periodo=2, limite_contatos_periodo=5))
    cs, prov = contas(db_session, 5), ProvedorPago()
    p = previa(db_session, eu(db_session, papel="super_admin"), cs, prov, d=8)
    assert p.estimativa["viavel"] is True and p.estimativa["bloqueios"] == []
    for papel in ("admin", "user"):
        with pytest.raises(ValidacaoFalhou, match="excede o máximo do seu plano"):
            previa(db_session, eu(db_session, papel=papel), cs, prov, d=8)
    ok_dentro = previa(db_session, eu(db_session, papel="user"), cs[:2], prov, d=2)
    assert ok_dentro.estimativa["viavel"] is True  # dentro do plano, o usuário comum pesquisa normalmente


def test_orcamento_global_do_provedor_continua_valendo_para_o_super_admin(client, db_session, monkeypatch):
    liberar_super_admin(db_session, monkeypatch, orcamento=50)
    p = previa(db_session, eu(db_session, papel="super_admin"), contas(db_session, 12), ProvedorPago(), d=10)  # teto de 120 > 50 do orçamento global
    assert p.estimativa["viavel"] is False and p.estimativa["bloqueios"][0]["codigo"] == "orcamento_global_esgotado"


def test_painel_do_super_admin_mostra_a_pesquisa_liberada_sem_limites(client, db_session, prov_api, monkeypatch):
    liberar_super_admin(db_session, monkeypatch)  # o usuário padrão da fixture `client` é super_admin
    d = client.get(f"{URL}/painel").json()
    assert d["lusha"]["disponivel"] is True and d["plano"]["disponivel"] is True and d["plano"]["origem"] == "super_admin"
    assert d["plano"]["limite_creditos_pesquisa"] is None and d["plano"]["itens_por_lote_max"] is None and d["plano"]["decisores_por_empresa_max"] == 10
