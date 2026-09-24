import csv
from datetime import UTC, datetime

from app.api.deps import get_crm_provider
from app.main import app
from app.models.conta import Conta
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.providers.crm.nucleo import NucleoCrmProvider

TENANT_ID = "tenant-teste"


def test_dashboard_funil_com_filtro_de_vendedor_via_api(client, db_session, criar_conta_com_decisor):
    """Raio-X 2026-09-24 (MAP por vendedor) — plumbing do query param
    opcional; a lógica de filtro em si já é testada em
    `test_crm_service.py`."""
    conta, decisor = criar_conta_com_decisor()
    client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0},
    )

    resposta_sem_filtro = client.get("/api/v1/crm/dashboard/funil")
    assert resposta_sem_filtro.status_code == 200

    resposta_com_filtro = client.get("/api/v1/crm/dashboard/funil", params={"vendedor_usuario_id": 999})
    assert resposta_com_filtro.status_code == 200
    assert sum(e["quantidade"] for e in resposta_com_filtro.json()["estagios"]) == 0


def test_listar_vendedores_com_contas_via_api(client, db_session, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()
    conta.vendedor_usuario_id = 1  # ATOR_ID da fixture `client` é sempre "1"
    db_session.commit()

    resposta = client.get("/api/v1/crm/vendedores-com-contas")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 1
    assert corpo[0]["usuario_id"] == 1
    assert corpo[0]["contas"][0]["id"] == conta.id


def test_estagios_padrao_via_api(client):
    resposta = client.get("/api/v1/crm/estagios")

    assert resposta.status_code == 200
    estagios = resposta.json()
    assert len(estagios) == 5
    assert {e["tipo"] for e in estagios} == {"aberto", "ganho", "perdido"}


def test_criar_estagio_via_api(client):
    """Client de teste é super_admin por padrão — "Editar Funil"."""
    resposta = client.post("/api/v1/crm/estagios", json={"nome": "Qualificação", "tipo": "aberto"})

    assert resposta.status_code == 201
    assert resposta.json()["nome"] == "Qualificação"

    listagem = client.get("/api/v1/crm/estagios").json()
    assert len(listagem) == 6


def test_definir_estagio_renomeia_via_api(client):
    estagio = client.get("/api/v1/crm/estagios").json()[0]

    resposta = client.put(f"/api/v1/crm/estagios/{estagio['id']}", json={"nome": "Nome Novo"})

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Nome Novo"


def test_criar_estagio_tipo_invalido_via_api_retorna_422(client):
    resposta = client.post("/api/v1/crm/estagios", json={"nome": "Estágio X", "tipo": "cancelado"})

    assert resposta.status_code == 422


def test_criar_e_definir_estagio_bloqueado_para_papel_user(client, criar_usuario_autenticado):
    """"Editar Funil" é poder exclusivo de admin/super_admin (pedido
    explícito do usuário) — antes desta entrega, PUT /estagios/{id}
    não tinha nenhuma restrição de papel."""
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="user-estagios@teste.com.br")
    estagio = client.get("/api/v1/crm/estagios").json()[0]

    resposta_criar = client.post(
        "/api/v1/crm/estagios", json={"nome": "Estágio X", "tipo": "aberto"}, headers=headers_user
    )
    resposta_definir = client.put(
        f"/api/v1/crm/estagios/{estagio['id']}", json={"nome": "Tentativa"}, headers=headers_user
    )

    assert resposta_criar.status_code == 403
    assert resposta_definir.status_code == 403


def test_excluir_estagio_via_api(client):
    novo = client.post("/api/v1/crm/estagios", json={"nome": "Fila Temporária", "tipo": "aberto"}).json()

    resposta = client.delete(f"/api/v1/crm/estagios/{novo['id']}")

    assert resposta.status_code == 204
    listagem = client.get("/api/v1/crm/estagios").json()
    assert novo["id"] not in {e["id"] for e in listagem}


def test_excluir_estagio_com_negocio_retorna_409(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    estagio = client.get("/api/v1/crm/estagios").json()[0]
    client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio API", "estagio_id": estagio["id"]},
    )

    resposta = client.delete(f"/api/v1/crm/estagios/{estagio['id']}")

    assert resposta.status_code == 409


def test_excluir_estagio_bloqueado_para_papel_user(client, criar_usuario_autenticado):
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="user-excluir-estagio@teste.com.br")
    estagio = client.get("/api/v1/crm/estagios").json()[0]

    resposta = client.delete(f"/api/v1/crm/estagios/{estagio['id']}", headers=headers_user)

    assert resposta.status_code == 403


