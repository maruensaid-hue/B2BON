"""Sinais técnicos lidos no HTML da home: pixel de anúncio, plataformas, vagas, agência no rodapé."""

from datetime import UTC, datetime

from app.contexts.predator import sinais, sinais_html
from app.models.conta import Conta
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import conta_service
from tests.fakes import FakeLLMProvider, FakeWebSearchProvider

TENANT = "tenant-sinais-html"
AGORA = datetime(2026, 11, 3, 12, tzinfo=UTC)

HOME = """<html><head>
<link rel="stylesheet" href="/wp-content/themes/x/style.css">
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-123"></script>
<script>gtag('config', 'AW-123456789');</script>
<script>!function(f,b,e,v,n,t,s){}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init', '999');</script>
<script type="application/ld+json">{"@type": "Organization"}</script>
</head><body>
<a href="https://wa.me/5511999999999">Fale no WhatsApp</a>
<a href="https://alpha.gupy.io/jobs/123">Trabalhe conosco</a>
<footer>© 2026 Alpha. Desenvolvido por <a href="https://agenciazeta.com.br">Agência Zeta</a></footer>
</body></html>"""


def _por_codigo(achados):
    return {a.codigo: a for a in achados}


def test_home_completa_gera_todos_os_sinais_com_evidencia():
    achados = _por_codigo(sinais_html.extrair(HOME, "alpha.com.br"))

    assert achados["ANUNCIA_GOOGLE_ADS"].num == 1 and "AW-123456789" in achados["ANUNCIA_GOOGLE_ADS"].trecho
    assert achados["ANUNCIA_META_ADS"].num == 1
    assert achados["TEM_SCHEMA_ORG"].num == 1
    assert achados["WHATSAPP_NO_SITE"].url == "https://wa.me/5511999999999"
    assert achados["TECNOLOGIA_SITE"].texto == "WordPress"
    assert achados["VAGAS_EM_PLATAFORMA"].texto == "Gupy" and achados["VAGAS_EM_PLATAFORMA"].url.startswith("https://alpha.gupy.io")
    assert achados["AGENCIA_NO_RODAPE"].texto == "Agência Zeta" and achados["AGENCIA_NO_RODAPE"].confianca == 0.9


def test_home_vazia_observa_ausencias_e_nao_inventa_texto():
    achados = _por_codigo(sinais_html.extrair("<html><body>Olá</body></html>", "alpha.com.br"))

    assert achados["ANUNCIA_GOOGLE_ADS"].num == 0 and achados["ANUNCIA_META_ADS"].num == 0
    assert {"TECNOLOGIA_SITE", "VAGAS_EM_PLATAFORMA", "AGENCIA_NO_RODAPE"}.isdisjoint(achados)


def test_palavra_solta_no_texto_nao_e_tecnologia_nem_anuncio():
    html = "<p>Somos especialistas em WordPress, VTEX e Google Ads para nossos clientes.</p>"
    achados = _por_codigo(sinais_html.extrair(html, "alpha.com.br"))

    assert "TECNOLOGIA_SITE" not in achados
    assert achados["ANUNCIA_GOOGLE_ADS"].num == 0


def test_plataforma_creditada_no_rodape_nao_e_agencia():
    assert sinais_html._agencia('<footer>Powered by <a href="https://wordpress.org">WordPress</a></footer>', "alpha.com.br") is None


def test_credito_que_aponta_para_o_proprio_dominio_nao_e_agencia():
    assert sinais_html._agencia('<footer>Desenvolvido por <a href="https://www.alpha.com.br">Alpha</a></footer>', "alpha.com.br") is None


def test_credito_sem_link_tem_confianca_menor():
    agencia = sinais_html._agencia("<footer>Site por Estúdio Nove | Todos os direitos</footer>", "alpha.com.br")
    assert agencia.texto == "Estúdio Nove" and agencia.confianca == 0.75


def _conta(db) -> Conta:
    conta = Conta(tenant_id=TENANT, nome="Alpha", dominio="alpha.com.br", status="prospectada")
    db.add(conta)
    db.commit()
    return conta


def test_vaga_que_sumiu_da_home_deixa_de_valer(db_session):
    conta = _conta(db_session)
    sinais.registrar_do_html(db_session, TENANT, conta.id, None, HOME, "alpha.com.br", "confirmado", AGORA)
    db_session.commit()
    sinais.registrar_do_html(db_session, TENANT, conta.id, None, "<html>sem nada</html>", "alpha.com.br", "confirmado", AGORA)
    db_session.commit()

    vigentes = sinais.vigentes(db_session, TENANT, [conta.id])[conta.id]
    assert "VAGAS_EM_PLATAFORMA" not in vigentes and "AGENCIA_NO_RODAPE" not in vigentes
    assert vigentes["ANUNCIA_GOOGLE_ADS"].valor_num == 0


def test_dominio_divergente_nao_grava_sinal_do_html(db_session):
    conta = _conta(db_session)
    assert sinais.registrar_do_html(db_session, TENANT, conta.id, None, HOME, "alpha.com.br", "divergente", AGORA) == []


def test_fatos_de_anuncio_e_vagas_podem_ser_citados(db_session):
    conta = _conta(db_session)
    sinais.registrar_do_html(db_session, TENANT, conta.id, None, HOME, "alpha.com.br", "confirmado", AGORA)
    db_session.commit()

    fatos = sinais.fatos_para_prompt(db_session, TENANT, conta.id)

    assert "investe em anúncios no Google (tag de conversão no site)" in fatos
    assert "está com processo seletivo aberto em plataforma de recrutamento (Gupy)" in fatos
    assert not any("Zeta" in f or "WordPress" in f for f in fatos)  # agência e plataforma não são citáveis


def test_enriquecer_le_o_html_da_home_e_falha_dele_nao_derruba_a_coleta(db_session):
    texto = "=== https://alpha.com.br ===\nAlpha."
    conta = _conta(db_session)
    conta_service.enriquecer(db_session, TENANT, "1", conta.id, FakeLLMProvider(["porte: media"]), lambda d: texto,
                             FakeWebSearchProvider(), StubPlanLimitsProvider(), html_fetcher=lambda d: HOME)
    assert sinais.vigentes(db_session, TENANT, [conta.id])[conta.id]["ANUNCIA_META_ADS"].valor_num == 1

    import httpx

    def falha(_dominio):
        raise httpx.ConnectError("fora do ar")

    outra = _conta(db_session)
    conta_service.enriquecer(db_session, TENANT, "1", outra.id, FakeLLMProvider(["porte: media"]), lambda d: texto,
                             FakeWebSearchProvider(), StubPlanLimitsProvider(), html_fetcher=falha)
    assert "ANUNCIA_META_ADS" not in sinais.vigentes(db_session, TENANT, [outra.id]).get(outra.id, {})
