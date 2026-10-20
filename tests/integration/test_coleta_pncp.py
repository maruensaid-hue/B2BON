"""Coleta agendada do PNCP: idempotência, recuperação sem duplicar, concorrência, saúde/alerta e isolamento por tenant. Sem rede e sem IA."""

import logging
from datetime import timedelta

import pytest

from app.api.v1.bids import get_fonte_pncp
from app.contexts.bids import coleta
from app.contexts.bids.fontes.base import LicitacaoExterna
from app.contexts.bids.fontes.pncp import ErroFonte, PaginaPncp
from app.core.config import settings
from app.main import app
from app.models.coleta_fonte import ExecucaoColetaFonte
from app.models.licitacao import Licitacao
from app.models.tenant import Tenant
from app.services.errors import ValidacaoFalhou

TENANT = "tenant-teste"
OUTRO = "tenant-outro-coleta"
B = "/api/v1/bids"
AGORA = coleta._agora().replace(hour=12, minute=0, second=0, microsecond=0)


def _item(n: int, objeto: str = "Aquisição de licenças de software") -> LicitacaoExterna:
    return LicitacaoExterna(
        fonte="PNCP", id_externo=f"CTRL-{n}", titulo=f"{objeto} {n}", objeto=objeto, orgao_nome="Órgão", orgao_cnpj="11222333000181",
        modalidade="PUBLIC_TENDER", data_publicacao=None, prazo_proposta=None, valor_estimado=10.0, url=f"https://pncp.test/{n}",
    )


class FonteFalsa:
    """Dublê do FontePncp: `paginas` mapeia (modalidade, uf, pagina) → itens; `falhar` levanta ErroFonte nas próximas chamadas."""

    def __init__(self, paginas=None, total_paginas=1):
        self.paginas, self.total_paginas, self.chamadas, self.falhar = paginas or {}, total_paginas, [], 0

    def buscar_pagina(self, data_inicial, data_final, modalidade, pagina=1, uf=None):
        self.chamadas.append((data_inicial, data_final, modalidade, pagina, uf))
        if self.falhar:
            self.falhar -= 1
            raise ErroFonte("PNCP respondeu 503.", tentativas=3)
        itens = self.paginas.get((modalidade, uf, pagina), [])
        return PaginaPncp(itens, pagina, self.total_paginas, len(itens), 0, 1)


@pytest.fixture(autouse=True)
def _habilitado(monkeypatch):
    monkeypatch.setattr(settings, "pncp_habilitado", True)


@pytest.fixture()
def configurada(db_session):
    coleta.salvar_configuracao(db_session, TENANT, None, {"ativa": True, "modalidades": [6], "palavras_chave": ["software"]})


def _executar(db, fonte, tenant=TENANT, agora=AGORA, disparo="agendado"):
    return coleta.executar(db, tenant, fonte, disparo, agora=agora, dormir=lambda s: None)


def _total(db, tenant=TENANT):
    return db.query(Licitacao).filter_by(tenant_id=tenant, fonte="PNCP").count()


# --- Configuração -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dados",
    [
        {"ativa": True, "modalidades": [], "ufs": ["SP"]},                       # sem modalidade
        {"ativa": True, "modalidades": [6]},                                       # sem UF nem palavra-chave: coletaria o país inteiro
        {"ativa": True, "modalidades": [25], "ufs": ["SP"]},                       # modalidade inexistente
        {"ativa": True, "modalidades": [6], "ufs": ["SAO"]},                       # UF inválida
        {"ativa": True, "modalidades": [6], "ufs": ["SP"], "janela_dias": 30},     # janela acima do teto
    ],
)
def test_configuracao_invalida_e_recusada(db_session, dados):
    with pytest.raises(ValidacaoFalhou):
        coleta.salvar_configuracao(db_session, TENANT, None, dados)


def test_configuracao_desativada_nao_exige_filtro_e_nada_executa(db_session):
    coleta.salvar_configuracao(db_session, TENANT, None, {"ativa": False})
    fonte = FonteFalsa()
    assert _executar(db_session, fonte) is None and fonte.chamadas == []


# --- Execução, idempotência e recuperação ----------------------------------------------------------


