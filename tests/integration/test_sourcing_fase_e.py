"""Phase E (plano unificado §41): Enterprise Strategic Sourcing — comprador privado.

- RFP completo: requisitos com peso/obrigatoriedade, descoberta (cadastro interno +
  Business Network só com o que o comprador pode ver), convite, propostas com
  respostas, avaliação, comparação (sem vencedor automático), shortlist,
  negociação por rodadas, aprovação humana por administrador, adjudicação e contrato.
- RFQ leve (itens e preços, sem avaliação técnica) e RFI (respostas, sem adjudicação).
- Barreira: tudo no lado BUY, tenant isolado, módulo próprio, sem IA.
"""

from app.api.deps import get_plan_limits_provider
from app.contexts.sourcing import contract as sourcing
from app.main import app
from app.models.perfil_empresa import PerfilEmpresa
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.sourcing import ContratoSourcing, LadoImutavel, ParticipanteSourcing, ProcessoSourcing
from app.models.tenant import Tenant
from app.providers.plan_limits.stub import StubPlanLimitsProvider

S, P = "/api/v1/sourcing", "/api/v1/procurement"
TENANT = "tenant-teste"


def _processo(client, tipo: str, titulo: str = "Notebooks corporativos com suporte") -> dict:
    resposta = client.post(f"{S}/processos", json={"tipo_processo": tipo, "titulo": titulo, "valor_estimado": 100000})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _status(client, processo_id: int, status: str):
    return client.post(f"{S}/processos/{processo_id}/status", json={"status": status})


def _perfil_rede(db, tenant_id: str, nome: str, visivel: bool = True, **campos) -> None:
    db.add(Tenant(id=tenant_id, razao_social=nome))
    db.add(PerfilEmpresa(tenant_id=tenant_id, nome_exibicao=nome, visivel_no_diretorio=visivel, **campos))
    db.commit()


