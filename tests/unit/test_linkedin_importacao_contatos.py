"""Conexões do LinkedIn viram contatos e empresas (lista "Importação LinkedIn"), sem duplicar, com a IA conferindo nomes parecidos. IA sempre simulada."""

import json

import pytest

from app.models.conexao_linkedin import ConexaoLinkedin
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.lista_prospeccao import ListaProspeccao
from app.models.usuario import Usuario
from app.services import linkedin_conexao_service as servico
from app.services import linkedin_importacao_service as importacao
from app.services.errors import IAIndisponivel
from tests.fakes import FakeGraphClient, FakeLLMProvider

TENANT = "tenant-li"
CABECALHO = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"


def csv(*linhas: str) -> str:
    return "Notes:\n\n\n" + CABECALHO + "\n".join(linhas) + "\n"


def usuario(db, papel="user") -> Usuario:
    u = Usuario(tenant_id=TENANT, nome=f"Vend {papel}", email=f"{papel}@li.com.br", papel=papel, ativo=True)
    db.add(u)
    db.commit()
    return u


def importar(db, u, texto, llm=None):
    return servico.importar_csv_e_criar_contatos(db, u, texto, llm or FakeLLMProvider(["{}"]), FakeGraphClient())


class LLMQueFalha(FakeLLMProvider):
    def generate(self, request):
        raise IAIndisponivel("fora do ar")


def test_conexoes_viram_contatos_e_empresas_na_lista_importacao_linkedin(db_session):
    u = usuario(db_session)
    r = importar(db_session, u, csv(
        "Ana,Lima,https://www.linkedin.com/in/ana-lima,ana@alpha.com.br,Alpha Tech,CEO,01 Jan 2024",
        "Bruno,Reis,https://www.linkedin.com/in/bruno-reis/,,Beta Clinica,Diretor,02 Feb 2024",
    ))
    lista = db_session.query(ListaProspeccao).one()
    assert (lista.nome, lista.criado_por_usuario_id, r["lista_id"], r["lista_nome"]) == ("Importação LinkedIn", u.id, lista.id, "Importação LinkedIn")
    assert (r["total_importado"], r["contas_criadas"], r["contatos_criados"], r["contatos_com_email"]) == (2, 2, 2, 1)
    contas = {c.nome: c for c in db_session.query(Conta).all()}
    assert set(contas) == {"Alpha Tech", "Beta Clinica"} and all(c.lista_prospeccao_id == lista.id and c.origem == "linkedin" for c in contas.values())
    ana = db_session.query(Decisor).filter_by(nome="Ana Lima").one()
    assert (ana.cargo, ana.email, ana.linkedin_url, ana.origem, ana.canal_provavel, ana.conta_id) == (
        "CEO", "ana@alpha.com.br", "https://linkedin.com/in/ana-lima", "linkedin", "email", contas["Alpha Tech"].id)
    bruno = db_session.query(Decisor).filter_by(nome="Bruno Reis").one()
    assert bruno.email is None and bruno.canal_provavel == "linkedin" and bruno.linkedin_url == "https://linkedin.com/in/bruno-reis"


def test_varias_conexoes_da_mesma_empresa_nao_duplicam_a_empresa_mesmo_com_grafias_equivalentes(db_session):
    u = usuario(db_session)
    llm = FakeLLMProvider(["{}"])
    r = importar(db_session, u, csv(
        "Ana,Lima,https://www.linkedin.com/in/ana,,Alpha Tech Ltda.,CEO,01 Jan 2024",
        "Caio,Dias,https://www.linkedin.com/in/caio,,ALPHA TECH,CTO,01 Jan 2024",
        "Dora,Neves,https://www.linkedin.com/in/dora,,Álpha  Tech S.A.,CFO,01 Jan 2024",
    ), llm)
    assert db_session.query(Conta).count() == 1 and r["contas_criadas"] == 1 and r["contatos_criados"] == 3
    assert llm.chamadas == []  # igualdade depois de normalizar não precisa de IA
    assert {d.nome for d in db_session.query(Decisor).all()} == {"Ana Lima", "Caio Dias", "Dora Neves"}


