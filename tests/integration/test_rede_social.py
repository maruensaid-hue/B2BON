from app.api.deps import get_rede_social_provider
from app.main import app
from app.models.indicacao import Indicacao
from app.models.usuario import Usuario
from app.providers.rede_social.nucleo import NucleoRedeSocialProvider

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def test_perfil_padrao_via_api(client):
    resposta = client.get("/api/v1/rede-social/perfil")

    assert resposta.status_code == 200
    assert resposta.json()["tenant_id"] == TENANT_A


def test_atualizar_perfil_via_api(client):
    resposta = client.put(
        "/api/v1/rede-social/perfil", json={"nome_exibicao": "CyberFort", "descricao": "Consultoria de vendas B2B"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["nome_exibicao"] == "CyberFort"


def test_diretorio_solicitar_e_aceitar_conexao(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.put("/api/v1/rede-social/perfil", json={"nome_exibicao": "Empresa B"}, headers=headers_b)

    diretorio = client.get("/api/v1/rede-social/empresas").json()
    entrada_b = next(item for item in diretorio if item["perfil"]["tenant_id"] == TENANT_B)
    assert entrada_b["status_conexao"] == "nenhuma"

    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B})
    assert conexao.status_code == 201
    conexao_id = conexao.json()["id"]

    aceita = client.put(f"/api/v1/rede-social/conexoes/{conexao_id}", json={"aceitar": True}, headers=headers_b)
    assert aceita.status_code == 200
    assert aceita.json()["status"] == "aceita"


def test_mensagem_bloqueada_antes_de_conectar_e_liberada_depois(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="mensagem-b@empresab.com.br")

    bloqueada = client.post(
        "/api/v1/rede-social/mensagens", json={"tenant_id_destinatario": TENANT_B, "texto": "Oi!"}
    )
    assert bloqueada.status_code == 409

    conexao_id = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B}).json()["id"]
    client.put(f"/api/v1/rede-social/conexoes/{conexao_id}", json={"aceitar": True}, headers=headers_b)

    enviada = client.post("/api/v1/rede-social/mensagens", json={"tenant_id_destinatario": TENANT_B, "texto": "Oi!"})
    assert enviada.status_code == 201

    conversa_do_b = client.get(f"/api/v1/rede-social/mensagens/{TENANT_A}", headers=headers_b).json()
    assert len(conversa_do_b) == 1

    marcada = client.post(f"/api/v1/rede-social/mensagens/{enviada.json()['id']}/marcar-lida", headers=headers_b)
    assert marcada.status_code == 200
    assert marcada.json()["lida_em"] is not None


def test_retroalimentacao_indicacao_intra_rede_identificada_de_verdade(
    client, db_session, criar_conta_com_decisor
):
    """Onda C: indicação convertida com o RedeSocialProvider real identifica
    intra-rede sem nenhuma mudança em indicacao_service.py — o indicado é
    contato de um usuário real de outro tenant da B2B ON."""
    conta_promotora, decisor_promotor = criar_conta_com_decisor()
    db_session.add(
        Indicacao(
            tenant_id=TENANT_A,
            promotor_decisor_id=decisor_promotor.id,
            promotor_conta_id=conta_promotora.id,
            codigo_indicacao="COD-TESTE-123",
            canal="whatsapp",
            status="aguardando",
        )
    )
    # o indicado é a mesma pessoa de contato de um assinante (tenant-outro) da B2B ON
    db_session.add(
        Usuario(tenant_id=TENANT_B, nome="Sócio Empresa B", email="socio@empresab.com.br", papel="admin", ativo=True)
    )
    db_session.commit()

    conta_indicada, _ = criar_conta_com_decisor(email="socio@empresab.com.br", telefone="+5511900000001")

    app.dependency_overrides[get_rede_social_provider] = lambda: NucleoRedeSocialProvider(db_session)

    resposta = client.post("/api/v1/indicacoes/COD-TESTE-123/converter", json={"conta_id": conta_indicada.id})

    assert resposta.status_code == 200
    assert resposta.json()["intra_rede"] is True
