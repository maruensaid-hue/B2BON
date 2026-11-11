from datetime import date, timedelta

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.negocio import Negocio
from app.models.pre_reserva import PreReserva
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service, link_captura_lead_service, pre_reserva_service

TENANT_ID = "tenant-pre-reserva"
HOJE = pre_reserva_service.hoje_no_brasil()
PERTO = HOJE + timedelta(days=3)  # dentro da antecedência mínima: não pode aparecer
LIVRE_1 = HOJE + timedelta(days=20)
LIVRE_2 = HOJE + timedelta(days=21)


def _preparar(db_session, client, papel: str = "admin") -> str:
    db_session.add(Tenant(id=TENANT_ID, razao_social="Dona do Formulário Ltda"))
    usuario = Usuario(
        tenant_id=TENANT_ID, nome="Admin", email=f"admin@{TENANT_ID}.com.br",
        senha_hash=auth_service.hash_senha("senha123"), papel=papel, ativo=True,
    )
    db_session.add(usuario)
    db_session.commit()
    # o cliente da fixture vem autenticado como o usuário padrão de outro tenant: troca pelo dono do formulário
    client.headers["Authorization"] = f"Bearer {auth_service.gerar_token(usuario)}"
    return link_captura_lead_service.obter_ou_criar(db_session, TENANT_ID).codigo


def _config(client, **extra) -> dict:
    corpo = {
        "marca": "O Vendedor Tubarão",
        "titulo": "Palestra O Vendedor Tubarão",
        "datas_disponiveis": [PERTO.isoformat(), LIVRE_1.isoformat(), LIVRE_2.isoformat()],
        "antecedencia_minima_dias": 10,
        "horas_pre_reserva": 48,
        "valor_presencial": 8000,
        "valor_online": 5000,
        "percentual_sinal": 50,
        "formas_pagamento": ["pix", "boleto", "cartao_credito", "cartao_debito"],
        "condicao_especial": "2 horas de consultoria",
        **extra,
    }
    resposta = client.put("/api/v1/pre-reserva/config", json=corpo)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _envio(data: date, **extra) -> dict:
    return {
        "data_evento": data.isoformat(),
        "formato": "presencial",
        "cidade": "Campinas",
        "participantes": 120,
        "forma_pagamento": "pix",
        "nome_empresa": "Distribuidora Exemplo Ltda",
        "cnpj": "12.345.678/0001-90",
        "nome_contato": "Fulana de Tal",
        "cargo_contato": "Diretora comercial",
        "email_contato": "fulana@exemplo.com.br",
        "telefone_contato": "11999998888",
        "observacoes": "Convenção anual",
        "aceite_contato": True,
        **extra,
    }


def test_info_publica_mostra_so_datas_livres_e_fora_da_antecedencia(client, db_session):
    codigo = _preparar(db_session, client)
    _config(client)

    resposta = client.get(f"/api/v1/pre-reserva/{codigo}/info")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["marca"] == "O Vendedor Tubarão"
    assert corpo["datas_livres"] == [LIVRE_1.isoformat(), LIVRE_2.isoformat()]
    assert "tenant_id" not in corpo


def test_sem_configuracao_o_formulario_nao_existe(client, db_session):
    codigo = _preparar(db_session, client)

    assert client.get(f"/api/v1/pre-reserva/{codigo}/info").status_code == 404


def test_pre_reserva_cai_no_crm_com_negocio_e_tira_a_data_da_agenda(client, db_session):
    codigo = _preparar(db_session, client)
    _config(client)

    resposta = client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_1))

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["valor"] == 8000
    assert resposta.json()["valor_sinal"] == 4000
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT_ID).one()
    assert conta.origem == "pre_reserva_publica"
    decisor = db_session.query(Decisor).filter_by(conta_id=conta.id).one()
    assert decisor.telefone == "11999998888"
    negocio = db_session.query(Negocio).filter_by(conta_id=conta.id).one()
    assert negocio.valor == 8000
    assert negocio.decisor_id == decisor.id
    assert LIVRE_1.strftime("%d/%m/%Y") in negocio.nome
    reserva = db_session.query(PreReserva).filter_by(tenant_id=TENANT_ID).one()
    assert reserva.status == "pre_reservada"
    assert reserva.forma_pagamento == "pix"

    info = client.get(f"/api/v1/pre-reserva/{codigo}/info").json()
    assert info["datas_livres"] == [LIVRE_2.isoformat()]


def test_data_ja_reservada_ou_fora_da_lista_e_recusada(client, db_session):
    codigo = _preparar(db_session, client)
    _config(client)
    assert client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_1)).status_code == 201

    repetida = client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_1, nome_empresa="Outra SA"))
    perto = client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(PERTO, nome_empresa="Apressada SA"))

    assert repetida.status_code in (409, 422) and "disponível" in repetida.text
    assert perto.status_code in (409, 422)
    assert db_session.query(PreReserva).count() == 1
    assert db_session.query(Conta).filter_by(tenant_id=TENANT_ID).count() == 1


def test_online_usa_o_valor_online_e_presencial_exige_cidade(client, db_session):
    codigo = _preparar(db_session, client)
    _config(client)

    sem_cidade = client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_1, cidade=""))
    online = client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_2, formato="online", cidade=None, forma_pagamento="cartao_credito"))

    assert sem_cidade.status_code == 422
    assert online.status_code == 201, online.text
    assert online.json()["valor"] == 5000


def test_sem_aceite_nao_reserva(client, db_session):
    codigo = _preparar(db_session, client)
    _config(client)

    resposta = client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_1, aceite_contato=False))

    assert resposta.status_code == 422
    assert db_session.query(PreReserva).count() == 0


def test_cancelar_devolve_a_data_e_confirmar_registra_no_crm(client, db_session):
    codigo = _preparar(db_session, client)
    _config(client)
    client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_1))
    client.post(f"/api/v1/pre-reserva/{codigo}", json=_envio(LIVRE_2, nome_empresa="Segunda SA"))
    reservas = client.get("/api/v1/pre-reserva/reservas").json()
    assert [r["nome_empresa"] for r in reservas] == ["Distribuidora Exemplo Ltda", "Segunda SA"]

    assert client.post(f"/api/v1/pre-reserva/reservas/{reservas[0]['id']}/status", json={"status": "cancelada"}).status_code == 204
    assert client.post(f"/api/v1/pre-reserva/reservas/{reservas[1]['id']}/status", json={"status": "confirmada"}).status_code == 204

    info = client.get(f"/api/v1/pre-reserva/{codigo}/info").json()
    assert info["datas_livres"] == [LIVRE_1.isoformat()]
    status = {r["nome_empresa"]: r["status"] for r in client.get("/api/v1/pre-reserva/reservas").json()}
    assert status == {"Distribuidora Exemplo Ltda": "cancelada", "Segunda SA": "confirmada"}


def test_vendedor_nao_configura_o_formulario(client, db_session):
    _preparar(db_session, client, papel="vendedor")

    assert client.put("/api/v1/pre-reserva/config", json={"marca": "X", "titulo": "Y"}).status_code == 403
    assert client.get("/api/v1/pre-reserva/reservas").status_code == 403