def test_ia_une_variacoes_do_mesmo_nome_e_mantem_homonimos_separados(db_session):
    u = usuario(db_session)
    # grupos candidatos (ordem por nº de conexões): Acme Brasil (2) × Acme (1); Orion Saúde (1) × Orion Seguros (1)
    resposta = json.dumps({"grupos": [{"grupo": 0, "mesmas": [[0, 1]]}, {"grupo": 1, "mesmas": [[0], [1]]}]})
    llm = FakeLLMProvider([resposta])
    r = importar(db_session, u, csv(
        "A,Um,https://www.linkedin.com/in/a1,a@acme.com.br,Acme Brasil,Gerente,01 Jan 2024",
        "B,Dois,https://www.linkedin.com/in/b2,b@acme.com.br,Acme Brasil,Analista,01 Jan 2024",
        "C,Tres,https://www.linkedin.com/in/c3,c@acme.com.br,Acme,Diretor,01 Jan 2024",
        "D,Quatro,https://www.linkedin.com/in/d4,,Orion Saude,CEO,01 Jan 2024",
        "E,Cinco,https://www.linkedin.com/in/e5,,Orion Seguros,CEO,01 Jan 2024",
    ), llm)
    nomes = sorted(c.nome for c in db_session.query(Conta).all())
    assert nomes == ["Acme Brasil", "Orion Saude", "Orion Seguros"]  # Acme == Acme Brasil; as duas Orion são empresas diferentes
    acme = db_session.query(Conta).filter_by(nome="Acme Brasil").one()
    assert db_session.query(Decisor).filter_by(conta_id=acme.id).count() == 3
    assert (r["contas_criadas"], r["grupos_analisados"], r["ia_disponivel"], r["homonimos_mantidos_separados"]) == (3, 2, True, 1)
    assert r["variacoes_unificadas"] == [{"empresa": "Acme Brasil", "variacoes": ["Acme", "Acme Brasil"]}]
    prompt = llm.chamadas[0].prompt
    assert "acme.com.br" in prompt and "Gerente" in prompt and llm.chamadas[0].system  # a IA recebe cargos e domínios de e-mail como evidência


def test_sem_ia_ou_com_resposta_invalida_nomes_parecidos_ficam_separados(db_session):
    u = usuario(db_session)
    texto = csv("A,Um,https://www.linkedin.com/in/a1,,Acme Brasil,Gerente,01 Jan 2024", "C,Tres,https://www.linkedin.com/in/c3,,Acme,Diretor,01 Jan 2024")
    r = importar(db_session, u, texto, LLMQueFalha())
    assert sorted(c.nome for c in db_session.query(Conta).all()) == ["Acme", "Acme Brasil"]
    assert r["ia_disponivel"] is False and r["grupos_sem_analise"] == 1 and r["variacoes_unificadas"] == []
    u2 = usuario(db_session, "admin")
    r2 = importar(db_session, u2, texto, FakeLLMProvider(["isto não é JSON"]))
    assert r2["ia_disponivel"] is False and r2["variacoes_unificadas"] == []


def test_resposta_da_ia_com_indices_faltando_e_descartada(db_session):
    u = usuario(db_session)
    llm = FakeLLMProvider([json.dumps({"grupos": [{"grupo": 0, "mesmas": [[0]]}]})])  # falta o índice 1
    importar(db_session, u, csv("A,Um,https://www.linkedin.com/in/a1,,Acme Brasil,G,01 Jan 2024", "C,Tres,https://www.linkedin.com/in/c3,,Acme,D,01 Jan 2024"), llm)
    assert db_session.query(Conta).count() == 2


def test_empresa_ja_cadastrada_no_crm_e_reaproveitada_inclusive_por_variacao_de_nome(db_session):
    u = usuario(db_session)
    existente = Conta(tenant_id=TENANT, icp_id=None, nome="Alpha Tech", status="prospectada", criado_por_usuario_id=u.id)
    parecida = Conta(tenant_id=TENANT, icp_id=None, nome="Gama Industrial", status="prospectada", criado_por_usuario_id=u.id)
    db_session.add_all([existente, parecida])
    db_session.commit()
    resposta = json.dumps({"grupos": [{"grupo": 0, "mesmas": [[0, 1]]}]})
    r = importar(db_session, u, csv(
        "Ana,Lima,https://www.linkedin.com/in/ana,,ALPHA TECH Ltda,CEO,01 Jan 2024",
        "Gil,Nunes,https://www.linkedin.com/in/gil,,Gama Industrial Brasil,Diretor,01 Jan 2024",
    ), FakeLLMProvider([resposta]))
    assert db_session.query(Conta).count() == 2 and r["contas_criadas"] == 0 and r["contas_reaproveitadas"] == 2
    assert db_session.query(Decisor).filter_by(conta_id=existente.id, nome="Ana Lima").count() == 1
    assert db_session.query(Decisor).filter_by(conta_id=parecida.id, nome="Gil Nunes").count() == 1
    lista = db_session.query(ListaProspeccao).one()
    assert db_session.get(Conta, existente.id).lista_prospeccao_id == lista.id  # empresa avulsa passa a aparecer na fila


