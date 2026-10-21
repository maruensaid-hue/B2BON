"""Governança de créditos de enriquecimento: configuração ausente/inválida, seleção explícita, decisores por empresa, estimativa e confirmação,
reserva atômica e idempotente, falhas/ambiguidade/reconciliação, deduplicação, orçamento global, separação IA × enriquecimento, isolamento de
tenant e permissões. Provedor sempre simulado: nenhuma chamada real, nenhum orçamento real."""

from datetime import timedelta

import pytest

from app.api.deps import get_contact_enrichment_provider
from app.contexts.enriquecimento import config, execucao, ledger, painel, pesquisa
from app.contexts.enriquecimento.pesquisa import Solicitante
from app.core.config import settings
from app.main import app
from app.models.carteira_creditos import CarteiraCreditos, MovimentoCredito
from app.models.conta import Conta
from app.models.creditos_ia import ExecucaoIa, LoteCreditos
from app.models.decisor import Decisor
from app.models.enriquecimento_creditos import (
    EnriquecimentoMovimento,
    PesquisaDecisores,
    PesquisaDecisoresEmpresa,
)
from app.models.plano import Plano
from app.models.usuario import Usuario
from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, ResultadoBuscaContatos
from app.services.errors import NaoEncontrado, PesquisaBloqueada, ValidacaoFalhou

A, B = "tenant-teste", "tenant-outro"
URL = "/api/v1/pesquisas-decisores"
ADMIN = "/api/v1/admin/enriquecimento"


class ProvedorPago(ContactEnrichmentProvider):
    """Duplo do provedor com custo por contato. Sem roteiro, revela exatamente `limite_contatos` por empresa."""

    nome_provedor = "lusha"
    pago = True
    max_contatos_por_consulta = 20

    def __init__(self, roteiro=None):
        self.chamadas = []
        self.roteiro = list(roteiro or [])

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
            estado="ok", ids_provedor=[f"id{i}" for i in range(n)],
            contatos=[ContatoCandidato(nome=f"{filtro.nome_empresa} Pessoa {i}", cargo="CEO", email=f"p{i}@{filtro.dominio}", fonte="lusha") for i in range(n)],
        )


def ok(n, prefixo="Fulano"):
    return ResultadoBuscaContatos(estado="ok", ids_provedor=[f"i{k}" for k in range(n)],
                                  contatos=[ContatoCandidato(nome=f"{prefixo} {k}", cargo="CEO", fonte="lusha") for k in range(n)])


def erro_seguro():
    return ResultadoBuscaContatos(estado="erro_seguro", detalhe="revelacao_rejeitada")


def ambiguo():
    return ResultadoBuscaContatos(estado="ambiguo", detalhe="revelacao_timeout", ids_provedor=["x1"])


def sem_resultados():
    return ResultadoBuscaContatos(estado="sem_resultados")


def plano_id(db):
    return db.query(Plano).filter_by(nome="Plano Padrão Teste").one().id


def cenario(db, *, franquia=10, itens=10, padrao=2, maximo=5, limite_periodo=None, orcamento=1000, periodicidade="mensal"):
    config.definir_config(db, plano_id=plano_id(db), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="teste", campos=dict(
        franquia_creditos=franquia, periodicidade=periodicidade, decisores_por_empresa_padrao=padrao, decisores_por_empresa_max=maximo,
        itens_por_lote_max=itens, limite_periodo_creditos=limite_periodo))
    if orcamento is not None:
        config.definir_orcamento_global(db, provedor="lusha", limite_creditos=orcamento, alerta_percentual=80, ator_id="1", tenant_auditoria=A, motivo="teste")


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


def previa(db, solic, ids, prov, d=None, agora=None):
    return pesquisa.estimar(db, solicitante=solic, conta_ids=[c.id if hasattr(c, "id") else c for c in ids], decisores_por_empresa=d, provider=prov, agora=agora)