def test_reordenar_estagios_via_api(client):
    estagios = client.get("/api/v1/crm/estagios").json()
    nova_ordem = list(reversed([e["id"] for e in estagios]))

    resposta = client.post("/api/v1/crm/estagios/reordenar", json={"ordem_ids": nova_ordem})

    assert resposta.status_code == 200
    assert [e["id"] for e in resposta.json()] == nova_ordem


def test_reordenar_estagios_conjunto_incompleto_retorna_422(client):
    estagios = client.get("/api/v1/crm/estagios").json()
    ids_parciais = [e["id"] for e in estagios[:-1]]

    resposta = client.post("/api/v1/crm/estagios/reordenar", json={"ordem_ids": ids_parciais})

    assert resposta.status_code == 422


def test_criar_e_listar_negocio_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()

    criado = client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio API", "valor": 5000.0},
    )
    assert criado.status_code == 201
    assert criado.json()["origem"] == "manual"
    assert criado.json()["conta_nome"]
    assert criado.json()["decisor_nome"] == decisor.nome

    listagem = client.get("/api/v1/crm/negocios").json()
    assert any(n["nome"] == "Negócio API" for n in listagem)


def test_criar_negocio_sem_decisor_via_api_falha(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()

    resposta = client.post("/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio", "valor": 100.0})

    assert resposta.status_code == 422


def test_listar_negocios_filtra_por_conta(client, criar_conta_com_decisor):
    """Necessário para a página "Ações na conta" (E-Leads) mostrar só as
    oportunidades daquela conta, não o kanban inteiro do tenant."""
    conta_a, decisor_a = criar_conta_com_decisor()
    conta_b, decisor_b = criar_conta_com_decisor()
    client.post("/api/v1/crm/negocios", json={"conta_id": conta_a.id, "decisor_id": decisor_a.id, "nome": "Negócio A", "valor": 100.0})
    client.post("/api/v1/crm/negocios", json={"conta_id": conta_b.id, "decisor_id": decisor_b.id, "nome": "Negócio B", "valor": 200.0})

    resposta = client.get(f"/api/v1/crm/negocios?conta_id={conta_a.id}").json()

    assert [n["nome"] for n in resposta] == ["Negócio A"]


def test_mover_estagio_via_api_marca_cliente(client, criar_conta_com_decisor):
    """E2-H4-like (Onda B): mover para estágio "ganho" marca a conta como cliente."""
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 1000.0}
    ).json()
    estagio_ganho = next(e for e in client.get("/api/v1/crm/estagios").json() if e["tipo"] == "ganho")

    resposta = client.put(f"/api/v1/crm/negocios/{negocio['id']}/estagio", json={"estagio_id": estagio_ganho["id"]})

    assert resposta.status_code == 200
    assert resposta.json()["ganho_em"] is not None


def test_mover_estagio_para_perdido_sem_motivo_via_api_falha(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 1000.0}
    ).json()
    estagio_perdido = next(e for e in client.get("/api/v1/crm/estagios").json() if e["tipo"] == "perdido")

    resposta = client.put(f"/api/v1/crm/negocios/{negocio['id']}/estagio", json={"estagio_id": estagio_perdido["id"]})

    assert resposta.status_code == 422


def test_excluir_negocio_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio a excluir", "valor": 1000.0}
    ).json()

    resposta = client.delete(f"/api/v1/crm/negocios/{negocio['id']}")

    assert resposta.status_code == 204
    assert client.get("/api/v1/crm/negocios", params={"conta_id": conta.id}).json() == []
    # Reexcluir o mesmo id agora não encontra mais o negócio.
    assert client.delete(f"/api/v1/crm/negocios/{negocio['id']}").status_code == 404


def test_atividade_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0}
    ).json()

    criada = client.post(
        f"/api/v1/crm/negocios/{negocio['id']}/atividades", json={"tipo": "ligacao", "descricao": "Falei com o cliente"}
    )
    assert criada.status_code == 201

    listagem = client.get(f"/api/v1/crm/negocios/{negocio['id']}/atividades").json()
    # +1 automática ("negócio criado") além da registrada manualmente aqui.
    assert len(listagem) == 2
    assert any(a["descricao"] == "Falei com o cliente" for a in listagem)


