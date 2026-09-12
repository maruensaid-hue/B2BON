def test_gerar_cadencia_para_conta_sem_icp(
    client, onboarding_completo, criar_cadencia, fake_llm
):
    """Decisão de escopo do E-Leads: a geração de cadência já usa o ICP
    ativo do tenant como contexto do prompt (não o icp_id da própria
    conta), então um lead sem ICP (icp_id=None) tem que gerar mensagem
    normalmente, sem nenhuma mudança no motor de IA."""
    lead = client.post("/api/v1/leads/contas", json={"nome": "Lead Sem ICP"}).json()
    client.post(f"/api/v1/contas/{lead['id']}/decisores", json={"nome": "Decisor do Lead", "cargo": "CEO"})
    cadencia = criar_cadencia()

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [lead["id"]]})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["contas_processadas"] == [lead["id"]]
    assert corpo["mensagens_geradas"] == 5


def _aprovar_tudo(client, cadencia_id: int) -> list[dict]:
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia_id}).json()
    for item in itens:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")
    return itens


def test_cadencia_exige_minimo_cinco_toques(client):
    """E3-H1: cadência gerada com no mínimo 5 toques."""
    resposta = client.post(
        "/api/v1/cadencias",
        json={
            "nome": "Curta demais",
            "toques": [
                {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
                {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1},
            ],
        },
    )
    assert resposta.status_code == 409


def test_cadencia_exige_pelo_menos_dois_canais(client):
    """E3-H1: toques distribuídos entre canais disponíveis."""
    toques = [{"ordem": i, "canal": "email", "intervalo_dias_apos_anterior": 1} for i in range(1, 6)]
    resposta = client.post("/api/v1/cadencias", json={"nome": "Só e-mail", "toques": toques})
    assert resposta.status_code == 409


def test_cadencia_criada_com_sucesso(client, criar_cadencia):
    cadencia = criar_cadencia()
    assert cadencia["status"] == "rascunho"
    assert len(cadencia["canais"]) >= 2


def test_listar_cadencias_via_api(client, criar_cadencia):
    criada = criar_cadencia()

    resposta = client.get("/api/v1/cadencias")

    assert resposta.status_code == 200
    assert any(c["id"] == criada["id"] for c in resposta.json())


def test_listar_toques_da_cadencia_via_api(client, criar_cadencia):
    criada = criar_cadencia()

    resposta = client.get(f"/api/v1/cadencias/{criada['id']}/toques")

    assert resposta.status_code == 200
    toques = resposta.json()
    assert len(toques) == 5
    assert toques[0]["ordem"] == 1


def test_mensagens_personalizadas_usam_dados_do_decisor(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    """E3-H1: mensagens personalizadas por conta/decisor, não mala direta."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["contas_processadas"] == [conta.id]
    assert corpo["mensagens_geradas"] == 5

    prompts = [chamada.prompt for chamada in fake_llm.chamadas]
    assert len(prompts) == 5
    assert all(decisor.nome in prompt and conta.nome in prompt for prompt in prompts)
    # a descrição/diferenciais/provas sociais da oferta e as dores/gatilhos do
    # ICP precisam alimentar o texto gerado, não só o nome da oferta
    assert all("Descrição da oferta" in prompt and "diferencial1" in prompt for prompt in prompts)
    assert all("dor1" in prompt and "gatilho1" in prompt for prompt in prompts)


def test_gerar_para_lote_grande_e_bloqueado(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    """Bug real de produção: um lote grande (muitas contas x vários toques)
    fazia chamadas demais à IA numa única requisição e estourava o tempo
    de conexão antes de salvar qualquer mensagem. Bloqueia antes de tentar."""
    cadencia = criar_cadencia()
    conta_ids = [criar_conta_com_decisor()[0].id for _ in range(5)]

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": conta_ids})

    assert resposta.status_code == 409
    assert "no máximo" in resposta.json()["detalhe"]


def test_gerar_para_conta_sem_decisor_nao_falha_o_lote(
    client, onboarding_completo, db_session, criar_conta_com_decisor, criar_cadencia
):
    from app.models.conta import Conta
    from app.models.icp import ICP

    icp = db_session.query(ICP).filter_by(tenant_id="tenant-teste", ativo=True).first()
    conta_sem_decisor = Conta(tenant_id="tenant-teste", icp_id=icp.id, nome="Sem Decisor", status="prospectada")
    db_session.add(conta_sem_decisor)
    db_session.commit()

    cadencia = criar_cadencia()
    resposta = client.post(
        f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_sem_decisor.id]}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["contas_sem_decisor"] == [conta_sem_decisor.id]
    assert corpo["mensagens_geradas"] == 0


def test_gerar_retenta_quando_texto_viola_restricao_e_recupera(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, configurar_comunicacao, fake_llm
):
    """Raio-X: sem retentativa, uma única resposta da IA que mencionasse
    por acaso uma restrição configurada já descartava o toque
    silenciosamente — podia zerar o lote inteiro sem nenhum aviso, e é
    exatamente o "gerar mensagens não gera nada" relatado. Uma resposta
    ruim seguida de uma boa tem que recuperar, não desistir na primeira."""
    configurar_comunicacao(restricoes=["concorrente x"])
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    # 5 toques x (1 resposta violadora + 1 válida) = 10 respostas.
    fake_llm.definir_respostas(["Fale com a concorrente x." if i % 2 == 0 else "Mensagem válida." for i in range(10)])

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["mensagens_geradas"] == 5
    assert corpo["toques_bloqueados_restricao"] == 0
    assert len(fake_llm.chamadas) == 10


def test_gerar_avisa_quando_toque_so_viola_restricao_apos_todas_as_tentativas(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, configurar_comunicacao, fake_llm
):
    """Quando a restrição realmente não deixa nenhuma tentativa passar
    (ex.: um termo genérico demais na lista), o toque é pulado — mas
    isso agora aparece em `toques_bloqueados_restricao`, não fica
    silencioso, e por isso a fila de aprovações "Pendentes" fica vazia
    corretamente (não há mensagem nova nenhuma pra aprovar)."""
    configurar_comunicacao(restricoes=["empresa"])
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    fake_llm.definir_respostas(["Fale com a empresa deles."] * 15)  # 5 toques x 3 tentativas

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["mensagens_geradas"] == 0
    assert corpo["toques_bloqueados_restricao"] == 5

    pendentes = client.get("/api/v1/aprovacoes", params={"status": "pendente"}).json()
    assert pendentes == []


def test_gerar_recupera_de_falha_intermitente_da_ia(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    """Raio-X: `llm_helpers.gerar` traduz falha da IA (resposta vazia,
    limite de taxa) em `RegraNegocioViolada` — sem capturar isso DENTRO
    da retentativa por toque, a exceção escapava na hora e derrubava a
    requisição INTEIRA (409), mesmo com só 1 conta selecionada e mesmo
    a IA tendo se recuperado logo na tentativa seguinte. Um hiccup
    pontual (2 falhas, depois sucesso) precisa se recuperar sozinho."""
    from app.api.deps import get_llm_provider
    from app.llm.base import LLMIndisponivel
    from app.llm.schemas import LLMResponse
    from app.main import app

    class LLMFalhaIntermitente:
        def __init__(self, falhas: int) -> None:
            self._falhas_restantes = falhas

        def generate(self, request):
            if self._falhas_restantes > 0:
                self._falhas_restantes -= 1
                raise LLMIndisponivel("instabilidade simulada")
            return LLMResponse(content="Mensagem válida.", model="fake", input_tokens=0, output_tokens=0)

    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()

    app.dependency_overrides[get_llm_provider] = lambda: LLMFalhaIntermitente(falhas=2)
    try:
        resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    finally:
        app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["mensagens_geradas"] == 5
    assert corpo["toques_falha_ia"] == 0


def test_gerar_nao_derruba_lote_inteiro_quando_ia_falha_persistentemente(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    """Quando a IA falha em TODAS as tentativas de um toque (não só uma
    vez), o toque é pulado e contado em `toques_falha_ia` — a requisição
    continua respondendo 200, nunca 409, mesmo sem gerar nenhuma
    mensagem. Essa é a diferença que importa pra quem usa a tela: 200
    com aviso claro ("instabilidade da IA, tente de novo") é bem
    diferente de um erro que parece ter quebrado tudo."""
    from app.api.deps import get_llm_provider
    from app.llm.base import LLMIndisponivel
    from app.main import app

    class LLMSempreIndisponivel:
        def generate(self, request):
            raise LLMIndisponivel("instabilidade simulada")

    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()

    app.dependency_overrides[get_llm_provider] = lambda: LLMSempreIndisponivel()
    try:
        resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    finally:
        app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["mensagens_geradas"] == 0
    assert corpo["toques_falha_ia"] == 5
    assert corpo["toques_bloqueados_restricao"] == 0


def test_ativar_falha_com_toques_pendentes_de_aprovacao(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia
):
    """E3-H1: cadência inteira submetida à fila de aprovações antes de ativar."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta.status_code == 409


def test_ativar_apos_aprovar_todos_os_toques(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta.status_code == 200
    assert resposta.json()["cadencia"]["status"] == "ativa"


def test_excluir_cadencia_em_rascunho(client, criar_cadencia):
    cadencia = criar_cadencia()

    resposta = client.delete(f"/api/v1/cadencias/{cadencia['id']}")

    assert resposta.status_code == 204
    assert client.get(f"/api/v1/cadencias/{cadencia['id']}").status_code == 404


def test_excluir_cadencia_ja_gerada_e_bloqueado(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia
):
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    resposta = client.delete(f"/api/v1/cadencias/{cadencia['id']}")

    assert resposta.status_code == 409


def test_ativar_cadencia_consome_franquia(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    """Gancho da Onda 1: franquia_service.consumir_para_ativacao chamado de verdade."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])

    franquia_antes = client.get("/api/v1/contas/franquia").json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    franquia_depois = client.get("/api/v1/contas/franquia").json()

    assert franquia_depois["usado"] == franquia_antes["usado"] + 1