def confirmar(db, solic, p, prov, chave="chave-de-teste-1", agora=None):
    return pesquisa.confirmar(db, solicitante=solic, pesquisa_id=p.id, selecao_hash=p.selecao_hash, idempotency_key=chave, provider=prov, agora=agora)


def rodar(db, graph, solic, ids, prov, d=None, chave="chave-de-teste-1"):
    p = previa(db, solic, ids, prov, d)
    p = confirmar(db, solic, p, prov, chave)
    return execucao.executar(db, tenant_id=solic.tenant_id, pesquisa_id=p.id, provider=prov, graph=graph, ator_id=str(solic.id))


def esperar_bloqueio(codigo, funcao):
    with pytest.raises(PesquisaBloqueada) as erro:
        funcao()
    assert erro.value.codigo == codigo, (erro.value.codigo, str(erro.value))
    return erro.value


def invariantes(db, tenant=A):
    """Saldo e reservado são somas do razão; o reservado é exatamente o que as empresas em aberto seguram."""
    movs = db.query(EnriquecimentoMovimento).filter_by(tenant_id=tenant).all()
    assert ledger.saldo(db, tenant) == sum(m.delta_saldo for m in movs)
    assert ledger.reservado(db, tenant) == sum(m.delta_reservado for m in movs)
    em_aberto = sum(i.creditos_reservados for i in db.query(PesquisaDecisoresEmpresa).filter_by(tenant_id=tenant).all()
                    if i.estado in ("pendente", "enviado", "ambiguo"))
    assert ledger.reservado(db, tenant) == em_aberto
    assert ledger.disponivel(db, tenant) >= 0


def tipos(db, tenant=A):
    return [m.tipo for m in db.query(EnriquecimentoMovimento).filter_by(tenant_id=tenant).order_by(EnriquecimentoMovimento.id).all()]


# =================================================== configuração ausente / inválida =================================================


def test_sem_configuracao_do_plano_a_previa_e_bloqueada_e_nada_e_chamado(client, db_session):
    prov, cs = ProvedorPago(), contas(db_session, 1)
    e = esperar_bloqueio("plano_sem_configuracao", lambda: previa(db_session, eu(db_session), cs, prov))
    assert "comercial" in str(e)
    assert prov.chamadas == [] and db_session.query(PesquisaDecisores).count() == 0


def test_configuracao_incompleta_bloqueia_e_diz_o_que_falta(client, db_session):
    config.definir_config(db_session, plano_id=plano_id(db_session), tenant_id=None, ator_id="1", tenant_auditoria=A, motivo="rascunho",
                          campos=dict(franquia_creditos=5, periodicidade="mensal"))
    e = esperar_bloqueio("config_incompleta", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago()))
    assert "decisores_por_empresa_max" in str(e) and "itens_por_lote_max" in str(e)


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
    cenario(db_session, franquia=20, maximo=5, orcamento=None)  # nova versão do plano
    vigente, _ = config.config_vigente(db_session, A)
    assert vigente.versao == 2 and vigente.franquia_creditos == 20 and vigente.origem == "plano"
    config.definir_config(db_session, plano_id=None, tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="contrato Corporate", campos=dict(
        franquia_creditos=500, periodicidade="mensal", decisores_por_empresa_padrao=3, decisores_por_empresa_max=10, itens_por_lote_max=50))
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


# =================================================== seleção explícita ================================================================


def test_icp_inteiro_nao_dispara_pesquisa_a_api_so_aceita_lista_explicita(client, db_session):
    cenario(db_session)
    for corpo in ({"icp_id": 1}, {"todas": True}, {"conta_ids": [], "decisores_por_empresa": 1}, {"conta_ids": [1], "icp_id": 3}):
        assert client.post(f"{URL}/previa", json=corpo).status_code == 422, corpo
    assert db_session.query(PesquisaDecisores).count() == 0