def test_rfp_da_descoberta_ao_contrato_com_negociacao_e_aprovacao(client, db_session, criar_usuario_autenticado, fake_llm):
    rfp = _processo(client, "RFP")
    url = f"{S}/processos/{rfp['id']}"
    assert (rfp["status"], rfp["workflow"], rfp["ruleset"]) == ("RASCUNHO", "ENTERPRISE_SOURCING_BUY@1", "ENTERPRISE_SOURCING_POLICY@1")
    vazio = _status(client, rfp["id"], "PUBLICADO")
    assert (vazio.status_code, vazio.json()["detalhe"]) == (409, "Cadastre ao menos um requisito ou item antes de publicar.")

    tecnico = client.post(f"{url}/requisitos", json={"categoria": "REQUISITO_TECNICO", "texto": "16 GB de RAM", "obrigatorio": True,
                                                    "peso": 2}).json()
    sla = client.post(f"{url}/requisitos", json={"categoria": "SLA", "texto": "Suporte em 4 horas", "peso": 1}).json()
    pergunta = client.post(f"{url}/requisitos", json={"categoria": "PERGUNTA", "texto": "Qual o prazo de garantia?"}).json()

    # descoberta: cadastro interno + rede (só perfis visíveis; o oculto não aparece nem pode ser convidado)
    interno = client.post(f"{P}/fornecedores", json={"razao_social": "Alfa Notebooks", "categorias": ["notebooks", "desktops"]}).json()
    _perfil_rede(db_session, "rede-beta", "Beta Tecnologia", produtos_servicos=["Notebooks corporativos"], sede_uf="SP")
    _perfil_rede(db_session, "rede-oculta", "Gama Oculta", visivel=False, produtos_servicos=["Notebooks"])
    achados = client.post(f"{url}/descoberta", json={"ufs": ["SP"]}).json()
    nomes = {c["nome"]: c for c in achados["candidatos"]}
    assert set(nomes) == {"Alfa Notebooks", "Beta Tecnologia"}
    assert nomes["Beta Tecnologia"]["origem"] == "NETWORK" and nomes["Alfa Notebooks"]["origem"] == "INTERNAL"
    assert "sede_uf" not in nomes["Alfa Notebooks"] and "cnpj" not in nomes["Beta Tecnologia"]  # só campos permitidos
    oculto = client.post(f"{url}/participantes", json={"empresa_rede_tenant_id": "rede-oculta"})
    assert (oculto.status_code, oculto.json()["detalhe"]) == (422, "Empresa não disponível para convite.")
    alfa = client.post(f"{url}/participantes", json={"fornecedor_id": interno["id"]}).json()
    beta = client.post(f"{url}/participantes", json={"empresa_rede_tenant_id": "rede-beta"}).json()
    assert {c["nome"] for c in client.post(f"{url}/descoberta", json={}).json()["candidatos"]} == set()  # convidados saem da lista

    assert _status(client, rfp["id"], "PUBLICADO").status_code == 200
    assert _status(client, rfp["id"], "RECEBENDO_PROPOSTAS").status_code == 200

    def proposta(participante, valor, prazo):
        resposta = client.post(f"{url}/propostas", json={
            "participante_id": participante["id"], "valor_total": valor, "prazo_entrega_dias": prazo, "condicoes_pagamento": "30 dias",
            "respostas": [{"requisito_id": pergunta["id"], "resposta": "36 meses"}]})
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    p_alfa, p_beta = proposta(alfa, 90000, 20), proposta(beta, 80000, 30)
    assert _status(client, rfp["id"], "EM_AVALIACAO").status_code == 200

    def avaliar(prop, requisito, status, nota, justificativa=None):
        return client.put(f"{S}/propostas/{prop['id']}/avaliacoes", json={"requisito_id": requisito["id"], "status": status,
                                                                          "nota": nota, "justificativa": justificativa})

    sem_motivo = avaliar(p_beta, tecnico, "NON_COMPLIANT", 2)
    assert (sem_motivo.status_code, sem_motivo.json()["detalhe"]) == (422, "Informe a justificativa de não atendimento.")
    avaliar(p_alfa, tecnico, "COMPLIANT", 9)
    avaliar(p_alfa, sla, "COMPLIANT", 6)
    avaliar(p_beta, tecnico, "NON_COMPLIANT", 2, "Só 8 GB")
    avaliar(p_beta, sla, "COMPLIANT", 10)

    comparacao = client.get(f"{url}/comparacao").json()
    linhas = {linha["participante"]: linha for linha in comparacao["linhas"]}
    assert linhas["Alfa Notebooks"]["tecnico"]["nota_ponderada"] == 8.0  # (9*2 + 6*1) / 3
    assert linhas["Beta Tecnologia"]["risco"] and linhas["Beta Tecnologia"]["tecnico"]["obrigatorios_nao_atendidos"] == [tecnico["id"]]
    # Beta é mais barata, mas não atende obrigatório: fica fora dos destaques; ninguém é escolhido automaticamente
    assert comparacao["destaques"] == {"menor_valor": alfa["id"], "maior_nota": alfa["id"]}

    client.put(f"{url}/participantes/{beta['id']}", json={"status": "DESQUALIFICADO", "motivo": "RAM abaixo do exigido"})
    assert client.put(f"{url}/participantes/{beta['id']}", json={"status": "SHORTLIST"}).status_code == 409
    client.put(f"{url}/participantes/{alfa['id']}", json={"status": "SHORTLIST"})
    assert _status(client, rfp["id"], "EM_NEGOCIACAO").status_code == 200
    fora = client.post(f"{url}/propostas", json={"participante_id": beta["id"], "valor_total": 1})
    assert fora.status_code == 409
    segunda = client.post(f"{url}/propostas", json={"participante_id": alfa["id"], "valor_total": 85000}).json()
    assert segunda["rodada"] == 2
    assert client.get(f"{url}/comparacao").json()["linhas"][0]["rodada"] == 2

    sem_justificativa = client.post(f"{url}/aprovacao", json={"participante_id": alfa["id"], "justificativa": " "})
    assert sem_justificativa.status_code == 422
    assert client.post(f"{url}/aprovacao", json={"participante_id": alfa["id"], "justificativa": "Melhor técnica e preço"}).json()[
        "status"] == "EM_APROVACAO"
    comprador = criar_usuario_autenticado(TENANT, papel="user", email="comprador@teste.com")
    assert client.put(f"{url}/aprovacao", json={"aprovar": True}, headers=comprador).status_code == 403
    assert client.put(f"{url}/aprovacao", json={"aprovar": True}).json()["status"] == "ADJUDICADO"
    situacoes = {p.nome: p.status for p in db_session.query(ParticipanteSourcing).filter_by(processo_id=rfp["id"])}
    assert situacoes == {"Alfa Notebooks": "ADJUDICADO", "Beta Tecnologia": "DESQUALIFICADO"}

    contrato = client.post(f"{url}/contrato", json={"numero": "CT-1", "vigencia_inicio": "2026-10-01", "vigencia_fim": "2027-09-30"})
    assert contrato.status_code == 201 and contrato.json()["valor_inicial"] == 85000.0  # última rodada
    workspace = client.get(f"{url}/workspace").json()
    assert workspace["processo"]["status"] == "CONTRATADO" and workspace["fluxo"]["final"] is True
    assert workspace["aprovacao"]["situacao"] == "APROVADA"
    assert db_session.query(ContratoSourcing).filter_by(processo_id=rfp["id"]).one().lado == "BUY"
    # C0: nada disso usou IA
    assert fake_llm.chamadas == [] and db_session.query(RegistroUsoIa).count() == 0


