import httpx
import pytest

from app.integrations.site_fetcher import HostNaoPublico
from app.models.conta import Conta
from app.providers.web_search.base import ResultadoBusca
from app.services import conta_service
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider, FakeWebSearchProvider

TENANT_ID = "tenant-enriquecer-site"


def _criar_conta(db_session, dominio: str | None = None) -> Conta:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Alpha Tech", dominio=dominio, status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def _site_fetcher(resposta: str = "=== https://alphatech.com.br ===\nConteúdo institucional."):
    return lambda dominio: resposta


def test_enriquecer_sem_dominio_descobre_e_persiste(db_session):
    conta = _criar_conta(db_session, dominio=None)
    web_search = FakeWebSearchProvider([ResultadoBusca(titulo="Alpha Tech", url="https://www.alphatech.com.br/", descricao="")])
    llm = FakeLLMProvider(["porte: media"])

    conta_service.enriquecer(db_session, TENANT_ID, "1", conta.id, llm, _site_fetcher(), web_search)

    db_session.refresh(conta)
    assert conta.dominio == "www.alphatech.com.br"
    assert web_search.buscas == ["Alpha Tech site oficial"]


def test_enriquecer_sem_dominio_e_sem_resultado_aceitavel_falha(db_session):
    conta = _criar_conta(db_session, dominio=None)
    web_search = FakeWebSearchProvider([ResultadoBusca(titulo="Alpha Tech no LinkedIn", url="https://www.linkedin.com/company/alpha-tech", descricao="")])
    llm = FakeLLMProvider(["porte: media"])

    with pytest.raises(RegraNegocioViolada):
        conta_service.enriquecer(db_session, TENANT_ID, "1", conta.id, llm, _site_fetcher(), web_search)


def test_enriquecer_com_dominio_ja_cadastrado_nao_busca_na_web(db_session):
    conta = _criar_conta(db_session, dominio="alphatech.com.br")
    web_search = FakeWebSearchProvider()
    llm = FakeLLMProvider(["porte: media"])

    conta_service.enriquecer(db_session, TENANT_ID, "1", conta.id, llm, _site_fetcher(), web_search)

    assert web_search.buscas == []


def test_enriquecer_popula_resumo_site_so_na_primeira_vez(db_session):
    """Pedido do usuário: resumo da pesquisa de site vira campo editável do
    vendedor — pesquisas seguintes não podem sobrescrever o que ele já
    editou."""
    conta = _criar_conta(db_session, dominio="alphatech.com.br")
    web_search = FakeWebSearchProvider()

    conta_service.enriquecer(
        db_session, TENANT_ID, "1", conta.id, FakeLLMProvider(["porte: media"]), _site_fetcher(), web_search
    )
    db_session.refresh(conta)
    assert conta.resumo_site == "porte: media"

    conta.resumo_site = "Editado manualmente pelo vendedor."
    db_session.commit()

    conta_service.enriquecer(
        db_session, TENANT_ID, "1", conta.id, FakeLLMProvider(["porte: grande"]), _site_fetcher(), web_search
    )
    db_session.refresh(conta)
    assert conta.resumo_site == "Editado manualmente pelo vendedor."


def test_descobrir_dominio_ignora_dominio_bloqueado_e_pega_o_proximo(db_session):
    web_search = FakeWebSearchProvider(
        [
            ResultadoBusca(titulo="Alpha Tech no LinkedIn", url="https://www.linkedin.com/company/alpha-tech", descricao=""),
            ResultadoBusca(titulo="Alpha Tech", url="https://alphatech.com.br/sobre", descricao=""),
        ]
    )

    dominio = conta_service._descobrir_dominio("Alpha Tech", web_search)

    assert dominio == "alphatech.com.br"


def test_descobrir_dominio_ignora_portal_de_agendamento_terceiro(db_session):
    """Raio-X de produção: busca por razão social completa achava um
    portal de agendamento de terceiros (não o site da própria clínica)."""
    web_search = FakeWebSearchProvider(
        [
            ResultadoBusca(titulo="Santorius - AgendarConsulta", url="https://guia.agendarconsulta.com/clinica-x", descricao=""),
            ResultadoBusca(titulo="Santorius Medicina", url="https://santoriusmedicina.com.br/", descricao=""),
        ]
    )

    dominio = conta_service._descobrir_dominio("Santorius Medicina Cirurgica E Diagnostica Ltda", web_search)

    assert dominio == "santoriusmedicina.com.br"


def test_descobrir_dominio_ignora_portal_de_vagas_mesmo_com_similaridade_perfeita(db_session):
    """Raio-X de produção 2026-08-27: pra "J&F S.A.", o subdomínio
    "j-f.gupy.io" (página de vagas hospedada na Gupy) batia 100% de
    similaridade com o núcleo do nome ("jf") — a lista de bloqueio
    precisa rejeitar isso mesmo com o score de similaridade perfeito, já
    que o domínio real da empresa vem depois, com similaridade menor."""
    web_search = FakeWebSearchProvider(
        [
            ResultadoBusca(titulo="Vagas J&F", url="https://j-f.gupy.io/", descricao=""),
            ResultadoBusca(titulo="J&F S.A.", url="https://jfsa.com.br/", descricao=""),
        ]
    )

    dominio = conta_service._descobrir_dominio("J&F S.A.", web_search)

    assert dominio == "jfsa.com.br"