def test_mapeamento_avulso_e_fila_automatica_nunca_chamam_o_provedor_pago(client, db_session, fake_graph, fake_account_data, fake_plan_limits,
                                                                        fake_llm, fake_site_fetcher, fake_web_search):
    """Importar planilha/gerar lista/enriquecer enfileira contas, mas a Lusha só é chamada por pesquisa confirmada: o QSA continua de graça."""
    from app.contexts.predator import contract as predator
    from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
    from app.providers.account_data.base import DecisorCandidato
    from app.services import enriquecimento_fila_service

    prov = ProvedorPago()
    cenario(db_session)
    conta = contas(db_session, 1)[0]
    fake_account_data.decisores[conta.cnpj] = [DecisorCandidato(cnpj=conta.cnpj, nome="Sócio Um", qualificacao="Sócio-Administrador", fonte="receita_federal")]
    decisores = predator.mapear_decisores(db_session, A, "1", conta.id, fake_account_data, prov, fake_graph, fake_plan_limits)
    assert prov.chamadas == [] and [d.nome for d in decisores] == ["Sócio Um"]

    outra = contas(db_session, 1)[0]
    enriquecimento_fila_service.enfileirar(db_session, A, [outra.id])
    resultado = enriquecimento_fila_service.processar_pendentes(db_session, fake_llm, fake_site_fetcher, fake_web_search, fake_account_data, prov,
                                                                fake_graph, fake_plan_limits)
    assert resultado["processados"] == 1 and prov.chamadas == []
    assert db_session.query(PesquisaDecisores).count() == 0 and db_session.query(EnriquecimentoMovimento).count() == 0
    assert db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=outra.id).one().status in ("concluido", "falhou")


def test_nenhum_codigo_fora_dos_adaptadores_chama_o_caminho_legado_do_provedor():
    """Guarda estrutural: `buscar_contatos(` (sem governança) só existe nos adaptadores e no ramo gratuito do mapeamento de decisores."""
    import ast
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[2] / "app"
    permitidos = {"providers", "prospeccao.py"}
    achados = []
    for arquivo in app_dir.rglob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "buscar_contatos":
                if not (permitidos & set(arquivo.relative_to(app_dir).parts)):
                    achados.append(str(arquivo.relative_to(app_dir)))
    assert achados == []


def test_selecao_de_outro_tenant_ou_inexistente_responde_igual(client, db_session):
    cenario(db_session)
    preparar_tenant_b(db_session)
    alheia = contas(db_session, 1, B)[0]
    r1 = client.post(f"{URL}/previa", json={"conta_ids": [alheia.id]})
    r2 = client.post(f"{URL}/previa", json={"conta_ids": [999999]})
    assert r1.status_code == r2.status_code == 404 and r1.json() == r2.json()


def test_vendedor_so_seleciona_empresas_do_proprio_escopo(client, db_session, criar_usuario_autenticado):
    cenario(db_session)
    cs = contas(db_session, 1)
    headers = criar_usuario_autenticado(A, papel="user", email="vendedor@x.com.br")
    resposta = client.post(f"{URL}/previa", json={"conta_ids": [cs[0].id]}, headers=headers)
    assert resposta.status_code == 403


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
    c = contas(db_session, 1)
    with pytest.raises(ValidacaoFalhou, match=trecho):
        previa(db_session, eu(db_session), c, ProvedorPago(), d=valor)
    assert db_session.query(PesquisaDecisores).count() == 0


def test_valor_acima_do_que_o_provedor_entrega_e_rejeitado(client, db_session):
    cenario(db_session, maximo=50)
    with pytest.raises(ValidacaoFalhou, match="provedor entrega"):
        previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=21)


def test_lote_acima_do_maximo_do_plano_e_rejeitado_sem_truncar(client, db_session):
    cenario(db_session, itens=3)
    with pytest.raises(ValidacaoFalhou, match="máximo por pesquisa"):
        previa(db_session, eu(db_session), contas(db_session, 4), ProvedorPago())