def test_execucao_ingere_so_o_que_casa_com_o_filtro_e_registra_tudo(db_session, configurada):
    fonte = FonteFalsa({(6, None, 1): [_item(1), _item(2, "Obras de pavimentação"), _item(3)]})

    execucao = _executar(db_session, fonte)

    assert execucao.estado == "concluida" and execucao.disparo == "agendado"
    assert (execucao.consultados, execucao.inseridos, execucao.atualizados, execucao.ignorados) == (3, 2, 0, 1)
    assert (execucao.paginas, execucao.tentativas, execucao.erro) == (1, 1, None)
    assert execucao.duracao_ms is not None and execucao.concluida_em >= execucao.iniciada_em
    assert execucao.cursor_referencia == execucao.data_final == AGORA.strftime("%Y%m%d")
    assert _total(db_session) == 2


def test_reexecucao_nao_duplica(db_session, configurada):
    fonte = FonteFalsa({(6, None, 1): [_item(1), _item(2)]})
    _executar(db_session, fonte)

    segunda = _executar(db_session, fonte, agora=AGORA + timedelta(hours=6))

    assert (segunda.inseridos, segunda.atualizados) == (0, 2) and _total(db_session) == 2


def test_falha_da_fonte_registra_nao_perde_dados_e_a_proxima_execucao_recupera(db_session, configurada):
    fonte = FonteFalsa({(6, None, 1): [_item(1), _item(2)]})
    _executar(db_session, fonte)
    cursor = coleta.saude(db_session, TENANT, AGORA)["cursor_referencia"]

    fonte.falhar = 1
    falha = _executar(db_session, fonte, agora=AGORA + timedelta(hours=6))

    assert falha.estado == "falhou" and "503" in falha.erro and falha.tentativas == 3
    assert _total(db_session) == 2  # nada foi apagado
    assert coleta.saude(db_session, TENANT, AGORA)["cursor_referencia"] == cursor  # o cursor não avançou

    fonte.paginas[(6, None, 1)] = [_item(1), _item(2), _item(3)]
    recuperada = _executar(db_session, fonte, agora=AGORA + timedelta(hours=12))

    assert recuperada.estado == "concluida" and (recuperada.inseridos, recuperada.atualizados) == (1, 2)
    assert _total(db_session) == 3  # sem duplicar


def test_falha_no_meio_mantem_o_progresso_das_paginas_anteriores(db_session, configurada):
    class FalhaNaSegunda(FonteFalsa):
        def buscar_pagina(self, *args):
            if args[3] == 2:
                raise ErroFonte("PNCP indisponível no momento.", tentativas=3)
            return super().buscar_pagina(*args)

    fonte = FalhaNaSegunda({(6, None, 1): [_item(1), _item(2)]}, total_paginas=2)

    execucao = _executar(db_session, fonte)

    assert execucao.estado == "falhou" and execucao.inseridos == 2 and _total(db_session) == 2


def test_janela_continua_do_cursor_com_um_dia_de_sobreposicao_e_no_maximo_7_dias(db_session, configurada):
    fonte = FonteFalsa()
    primeira = _executar(db_session, fonte)
    assert primeira.data_inicial == (AGORA - timedelta(days=2)).strftime("%Y%m%d")

    depois = _executar(db_session, fonte, agora=AGORA + timedelta(days=20))  # 20 dias parado

    assert depois.data_inicial == (AGORA - timedelta(days=1)).strftime("%Y%m%d")  # cursor − 1
    assert depois.data_final == (AGORA + timedelta(days=6)).strftime("%Y%m%d")   # início + 7: recupera aos poucos


def test_teto_de_novas_deixa_a_execucao_parcial_sem_avancar_o_cursor(db_session):
    coleta.salvar_configuracao(db_session, TENANT, None,
                               {"ativa": True, "modalidades": [6], "ufs": ["SP"], "max_novas_por_execucao": 2})
    fonte = FonteFalsa({(6, "SP", 1): [_item(1), _item(2)], (6, "SP", 2): [_item(3), _item(4)]}, total_paginas=2)

    execucao = _executar(db_session, fonte)

    assert execucao.estado == "parcial" and execucao.inseridos == 2 and execucao.cursor_referencia is None
    assert coleta.saude(db_session, TENANT, AGORA)["estado"] == "atrasada"  # sem sincronização completa


# --- Concorrência -----------------------------------------------------------------------------------


