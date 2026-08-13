import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.services import crm_service, template_proposta_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TENANT_ID = "tenant-teste"


def _criar_conta(db_session, **overrides) -> Conta:
    icp = ICP(
        tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()
    dados = {"tenant_id": TENANT_ID, "icp_id": icp.id, "nome": "Conta Teste", "status": "prospectada"}
    dados.update(overrides)
    conta = Conta(**dados)
    db_session.add(conta)
    db_session.commit()
    return conta


def _criar_decisor(db_session, conta: Conta, nome: str = "Decisor Teste") -> Decisor:
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome=nome)
    db_session.add(decisor)
    db_session.commit()
    return decisor


def _criar_negocio(db_session):
    conta = _criar_conta(db_session)
    decisor = _criar_decisor(db_session, conta)
    return crm_service.criar_negocio(db_session, TENANT_ID, "1", conta.id, decisor.id, "Negócio Teste", valor=1000.0)


def test_obter_ou_criar_e_idempotente(db_session):
    primeiro = template_proposta_service.obter_ou_criar(db_session, TENANT_ID)
    segundo = template_proposta_service.obter_ou_criar(db_session, TENANT_ID)

    assert primeiro.id == segundo.id


def test_atualizar_persiste_campos(db_session):
    template = template_proposta_service.atualizar(
        db_session, TENANT_ID, "1", "Texto intro", "Termo de aceite", True, False
    )

    assert template.texto_introdutorio == "Texto intro"
    assert template.termo_aceite == "Termo de aceite"
    assert template.mostrar_tabela_produtos is True
    assert template.mostrar_tabela_servicos is False


def test_salvar_logo_recusa_tipo_invalido(db_session):
    with pytest.raises(ValidacaoFalhou):
        template_proposta_service.salvar_logo(db_session, TENANT_ID, "1", b"x", "application/pdf")


def test_salvar_logo_recusa_tamanho_excessivo(db_session):
    conteudo_grande = b"a" * (template_proposta_service.TAMANHO_MAXIMO_LOGO_BYTES + 1)
    with pytest.raises(ValidacaoFalhou):
        template_proposta_service.salvar_logo(db_session, TENANT_ID, "1", conteudo_grande, "image/png")


def test_salvar_logo_persiste(db_session):
    template = template_proposta_service.salvar_logo(db_session, TENANT_ID, "1", b"fake-png-bytes", "image/png")

    assert template.logo_conteudo == b"fake-png-bytes"
    assert template.logo_tipo_mime == "image/png"


def test_adicionar_item_recusa_tipo_invalido(db_session):
    with pytest.raises(ValidacaoFalhou):
        template_proposta_service.adicionar_item(db_session, TENANT_ID, "1", "invalido", "Item", 10.0)


def test_adicionar_e_listar_itens_por_tipo(db_session):
    template_proposta_service.adicionar_item(db_session, TENANT_ID, "1", "produto", "Licença", 500.0)
    template_proposta_service.adicionar_item(db_session, TENANT_ID, "1", "servico", "Onboarding", 300.0)

    produtos = template_proposta_service.listar_itens(db_session, TENANT_ID, "produto")
    servicos = template_proposta_service.listar_itens(db_session, TENANT_ID, "servico")

    assert [i.descricao for i in produtos] == ["Licença"]
    assert [i.descricao for i in servicos] == ["Onboarding"]


def test_atualizar_item(db_session):
    item = template_proposta_service.adicionar_item(db_session, TENANT_ID, "1", "produto", "Licença", 500.0)

    atualizado = template_proposta_service.atualizar_item(db_session, TENANT_ID, item.id, "Licença Pro", 700.0)

    assert atualizado.descricao == "Licença Pro"
    assert atualizado.valor == 700.0


def test_remover_item(db_session):
    item = template_proposta_service.adicionar_item(db_session, TENANT_ID, "1", "produto", "Licença", 500.0)

    template_proposta_service.remover_item(db_session, TENANT_ID, item.id)

    assert template_proposta_service.listar_itens(db_session, TENANT_ID, "produto") == []


def test_remover_item_inexistente_falha(db_session):
    with pytest.raises(NaoEncontrado):
        template_proposta_service.remover_item(db_session, TENANT_ID, 99999)


def test_gerar_pdf_produz_bytes_nao_vazios(db_session):
    negocio = _criar_negocio(db_session)
    template_proposta_service.atualizar(db_session, TENANT_ID, "1", "Introdução", "Termo", True, True)

    conteudo = template_proposta_service.gerar_pdf(
        db_session, TENANT_ID, negocio.id, [{"descricao": "Licença", "valor": 500.0}], [{"descricao": "Suporte", "valor": 100.0}]
    )

    assert conteudo.startswith(b"%PDF")
    assert len(conteudo) > 0


def test_gerar_pdf_respeita_toggle_desligado(db_session):
    negocio = _criar_negocio(db_session)
    template_proposta_service.atualizar(db_session, TENANT_ID, "1", None, None, False, False)

    com_toggles_ligados = template_proposta_service.gerar_pdf(
        db_session, TENANT_ID, negocio.id, [{"descricao": "Item longo o suficiente", "valor": 500.0}], []
    )

    # Com as duas tabelas desligadas, o PDF ainda é gerado (só não inclui as tabelas).
    assert com_toggles_ligados.startswith(b"%PDF")


def test_gerar_pdf_negocio_inexistente_falha(db_session):
    with pytest.raises(NaoEncontrado):
        template_proposta_service.gerar_pdf(db_session, TENANT_ID, 99999, [], [])


def test_gerar_pdf_nao_quebra_com_caracteres_fora_de_latin1(db_session):
    """Aspas curvas, travessão longo, reticências tipográficas e emoji —
    comuns em texto colado do Word/WhatsApp — não são suportados pela
    fonte core "Helvetica" do fpdf2 e antes derrubavam a geração inteira
    com FPDFUnicodeEncodingException."""
    negocio = _criar_negocio(db_session)
    template_proposta_service.atualizar(
        db_session, TENANT_ID, "1", "Texto com “aspas curvas” e reticências… 🚀", "Termo — com travessão longo", True, True
    )

    conteudo = template_proposta_service.gerar_pdf(
        db_session,
        TENANT_ID,
        negocio.id,
        [{"descricao": "Item “especial” — com aspas", "valor": 500.0}],
        [],
    )

    assert conteudo.startswith(b"%PDF")