def test_limite_por_empresa_nao_substitui_os_limites_totais(client, db_session):
    """Dentro do máximo por empresa, mas o total estoura o saldo: continua bloqueado."""
    cenario(db_session, franquia=5, padrao=2, maximo=5)
    p = previa(db_session, eu(db_session), contas(db_session, 3), ProvedorPago(), d=2)  # 6 > 5
    assert p.estimativa["viavel"] is False and p.estimativa["bloqueios"][0]["codigo"] == "saldo_insuficiente"


# =================================================== estimativa e confirmação =========================================================


def test_previa_mostra_estimativa_incertezas_e_nao_reserva_nem_chama(client, db_session):
    cenario(db_session, franquia=10)
    prov = ProvedorPago()
    p = previa(db_session, eu(db_session), contas(db_session, 3), prov)
    e = p.estimativa
    assert (e["creditos_maximos"], e["empresas_selecionadas"], e["empresas_a_consultar"], e["disponivel"], e["viavel"]) == (6, 3, 3, 10, True)
    assert e["limites"]["decisores_por_empresa_max"] == 5 and e["config"] == {"origem": "plano", "versao": 1}
    assert any("pode ser menor" in i for i in e["incertezas"]) and any("reais" in i for i in e["incertezas"])
    assert prov.chamadas == [] and ledger.reservado(db_session, A) == 0 and "RESERVA" not in tipos(db_session)


def test_ajustes_sugeridos_usam_so_limites_conhecidos_e_nao_alteram_a_escolha(client, db_session):
    cenario(db_session, franquia=3, padrao=2, maximo=5, itens=10)
    p = previa(db_session, eu(db_session), contas(db_session, 2), ProvedorPago(), d=2)  # precisa de 4, há 3
    por_tipo = {s["tipo"]: s for s in p.estimativa["ajustes_sugeridos"]}
    assert por_tipo["reduzir_profundidade"] == {"tipo": "reduzir_profundidade", "decisores_por_empresa": 1, "empresas_cobertas": 2}
    assert por_tipo["ampliar_abrangencia"]["empresas_cobertas"] == 3 and por_tipo["reduzir_selecao"]["empresas_cobertas"] == 1
    assert p.decisores_por_empresa == 2 and p.total_empresas == 2 and "não foi alterada" in p.estimativa["nota_ajustes"]


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
    cenario(db_session, franquia=10, orcamento=None)  # nova versão do plano
    esperar_bloqueio("estimativa_desatualizada", lambda: confirmar(db_session, solic, p, prov))
    assert ledger.reservado(db_session, A) == 0
    assert db_session.get(PesquisaDecisores, p.id).estado == "criada"  # continua revisável (a recusa deixa rastro, não destrói a prévia)


def test_decisores_obtidos_entre_a_previa_e_a_confirmacao_invalidam_a_estimativa(client, db_session):
    cenario(db_session)
    prov, solic, cs = ProvedorPago(), eu(db_session), contas(db_session, 1)
    p = previa(db_session, solic, cs, prov)
    db_session.add(Decisor(tenant_id=A, conta_id=cs[0].id, nome="Já veio", origem="lusha"))
    db_session.commit()
    esperar_bloqueio("estimativa_desatualizada", lambda: confirmar(db_session, solic, p, prov))


def test_valores_do_cliente_nao_alteram_nada_no_servidor(client, db_session):
    """Campos extras (plano, saldo, limite, orçamento, estado) são recusados na prévia e na confirmação."""
    cenario(db_session)
    c = contas(db_session, 1)
    for extra in ({"franquia_creditos": 999}, {"saldo": 999}, {"orcamento": 999}, {"estado": "concluida"}, {"plano_id": 1}):
        assert client.post(f"{URL}/previa", json={"conta_ids": [c[0].id], **extra}).status_code == 422
    p = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id]}).json()
    assert client.post(f"{URL}/{p['id']}/confirmar", json={"selecao_hash": p["selecao_hash"], "idempotency_key": "chave-12345", "creditos": 0}).status_code == 422