def test_reimportar_nao_duplica_e_so_completa_campos_vazios(db_session):
    u = usuario(db_session)
    importar(db_session, u, csv("Ana,Lima,https://www.linkedin.com/in/ana,,Alpha Tech,,01 Jan 2024"))
    r = importar(db_session, u, csv("Ana,Lima,https://www.linkedin.com/in/ana,ana@alpha.com.br,Alpha Tech,CEO,01 Jan 2024"))
    assert (db_session.query(Conta).count(), db_session.query(Decisor).count(), db_session.query(ListaProspeccao).count()) == (1, 1, 1)
    assert (r["contas_criadas"], r["contas_reaproveitadas"], r["contatos_criados"], r["contatos_atualizados"]) == (0, 1, 0, 1)
    ana = db_session.query(Decisor).one()
    assert (ana.cargo, ana.email) == ("CEO", "ana@alpha.com.br")
    importar(db_session, u, csv("Ana,Lima,https://www.linkedin.com/in/ana,outro@alpha.com.br,Alpha Tech,Presidente,01 Jan 2024"))
    assert db_session.query(Decisor).one().cargo == "CEO"  # o que já estava preenchido não é sobrescrito


def test_conexao_sem_empresa_ou_autonomo_nao_cria_empresa(db_session):
    u = usuario(db_session)
    r = importar(db_session, u, csv("Ana,Lima,https://www.linkedin.com/in/ana,,,Consultora,01 Jan 2024", "Rui,Paz,https://www.linkedin.com/in/rui,,Autônomo,Dev,01 Jan 2024"))
    assert db_session.query(Conta).count() == 0 and r["conexoes_sem_empresa"] == 2 and r["contatos_criados"] == 0 and r["total_importado"] == 2


def test_cada_vendedor_tem_a_sua_lista_e_outro_vendedor_nao_enxerga_as_empresas_dele(db_session):
    a, b = usuario(db_session), Usuario(tenant_id=TENANT, nome="Outro", email="outro@li.com.br", papel="user", ativo=True)
    db_session.add(b)
    db_session.commit()
    importar(db_session, a, csv("Ana,Lima,https://www.linkedin.com/in/ana,,Alpha Tech,CEO,01 Jan 2024"))
    importar(db_session, b, csv("Bia,Melo,https://www.linkedin.com/in/bia,,Alpha Tech,CTO,01 Jan 2024"))
    assert db_session.query(ListaProspeccao).count() == 2 and db_session.query(Conta).count() == 2  # cada um com a própria Alpha Tech
    assert db_session.query(ConexaoLinkedin).count() == 2


def test_normalizacao_de_nomes_de_empresa():
    assert importacao.normalizar_empresa("Álpha Tech S.A.") == importacao.normalizar_empresa("alpha  tech") == "alpha tech"
    assert importacao.normalizar_empresa("Banco do Brasil") == "banco do brasil"  # "Brasil" nunca é cortado como sufixo
    assert importacao.normalizar_empresa("Ltda") == "ltda"  # nome só de sufixo não vira vazio


@pytest.mark.parametrize("a,b,candidatos", [("acme", "acme brasil", True), ("banco itau", "itau unibanco", True), ("banco itau", "banco bradesco", False),
                                            ("grupo alpha", "grupo beta", False)])
def test_so_nomes_com_palavra_distintiva_em_comum_viram_candidatos_a_mesma_empresa(a, b, candidatos):
    empresas = {a: importacao._Empresa(chave=a), b: importacao._Empresa(chave=b)}
    assert bool(importacao._candidatos(empresas)) is candidatos