def test_cancelar_cliente_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0}
    ).json()
    estagio_ganho = next(e for e in client.get("/api/v1/crm/estagios").json() if e["tipo"] == "ganho")
    client.put(f"/api/v1/crm/negocios/{negocio['id']}/estagio", json={"estagio_id": estagio_ganho["id"]})

    resposta = client.post(f"/api/v1/crm/contas/{conta.id}/cancelar-cliente", json={"motivo": "Insatisfeito"})

    assert resposta.status_code == 200
    assert resposta.json()["cliente_cancelado_em"] is not None


def test_cancelar_cliente_sem_ser_cliente_falha(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()

    resposta = client.post(f"/api/v1/crm/contas/{conta.id}/cancelar-cliente", json={})

    assert resposta.status_code == 409


def test_custo_aquisicao_via_api(client):
    resposta = client.put("/api/v1/crm/custo-aquisicao", json={"periodo": "2026-01", "valor": 5000.0})

    assert resposta.status_code == 200
    assert resposta.json()["valor"] == 5000.0


def test_dashboard_funil_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    client.post("/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0})

    resposta = client.get("/api/v1/crm/dashboard/funil")

    assert resposta.status_code == 200
    assert len(resposta.json()["estagios"]) == 5


def test_dashboard_atividade_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 0.0}
    ).json()
    client.post(f"/api/v1/crm/negocios/{negocio['id']}/atividades", json={"tipo": "nota", "descricao": "Nota"})

    resposta = client.get("/api/v1/crm/dashboard/atividade")

    assert resposta.status_code == 200
    # +1 automática ("negócio criado") além da atividade manual registrada aqui.
    assert resposta.json()["total_equipe"] == 2


def test_dashboard_economia_via_api(client):
    periodo_atual = datetime.now(UTC).strftime("%Y-%m")

    resposta = client.get("/api/v1/crm/dashboard/economia", params={"periodo": periodo_atual})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["periodo"] == periodo_atual
    # Raio-X: ROI e CS existiam numa versão anterior do MAP, antes de
    # integrar à B2B ON — pedido do usuário pra trazer de volta.
    assert "roi" in corpo
    assert "cs_score" in corpo
    assert "nps_medio" in corpo


def test_dashboard_flywheel_via_api(client):
    resposta = client.get("/api/v1/crm/dashboard/flywheel")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "metrica_norte" in corpo
    assert "funil" in corpo


def test_anexar_listar_e_baixar_proposta_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0}
    ).json()

    anexada = client.post(
        f"/api/v1/crm/negocios/{negocio['id']}/propostas",
        files={"arquivo": ("proposta.pdf", b"%PDF-1.4 conteudo", "application/pdf")},
        data={"nome": "Proposta Acme Q3"},
    )
    assert anexada.status_code == 201
    assert anexada.json()["versao"] == 1
    assert anexada.json()["nome"] == "Proposta Acme Q3"
    assert anexada.json()["numero"] == 1

    listagem = client.get(f"/api/v1/crm/negocios/{negocio['id']}/propostas").json()
    assert len(listagem) == 1

    download = client.get(f"/api/v1/crm/negocios/{negocio['id']}/propostas/{listagem[0]['id']}/download")
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 conteudo"


def test_anexar_proposta_tipo_invalido_falha_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0}
    ).json()

    resposta = client.post(
        f"/api/v1/crm/negocios/{negocio['id']}/propostas",
        files={"arquivo": ("malware.exe", b"x", "application/x-msdownload")},
    )

    assert resposta.status_code == 422


def test_gerar_proposta_automatica_via_api(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0}
    ).json()
    client.put(
        "/api/v1/template-proposta",
        json={
            "texto_introdutorio": "Bem-vindo",
            "termo_aceite": "Termo",
            "mostrar_tabela_produtos": True,
            "mostrar_tabela_servicos": True,
        },
    )

    gerada = client.post(
        f"/api/v1/crm/negocios/{negocio['id']}/propostas/gerar",
        json={"nome": "Proposta gerada", "itens_produtos": [{"descricao": "Licença", "valor": 500.0}], "itens_servicos": []},
    )

    assert gerada.status_code == 201
    corpo = gerada.json()
    assert corpo["gerada_automaticamente"] is True
    assert corpo["enviada_por_usuario_id"] is None
    assert corpo["nome"] == "Proposta gerada"
    assert corpo["numero"] == 1

    download = client.get(f"/api/v1/crm/negocios/{negocio['id']}/propostas/{corpo['id']}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")