def test_nao_inicia_outra_execucao_enquanto_uma_esta_em_andamento(db_session, configurada):
    db_session.add(ExecucaoColetaFonte(tenant_id=TENANT, fonte="PNCP", estado="em_andamento", iniciada_em=AGORA - timedelta(minutes=5)))
    db_session.commit()
    fonte = FonteFalsa({(6, None, 1): [_item(1)]})

    assert _executar(db_session, fonte) is None
    assert fonte.chamadas == [] and _total(db_session) == 0


def test_execucao_esquecida_e_encerrada_e_a_coleta_segue(db_session, configurada):
    db_session.add(ExecucaoColetaFonte(tenant_id=TENANT, fonte="PNCP", estado="em_andamento", iniciada_em=AGORA - timedelta(hours=2)))
    db_session.commit()

    execucao = _executar(db_session, FonteFalsa({(6, None, 1): [_item(1)]}))

    assert execucao.estado == "concluida"
    antiga = db_session.query(ExecucaoColetaFonte).filter_by(estado="falhou").one()
    assert "interrompida" in antiga.erro


# --- Saúde e alerta ---------------------------------------------------------------------------------


def test_saude_percorre_os_estados(db_session, configurada):
    assert coleta.saude(db_session, OUTRO, AGORA)["estado"] == "desabilitada"
    assert coleta.saude(db_session, TENANT, AGORA)["estado"] == "nunca_executada"

    fonte = FonteFalsa()
    _executar(db_session, fonte)
    saudavel = coleta.saude(db_session, TENANT, AGORA)
    assert saudavel["estado"] == "saudavel" and saudavel["ultima_concluida_em"] is not None
    assert saudavel["cursor_referencia"] == AGORA.strftime("%Y%m%d")

    assert coleta.saude(db_session, TENANT, AGORA + timedelta(hours=settings.coleta_atraso_horas + 1))["estado"] == "atrasada"


def test_falhas_seguidas_viram_falhando_e_geram_alerta_no_log(db_session, configurada, caplog):
    fonte = FonteFalsa()
    fonte.falhar = 10
    with caplog.at_level(logging.ERROR):
        for horas in range(settings.coleta_falhas_alerta):
            _executar(db_session, fonte, agora=AGORA + timedelta(hours=horas))

    saude = coleta.saude(db_session, TENANT, AGORA + timedelta(hours=3))
    assert saude["estado"] == "falhando" and saude["falhas_consecutivas"] == settings.coleta_falhas_alerta
    assert "503" in saude["ultimo_erro"]
    assert any("COLETA_FONTE_FALHANDO" in r.getMessage() for r in caplog.records)


def test_um_sucesso_zera_a_contagem_de_falhas(db_session, configurada):
    fonte = FonteFalsa()
    fonte.falhar = 2
    _executar(db_session, fonte, agora=AGORA)
    _executar(db_session, fonte, agora=AGORA + timedelta(hours=1))
    _executar(db_session, fonte, agora=AGORA + timedelta(hours=2))
    assert coleta.saude(db_session, TENANT, AGORA + timedelta(hours=2))["falhas_consecutivas"] == 0


# --- Cron, API e isolamento por tenant -----------------------------------------------------------


@pytest.fixture()
def fonte_na_api():
    fonte = FonteFalsa({(6, None, 1): [_item(1), _item(2)]})
    app.dependency_overrides[get_fonte_pncp] = lambda: fonte
    yield fonte
    app.dependency_overrides.pop(get_fonte_pncp, None)


def _cron(client):
    return client.post("/api/v1/cron/coletar-licitacoes", headers={"X-Cron-Secret": settings.cron_secret})


@pytest.fixture()
def com_segredo_de_cron(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "segredo-de-teste")


def test_cron_exige_segredo(client, com_segredo_de_cron):
    assert client.post("/api/v1/cron/coletar-licitacoes").status_code == 403


def test_cron_desligado_no_ambiente_nao_chama_a_fonte(client, com_segredo_de_cron, fonte_na_api, configurada, monkeypatch):
    monkeypatch.setattr(settings, "pncp_habilitado", False)
    assert _cron(client).json() == {"estado": "desabilitada_no_ambiente"}
    assert fonte_na_api.chamadas == []


