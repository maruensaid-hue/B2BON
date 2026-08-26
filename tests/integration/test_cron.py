import pytest

from app.core.config import settings
from app.providers.web_search.base import ResultadoBusca

SEGREDO = "segredo-de-teste-super-secreto"


@pytest.fixture()
def com_segredo_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cron_secret", SEGREDO)


def test_processar_envios_sem_segredo_configurado_recusa(client):
    """cron_secret vazio nunca autoriza, mesmo sem header (Onda I)."""
    resposta = client.post("/api/v1/cron/processar-envios")
    assert resposta.status_code == 403


def test_processar_envios_com_segredo_errado_recusa(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-envios", headers={"X-Cron-Secret": "errado"})
    assert resposta.status_code == 403


def test_processar_envios_sem_header_recusa(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-envios")
    assert resposta.status_code == 403


def test_processar_envios_com_segredo_certo_processa_todos_os_tenants(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-envios", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "totais" in corpo
    assert set(corpo["totais"]) == {
        "enviadas",
        "falhas",
        "adiadas",
        "tarefas_linkedin_criadas",
        "descartadas_email_invalido",
    }
    assert isinstance(corpo["por_tenant"], dict)


def test_processar_retorno_sem_segredo_configurado_recusa(client):
    resposta = client.post("/api/v1/cron/processar-retorno")
    assert resposta.status_code == 403


def test_processar_retorno_com_segredo_certo_processa_todos_os_tenants(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-retorno", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "totais" in corpo
    assert set(corpo["totais"]) == {
        "lembretes_d1_enviados",
        "lembretes_h2_enviados",
        "pesquisas_disparadas",
    }
    assert isinstance(corpo["por_tenant"], dict)


def test_expirar_titulares_sem_segredo_configurado_recusa(client):
    resposta = client.post("/api/v1/cron/expirar-titulares")
    assert resposta.status_code == 403


def test_expirar_titulares_com_segredo_certo_processa_todos_os_tenants(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/expirar-titulares", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "total_decisores_expirados" in corpo
    assert isinstance(corpo["por_tenant"], dict)


def test_suspender_licencas_vencidas_sem_segredo_configurado_recusa(client):
    resposta = client.post("/api/v1/cron/suspender-licencas-vencidas")
    assert resposta.status_code == 403


def test_suspender_licencas_vencidas_com_segredo_certo_retorna_lista(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/suspender-licencas-vencidas", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    assert "tenants_suspensos" in resposta.json()


def test_disparar_webhooks_parceiros_sem_segredo_configurado_recusa(client):
    resposta = client.post("/api/v1/cron/disparar-webhooks-parceiros")
    assert resposta.status_code == 403


def test_disparar_webhooks_parceiros_com_segredo_certo_retorna_resumo(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/disparar-webhooks-parceiros", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    assert set(resposta.json()) == {"entregues", "com_nova_tentativa", "desistencias"}


def test_disparar_relatorios_periodicos_sem_segredo_configurado_recusa(client):
    resposta = client.post("/api/v1/cron/disparar-relatorios-periodicos")
    assert resposta.status_code == 403


def test_disparar_relatorios_periodicos_com_segredo_certo_retorna_resumo(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/disparar-relatorios-periodicos", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    assert set(resposta.json()) == {"tenants_processados", "emails_enviados"}


def test_atualizar_recorte_cnpj_sem_segredo_configurado_recusa(client):
    resposta = client.post("/api/v1/cron/atualizar-recorte-cnpj")
    assert resposta.status_code == 403


def test_atualizar_recorte_cnpj_dispara_em_segundo_plano(client, com_segredo_cron):
    """Responde na hora (raio-X 2026-08-26: download+processamento de
    vários GB facilmente passa do timeout do proxy do Render — a conexão
    cortava com 502 e o processo morria junto) — a lógica de
    executar/pular fica em `test_cnpj_recorte_service.py` (mockada), aqui
    só confirma que a rota aceita e despacha a tarefa."""
    resposta = client.post("/api/v1/cron/atualizar-recorte-cnpj", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    assert resposta.json() == {"disparado": True}


def test_processar_fila_enriquecimento_sem_segredo_configurado_recusa(client):
    resposta = client.post("/api/v1/cron/processar-fila-enriquecimento")
    assert resposta.status_code == 403


def test_processar_fila_enriquecimento_sem_itens_pendentes(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-fila-enriquecimento", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    assert resposta.json() == {"processados": 0, "concluidos": 0, "falhas": 0}


def test_processar_fila_enriquecimento_processa_conta_importada(client, com_segredo_cron, fake_llm, fake_web_search):
    """Fim a fim: importar planilha (via Lista de Prospecção) enfileira, o
    cron processa e enriquece de verdade (mesma cadeia usada pelo botão
    "Enriquecer" de uma conta só, só que disparada em lote)."""
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": "Evento Teste"}).json()
    client.post(
        f"/api/v1/listas-prospeccao/{lista['id']}/contas/importar-participantes",
        json={"participantes": [{"nome": "Joana Silva", "empresa": "Alpha Tech"}]},
    )
    fake_web_search.resultados = [ResultadoBusca(titulo="Alpha Tech", url="https://www.alphatech.com.br/", descricao="")]
    fake_llm.definir_respostas(["porte: media"])

    resposta = client.post("/api/v1/cron/processar-fila-enriquecimento", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["processados"] == 1
    assert corpo["concluidos"] == 1
