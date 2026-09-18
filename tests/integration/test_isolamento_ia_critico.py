"""Teste crítico obrigatório do master prompt (§88):

    Tenant C tem segredo
        ↓
    Tenant B pergunta à IA (agente do Tenant A)
        ↓
    ESPERADO: SEM ACESSO, SEM RETRIEVAL, SEM VAZAMENTO

Tenant A (o `client` padrão, "tenant-teste") ativa seu próprio agente
corporativo e está conectado ao Tenant B — isso é o uso PRETENDIDO
(B pode ver o que A cadastrou). O risco real a provar é diferente:
mesmo que a pergunta de B "acerte" por coincidência de palavras-chave
o segredo de um TERCEIRO tenant (C, sem nenhuma conexão com A nem B),
esse segredo nunca deve aparecer — `_buscar_conhecimento` é escopado
só ao `tenant_id_alvo` da pergunta."""

from app.models.oferta import Oferta
from app.services import agente_corporativo_service

TENANT_B = "tenant-outro"
TENANT_C_SEGREDO = "tenant-terceiro-com-segredo"
SEGREDO_DO_TENANT_C = "Projeto Confidencial Vortex-77 fusão hostil"


def test_pergunta_nao_vaza_segredo_de_tenant_terceiro_nao_conectado(client, criar_usuario_autenticado, db_session):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")

    # Tenant C: segredo real, sem NENHUMA conexão com A ou B.
    db_session.add(
        Oferta(
            tenant_id=TENANT_C_SEGREDO,
            nome="Oferta Interna",
            descricao=SEGREDO_DO_TENANT_C,
            ativo=True,
        )
    )
    db_session.commit()

    # Tenant A (client padrão) ativa o próprio agente, conectado a B.
    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B}).json()
    client.put(f"/api/v1/rede-social/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_b)
    client.put("/api/v1/agente-corporativo/modo", json={"modo": "assistido"})

    # B pergunta ao agente de A usando as MESMAS palavras-chave do
    # segredo de C — A não tem nada sobre isso cadastrado.
    resposta = client.post(
        "/api/v1/agente-corporativo/perguntar",
        json={"tenant_id_alvo": "tenant-teste", "pergunta": "Vocês sabem algo sobre o Projeto Vortex-77 fusão hostil?"},
        headers=headers_b,
    )

    assert resposta.status_code == 201
    dados = resposta.json()
    assert SEGREDO_DO_TENANT_C not in (dados["resposta_rascunho"] or "")
    assert all(SEGREDO_DO_TENANT_C not in str(evidencia) for evidencia in dados["evidencias"])
    assert dados["evidencias"] == []


def test_buscar_conhecimento_nunca_cruza_tenant_mesmo_com_keyword_identica(db_session):
    """Mesmo teste, direto na função de serviço (sem HTTP) — prova que
    `_buscar_conhecimento` em si nunca olha pra outro tenant, mesmo que
    a pergunta contenha exatamente as palavras do segredo de outro."""
    db_session.add(
        Oferta(tenant_id=TENANT_C_SEGREDO, nome="Oferta Interna", descricao=SEGREDO_DO_TENANT_C, ativo=True)
    )
    db_session.commit()

    evidencias = agente_corporativo_service._buscar_conhecimento(
        db_session, "tenant-teste", "Projeto Confidencial Vortex-77 fusão hostil"
    )

    assert evidencias == []
