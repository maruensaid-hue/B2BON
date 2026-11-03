"""Pessoas e e-mails do próprio site: decisores sem custo, padrão de e-mail aprendido e e-mail deduzido que só sai depois de confirmado."""

import pytest

from app.contexts.predator import pessoas_site
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import conta_service
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider, FakeWebSearchProvider

TENANT = "tenant-pessoas-site"

SOBRE = """Nossa Equipe
Maria Clara Souza
CEO e Fundadora
João da Silva – Diretor Comercial
"A Alpha mudou nosso negócio" – Pedro Alves, CEO da Beta
A empresa foi fundada em 1998 por Roberto Lima Neto.
Ex-diretor: Carlos Mendes Rocha
Fale Conosco
Contato: joao.silva@alpha.com.br ou contato@alpha.com.br"""


def _paginas(texto=SOBRE):
    return [("https://alpha.com.br/sobre", texto)]


def test_acha_quem_decide_com_dono_primeiro_e_ignora_depoimento_e_ex():
    achadas = pessoas_site.pessoas(_paginas(), limite=10)
    nomes = [p.nome for p in achadas]

    assert nomes[:2] == ["Maria Clara Souza", "Roberto Lima Neto"]  # donos primeiro
    assert "João da Silva" in nomes
    assert "Pedro Alves" not in nomes  # depoimento de cliente
    assert "Carlos Mendes Rocha" not in nomes  # ex-diretor
    assert not any(n.startswith("Nossa") or n.startswith("Fale") for n in nomes)


def test_limite_padrao_e_de_tres_pessoas():
    assert len(pessoas_site.pessoas(_paginas())) == 3


def test_emails_do_dominio_inclusive_ofuscados_e_nunca_de_outro_dominio():
    texto = "joao.silva@alpha.com.br, maria [arroba] alpha [ponto] com [ponto] br, fulano@gmail.com, rh@vagas.alpha.com.br"
    assert pessoas_site.emails_publicados(_paginas(texto), "www.alpha.com.br") == [
        "joao.silva@alpha.com.br", "rh@vagas.alpha.com.br", "maria@alpha.com.br"]


@pytest.mark.parametrize(("email", "nome", "formato"), [
    ("joao.silva@x.com", "João da Silva", "{n}.{s}"),
    ("jsilva@x.com", "João da Silva", "{i}{s}"),
    ("joao@x.com", "João da Silva", "{n}"),
    ("pedro@x.com", "João da Silva", None),
])
def test_padrao_de(email, nome, formato):
    assert pessoas_site.padrao_de(email, nome) == formato


def test_endereco_que_duas_pessoas_poderiam_ter_nao_ensina_padrao():
    assert pessoas_site.aprender_padrao(["jsilva@x.com"], ["João Silva", "Júlia Silva"]) is None


def test_enderecos_que_discordam_deixam_o_padrao_indefinido():
    assert pessoas_site.aprender_padrao(["joao.silva@x.com", "mcosta@x.com"], ["João Silva", "Maria Costa"]) is None


def test_endereco_generico_nao_ensina_padrao():
    assert pessoas_site.aprender_padrao(["contato@x.com"], ["Contato Geral"]) is None


def _enriquecer(db, texto=SOBRE, cnpj_no_site=True):
    conta = Conta(tenant_id=TENANT, nome="Alpha", dominio="alpha.com.br", status="prospectada", cnpj="11222333000181")
    db.add(conta)
    db.commit()
    conteudo = f"=== https://alpha.com.br ===\nAlpha. CNPJ 11.222.333/0001-81\n\n=== https://alpha.com.br/sobre ===\n{texto}"
    if not cnpj_no_site:
        conteudo = conteudo.replace("CNPJ 11.222.333/0001-81", "")
    conta_service.enriquecer(db, TENANT, "1", conta.id, FakeLLMProvider(["porte: media"]), lambda d: conteudo,
                             FakeWebSearchProvider(), StubPlanLimitsProvider())
    return conta


def _decisores(db, conta) -> dict[str, Decisor]:
    return {d.nome: d for d in db.query(Decisor).filter_by(conta_id=conta.id)}


def test_enriquecer_cria_decisores_do_site_com_email_publicado_e_deduzido(db_session):
    conta = _enriquecer(db_session)
    decisores = _decisores(db_session, conta)

    assert set(decisores) == {"Maria Clara Souza", "Roberto Lima Neto", "João da Silva"}
    assert decisores["João da Silva"].email == "joao.silva@alpha.com.br"
    assert decisores["João da Silva"].email_status == "publicado"
    assert decisores["Maria Clara Souza"].email == "maria.souza@alpha.com.br"
    assert decisores["Maria Clara Souza"].email_status == "inferido"
    assert all(d.origem == "site_institucional" for d in decisores.values())


def test_dominio_nao_confirmado_nao_cria_decisor(db_session):
    conta = _enriquecer(db_session, cnpj_no_site=False)
    assert _decisores(db_session, conta) == {}


def test_padrao_completa_email_do_socio_do_qsa_sem_email(db_session):
    conta = Conta(tenant_id=TENANT, nome="Alpha", dominio="alpha.com.br", status="prospectada", cnpj="11222333000181")
    db_session.add(conta)
    db_session.flush()
    db_session.add(Decisor(tenant_id=TENANT, conta_id=conta.id, nome="Ana Beatriz Ramos", cargo="Sócio-Administrador", origem="receita_federal_cnpj_qsa"))
    db_session.commit()
    conteudo = "=== https://alpha.com.br ===\nAlpha. CNPJ 11.222.333/0001-81\n\n=== https://alpha.com.br/sobre ===\n" + SOBRE
    conta_service.enriquecer(db_session, TENANT, "1", conta.id, FakeLLMProvider(["porte: media"]), lambda d: conteudo,
                             FakeWebSearchProvider(), StubPlanLimitsProvider())

    socia = _decisores(db_session, conta)["Ana Beatriz Ramos"]
    assert (socia.email, socia.email_status) == ("ana.ramos@alpha.com.br", "inferido")


def test_confirmar_email_libera_e_editar_o_email_conta_como_confirmado(db_session):
    conta = _enriquecer(db_session)
    maria = _decisores(db_session, conta)["Maria Clara Souza"]

    assert conta_service.confirmar_email_decisor(db_session, TENANT, "1", conta.id, maria.id).email_status == "confirmado"

    roberto = _decisores(db_session, conta)["Roberto Lima Neto"]
    conta_service.atualizar_decisor(db_session, TENANT, "1", conta.id, roberto.id, roberto.nome, "Fundador", "roberto@alpha.com.br", None, None)
    db_session.refresh(roberto)
    assert roberto.email_status == "confirmado"


def test_confirmar_sem_email_e_recusado(db_session):
    conta = _enriquecer(db_session)
    roberto = _decisores(db_session, conta)["Roberto Lima Neto"]
    roberto.email = None
    db_session.commit()
    with pytest.raises(RegraNegocioViolada):
        conta_service.confirmar_email_decisor(db_session, TENANT, "1", conta.id, roberto.id)