# =================================================== fluxo completo, razão, reserva ===================================================


def test_fluxo_feliz_reserva_consome_e_grava_decisores(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov, solic, cs = ProvedorPago(), eu(db_session), contas(db_session, 2)
    p = rodar(db_session, fake_graph, solic, cs, prov)
    assert p.estado == "concluida" and (p.creditos_reservados, p.creditos_consumidos, p.requer_reconciliacao) == (4, 4, False)
    assert [f.limite_contatos for f in prov.chamadas] == [2, 2]
    assert ledger.disponivel(db_session, A) == 6 and ledger.reservado(db_session, A) == 0
    assert tipos(db_session) == ["CONCESSAO", "RESERVA", "CONSUMO", "CONSUMO"]
    assert db_session.query(Decisor).filter_by(tenant_id=A, origem="lusha").count() == 4
    detalhe = painel.serializar_pesquisa(db_session, p, com_itens=True, com_transicoes=True)
    assert [t["para"] for t in detalhe["transicoes"] if t["item_id"] is None] == ["criada", "validada", "reservada", "enviada", "concluida"]
    assert {i["estado"] for i in detalhe["itens"]} == {"concluido"}
    invariantes(db_session)


def test_provedor_devolve_menos_que_o_pedido_so_o_revelado_e_cobrado_e_o_resto_volta(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    prov = ProvedorPago([ok(1), sem_resultados()])
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 2), prov)
    assert p.estado == "concluida" and p.creditos_consumidos == 1 and ledger.disponivel(db_session, A) == 9  # reservou 4, cobrou 1
    assert "LIBERACAO" in tipos(db_session)
    invariantes(db_session)


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
            visto["estado_item"] = db_session.query(PesquisaDecisoresEmpresa).filter_by(estado="enviado").count()
            return super().buscar_contatos_governado(filtro)

    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), Espiao())
    assert visto == {"reservado": 2, "estado_item": 1}  # reserva já no razão e empresa já marcada como enviada


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


def test_idempotencia_pela_api_a_segunda_chamada_nao_consome_de_novo(client, db_session):
    cenario(db_session, franquia=10)
    prov = ProvedorPago()
    app.dependency_overrides[get_contact_enrichment_provider] = lambda: prov
    c = contas(db_session, 1)
    p = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id]}).json()
    corpo = {"selecao_hash": p["selecao_hash"], "idempotency_key": "chave-api-123"}
    r1, r2 = client.post(f"{URL}/{p['id']}/confirmar", json=corpo), client.post(f"{URL}/{p['id']}/confirmar", json=corpo)
    assert r1.status_code == r2.status_code == 200 and r1.json()["estado"] == "reservada"  # a consulta roda em segundo plano
    assert client.get(f"{URL}/{p['id']}").json()["estado"] == "concluida"
    assert len(prov.chamadas) == 1 and tipos(db_session).count("CONSUMO") == 1 and tipos(db_session).count("RESERVA") == 1


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

    p = execucao.reconciliar_item(db_session, pesquisa_id=p.id, item_id=item.id, creditos_consumidos=1, motivo="relatório de uso Lusha de 20/10",
                                  ator_id="1", tenant_auditoria=A)
    assert p.estado == "reconciliada" and not p.requer_reconciliacao and p.creditos_consumidos == 1
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


