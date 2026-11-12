"""SEO e palavras-chave da Inteligência de Oferta: validação, persistência e uso como vocabulário nas mensagens (cadência, resposta comercial e amostra)."""

from types import SimpleNamespace

import pytest

from app.models.icp import ICP
from app.models.oferta import Oferta
from app.services import cadencia_service, oferta_seo
from tests.conftest import TENANT_ID

OFERTAS = "/api/v1/ofertas"


# ---------------------------------------------------------------- módulo de prompt (sem banco)


def _oferta(**campos):
    return SimpleNamespace(**({"palavras_chave": None, "seo_titulo": None, "seo_descricao": None} | campos))


def test_sem_nenhum_campo_o_trecho_e_vazio_e_o_prompt_nao_muda():
    assert oferta_seo.trecho_prompt(_oferta()) == ""
    assert oferta_seo.trecho_prompt(_oferta(palavras_chave=[], seo_titulo="  ", seo_descricao="")) == ""


def test_palavras_chave_normalizadas_sem_repetir_e_na_ordem():
    assert oferta_seo.normalizar_palavras_chave(["  gestão  de licenças ", "SAM", "gestão de licenças", "", "sam"]) == ["gestão de licenças", "SAM"]


def test_trecho_traz_palavras_chave_e_diz_que_nao_sao_fatos_sobre_a_empresa():
    trecho = oferta_seo.trecho_prompt(_oferta(palavras_chave=["gestão de licenças", "SAM"]))

    assert "gestão de licenças, SAM" in trecho and "a primeira é a principal" in trecho
    assert "não são fatos sobre a empresa da pessoa" in trecho and "nunca force, repita nem liste" in trecho
    assert "assunto do e-mail" not in trecho  # sem canal, sem orientação de assunto


def test_email_ganha_orientacao_de_assunto_e_outros_canais_nao():
    oferta = _oferta(palavras_chave=["gestão de licenças"])

    assert "No assunto do e-mail, prefira a palavra-chave principal" in oferta_seo.trecho_prompt(oferta, canal="email")
    assert "assunto do e-mail" not in oferta_seo.trecho_prompt(oferta, canal="linkedin")


def test_seo_entra_como_referencia_de_vocabulario_sem_copiar():
    trecho = oferta_seo.trecho_prompt(_oferta(seo_titulo="Gestão de licenças de software", seo_descricao="Reduza o custo com licenças sem uso."))

    assert "título 'Gestão de licenças de software'" in trecho and "descrição 'Reduza o custo com licenças sem uso.'" in trecho
    assert "não copie literalmente" in trecho


def test_palavra_chave_que_contem_restricao_nao_vai_ao_prompt():
    oferta = _oferta(palavras_chave=["desconto em licenças", "gestão de licenças", "SAM"])

    permitidas = oferta_seo.palavras_chave_permitidas(oferta, ["Desconto", "  "])

    assert permitidas == ["gestão de licenças", "SAM"]
    assert "desconto" not in oferta_seo.trecho_prompt(oferta, ["Desconto"]).lower().split("sobre o que é")[0]


# ---------------------------------------------------------------- API: validação e persistência


def test_criar_oferta_com_seo_e_palavras_chave_guarda_normalizado(client, criar_oferta):
    oferta = criar_oferta(palavras_chave=[" gestão de licenças ", "SAM", "sam"], seo_titulo="  Gestão de licenças  ", seo_descricao="Reduza custo.")

    assert oferta["palavras_chave"] == ["gestão de licenças", "SAM"]
    assert (oferta["seo_titulo"], oferta["seo_descricao"]) == ("Gestão de licenças", "Reduza custo.")
    assert client.get(OFERTAS).json()[0]["palavras_chave"] == ["gestão de licenças", "SAM"]


def test_oferta_antiga_continua_sem_os_campos(client, criar_oferta):
    oferta = criar_oferta()

    assert (oferta["palavras_chave"], oferta["seo_titulo"], oferta["seo_descricao"]) == (None, None, None)


def test_editar_so_o_basico_nao_apaga_seo_nem_palavras_chave(client, criar_oferta):
    oferta = criar_oferta(palavras_chave=["SAM"], seo_titulo="Título")

    resposta = client.put(f"{OFERTAS}/{oferta['id']}", json={"nome": "Novo nome", "descricao": "d", "diferenciais": [], "provas_sociais": []})

    assert resposta.status_code == 200
    assert resposta.json()["palavras_chave"] == ["SAM"] and resposta.json()["seo_titulo"] == "Título"


def test_editar_pode_limpar_os_campos(client, criar_oferta):
    oferta = criar_oferta(palavras_chave=["SAM"], seo_titulo="Título", seo_descricao="Descrição")

    resposta = client.put(f"{OFERTAS}/{oferta['id']}", json={
        "nome": "n", "descricao": "d", "diferenciais": [], "provas_sociais": [], "palavras_chave": [], "seo_titulo": "", "seo_descricao": None})

    assert resposta.status_code == 200
    assert (resposta.json()["palavras_chave"], resposta.json()["seo_titulo"], resposta.json()["seo_descricao"]) == ([], None, None)