def test_retroalimentacao_reuniao_confirmada_cria_negocio_real(client, db_session, criar_conta_com_decisor):
    """Onda B: o que acontece no PREDATOR aparece no CRM sem nenhuma
    mudança em reuniao_service.py — usa o NucleoCrmProvider real em vez
    do fake_crm padrão da fixture, só neste teste."""
    conta, decisor = criar_conta_com_decisor()
    app.dependency_overrides[get_crm_provider] = lambda: NucleoCrmProvider(db_session)

    proposta = client.post(
        f"/api/v1/decisores/{decisor.id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = proposta["horarios_propostos"][0]
    client.post(f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": horario})

    negocios = client.get("/api/v1/crm/negocios").json()
    negocio_da_reuniao = next(n for n in negocios if n["conta_id"] == conta.id and n["origem"] == "predator_reuniao")

    assert negocio_da_reuniao is not None
    # Ganho de brinde: o contato que conduziu a reunião já vira o
    # responsável pela oportunidade, sem precisar de ação manual.
    assert negocio_da_reuniao["decisor_id"] == decisor.id


def test_importar_negocios_cria_conta_decisor_e_negocio(client, db_session):
    """Raio-X 2026-09-14: cliente chegando de outra plataforma com
    histórico de oportunidades — sem conta/decisor pré-cadastrados."""
    resposta = client.post(
        "/api/v1/crm/negocios/importar",
        json={
            "linhas": [
                {
                    "empresa_nome": "Acme Importada",
                    "empresa_cnpj": "12.345.678/0001-90",
                    "decisor_nome": "Fulano da Silva",
                    "decisor_email": "fulano@acme.com.br",
                    "nome": "Oportunidade Acme",
                    "valor": 1500.0,
                    "probabilidade": 40,
                }
            ]
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["negocios_criados"] == 1
    assert corpo["contas_criadas"] == 1
    assert corpo["decisores_criados"] == 1
    assert corpo["erros"] == []

    negocio = db_session.query(Negocio).filter_by(tenant_id=TENANT_ID, nome="Oportunidade Acme").one()
    estagio = db_session.query(EstagioFunil).filter_by(id=negocio.estagio_id).one()
    assert estagio.tipo == "aberto"

    # Raio-X 2026-09-16: guarda só os dígitos, não o CNPJ formatado da
    # planilha — senão a conta criada aqui ficava com um CNPJ num
    # formato diferente do usado pra BrasilAPI/geração de lista por ICP.
    conta_criada = db_session.query(Conta).filter_by(tenant_id=TENANT_ID, nome="Acme Importada").one()
    assert conta_criada.cnpj == "12345678000190"


def test_importar_negocios_reaproveita_conta_existente_por_cnpj(client, db_session):
    """CNPJ formatado de forma diferente do CSV ainda casa (normalizado
    pra dígitos antes de comparar)."""
    conta_existente = Conta(tenant_id=TENANT_ID, nome="Beta Existente", cnpj="12345678000190", status="prospectada")
    db_session.add(conta_existente)
    db_session.commit()

    resposta = client.post(
        "/api/v1/crm/negocios/importar",
        json={
            "linhas": [
                {
                    "empresa_nome": "Beta Existente Ltda",
                    "empresa_cnpj": "12.345.678/0001-90",
                    "nome": "Oportunidade Beta",
                }
            ]
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["contas_criadas"] == 0
    assert corpo["contas_reaproveitadas"] == 1

    negocio = db_session.query(Negocio).filter_by(tenant_id=TENANT_ID, nome="Oportunidade Beta").one()
    assert negocio.conta_id == conta_existente.id


def test_importar_negocios_reimportar_com_mesma_chave_atualiza(client, db_session):
    linha_base = {
        "chave_importacao": "hubspot-123",
        "empresa_nome": "Gamma Ltda",
        "nome": "Oportunidade Gamma",
        "valor": 1000.0,
    }
    client.post("/api/v1/crm/negocios/importar", json={"linhas": [linha_base]})

    resposta = client.post(
        "/api/v1/crm/negocios/importar",
        json={"linhas": [{**linha_base, "valor": 2000.0, "nome": "Oportunidade Gamma Atualizada"}]},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["negocios_criados"] == 0
    assert corpo["negocios_atualizados"] == 1

    negocios = db_session.query(Negocio).filter_by(tenant_id=TENANT_ID, chave_importacao="hubspot-123").all()
    assert len(negocios) == 1
    assert negocios[0].valor == 2000.0
    assert negocios[0].nome == "Oportunidade Gamma Atualizada"


def test_importar_negocios_sem_chave_reimportar_duplica(client, db_session):
    """Comportamento aceito conscientemente (raio-X 2026-09-14): sem uma
    coluna de ID externo mapeada, reimportar o mesmo CSV duplica."""
    linha = {"empresa_nome": "Delta Ltda", "nome": "Oportunidade Delta", "valor": 500.0}
    client.post("/api/v1/crm/negocios/importar", json={"linhas": [linha]})
    client.post("/api/v1/crm/negocios/importar", json={"linhas": [linha]})

    negocios = db_session.query(Negocio).filter_by(tenant_id=TENANT_ID, nome="Oportunidade Delta").all()
    assert len(negocios) == 2


def test_importar_negocios_estagio_invalido_gera_erro_sem_derrubar_lote(client):
    resposta = client.post(
        "/api/v1/crm/negocios/importar",
        json={
            "linhas": [
                {"empresa_nome": "Epsilon Ltda", "nome": "Oportunidade Epsilon", "estagio_nome": "Estágio Inexistente"},
                {"empresa_nome": "Zeta Ltda", "nome": "Oportunidade Zeta"},
            ]
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["negocios_criados"] == 1
    assert len(corpo["erros"]) == 1
    assert corpo["erros"][0]["linha"] == 1
    assert "Estágio Inexistente" in corpo["erros"][0]["motivo"]


def test_importar_negocios_estagio_ganho_marca_data_e_cliente(client, db_session):
    resposta = client.post(
        "/api/v1/crm/negocios/importar",
        json={
            "linhas": [
                {
                    "empresa_nome": "Theta Ltda",
                    "nome": "Oportunidade Theta",
                    "estagio_nome": "Ganho",
                    "criado_em": "2026-01-10T00:00:00",
                }
            ]
        },
    )

    assert resposta.status_code == 200
    negocio = db_session.query(Negocio).filter_by(tenant_id=TENANT_ID, nome="Oportunidade Theta").one()
    conta = db_session.query(Conta).filter_by(id=negocio.conta_id).one()
    assert negocio.ganho_em is not None
    assert conta.cliente_desde is not None


def test_importar_e_exportar_negocios_bloqueado_para_papel_user(client, criar_usuario_autenticado):
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="user-negocios@teste.com.br")

    resposta_importar = client.post("/api/v1/crm/negocios/importar", json={"linhas": []}, headers=headers_user)
    resposta_exportar = client.get("/api/v1/crm/negocios/exportar.csv", headers=headers_user)

    assert resposta_importar.status_code == 403
    assert resposta_exportar.status_code == 403


def test_exportar_negocios_csv(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio Export", "valor": 100.0},
    )

    resposta = client.get("/api/v1/crm/negocios/exportar.csv")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    linhas = resposta.text.strip().splitlines()
    assert linhas[0].startswith("chave_importacao,empresa_nome,empresa_cnpj")
    assert any("Negócio Export" in linha for linha in linhas[1:])


def test_exportar_e_reimportar_negocios_nao_duplica(client, criar_conta_com_decisor, db_session):
    """Round-trip: exportar a própria B2B ON e reimportar não duplica —
    a `chave_importacao` "b2bon-{id}" preenchida automaticamente no
    export garante que a reimportação atualiza em vez de criar."""
    conta, decisor = criar_conta_com_decisor()
    client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio Roundtrip", "valor": 300.0},
    )

    csv_exportado = client.get("/api/v1/crm/negocios/exportar.csv").text
    leitor = csv.DictReader(csv_exportado.strip().splitlines())
    linhas_importacao = []
    for linha in leitor:
        linha_convertida: dict = {chave: (valor or None) for chave, valor in linha.items()}
        if linha_convertida["valor"] is not None:
            linha_convertida["valor"] = float(linha_convertida["valor"])
        if linha_convertida["probabilidade"] is not None:
            linha_convertida["probabilidade"] = int(linha_convertida["probabilidade"])
        linhas_importacao.append(linha_convertida)

    resposta = client.post("/api/v1/crm/negocios/importar", json={"linhas": linhas_importacao})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["negocios_criados"] == 0
    assert corpo["negocios_atualizados"] == 1

    total = db_session.query(Negocio).filter_by(tenant_id=TENANT_ID, nome="Negócio Roundtrip").count()
    assert total == 1