def test_provedor_que_devolve_acima_do_limite_nao_estoura_a_reserva(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([ok(3)]))
    assert p.creditos_consumidos == 2 and p.requer_reconciliacao  # cobra até o reservado e sinaliza a diferença
    assert db_session.query(Decisor).filter_by(origem="lusha").count() == 2
    invariantes(db_session)
    execucao.encerrar_reconciliacao(db_session, pesquisa_id=p.id, motivo="diferença tratada por ajuste", ator_id="1", tenant_auditoria=A)
    assert not db_session.get(PesquisaDecisores, p.id).requer_reconciliacao


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
    db_session.add_all([Decisor(tenant_id=A, conta_id=c.id, nome="Pessoa X", origem="lusha"), Decisor(tenant_id=A, conta_id=c.id, nome="Pessoa Y", origem="lusha")])
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
    db_session.add(Decisor(tenant_id=A, conta_id=cs[0].id, nome="Já tenho", origem="lusha"))
    db_session.commit()
    p = rodar(db_session, fake_graph, eu(db_session), cs, prov)
    assert prov.chamadas[0].limite_contatos == 2 and p.creditos_reservados == 2


def test_nada_a_consultar_conclui_sem_reservar(client, db_session, fake_graph):
    cenario(db_session, franquia=20, padrao=1)
    prov, cs, solic = ProvedorPago(), contas(db_session, 1), eu(db_session)
    db_session.add(Decisor(tenant_id=A, conta_id=cs[0].id, nome="Já tenho", origem="lusha"))
    db_session.commit()
    p = confirmar(db_session, solic, previa(db_session, solic, cs, prov), prov)
    assert p.estado == "concluida" and "RESERVA" not in tipos(db_session) and prov.chamadas == []


# =================================================== limites: período, orçamento global ==============================================


def test_limite_do_periodo_bloqueia_mesmo_com_saldo(client, db_session, fake_graph):
    cenario(db_session, franquia=100, limite_periodo=3)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 2), prov)  # 4 > 3
    assert p.estimativa["bloqueios"][0]["codigo"] == "limite_periodo" and p.estimativa["limite_periodo_restante"] == 3
    esperar_bloqueio("limite_periodo", lambda: confirmar(db_session, solic, p, prov))


def test_sem_orcamento_global_configurado_as_chamadas_ao_provedor_sao_bloqueadas(client, db_session, fake_graph):
    cenario(db_session, franquia=10, orcamento=None)
    prov, solic = ProvedorPago(), eu(db_session)
    p = previa(db_session, solic, contas(db_session, 1), prov)
    assert p.estimativa["bloqueios"][0]["codigo"] == "orcamento_global_nao_configurado"
    esperar_bloqueio("orcamento_global_nao_configurado", lambda: confirmar(db_session, solic, p, prov))
    assert prov.chamadas == [] and "RESERVA" not in tipos(db_session)


def test_orcamento_global_soma_reservas_e_consumo_de_todos_os_tenants(client, db_session, fake_graph):
    cenario(db_session, franquia=10, orcamento=5)
    preparar_tenant_b(db_session)
    prov = ProvedorPago()
    sa, sb = eu(db_session), eu(db_session, B)
    pa = previa(db_session, sa, contas(db_session, 2), prov)       # 4
    pb = previa(db_session, sb, contas(db_session, 2, B), prov)    # 4
    confirmar(db_session, sa, pa, prov, "chave-do-tenant-a")
    esperar_bloqueio("orcamento_global_esgotado", lambda: confirmar(db_session, sb, pb, prov, "chave-do-tenant-b"))  # 4 reservados + 4 > 5
    assert ledger.situacao_global(db_session, "lusha")["reservado"] == 4
    execucao.executar(db_session, tenant_id=A, pesquisa_id=pa.id, provider=prov, graph=fake_graph, ator_id="1")
    esperar_bloqueio("orcamento_global_esgotado", lambda: confirmar(db_session, sb, pb, prov, "chave-do-tenant-b"))  # agora 4 consumidos
    g = ledger.situacao_global(db_session, "lusha")
    assert (g["consumido"], g["reservado"], g["restante"], g["nivel"]) == (4, 0, 1, "alerta")
    invariantes(db_session, A)


