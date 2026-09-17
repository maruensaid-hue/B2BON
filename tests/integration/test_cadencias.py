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


def test_regra_aprendida_ativa_entra_no_prompt_da_cadencia(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(
        "/api/v1/regras-aprendidas",
        json={
            "icp_id": cadencia["icp_id"], "oferta_id": cadencia["oferta_id"], "canal": "email",
            "regra": "Nunca usar a palavra sinergia",
        },
    )

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert resposta.status_code == 200
    prompts_email = [chamada.prompt for chamada in fake_llm.chamadas if "canal email" in chamada.prompt]
    prompts_whatsapp = [chamada.prompt for chamada in fake_llm.chamadas if "canal whatsapp" in chamada.prompt]
    assert len(prompts_email) == 3  # toques 1, 3 e 5 da cadencia-padrao sao email
    assert all("Nunca usar a palavra sinergia" in prompt for prompt in prompts_email)
    assert all("Nunca usar a palavra sinergia" not in prompt for prompt in prompts_whatsapp)


def test_sem_regra_aprendida_prompt_nao_ganha_o_trecho(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()

    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert all("Regras aprendidas" not in chamada.prompt for chamada in fake_llm.chamadas)


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


def test_gerar_usa_oferta_travada_na_criacao_mesmo_apos_trocar_a_ativa(
    client, criar_icp, criar_oferta, configurar_comunicacao, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    """Raio-X de produção real: usuário tinha uma cadência desenhada pra
    prospectar "B2B ON" e, depois de criá-la, trocou a oferta ativa pra
    outra campanha ("Acronis", que a CyberFort também revende) —
    `oferta_service.ativar` desativa a anterior ao ativar uma nova.
    Antes desta correção isso corrompia silenciosamente a geração da
    cadência JÁ CRIADA (ela usava "a oferta ativa agora", não a que
    existia quando foi desenhada). A partir de agora a cadência fica
    travada na oferta que estava ativa no momento em que foi criada."""
    criar_icp(nome="ICP B2B ON")
    criar_oferta(nome="Oferta B2B ON", descricao="Plataforma de CRM B2B ON")
    configurar_comunicacao()
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()

    # Troca a oferta ativa DEPOIS de criar a cadência.
    criar_oferta(nome="Oferta Acronis", descricao="Backup e cibersegurança Acronis")

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    assert resposta.status_code == 200
    assert resposta.json()["mensagens_geradas"] == 5
    prompts = [chamada.prompt for chamada in fake_llm.chamadas]
    assert all("Oferta B2B ON" in prompt for prompt in prompts)
    assert all("Acronis" not in prompt for prompt in prompts)


def test_criar_cadencia_com_icp_explicito_quando_ha_mais_de_um_ativo(
    client, criar_icp, criar_oferta, configurar_comunicacao, criar_cadencia
):
    """Múltiplos ICPs ativos ao mesmo tempo são suportados de propósito
    (comparação de campanhas, `icp_service.performance`) — quem cria a
    cadência precisa poder escolher qual dos dois é o certo, em vez de
    a API adivinhar "o primeiro que aparecer"."""
    criar_icp(nome="ICP A")
    icp_b = criar_icp(nome="ICP B")
    criar_oferta()
    configurar_comunicacao()

    cadencia = criar_cadencia(icp_id=icp_b["id"])

    assert cadencia["icp_id"] == icp_b["id"]


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


def test_definir_template_whatsapp_em_toque_existente(client, criar_cadencia, db_session):
    """Raio-X 2026-09-15: quem cria a cadência antes do template ser
    aprovado pela Meta precisa de um jeito de configurá-lo depois — o
    template só podia ser escolhido na criação até aqui. Simula uma
    cadência "legada" (toque de WhatsApp sem template) direto no banco,
    já que criar uma cadência assim pela API não é mais permitido (regra
    nova: todo toque de WhatsApp exige template já na criação)."""
    from app.models.toque_cadencia import ToqueCadencia

    cadencia = criar_cadencia()
    toque_whatsapp = db_session.query(ToqueCadencia).filter_by(cadencia_id=cadencia["id"], canal="whatsapp").one()
    toque_whatsapp.template_whatsapp_id = None
    db_session.commit()

    resposta = client.put(
        f"/api/v1/cadencias/{cadencia['id']}/toques/{toque_whatsapp.id}/template-whatsapp",
        json={"template_whatsapp_id": "prospeccao_inicial"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["template_whatsapp_id"] == "prospeccao_inicial"
    atualizado = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()
    assert next(t for t in atualizado if t["id"] == toque_whatsapp.id)["template_whatsapp_id"] == "prospeccao_inicial"


def test_definir_template_whatsapp_em_toque_de_outro_canal_falha(client, criar_cadencia):
    cadencia = criar_cadencia()
    toques = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()
    toque_email = next(t for t in toques if t["canal"] == "email")

    resposta = client.put(
        f"/api/v1/cadencias/{cadencia['id']}/toques/{toque_email['id']}/template-whatsapp",
        json={"template_whatsapp_id": "prospeccao_inicial"},
    )

    assert resposta.status_code == 409


def test_definir_template_whatsapp_toque_de_outra_cadencia_falha(client, criar_cadencia):
    cadencia_a = criar_cadencia(nome="Cadência A")
    cadencia_b = criar_cadencia(nome="Cadência B")
    toque_da_b = next(t for t in client.get(f"/api/v1/cadencias/{cadencia_b['id']}/toques").json() if t["canal"] == "whatsapp")

    resposta = client.put(
        f"/api/v1/cadencias/{cadencia_a['id']}/toques/{toque_da_b['id']}/template-whatsapp",
        json={"template_whatsapp_id": "prospeccao_inicial"},
    )

    assert resposta.status_code == 404


def test_cancelar_cadencia_ativa_para_pendentes_mas_preserva_enviadas(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, db_session
):
    """Raio-X 2026-09-15: "excluir mesmo já disparada" virou "cancelar" —
    mensagens já enviadas (histórico real de comunicação) nunca são
    tocadas; só as pendentes/aprovadas ainda não enviadas viram
    "cancelado" (mesmo padrão de `resposta_service.marcar_resposta`)."""
    from app.models.mensagem import Mensagem

    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    mensagens = db_session.query(Mensagem).filter_by(cadencia_id=cadencia["id"]).all()
    assert len(mensagens) == 5
    ja_enviada = mensagens[0]
    ja_enviada.status = "enviado"
    db_session.commit()

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/cancelar")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cadencia"]["status"] == "cancelada"
    assert corpo["mensagens_canceladas"] == 4

    db_session.refresh(ja_enviada)
    assert ja_enviada.status == "enviado"
    for outra in mensagens[1:]:
        db_session.refresh(outra)
        assert outra.status == "cancelado"


def test_cancelar_cadencia_ja_cancelada_falha(client, criar_cadencia):
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/cancelar")

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/cancelar")

    assert resposta.status_code == 409


def test_gerar_e_ativar_em_cadencia_cancelada_falha(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/cancelar")

    resposta_gerar = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    resposta_ativar = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta_gerar.status_code == 409
    assert resposta_ativar.status_code == 409


def test_renomear_cadencia(client, criar_cadencia):
    cadencia = criar_cadencia()

    resposta = client.put(f"/api/v1/cadencias/{cadencia['id']}", json={"nome": "Nome Novo"})

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Nome Novo"
    assert client.get(f"/api/v1/cadencias/{cadencia['id']}").json()["nome"] == "Nome Novo"


def test_adicionar_toque_em_cadencia_existente(client, criar_cadencia):
    cadencia = criar_cadencia()

    resposta = client.post(
        f"/api/v1/cadencias/{cadencia['id']}/toques",
        json={"canal": "email", "intervalo_dias_apos_anterior": 5},
    )

    assert resposta.status_code == 201
    novo = resposta.json()
    assert novo["ordem"] == 6
    toques = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()
    assert len(toques) == 6
    assert client.get(f"/api/v1/cadencias/{cadencia['id']}").json()["canais"] == ["email", "linkedin", "whatsapp"]


def test_remover_toque_desvincula_mensagem_em_vez_de_bloquear(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, db_session
):
    """Mesmo padrão de `crm_service.excluir_negocio` pra `Atividade`:
    desvincula a mensagem já gerada em vez de bloquear a remoção do toque."""
    from app.models.mensagem import Mensagem

    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/toques", json={"canal": "email", "intervalo_dias_apos_anterior": 5})
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    toques = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()
    toque_a_remover = toques[0]

    resposta = client.delete(f"/api/v1/cadencias/{cadencia['id']}/toques/{toque_a_remover['id']}")

    assert resposta.status_code == 204
    assert len(client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()) == 5
    mensagens = db_session.query(Mensagem).filter_by(cadencia_id=cadencia["id"]).all()
    assert len(mensagens) == 6  # nenhuma mensagem foi apagada
    orfas = [m for m in mensagens if m.toque_cadencia_id is None]
    assert len(orfas) == 1


def test_remover_toque_abaixo_do_minimo_falha(client, criar_cadencia):
    cadencia = criar_cadencia()
    toques = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()

    resposta = client.delete(f"/api/v1/cadencias/{cadencia['id']}/toques/{toques[0]['id']}")

    assert resposta.status_code == 409


def test_atualizar_toque_troca_canal_e_intervalo(client, criar_cadencia):
    cadencia = criar_cadencia()
    toques = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()
    toque_linkedin = next(t for t in toques if t["canal"] == "linkedin")

    resposta = client.put(
        f"/api/v1/cadencias/{cadencia['id']}/toques/{toque_linkedin['id']}",
        json={"canal": "email", "intervalo_dias_apos_anterior": 10},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["canal"] == "email"
    assert corpo["intervalo_dias_apos_anterior"] == 10


def test_atualizar_toque_abaixo_do_minimo_de_canais_falha(client, criar_cadencia):
    """Cadência padrão tem canais {email, whatsapp, linkedin} — trocar o
    único toque de linkedin AND algum whatsapp por email reduziria pra 1
    canal só, abaixo do mínimo de 2."""
    cadencia = criar_cadencia()
    toques = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()
    toque_linkedin = next(t for t in toques if t["canal"] == "linkedin")
    client.put(f"/api/v1/cadencias/{cadencia['id']}/toques/{toque_linkedin['id']}", json={"canal": "email"})

    for toque in [t for t in toques if t["canal"] == "whatsapp"]:
        resposta = client.put(f"/api/v1/cadencias/{cadencia['id']}/toques/{toque['id']}", json={"canal": "email"})

    assert resposta.status_code == 409


def test_adicionar_conta_nova_em_cadencia_ja_ativa_nao_reagenda_a_antiga(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, db_session
):
    """Raio-X 2026-09-15: `ativar` agora só processa mensagens com
    `agendado_para IS NULL` — chamar de novo numa cadência já ativa (após
    gerar pra uma conta nova) não reagenda o que já estava correto."""
    from app.models.mensagem import Mensagem

    conta_antiga, decisor_antigo = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_antiga.id]})
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    agendamento_antes = {
        m.id: m.agendado_para
        for m in db_session.query(Mensagem).filter_by(cadencia_id=cadencia["id"], decisor_id=decisor_antigo.id)
    }
    assert len(agendamento_antes) == 5
    assert all(valor is not None for valor in agendamento_antes.values())

    conta_nova, decisor_novo = criar_conta_com_decisor()
    resultado_gerar = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_nova.id]}).json()
    assert resultado_gerar["mensagens_geradas"] == 5
    _aprovar_tudo(client, cadencia["id"])

    resposta_ativar = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    assert resposta_ativar.status_code == 200

    for mensagem_id, valor_antigo in agendamento_antes.items():
        atual = db_session.query(Mensagem).filter_by(id=mensagem_id).one()
        assert atual.agendado_para == valor_antigo

    novas = db_session.query(Mensagem).filter_by(cadencia_id=cadencia["id"], decisor_id=decisor_novo.id).all()
    assert len(novas) == 5
    assert all(m.agendado_para is not None for m in novas)