def test_cron_coleta_cada_tenant_isoladamente(client, com_segredo_de_cron, fonte_na_api, db_session):
    db_session.add(Tenant(id=OUTRO, razao_social="Outro S/A"))
    db_session.commit()
    coleta.salvar_configuracao(db_session, TENANT, None, {"ativa": True, "modalidades": [6], "palavras_chave": ["software"]})
    coleta.salvar_configuracao(db_session, OUTRO, None, {"ativa": True, "modalidades": [6], "palavras_chave": ["software"]})

    resumo = _cron(client).json()

    assert resumo["tenants"] == 2 and resumo["concluidas"] == 2 and resumo["falhas"] == 0
    assert len(fonte_na_api.chamadas) == 1  # mesmo filtro: a rodada consulta o portal uma vez e serve os dois tenants
    assert _total(db_session, TENANT) == 2 and _total(db_session, OUTRO) == 2
    assert {e.tenant_id for e in db_session.query(ExecucaoColetaFonte).all()} == {TENANT, OUTRO}


def test_cron_falha_de_um_tenant_nao_impede_os_outros(client, com_segredo_de_cron, db_session, monkeypatch):
    db_session.add(Tenant(id=OUTRO, razao_social="Outro S/A"))
    db_session.commit()
    for tenant in (TENANT, OUTRO):
        coleta.salvar_configuracao(db_session, tenant, None, {"ativa": True, "modalidades": [6], "palavras_chave": ["software"]})
    original = coleta.executar

    def executar_quebrando_o_primeiro(db, tenant_id, *a, **k):
        if tenant_id == OUTRO:
            raise RuntimeError("falha inesperada")
        return original(db, tenant_id, *a, **k)

    monkeypatch.setattr(coleta, "executar", executar_quebrando_o_primeiro)
    fonte = FonteFalsa({(6, None, 1): [_item(1)]})
    app.dependency_overrides[get_fonte_pncp] = lambda: fonte
    try:
        resumo = _cron(client).json()
    finally:
        app.dependency_overrides.pop(get_fonte_pncp, None)

    assert resumo["concluidas"] == 1 and resumo["falhas"] == 1


def test_api_configuracao_saude_e_historico_so_do_proprio_tenant(client, fonte_na_api, criar_usuario_autenticado):
    corpo = {"ativa": True, "modalidades": [6], "ufs": ["SP"], "palavras_chave": []}
    assert client.put(f"{B}/coleta/pncp/configuracao", json=corpo).status_code == 200
    assert client.get(f"{B}/coleta/pncp/configuracao").json()["ufs"] == ["SP"]
    execucao = client.post(f"{B}/coleta/pncp/executar").json()
    assert execucao["disparo"] == "manual" and execucao["estado"] == "concluida"
    assert client.get(f"{B}/coleta/pncp/saude").json()["estado"] == "saudavel"
    assert len(client.get(f"{B}/coleta/pncp/execucoes").json()) == 1

    outro = criar_usuario_autenticado("tenant-api-coleta-b", papel="admin", email="admin@coleta-b.com")
    assert client.get(f"{B}/coleta/pncp/execucoes", headers=outro).json() == []
    assert client.get(f"{B}/coleta/pncp/configuracao", headers=outro).json()["ativa"] is False
    assert client.get(f"{B}/coleta/pncp/saude", headers=outro).json()["estado"] == "desabilitada"


def test_api_configurar_e_executar_exigem_gestor(client, criar_usuario_autenticado):
    vendedor = criar_usuario_autenticado(TENANT, papel="user", email="vendedor@coleta.com")
    corpo = {"ativa": True, "modalidades": [6], "ufs": ["SP"]}
    assert client.put(f"{B}/coleta/pncp/configuracao", json=corpo, headers=vendedor).status_code == 403
    assert client.post(f"{B}/coleta/pncp/executar", headers=vendedor).status_code == 403
    assert client.get(f"{B}/coleta/pncp/saude", headers=vendedor).status_code == 200


def test_executar_manual_com_ambiente_desligado_e_recusado(client, monkeypatch):
    monkeypatch.setattr(settings, "pncp_habilitado", False)
    assert client.post(f"{B}/coleta/pncp/executar").status_code == 409


def test_coleta_nao_usa_ia(db_session, configurada):
    """A rotina não recebe nem importa provedor de IA: roda por inteiro com a IA indisponível."""
    import inspect

    assert "llm" not in inspect.getsource(coleta).lower().replace("llm_", "")
    assert _executar(db_session, FonteFalsa({(6, None, 1): [_item(1)]})).estado == "concluida"