def test_orcamento_global_so_aparece_na_area_administrativa(client, db_session, criar_usuario_autenticado):
    cenario(db_session)
    corpo_painel = client.get(f"{URL}/painel").json()
    assert "orcamento_global" not in corpo_painel and "orcamento" not in str(corpo_painel.keys()).lower()
    assert client.get(f"{ADMIN}/orcamento-global").json()["orcamento_global"]["limite"] == 1000
    comum = criar_usuario_autenticado(A, papel="admin", email="adm@x.com.br")
    assert client.get(f"{ADMIN}/orcamento-global", headers=comum).status_code == 403
    assert client.put(f"{ADMIN}/orcamento-global", json={"provedor": "lusha", "limite_creditos": 9, "motivo": "tentativa"}, headers=comum).status_code == 403


def test_alteracao_do_orcamento_global_e_versionada_auditada_e_exige_motivo(client, db_session):
    from app.models.auditoria import AuditLog

    cenario(db_session, orcamento=100)
    r = client.put(f"{ADMIN}/orcamento-global", json={"provedor": "lusha", "limite_creditos": 300, "alerta_percentual": 70, "motivo": "contrato ampliado"})
    assert r.status_code == 200 and r.json()["versao"] == 2
    assert config.orcamento_vigente(db_session, "lusha").limite_creditos == 300
    log = db_session.query(AuditLog).filter_by(evento_tipo="enriquecimento_orcamento_global_definido").order_by(AuditLog.id.desc()).first()
    assert log.detalhes["limite_anterior"] == 100 and log.detalhes["limite_novo"] == 300
    assert client.put(f"{ADMIN}/orcamento-global", json={"provedor": "lusha", "limite_creditos": 300, "motivo": ""}).status_code == 422


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


def test_ajuste_e_estorno_administrativos_exigem_motivo_e_respeitam_limites(client, db_session, fake_graph):
    cenario(db_session, franquia=10)
    p = rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    assert client.post(f"{ADMIN}/tenants/{A}/ajustes", json={"quantidade": 5, "motivo": "cortesia comercial"}).status_code == 200
    assert ledger.disponivel(db_session, A) == 13
    assert client.post(f"{ADMIN}/tenants/{A}/ajustes", json={"quantidade": -100, "motivo": "débito grande"}).status_code == 422
    assert client.post(f"{ADMIN}/tenants/{A}/ajustes", json={"quantidade": 0, "motivo": "zero aqui"}).status_code == 422
    assert client.post(f"{ADMIN}/tenants/{A}/estornos", json={"quantidade": 3, "motivo": "crédito do provedor", "pesquisa_id": p.id}).status_code == 422  # só 2 consumidos
    assert client.post(f"{ADMIN}/tenants/{A}/estornos", json={"quantidade": 1, "motivo": "crédito do provedor", "pesquisa_id": p.id}).status_code == 200
    assert ledger.disponivel(db_session, A) == 14
    invariantes(db_session)


def test_enriquecimento_e_ia_sao_contabilidades_separadas(client, db_session, fake_graph):
    from decimal import Decimal

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


def test_pesquisa_de_um_tenant_nao_aparece_para_outro(client, db_session, fake_graph, criar_usuario_autenticado):
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


def test_confirmar_pesquisa_de_outro_tenant_e_negado(client, db_session, criar_usuario_autenticado):
    cenario(db_session)
    preparar_tenant_b(db_session)
    p = previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago())
    outro = criar_usuario_autenticado(B, papel="admin", email="adm@b.com.br")
    r = client.post(f"{URL}/{p.id}/confirmar", json={"selecao_hash": p.selecao_hash, "idempotency_key": "chave-roubada-1"}, headers=outro)
    assert r.status_code == 404 and db_session.get(PesquisaDecisores, p.id).estado == "criada"


def test_vendedor_so_ve_as_proprias_pesquisas_e_nao_ve_o_extrato(client, db_session, fake_graph, criar_usuario_autenticado):
    cenario(db_session)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago())
    vendedor = criar_usuario_autenticado(A, papel="user", email="vendedor@x.com.br")
    assert client.get(f"{URL}", headers=vendedor).json() == []
    assert client.get(f"{URL}/movimentacoes", headers=vendedor).status_code == 403
    assert client.get(f"{URL}/painel", headers=vendedor).json()["pesquisas_por_estado"] == {}
    assert len(client.get(f"{URL}").json()) == 1  # o admin (super_admin do teste) vê