def test_ativar_sem_mensagem_nova_pendente_falha(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia
):
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta.status_code == 409


def test_criar_cadencia_com_dois_toques_whatsapp_falha(client):
    """Raio-X 2026-09-15: no máximo 1 toque de WhatsApp por cadência —
    nenhum toque agendado pra depois tem garantia de a janela de 24h
    ainda estar aberta quando a data chegar."""
    toques = [
        {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
        {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
        {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 1},
        {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
        {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 1},
    ]
    resposta = client.post("/api/v1/cadencias", json={"nome": "Dois WhatsApp", "toques": toques})

    assert resposta.status_code == 409


def test_criar_cadencia_com_whatsapp_sem_template_falha(client):
    """Raio-X 2026-09-15: o único toque de WhatsApp é sempre obrigatório
    ter template — nunca mais texto livre agendado por cadência."""
    toques = [
        {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
        {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1},
        {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 1},
        {"ordem": 4, "canal": "linkedin", "intervalo_dias_apos_anterior": 1},
        {"ordem": 5, "canal": "email", "intervalo_dias_apos_anterior": 1},
    ]
    resposta = client.post("/api/v1/cadencias", json={"nome": "WhatsApp sem template", "toques": toques})

    assert resposta.status_code == 409


def test_adicionar_segundo_toque_whatsapp_falha(client, criar_cadencia):
    """Cadência padrão já tem 1 toque de WhatsApp (com template) — adicionar
    um segundo deve falhar, mesmo em cadência já existente."""
    cadencia = criar_cadencia()

    resposta = client.post(
        f"/api/v1/cadencias/{cadencia['id']}/toques",
        json={"canal": "whatsapp", "template_whatsapp_id": "y"},
    )

    assert resposta.status_code == 409


def test_atualizar_toque_para_whatsapp_sem_template_falha(client, criar_cadencia):
    """`atualizar_toque` não recebe `template_whatsapp_id` — trocar um
    toque de e-mail/LinkedIn pra WhatsApp por aqui nunca teria template,
    então tem que falhar (a troca de canal pra whatsapp só é segura via
    `adicionar_toque`, que já exige template)."""
    cadencia = criar_cadencia()
    toques = client.get(f"/api/v1/cadencias/{cadencia['id']}/toques").json()
    toque_email = next(t for t in toques if t["canal"] == "email")

    resposta = client.put(f"/api/v1/cadencias/{cadencia['id']}/toques/{toque_email['id']}", json={"canal": "whatsapp"})

    assert resposta.status_code == 409


def test_definir_cancelamento_ao_responder(client, criar_cadencia):
    cadencia = criar_cadencia()
    assert cadencia["cancelar_ao_responder"] is False

    resposta = client.put(
        f"/api/v1/cadencias/{cadencia['id']}/cancelamento-ao-responder", json={"cancelar_ao_responder": True}
    )

    assert resposta.status_code == 200
    assert resposta.json()["cancelar_ao_responder"] is True
    assert client.get(f"/api/v1/cadencias/{cadencia['id']}").json()["cancelar_ao_responder"] is True
