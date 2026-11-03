"""WhatsApp sem template (Direct Send da Meta, categoria utilidade) com as travas, e conexão do número pelo botão da Meta."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import settings
from app.models.aprovacao import Aprovacao
from app.models.cadencia import Cadencia
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.toque_cadencia import ToqueCadencia
from app.providers.channels.whatsapp.meta import MetaWhatsAppProvider
from app.services import cadencia_service, envio_service, whatsapp_conexao_service, whatsapp_service
from app.services.errors import RegraNegocioViolada

TENANT = "tenant-direct-send"
RECUSA = (100, "Meta recusou (100): Parameter Invalid: The 'category' value requires Direct Send, which isn't enabled for this account.")


def _config(db, direct_send=True):
    db.add(ConfiguracaoWhatsApp(tenant_id=TENANT, access_token="EAAGteste", phone_number_id="111", business_account_id="222",
                                direct_send_habilitado=direct_send))
    db.commit()


def _decisor(db, ultima_interacao=None):
    conta = Conta(tenant_id=TENANT, nome="Clínica Sorriso", status="prospectada")
    db.add(conta)
    db.flush()
    decisor = Decisor(tenant_id=TENANT, conta_id=conta.id, nome="Marina Alves", telefone="5511999990000", ultima_interacao_em=ultima_interacao)
    db.add(decisor)
    db.commit()
    db.expire_all()  # relê do banco: a data volta sem fuso, como em produção
    return db.get(Decisor, decisor.id)


def _mensagem(db, decisor, conteudo, modo="direct_send"):
    mensagem = Mensagem(tenant_id=TENANT, decisor_id=decisor.id, canal="whatsapp", conteudo=conteudo, status="aprovado",
                        agendado_para=datetime.now(UTC) - timedelta(minutes=1), whatsapp_modo=modo)
    db.add(mensagem)
    db.flush()
    db.add(Aprovacao(tenant_id=TENANT, mensagem_id=mensagem.id, status="aprovado"))
    db.commit()
    return mensagem


class _Resposta:
    def __init__(self, status, corpo):
        self.status_code, self._corpo = status, corpo
        self.is_success = 200 <= status < 300

    def json(self):
        return self._corpo


# --- Provedor -------------------------------------------------------------------------------------------------------------

def test_provedor_envia_com_categoria_utilidade_e_le_o_erro_da_meta(monkeypatch):
    chamadas = []

    def post(url, json=None, headers=None, timeout=None):
        chamadas.append(json)
        if len(chamadas) == 1:
            return _Resposta(200, {"messages": [{"id": "wamid.1"}]})
        return _Resposta(400, {"error": {"code": 131047, "message": "Re-engagement message"}})

    urls = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (urls.append(url), post(url, **kw))[1])
    provider = MetaWhatsAppProvider("t", "111", "222")

    assert provider.enviar_direct_send("5511", "Oi").id_externo == "wamid.1"
    assert chamadas[0]["category"] == "utility" and chamadas[0]["type"] == "text"
    falha = provider.enviar_texto_livre("5511", "Oi")
    assert falha.codigo_erro == 131047 and "Re-engagement" in falha.motivo_falha
    assert urls[0] == f"https://graph.facebook.com/{settings.meta_graph_versao}/111/messages"


def test_versao_da_graph_api_nao_esta_expirada():
    # v20.0 expirou em 24/09/2026 (calendário de versões da Meta); a configuração padrão precisa ser uma versão ainda suportada.
    assert int(settings.meta_graph_versao.lstrip("v").split(".")[0]) >= 26


# --- Regras do serviço ----------------------------------------------------------------------------------------------------

def test_sem_conta_habilitada_ou_com_texto_promocional_nao_tenta(db_session, fake_whatsapp):
    _config(db_session, direct_send=False)
    assert whatsapp_service.enviar_direct_send(db_session, TENANT, fake_whatsapp, "5511", "Oi, tudo bem?") is None
    db_session.query(ConfiguracaoWhatsApp).update({"direct_send_habilitado": True})
    db_session.commit()
    assert whatsapp_service.enviar_direct_send(db_session, TENANT, fake_whatsapp, "5511", "Temos 20% de desconto!") is None
    assert fake_whatsapp.envios == []


def test_recusa_da_meta_desliga_o_recurso_no_tenant(db_session, fake_whatsapp):
    _config(db_session)
    fake_whatsapp.erro_direct_send = RECUSA

    whatsapp_service.enviar_direct_send(db_session, TENANT, fake_whatsapp, "5511", "Sua reunião é amanhã às 10h.")
    db_session.commit()

    config = db_session.query(ConfiguracaoWhatsApp).one()
    assert config.direct_send_habilitado is False and "requires Direct Send" in config.direct_send_motivo_desligado


def test_aviso_de_utilidade_usa_direct_send_e_cai_para_texto_livre_sem_ele(db_session, fake_whatsapp):
    _config(db_session)
    whatsapp_service.enviar_aviso(db_session, TENANT, fake_whatsapp, "5511", "Lembrete: reunião amanhã às 10h.")
    db_session.query(ConfiguracaoWhatsApp).update({"direct_send_habilitado": False})
    db_session.commit()
    whatsapp_service.enviar_aviso(db_session, TENANT, fake_whatsapp, "5511", "Lembrete: reunião amanhã às 10h.")

    assert [e["tipo"] for e in fake_whatsapp.envios] == ["direct_send", "livre"]


# --- Envio da cadência ----------------------------------------------------------------------------------------------------

def test_janela_fechada_sai_por_direct_send_e_janela_aberta_por_texto_livre(db_session, fake_whatsapp):
    _config(db_session)
    fora = _decisor(db_session)
    dentro = _decisor(db_session, ultima_interacao=datetime.now(UTC) - timedelta(hours=2))

    assert envio_service._processar_whatsapp(db_session, _mensagem(db_session, fora, "Vi as vagas abertas. Ainda faz sentido?"), fora, fake_whatsapp).sucesso
    assert envio_service._processar_whatsapp(db_session, _mensagem(db_session, dentro, "Combinado!"), dentro, fake_whatsapp).sucesso
    assert [e["tipo"] for e in fake_whatsapp.envios] == ["direct_send", "livre"]


def test_sem_o_modo_a_regra_antiga_continua_adiando(db_session, fake_whatsapp):
    _config(db_session)
    fora = _decisor(db_session)
    assert envio_service._processar_whatsapp(db_session, _mensagem(db_session, fora, "Oi", modo=None), fora, fake_whatsapp) is None
    assert fake_whatsapp.envios == []


def test_texto_promocional_volta_para_revisao_em_vez_de_sair(db_session, fake_whatsapp):
    _config(db_session)
    fora = _decisor(db_session)
    mensagem = _mensagem(db_session, fora, "Condição especial só hoje, 30% de desconto!")

    assert envio_service._processar_whatsapp(db_session, mensagem, fora, fake_whatsapp) is None
    db_session.commit()
    db_session.refresh(mensagem)
    assert mensagem.status == "aguardando_aprovacao" and "promocional" in mensagem.motivo_falha
    assert fake_whatsapp.envios == []


# --- Cadência: a trava ----------------------------------------------------------------------------------------------------

def _cadencia_com_whatsapp(db):
    cadencia = Cadencia(tenant_id=TENANT, nome="C", canais=["whatsapp", "email"], status="rascunho")
    db.add(cadencia)
    db.flush()
    toque = ToqueCadencia(tenant_id=TENANT, cadencia_id=cadencia.id, ordem=1, canal="whatsapp", template_whatsapp_id="tpl")
    db.add(toque)
    db.commit()
    return cadencia, toque


def test_ligar_sem_template_exige_conta_habilitada_e_risco_aceito(db_session):
    cadencia, toque = _cadencia_com_whatsapp(db_session)
    with pytest.raises(RegraNegocioViolada, match="não está habilitada"):
        cadencia_service.definir_whatsapp_sem_template(db_session, TENANT, "7", cadencia.id, toque.id, True, True)
    _config(db_session)
    with pytest.raises(RegraNegocioViolada, match="risco"):
        cadencia_service.definir_whatsapp_sem_template(db_session, TENANT, "7", cadencia.id, toque.id, True, False)

    cadencia_service.definir_whatsapp_sem_template(db_session, TENANT, "7", cadencia.id, toque.id, True, True)

    db_session.refresh(cadencia)
    db_session.refresh(toque)
    assert toque.whatsapp_sem_template is True and cadencia.direct_send_aceito_por == "7" and cadencia.direct_send_aceito_em


def test_toque_sem_template_passa_na_validacao_e_sem_nenhum_dos_dois_nao():
    class T:
        def __init__(self, sem_template):
            self.canal, self.template_whatsapp_id, self.whatsapp_sem_template = "whatsapp", None, sem_template

    cadencia_service._validar_no_maximo_um_whatsapp_com_template([T(True)])
    with pytest.raises(RegraNegocioViolada):
        cadencia_service._validar_no_maximo_um_whatsapp_com_template([T(False)])


# --- Conexão pelo botão da Meta -------------------------------------------------------------------------------------------

@pytest.fixture()
def meta_configurada(monkeypatch):
    monkeypatch.setattr(settings, "meta_app_id", "123")
    monkeypatch.setattr(settings, "meta_embedded_signup_config_id", "456")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "segredo")


def test_sem_app_configurado_o_botao_nao_aparece(monkeypatch):
    monkeypatch.setattr(settings, "meta_app_id", "")
    assert whatsapp_conexao_service.parametros()["disponivel"] is False


def test_conectar_troca_o_codigo_inscreve_registra_e_salva(db_session, meta_configurada, monkeypatch):
    chamadas = []

    def get(url, params=None, headers=None, timeout=None):
        chamadas.append(("GET", url))
        if url.endswith("/oauth/access_token"):
            assert params["client_secret"] == "segredo" and params["code"] == "codigo-1"
            return _Resposta(200, {"access_token": "EAAGnovo"})
        return _Resposta(200, {"display_phone_number": "+55 11 98888-7777", "verified_name": "Clínica Sorriso", "quality_rating": "GREEN"})

    def post(url, json=None, headers=None, timeout=None):
        chamadas.append(("POST", url))
        return _Resposta(200, {"success": True})

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(httpx, "post", post)

    resultado = whatsapp_conexao_service.conectar(db_session, TENANT, "1", "codigo-1", "111", "222")

    assert resultado["numero_exibicao"] == "+55 11 98888-7777" and resultado["avisos"] == []
    assert ("POST", f"https://graph.facebook.com/{settings.meta_graph_versao}/222/subscribed_apps") in chamadas
    assert ("POST", f"https://graph.facebook.com/{settings.meta_graph_versao}/111/register") in chamadas
    config = db_session.query(ConfiguracaoWhatsApp).one()
    assert config.access_token == "EAAGnovo" and config.origem_conexao == "meta_conectar"
    assert config.qualidade == "GREEN" and len(config.pin_registro) == 6


def test_registro_recusado_conecta_mesmo_assim_com_aviso(db_session, meta_configurada, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **_: _Resposta(200, {"access_token": "EAAGnovo"} if "oauth" in url else {}))
    monkeypatch.setattr(httpx, "post", lambda url, **_: _Resposta(400, {"error": {"message": "PIN mismatch"}}) if url.endswith("/register")
                        else _Resposta(200, {}))

    resultado = whatsapp_conexao_service.conectar(db_session, TENANT, "1", "c", "111", "222")

    assert any("PIN mismatch" in aviso for aviso in resultado["avisos"])
    assert db_session.query(ConfiguracaoWhatsApp).one().pin_registro is None


def test_codigo_recusado_nao_salva_nada(db_session, meta_configurada, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **_: _Resposta(400, {"error": {"message": "Code expired"}}))
    with pytest.raises(RegraNegocioViolada, match="Code expired"):
        whatsapp_conexao_service.conectar(db_session, TENANT, "1", "c", "111", "222")
    assert db_session.query(ConfiguracaoWhatsApp).count() == 0