def test_so_o_criador_ou_gestor_confirma(client, db_session, criar_usuario_autenticado):
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
        ("post", f"{ADMIN}/tenants/{A}/ajustes", {"quantidade": 9, "motivo": "tentativa"}),
        ("post", f"{ADMIN}/tenants/{A}/estornos", {"quantidade": 1, "motivo": "tentativa"}),
        ("post", f"{ADMIN}/pesquisas/x/itens/1/reconciliar", {"creditos_consumidos": 0, "motivo": "tentativa"}),
        ("post", f"{ADMIN}/pesquisas/x/encerrar-reconciliacao", {"motivo": "tentativa"}),
    ]:
        assert getattr(client, metodo)(caminho, headers=comum, **({"json": corpo} if corpo else {})).status_code == 403, caminho


def test_painel_do_tenant_mostra_franquia_saldos_pesquisas_e_estimado_vs_consumido(client, db_session, fake_graph):
    cenario(db_session, franquia=10, limite_periodo=3)
    rodar(db_session, fake_graph, eu(db_session), contas(db_session, 1), ProvedorPago([ok(1)]))
    d = client.get(f"{URL}/painel").json()
    assert d["plano"]["franquia_creditos"] == 10 and d["plano"]["disponivel"] is True
    assert d["creditos"] == {"disponivel": 9, "reservado": 0, "saldo": 9, "consumido_no_periodo": 1, "expirado_no_periodo": 0, "concedido_no_periodo": 10}
    assert d["pesquisas_por_estado"] == {"concluida": 1} and d["estimado_vs_reconciliado"] == {"estimado_maximo": 2, "consumido": 1}
    extrato = client.get(f"{URL}/movimentacoes", params={"tipo": "CONSUMO"}).json()
    assert [m["delta_saldo"] for m in extrato] == [-1]
    assert d["alertas"] == []


def test_painel_sem_configuracao_orienta_e_alerta(client, db_session):
    d = client.get(f"{URL}/painel").json()
    assert d["plano"]["disponivel"] is False and "comercial" in d["plano"]["orientacao"]
    assert d["alertas"][0]["codigo"] == "config_indisponivel"


def test_previa_pela_api_traz_estimativa_completa_e_codigos_estaveis_de_bloqueio(client, db_session):
    c = contas(db_session, 1)
    r = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id]})
    assert r.status_code == 409 and r.json()["codigo"] == "plano_sem_configuracao" and r.json()["bloqueios"][0]["codigo"] == "plano_sem_configuracao"
    cenario(db_session)
    r = client.post(f"{URL}/previa", json={"conta_ids": [c[0].id], "decisores_por_empresa": 3})
    assert r.status_code == 201 and r.json()["estado"] == "criada" and r.json()["estimativa"]["decisores_por_empresa"] == 3


def test_provedor_nao_configurado_bloqueia_antes_de_reservar(client, db_session):
    from app.providers.contact_enrichment.desativado import ContactEnrichmentDesativadoProvider

    cenario(db_session)
    prov = ContactEnrichmentDesativadoProvider()
    p = previa(db_session, eu(db_session), contas(db_session, 1), prov)
    assert p.estimativa["bloqueios"][0]["codigo"] == "provedor_indisponivel"
    esperar_bloqueio("provedor_indisponivel", lambda: confirmar(db_session, eu(db_session), p, prov))
    assert "RESERVA" not in tipos(db_session)


def test_pesquisa_inexistente_responde_404(client, db_session):
    cenario(db_session)
    with pytest.raises(NaoEncontrado):
        pesquisa.obter(db_session, A, eu(db_session), "nao-existe")