@pytest.mark.parametrize(("campos", "trecho"), [
    ({"palavras_chave": [f"termo {i}" for i in range(16)]}, "no máximo 15"),
    ({"palavras_chave": ["x" * 61]}, "até 60 caracteres"),
    ({"seo_titulo": "t" * 71}, "título SEO pode ter até 70"),
    ({"seo_descricao": "d" * 201}, "descrição SEO pode ter até 200"),
])
def test_limites_de_tamanho_dao_erro_claro(client, campos, trecho):
    resposta = client.post(OFERTAS, json={"nome": "n", "descricao": "d", "diferenciais": [], "provas_sociais": []} | campos)

    assert resposta.status_code == 422 and trecho in str(resposta.json())


def test_oferta_de_outro_tenant_nao_vaza_seo(client, db_session, criar_oferta):
    db_session.add(Oferta(tenant_id="tenant-outro", nome="Alheia", descricao="d", diferenciais=[], provas_sociais=[], palavras_chave=["segredo"]))
    db_session.commit()
    criar_oferta(palavras_chave=["minha"])

    assert [o["palavras_chave"] for o in client.get(OFERTAS).json()] == [["minha"]]


# ---------------------------------------------------------------- uso nas mensagens


def _gerar(client, conta, cadencia):
    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    assert resposta.status_code == 200, resposta.text


def test_cadencia_leva_palavras_chave_e_seo_no_prompt_e_o_assunto_so_no_email(
    client, criar_icp, criar_oferta, configurar_comunicacao, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    criar_icp()
    criar_oferta(palavras_chave=["gestão de licenças", "SAM"], seo_titulo="Gestão de licenças de software", seo_descricao="Reduza custo com licenças sem uso.")
    configurar_comunicacao()
    conta, _ = criar_conta_com_decisor()

    _gerar(client, conta, criar_cadencia())

    prompts = [c.prompt for c in fake_llm.chamadas]
    assert prompts and all("gestão de licenças, SAM" in p for p in prompts)
    assert all("título 'Gestão de licenças de software'" in p for p in prompts)
    por_canal = {"email": [p for p in prompts if "canal email" in p], "outros": [p for p in prompts if "canal email" not in p]}
    assert por_canal["email"] and all("No assunto do e-mail" in p for p in por_canal["email"])
    assert all("No assunto do e-mail" not in p for p in por_canal["outros"])


def test_cadencia_sem_os_campos_tem_o_prompt_de_sempre(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm):
    conta, _ = criar_conta_com_decisor()

    _gerar(client, conta, criar_cadencia())

    assert all("Palavras-chave da oferta" not in c.prompt and "Posicionamento da oferta" not in c.prompt for c in fake_llm.chamadas)


def test_palavra_chave_proibida_pelas_restricoes_nao_chega_ao_prompt(
    client, criar_icp, criar_oferta, configurar_comunicacao, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    criar_icp()
    criar_oferta(palavras_chave=["desconto em licenças", "gestão de licenças"])
    configurar_comunicacao(restricoes=["desconto"])
    conta, _ = criar_conta_com_decisor()

    _gerar(client, conta, criar_cadencia())

    trechos = [p.split("Palavras-chave da oferta")[1].split("Use de uma")[0] for p in (c.prompt for c in fake_llm.chamadas) if "Palavras-chave da oferta" in p]
    assert trechos and all("gestão de licenças" in t and "desconto em licenças" not in t for t in trechos)


def test_whatsapp_sem_template_nao_recebe_seo_nem_palavras_chave(db_session, fake_llm):
    icp = ICP(tenant_id=TENANT_ID, nome="ICP", segmento="TI", cnae_codigos=[], ufs=[], dores=[], gatilhos=[], ativo=True)
    oferta = Oferta(tenant_id=TENANT_ID, nome="Of", descricao="d", diferenciais=["dif"], provas_sociais=[], palavras_chave=["gestão de licenças"], seo_titulo="Título")
    config = SimpleNamespace(tom="consultivo", restricoes=[])
    conta = SimpleNamespace(id=1, tenant_id=TENANT_ID, nome="Conta", resumo_site=None)
    decisor = SimpleNamespace(nome="Ana Silva", cargo="CEO")
    sem_template = SimpleNamespace(ordem=2, canal="whatsapp", whatsapp_sem_template=True)
    com_email = SimpleNamespace(ordem=1, canal="email", whatsapp_sem_template=False)

    cadencia_service._gerar_conteudo_toque(db_session, fake_llm, icp, oferta, config, conta, decisor, sem_template)
    cadencia_service._gerar_conteudo_toque(db_session, fake_llm, icp, oferta, config, conta, decisor, com_email)

    prompt_whatsapp, prompt_email = fake_llm.chamadas[-2].prompt, fake_llm.chamadas[-1].prompt
    assert "SEM template" in prompt_whatsapp and "Palavras-chave da oferta" not in prompt_whatsapp and "Posicionamento da oferta" not in prompt_whatsapp
    assert "Palavras-chave da oferta" in prompt_email and "Posicionamento da oferta" in prompt_email


def test_amostra_de_comunicacao_tambem_usa_o_vocabulario(client, criar_icp, criar_oferta, configurar_comunicacao, fake_llm):
    criar_icp()
    criar_oferta(palavras_chave=["gestão de licenças"])
    configurar_comunicacao()

    resposta = client.post("/api/v1/comunicacao/amostra", json={})

    assert resposta.status_code == 200, resposta.text
    assert any("gestão de licenças" in c.prompt for c in fake_llm.chamadas)