def test_rfq_leve_com_itens_e_aprovacao_recusada(client):
    rfq = _processo(client, "RFQ", "Cotação de cadeiras")
    url = f"{S}/processos/{rfq['id']}"
    assert rfq["workflow"] == "ENTERPRISE_RFQ_BUY@1"
    item = client.post(f"{url}/itens", json={"descricao": "Cadeira ergonômica", "quantidade": 10, "unidade": "un"}).json()
    fornecedor = client.post(f"{url}/participantes", json={"nome": "Móveis Delta"}).json()
    _status(client, rfq["id"], "PUBLICADO")
    _status(client, rfq["id"], "RECEBENDO_PROPOSTAS")
    sem_avaliacao_tecnica = _status(client, rfq["id"], "EM_AVALIACAO")
    assert (sem_avaliacao_tecnica.status_code, sem_avaliacao_tecnica.json()["detalhe"]) == (422, "Status inválido: EM_AVALIACAO")
    proposta = client.post(f"{url}/propostas", json={"participante_id": fornecedor["id"], "prazo_entrega_dias": 10,
                                                    "itens": [{"item_id": item["id"], "preco_unitario": 850.5}]}).json()
    assert proposta["valor_total"] == 8505.0  # calculado dos itens
    linha = client.get(f"{url}/comparacao").json()["linhas"][0]
    assert linha["comercial"]["itens_cotados"] == 1 and linha["comercial"]["itens_total"] == 1

    client.post(f"{url}/aprovacao", json={"participante_id": fornecedor["id"], "justificativa": "Único cotado"})
    sem_motivo = client.put(f"{url}/aprovacao", json={"aprovar": False})
    assert (sem_motivo.status_code, sem_motivo.json()["detalhe"]) == (422, "Informe o motivo da recusa.")
    recusada = client.put(f"{url}/aprovacao", json={"aprovar": False, "motivo": "Cotar mais fornecedores"}).json()
    assert recusada["status"] == "RECEBENDO_PROPOSTAS"
    assert client.post(f"{url}/contrato", json={}).status_code == 409


def test_rfi_coleta_respostas_e_encerra_sem_adjudicar(client):
    rfi = _processo(client, "RFI", "Mapeamento de fornecedores de cloud")
    url = f"{S}/processos/{rfi['id']}"
    assert rfi["workflow"] == "ENTERPRISE_RFI_BUY@1"
    pergunta = client.post(f"{url}/requisitos", json={"categoria": "PERGUNTA", "texto": "Tem região no Brasil?"}).json()
    fornecedor = client.post(f"{url}/participantes", json={"nome": "Nuvem Epsilon"}).json()
    for status in ("PUBLICADO", "RECEBENDO_RESPOSTAS"):
        _status(client, rfi["id"], status)
    resposta = client.post(f"{url}/propostas", json={"participante_id": fornecedor["id"],
                                                    "respostas": [{"requisito_id": pergunta["id"], "resposta": "Sim, São Paulo"}]}).json()
    assert resposta["tipo"] == "RESPOSTA"
    _status(client, rfi["id"], "EM_AVALIACAO")
    adjudicar = client.post(f"{url}/aprovacao", json={"participante_id": fornecedor["id"], "justificativa": "x"})
    assert adjudicar.status_code == 409  # RFI não adjudica
    assert _status(client, rfi["id"], "ENCERRADO").json()["status"] == "ENCERRADO"
    avaliacoes = client.get(f"{url}/workspace").json()["propostas"][0]["avaliacoes"]
    assert avaliacoes == [{"requisito_id": pergunta["id"], "resposta": "Sim, São Paulo", "status": None, "nota": None, "justificativa": None}]