def test_descobrir_dominio_rejeita_diretorio_desconhecido_por_similaridade(db_session):
    """Raio-X de produção: "dnb.com" (Dun & Bradstreet, diretório global de
    empresas) veio como resultado antes de entrar pra lista de bloqueio —
    a checagem de similaridade rejeita mesmo sem conhecer o domínio de
    antemão, porque "dnb" não se parece em nada com o nome da empresa."""
    web_search = FakeWebSearchProvider(
        [ResultadoBusca(titulo="Total Life na DNB", url="https://www.exemplo-diretorio-desconhecido.com/perfil", descricao="")]
    )

    dominio = conta_service._descobrir_dominio("Total Life Clinica Medica Ltda 416 - SCP", web_search)

    assert dominio is None


def test_descobrir_dominio_prefere_o_mais_parecido_entre_varios_candidatos(db_session):
    web_search = FakeWebSearchProvider(
        [
            ResultadoBusca(titulo="Total Life no diretório", url="https://www.perfil-empresarial-x.com/total-life", descricao=""),
            ResultadoBusca(titulo="Total Life Clínica", url="https://www.totallifeclinica.com.br/", descricao=""),
        ]
    )

    dominio = conta_service._descobrir_dominio("Total Life Clinica Medica Ltda", web_search)

    assert dominio == "www.totallifeclinica.com.br"


def test_descobrir_dominio_aceita_marca_diferente_da_razao_social(db_session):
    """Nome de marca costuma divergir da razão social no Brasil — a
    similaridade não pode exigir bater 100%, só ficar acima do limiar."""
    web_search = FakeWebSearchProvider(
        [ResultadoBusca(titulo="Padaria do Silva", url="https://www.padariadosilva.com.br/", descricao="")]
    )

    dominio = conta_service._descobrir_dominio("Comercio De Alimentos Silva Ltda", web_search)

    assert dominio == "www.padariadosilva.com.br"


@pytest.mark.parametrize(
    ("razao_social", "esperado"),
    [
        ("Alpha Tech Ltda", "Alpha Tech"),
        ("Alpha Tech Ltda.", "Alpha Tech"),
        ("Alpha Tech S/A", "Alpha Tech"),
        ("Alpha Tech S.A.", "Alpha Tech"),
        ("Alpha Tech EIRELI", "Alpha Tech"),
        ("Alpha Tech ME", "Alpha Tech"),
        ("Alpha Tech EPP", "Alpha Tech"),
        ("Alpha Tech Sociedade Simples", "Alpha Tech"),
        ("Alpha Tech", "Alpha Tech"),  # sem sufixo, não mexe
    ],
)
def test_nome_para_busca_remove_sufixo_de_natureza_juridica(razao_social, esperado):
    assert conta_service._nome_para_busca(razao_social) == esperado


def test_descobrir_dominio_busca_com_nome_limpo_de_sufixo_juridico(db_session):
    web_search = FakeWebSearchProvider([ResultadoBusca(titulo="Alpha Tech", url="https://alphatech.com.br/", descricao="")])

    conta_service._descobrir_dominio("Alpha Tech Ltda ME", web_search)

    assert web_search.buscas == ["Alpha Tech site oficial"]


def _site_fetcher_que_falha(excecao):
    def _fetcher(dominio):
        raise excecao

    return _fetcher


def test_enriquecer_com_dominio_que_nao_resolve_da_mensagem_amigavel(db_session):
    conta = _criar_conta(db_session, dominio="dominio-inexistente-xyz.com.br")

    with pytest.raises(RegraNegocioViolada) as excinfo:
        conta_service.enriquecer(
            db_session, TENANT_ID, "1", conta.id, FakeLLMProvider(["x"]),
            _site_fetcher_que_falha(HostNaoPublico("Não foi possível resolver o domínio: x")),
            FakeWebSearchProvider(),
        )

    mensagem = str(excinfo.value)
    assert "não existe ou não resolve" in mensagem
    assert "Editar dados da conta" in mensagem


def test_enriquecer_com_site_bloqueando_acesso_da_mensagem_amigavel(db_session):
    """Antes desta correção, o erro cru do httpx (com URL/link do MDN)
    era mostrado direto pro usuário — raio-X de produção real (403 do
    site institucional)."""
    conta = _criar_conta(db_session, dominio="site-bloqueado.com.br")
    request = httpx.Request("GET", "https://site-bloqueado.com.br")
    resposta = httpx.Response(403, request=request)
    erro = httpx.HTTPStatusError("403 Forbidden", request=request, response=resposta)

    with pytest.raises(RegraNegocioViolada) as excinfo:
        conta_service.enriquecer(
            db_session, TENANT_ID, "1", conta.id, FakeLLMProvider(["x"]),
            _site_fetcher_que_falha(erro),
            FakeWebSearchProvider(),
        )

    mensagem = str(excinfo.value)
    assert "erro 403" in mensagem
    assert "developer.mozilla.org" not in mensagem


def test_enriquecer_com_timeout_da_mensagem_amigavel(db_session):
    conta = _criar_conta(db_session, dominio="site-lento.com.br")

    with pytest.raises(RegraNegocioViolada) as excinfo:
        conta_service.enriquecer(
            db_session, TENANT_ID, "1", conta.id, FakeLLMProvider(["x"]),
            _site_fetcher_que_falha(httpx.TimeoutException("timeout")),
            FakeWebSearchProvider(),
        )

    assert "fora do ar ou muito lento" in str(excinfo.value)