def test_barreira_tenant_lado_e_modulo(client, db_session, criar_usuario_autenticado, monkeypatch):
    rfp = _processo(client, "RFP")
    # tudo no lado BUY, segmento ENTERPRISE, com origem nativa (espelho e backfill não tocam)
    linha = db_session.get(ProcessoSourcing, rfp["id"])
    assert (linha.lado, linha.segmento, linha.origem_tabela, linha.origem_id) == ("BUY", "ENTERPRISE", "nativo", rfp["id"])
    # o núcleo nunca entrega a linha BUY para quem pergunta como VENDA, nem por id
    assert sourcing.nativo.listar(db_session, "processo", sourcing.tipos.Lado.VENDA, TENANT) == []
    assert sourcing.espelho.sincronizar_todos(db_session)["BUY"]["processo_contratacao"]["orfaos_removidos"] == 0
    assert db_session.get(ProcessoSourcing, rfp["id"]) is not None

    outro = criar_usuario_autenticado("tenant-outro")
    assert client.get(f"{S}/processos/{rfp['id']}/workspace", headers=outro).status_code == 404
    assert client.get(f"{S}/processos", headers=outro).json() == []

    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT: {"sourcing"}}))
    bloqueado = client.get(f"{S}/processos")
    assert bloqueado.status_code == 403 and "Strategic Sourcing" in bloqueado.json()["detalhe"]


def test_processo_publico_do_comprador_nao_aparece_no_sourcing_privado(client):
    orgao = client.post(f"{P}/orgaos", json={"nome": "Prefeitura"}).json()
    publico = client.post(f"{P}/processos", json={"orgao_id": orgao["id"], "objeto": "Limpeza"}).json()
    assert client.get(f"{S}/processos").json() == []
    assert client.get(f"{S}/processos/{publico['id']}/workspace").status_code == 404


def test_lado_imutavel_nas_tabelas_novas(client, db_session):
    import pytest
    from sqlalchemy import exc, text

    rfp = _processo(client, "RFP")
    client.post(f"{S}/processos/{rfp['id']}/participantes", json={"nome": "Fornecedor Zeta"})
    with pytest.raises(exc.IntegrityError):
        db_session.execute(text("UPDATE participante_sourcing SET lado = 'SELL'"))
    db_session.rollback()
    participante = db_session.query(ParticipanteSourcing).first()
    participante.lado = "SELL"
    with pytest.raises(LadoImutavel):  # o evento do ORM recusa antes do banco
        db_session.flush()
    db_session.rollback()


def test_workspace_e_comparacao_nao_crescem_com_participantes(client, db_session):
    from sqlalchemy import event

    def consultas(caminho: str) -> int:
        contagem = []
        ouvir = lambda *a: contagem.append(1)  # noqa: E731
        event.listen(db_session.get_bind(), "before_cursor_execute", ouvir)
        try:
            assert client.get(caminho).status_code == 200
        finally:
            event.remove(db_session.get_bind(), "before_cursor_execute", ouvir)
        return len(contagem)

    def montar(quantidade: int) -> int:
        rfp = _processo(client, "RFP")
        url = f"{S}/processos/{rfp['id']}"
        requisito = client.post(f"{url}/requisitos", json={"categoria": "SLA", "texto": "Suporte 24x7"}).json()
        participantes = [client.post(f"{url}/participantes", json={"nome": f"F{i}"}).json() for i in range(quantidade)]
        for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
            _status(client, rfp["id"], status)
        for p in participantes:
            proposta = client.post(f"{url}/propostas", json={"participante_id": p["id"], "valor_total": 10}).json()
            client.put(f"{S}/propostas/{proposta['id']}/avaliacoes", json={"requisito_id": requisito["id"], "status": "COMPLIANT", "nota": 8})
        return rfp["id"]

    poucos, muitos = montar(2), montar(8)
    for sufixo in ("workspace", "comparacao"):
        assert consultas(f"{S}/processos/{poucos}/{sufixo}") == consultas(f"{S}/processos/{muitos}/{sufixo}"), sufixo
