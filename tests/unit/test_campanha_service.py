from datetime import UTC, datetime, timedelta

import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.schemas.campanha import DestinatarioAvulsoSchema
from app.services import campanha_service, reputacao_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou
from tests.fakes import FakeEmailProvider, FakeWhatsAppProvider

TENANT_ID = "tenant-campanhas"
PLAN_LIMITS = StubPlanLimitsProvider()


def _criar_decisor(db_session, nome: str, email: str | None = "fulano@teste.com", suprimido: bool = False) -> Decisor:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome=f"Empresa de {nome}", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(
        tenant_id=TENANT_ID,
        conta_id=conta.id,
        nome=nome,
        email=email,
        telefone="11999990000",
        suprimido_em=datetime.now(UTC) if suprimido else None,
    )
    db_session.add(decisor)
    db_session.commit()
    return decisor


def _criar_campanha_email(db_session, canais=None) -> int:
    campanha = campanha_service.criar(
        db_session,
        TENANT_ID,
        None,
        "Campanha Teste",
        "marketing",
        canais or ["email"],
        "Assunto de teste",
        "Corpo de teste",
        None,
        PLAN_LIMITS,
    )
    return campanha.id


def test_criar_campanha_email_exige_assunto_e_conteudo(db_session):
    with pytest.raises(ValidacaoFalhou):
        campanha_service.criar(
            db_session, TENANT_ID, None, "Sem conteúdo", "marketing", ["email"], None, None, None, PLAN_LIMITS
        )


def test_criar_campanha_whatsapp_exige_template(db_session):
    with pytest.raises(ValidacaoFalhou):
        campanha_service.criar(
            db_session, TENANT_ID, None, "Sem template", "vendas", ["whatsapp"], None, None, None, PLAN_LIMITS
        )


def test_adicionar_de_decisores_pula_suprimido(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor_ativo = _criar_decisor(db_session, "Ativo")
    decisor_suprimido = _criar_decisor(db_session, "Suprimido", suprimido=True)

    adicionados = campanha_service.adicionar_de_decisores(
        db_session, TENANT_ID, None, campanha_id, [decisor_ativo.id, decisor_suprimido.id]
    )

    assert len(adicionados) == 1
    assert adicionados[0].decisor_id == decisor_ativo.id


def test_adicionar_de_decisores_nao_duplica(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")

    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    segunda_vez = campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])

    assert segunda_vez == []
    assert len(campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)) == 1


def test_adicionar_avulsos_dedupe_por_email(db_session):
    campanha_id = _criar_campanha_email(db_session)
    destinatarios = [
        DestinatarioAvulsoSchema(nome="Ciclano", email="ciclano@teste.com"),
        DestinatarioAvulsoSchema(nome="Ciclano Repetido", email="CICLANO@teste.com"),
        DestinatarioAvulsoSchema(nome="Sem contato", email=None, telefone=None),
    ]

    adicionados = campanha_service.adicionar_avulsos(db_session, TENANT_ID, None, campanha_id, destinatarios)

    assert len(adicionados) == 1
    assert adicionados[0].nome == "Ciclano"


def test_marcar_pronta_exige_destinatario(db_session):
    campanha_id = _criar_campanha_email(db_session)
    with pytest.raises(ValidacaoFalhou):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)


def test_marcar_pronta_com_destinatario_funciona(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])

    campanha = campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    assert campanha.status == "pronta"


def test_excluir_campanha_fora_de_rascunho_falha(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    with pytest.raises(RegraNegocioViolada):
        campanha_service.excluir(db_session, TENANT_ID, None, campanha_id)


def test_processar_pendentes_envia_email_e_marca_concluida(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano", email="fulano@teste.com")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 1, "falhas": 0, "adiadas": 0}
    assert len(fake_email.envios) == 1
    assert fake_email.envios[0]["destinatario"] == "fulano@teste.com"

    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    assert campanha.status == "concluida"
    destinatarios = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert destinatarios[0].status == "enviado"


def test_processar_pendentes_whatsapp_usa_template(db_session):
    campanha = campanha_service.criar(
        db_session,
        TENANT_ID,
        None,
        "Campanha WhatsApp",
        "vendas",
        ["whatsapp"],
        None,
        None,
        "prospeccao_inicial",
        PLAN_LIMITS,
    )
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha.id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha.id)

    fake_email = FakeEmailProvider()
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 1, "falhas": 0, "adiadas": 0}
    assert fake_whatsapp.envios == [
        {"tipo": "template", "telefone": "11999990000", "template_id": "prospeccao_inicial", "variavel_botao": None}
    ]


def test_processar_pendentes_registra_falha(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    fake_email.falhar_proximos = 1
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 0, "falhas": 1, "adiadas": 0}
    destinatarios = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert destinatarios[0].status == "falhou"
    assert destinatarios[0].motivo_falha


def _pausar_canal_email(db_session) -> None:
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 100)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 6)
    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email") is True


def test_marcar_pronta_com_email_pausado_falha(db_session):
    """Raio-X 2026-09-16: bloqueia ativar uma nova campanha de e-mail
    enquanto o canal está pausado por bounce — antes disso passava
    direto e a campanha ficava presa tentando enviar pra sempre."""
    _pausar_canal_email(db_session)
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])

    with pytest.raises(RegraNegocioViolada):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)


def test_marcar_pronta_whatsapp_nao_bloqueado_por_email_pausado(db_session):
    """Só o canal de fato usado pela campanha é checado — uma campanha só
    de WhatsApp não deveria ser afetada pela pausa do e-mail."""
    _pausar_canal_email(db_session)
    campanha = campanha_service.criar(
        db_session,
        TENANT_ID,
        None,
        "Campanha WhatsApp",
        "vendas",
        ["whatsapp"],
        None,
        None,
        "prospeccao_inicial",
        PLAN_LIMITS,
    )
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha.id, [decisor.id])

    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha.id)  # não levanta


def test_processar_pendentes_email_pausado_fica_pendente_em_vez_de_falhar(db_session):
    """Raio-X 2026-09-16: canal pausado no meio de uma campanha já
    `enviando` (pausa disparada depois do `marcar_pronta`) não deve
    marcar o destinatário como "falhou" — fica "pendente" pra tentar de
    novo quando o canal reabrir."""
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    _pausar_canal_email(db_session)

    fake_email = FakeEmailProvider()
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 0, "falhas": 0, "adiadas": 1}
    assert fake_email.envios == []
    destinatarios = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert destinatarios[0].status == "pendente"
    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    assert campanha.status == "enviando"


def test_processar_pendentes_email_pausado_ainda_tenta_whatsapp(db_session):
    """Destinatário multicanal com e-mail pausado ainda recebe o WhatsApp
    — só o e-mail é pulado, não o destinatário inteiro."""
    campanha = campanha_service.criar(
        db_session, TENANT_ID, None, "Campanha Multicanal", "vendas", ["email", "whatsapp"],
        "Assunto", "Corpo", "prospeccao_inicial", PLAN_LIMITS,
    )
    decisor = _criar_decisor(db_session, "Fulano")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha.id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha.id)
    _pausar_canal_email(db_session)

    fake_email = FakeEmailProvider()
    fake_whatsapp = FakeWhatsAppProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert resultado == {"enviadas": 1, "falhas": 0, "adiadas": 0}
    assert fake_email.envios == []
    assert len(fake_whatsapp.envios) == 1


def test_optout_por_token_suprime_destinatario_e_decisor(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Fulano")
    destinatarios = campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    destinatario_id = destinatarios[0].id

    token = campanha_service.gerar_token_optout(TENANT_ID, destinatario_id)
    resultado = campanha_service.processar_optout_por_token(db_session, token)

    assert resultado == {"destinatario_id": destinatario_id, "suprimido": True}
    destinatario_atualizado = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]
    assert destinatario_atualizado.status == "optout"
    db_session.refresh(decisor)
    assert decisor.suprimido_em is not None


def test_optout_por_token_invalido_falha(db_session):
    with pytest.raises(ValidacaoFalhou):
        campanha_service.processar_optout_por_token(db_session, "token-invalido")


class _EmailQueCaiNoTerceiro(FakeEmailProvider):
    """Simula o processo morrendo no meio do disparo: os dois primeiros saem, o terceiro levanta."""

    def enviar(self, *args, **kwargs):
        if len(self.envios) == 2:
            raise RuntimeError("processo caiu")
        return super().enviar(*args, **kwargs)


def _campanha_pronta_com_destinatarios(db_session, quantidade: int) -> int:
    campanha_id = _criar_campanha_email(db_session)
    for i in range(quantidade):
        decisor = _criar_decisor(db_session, f"Pessoa {i}", email=f"pessoa{i}@teste.com")
        campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    return campanha_id


def test_queda_no_meio_nao_reenvia_quem_ja_recebeu(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 5)

    queda = _EmailQueCaiNoTerceiro()
    with pytest.raises(RuntimeError):
        campanha_service.processar_pendentes(db_session, TENANT_ID, queda, FakeWhatsAppProvider())

    estados = [d.status for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)]
    assert estados.count("enviado") == 2 and estados.count("pendente") == 3  # os dois primeiros ficaram gravados
    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    assert campanha.status == "enviando" and campanha.processando_ate is None  # a reserva é devolvida, o ciclo seguinte continua

    seguinte = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, seguinte, FakeWhatsAppProvider())
    assert resultado["enviadas"] == 3
    assert {e["destinatario"] for e in seguinte.envios}.isdisjoint({e["destinatario"] for e in queda.envios})  # ninguém recebeu duas vezes
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "concluida"


def test_campanha_reservada_por_outro_processo_e_pulada_ate_a_reserva_vencer(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 2)
    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    campanha.status, campanha.processando_ate = "enviando", datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
    db_session.commit()

    fake_email = FakeEmailProvider()
    assert campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())["enviadas"] == 0
    assert fake_email.envios == []

    campanha.processando_ate = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)  # o outro processo caiu: a reserva venceu
    db_session.commit()
    assert campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())["enviadas"] == 2
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "concluida"


def test_processar_com_campanha_id_envia_so_aquela_campanha(db_session):
    alvo = _campanha_pronta_com_destinatarios(db_session, 1)
    outra = _campanha_pronta_com_destinatarios(db_session, 1)

    fake_email = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider(), campanha_id=alvo)

    assert resultado["enviadas"] == 1
    assert campanha_service.obter(db_session, TENANT_ID, alvo).status == "concluida"
    assert campanha_service.obter(db_session, TENANT_ID, outra).status == "pronta"


def test_destinatario_que_saiu_da_lista_durante_o_envio_nao_recebe(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 3)
    ultimo = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[-1]

    class _DescadastraOUltimoNoPrimeiroEnvio(FakeEmailProvider):
        def enviar(self, *args, **kwargs):
            if not self.envios:
                ultimo.status = "optout"
                db_session.commit()
            return super().enviar(*args, **kwargs)

    fake_email = _DescadastraOUltimoNoPrimeiroEnvio()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    assert resultado["enviadas"] == 2 and len(fake_email.envios) == 2


class _EmailSemRede(FakeEmailProvider):
    """Servidor de e-mail inalcançável: toda tentativa falha de forma passageira."""

    def enviar(self, *args, **kwargs):
        self.tentativas = getattr(self, "tentativas", 0) + 1
        from app.providers.channels.email.base import ResultadoEnvio

        return ResultadoEnvio(sucesso=False, motivo_falha="[Errno 101] Network is unreachable", transitoria=True)


def test_falha_de_rede_nao_perde_destinatarios_e_o_ciclo_seguinte_continua(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 4)

    sem_rede = _EmailSemRede()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, sem_rede, FakeWhatsAppProvider())

    assert sem_rede.tentativas == 1  # com a rede fora, não insiste nos outros destinatários
    assert resultado == {"enviadas": 0, "falhas": 0, "adiadas": 1}
    estados = [d.status for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)]
    assert estados == ["pendente"] * 4  # ninguém foi marcado como falha
    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    assert campanha.status == "enviando" and campanha.processando_ate is None

    com_rede = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, com_rede, FakeWhatsAppProvider())
    assert resultado["enviadas"] == 4 and len(com_rede.envios) == 4
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "concluida"


def test_recusa_definitiva_continua_marcando_o_destinatario_como_falha(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 2)
    fake_email = FakeEmailProvider()
    fake_email.falhar_proximos = 1

    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    assert resultado["falhas"] == 1 and resultado["enviadas"] == 1
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "concluida"


def test_voltar_para_rascunho_devolve_as_falhas_a_fila_e_preserva_quem_ja_recebeu(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 3)
    fake_email = FakeEmailProvider()
    fake_email.falhar_proximos = 1
    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())
    antes = [d.status for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)]
    assert antes.count("falhou") == 1 and antes.count("enviado") == 2

    campanha = campanha_service.voltar_para_rascunho(db_session, TENANT_ID, None, campanha_id)

    assert campanha.status == "rascunho"
    depois = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert sorted(d.status for d in depois) == ["enviado", "enviado", "pendente"]
    assert all(d.motivo_falha is None for d in depois)

    campanha_service.atualizar(db_session, TENANT_ID, None, campanha_id, "Campanha Teste", "marketing", ["email"], "Novo assunto", "Novo corpo", None)
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    reenvio = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, reenvio, FakeWhatsAppProvider())
    assert resultado["enviadas"] == 1 and len(reenvio.envios) == 1  # só quem faltava
    assert reenvio.envios[0]["assunto"] == "Novo assunto" and "Novo corpo" in reenvio.envios[0]["corpo"]


def test_voltar_para_rascunho_durante_o_envio_faz_o_envio_parar(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 4)

    class _PausaNoSegundo(FakeEmailProvider):
        def enviar(self, *args, **kwargs):
            if len(self.envios) == 1:
                campanha_service.voltar_para_rascunho(db_session, TENANT_ID, None, campanha_id)
            return super().enviar(*args, **kwargs)

    fake_email = _PausaNoSegundo()
    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    assert len(fake_email.envios) == 2  # o que estava em andamento termina; os seguintes não saem
    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    assert campanha.status == "rascunho" and campanha.processando_ate is None
    assert [d.status for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)].count("pendente") == 2


def _campanha_rascunho_com_destinatarios(db_session, quantidade: int) -> tuple[int, list[int]]:
    campanha_id = _criar_campanha_email(db_session)
    for i in range(quantidade):
        decisor = _criar_decisor(db_session, f"Pessoa {i}", email=f"pessoa{i}@teste.com")
        campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    ids = [d.id for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)]
    return campanha_id, ids


def _estados(db_session, campanha_id: int) -> list[str]:
    return [d.status for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)]


def test_envio_so_para_os_selecionados_retem_os_demais_e_volta_ao_rascunho(db_session):
    campanha_id, ids = _campanha_rascunho_com_destinatarios(db_session, 5)

    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [ids[0], ids[2]])
    assert sorted(_estados(db_session, campanha_id)) == ["pendente", "pendente", "retido", "retido", "retido"]

    fake_email = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    assert resultado["enviadas"] == 2
    assert {e["destinatario"] for e in fake_email.envios} == {"pessoa0@teste.com", "pessoa2@teste.com"}
    assert sorted(_estados(db_session, campanha_id)) == ["enviado", "enviado", "pendente", "pendente", "pendente"]
    campanha = campanha_service.obter(db_session, TENANT_ID, campanha_id)
    assert campanha.status == "rascunho" and campanha.processando_ate is None


def test_enviar_para_todos_depois_do_teste_pula_quem_ja_recebeu(db_session):
    campanha_id, ids = _campanha_rascunho_com_destinatarios(db_session, 5)
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [ids[0], ids[2]])
    teste = FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, teste, FakeWhatsAppProvider())

    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    todos = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, todos, FakeWhatsAppProvider())

    assert resultado["enviadas"] == 3
    assert {e["destinatario"] for e in todos.envios}.isdisjoint({e["destinatario"] for e in teste.envios})
    assert _estados(db_session, campanha_id).count("enviado") == 5
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "concluida"


def test_selecao_vazia_ou_so_de_quem_ja_recebeu_e_recusada(db_session):
    campanha_id, ids = _campanha_rascunho_com_destinatarios(db_session, 2)
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [ids[0]])
    campanha_service.processar_pendentes(db_session, TENANT_ID, FakeEmailProvider(), FakeWhatsAppProvider())  # ids[0] já recebeu

    with pytest.raises(ValidacaoFalhou):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [])
    with pytest.raises(ValidacaoFalhou):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [ids[0]])
    with pytest.raises(ValidacaoFalhou):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [999999])
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "rascunho"
    assert sorted(_estados(db_session, campanha_id)) == ["enviado", "pendente"]  # a recusa não mexeu em ninguém


def test_enviar_para_todos_sem_ninguem_pendente_e_recusado(db_session):
    campanha_id, _ = _campanha_rascunho_com_destinatarios(db_session, 1)
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    campanha_service.processar_pendentes(db_session, TENANT_ID, FakeEmailProvider(), FakeWhatsAppProvider())
    campanha_service.voltar_para_rascunho(db_session, TENANT_ID, None, campanha_id)

    with pytest.raises(ValidacaoFalhou):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)


def test_queda_no_meio_do_envio_parcial_nao_libera_os_retidos_para_o_agendador(db_session):
    campanha_id, ids = _campanha_rascunho_com_destinatarios(db_session, 5)
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, ids[:3])

    queda = _EmailQueCaiNoTerceiro()
    with pytest.raises(RuntimeError):
        campanha_service.processar_pendentes(db_session, TENANT_ID, queda, FakeWhatsAppProvider())
    assert sorted(_estados(db_session, campanha_id)) == ["enviado", "enviado", "pendente", "retido", "retido"]

    seguinte = FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, seguinte, FakeWhatsAppProvider())  # o ciclo de reserva

    assert {e["destinatario"] for e in seguinte.envios} == {"pessoa2@teste.com"}  # só o selecionado que faltava
    assert sorted(_estados(db_session, campanha_id)) == ["enviado", "enviado", "enviado", "pendente", "pendente"]
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "rascunho"


def test_enviar_para_todos_tenta_de_novo_quem_falhou_no_envio_parcial(db_session):
    campanha_id, ids = _campanha_rascunho_com_destinatarios(db_session, 3)
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, ids[:2])
    falha = FakeEmailProvider()
    falha.falhar_proximos = 1
    campanha_service.processar_pendentes(db_session, TENANT_ID, falha, FakeWhatsAppProvider())
    assert sorted(_estados(db_session, campanha_id)) == ["enviado", "falhou", "pendente"]

    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    reenvio = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, reenvio, FakeWhatsAppProvider())

    assert resultado["enviadas"] == 2
    assert _estados(db_session, campanha_id).count("enviado") == 3
    assert all(d.motivo_falha is None for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id))


def test_voltar_para_rascunho_devolve_os_retidos_a_fila(db_session):
    campanha_id, ids = _campanha_rascunho_com_destinatarios(db_session, 3)
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [ids[0]])
    assert _estados(db_session, campanha_id).count("retido") == 2

    campanha_service.voltar_para_rascunho(db_session, TENANT_ID, None, campanha_id)

    assert _estados(db_session, campanha_id) == ["pendente", "pendente", "pendente"]


def _campanha_personalizada(db_session) -> int:
    return campanha_service.criar(
        db_session, TENANT_ID, None, "Personalizada", "marketing", ["email"],
        "Novidade para a [Empresa]", "Olá, [Nome],\n\nUma conversa sobre a [Empresa].", None, PLAN_LIMITS,
    ).id


def test_envio_troca_nome_e_empresa_pelo_cadastro_de_cada_destinatario(db_session):
    campanha_id = _campanha_personalizada(db_session)
    maria = _criar_decisor(db_session, "Maria Souza", email="maria@teste.com")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [maria.id])
    campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, campanha_id, [DestinatarioAvulsoSchema(nome="JOAO PEREIRA", email="joao@teste.com")]
    )
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    por_email = {e["destinatario"]: e for e in fake_email.envios}
    assert por_email["maria@teste.com"]["assunto"] == "Novidade para a Empresa de Maria Souza"
    assert por_email["maria@teste.com"]["corpo"].startswith("Olá, Maria,\n\nUma conversa sobre a Empresa de Maria Souza.")
    assert por_email["joao@teste.com"]["assunto"] == "Novidade para a a sua empresa"  # avulso não tem empresa no cadastro
    assert por_email["joao@teste.com"]["corpo"].startswith("Olá, Joao,\n\nUma conversa sobre a a sua empresa.")
    assert "[" not in por_email["maria@teste.com"]["corpo"].split("\n\n")[0]


def test_empresa_usa_o_nome_fantasia_quando_existe(db_session):
    campanha_id = _campanha_personalizada(db_session)
    decisor = _criar_decisor(db_session, "Carla Dias", email="carla@teste.com")
    db_session.get(Conta, decisor.conta_id).nome_fantasia = "Fantasia Ltda"
    db_session.commit()
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    assert fake_email.envios[0]["assunto"] == "Novidade para a Fantasia Ltda"


def test_previa_mostra_como_o_email_chega_para_um_destinatario(db_session):
    campanha_id = _campanha_personalizada(db_session)
    sem_lista = campanha_service.previa(db_session, TENANT_ID, campanha_id)
    assert sem_lista["destinatario_nome"] is None and sem_lista["corpo"].startswith("Olá!")

    decisor = _criar_decisor(db_session, "Maria Souza", email="maria@teste.com")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])

    previa = campanha_service.previa(db_session, TENANT_ID, campanha_id)

    assert previa["destinatario_nome"] == "Maria Souza"
    assert previa["assunto"] == "Novidade para a Empresa de Maria Souza"
    assert previa["corpo"].startswith("Olá, Maria,")


def test_envio_adiado_por_falha_de_rede_mostra_o_motivo_no_destinatario_e_limpa_quando_envia(db_session):
    campanha_id = _campanha_pronta_com_destinatarios(db_session, 2)

    campanha_service.processar_pendentes(db_session, TENANT_ID, _EmailSemRede(), FakeWhatsAppProvider())

    primeiro, segundo = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert primeiro.status == "pendente" and "nova tentativa automática" in primeiro.motivo_falha
    assert "Network is unreachable" in primeiro.motivo_falha
    assert segundo.status == "pendente" and segundo.motivo_falha is None  # só quem foi tentado

    campanha_service.processar_pendentes(db_session, TENANT_ID, FakeEmailProvider(), FakeWhatsAppProvider())

    assert all(d.status == "enviado" and d.motivo_falha is None for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id))


def test_lista_colada_com_empresa_usa_a_empresa_digitada_e_sem_empresa_cai_em_a_sua_empresa(db_session):
    campanha_id = _campanha_personalizada(db_session)
    adicionados = campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, campanha_id,
        [
            DestinatarioAvulsoSchema(nome="Maruen Said", email="com@teste.com", empresa="  CyberFort "),
            DestinatarioAvulsoSchema(nome="Maruen Ghadieh", email="sem@teste.com", empresa="   "),
        ],
    )
    assert [d.empresa for d in adicionados] == ["CyberFort", None]  # espaços sobrando e vazio não viram empresa
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    por_email = {e["destinatario"]: e for e in fake_email.envios}
    assert por_email["com@teste.com"]["assunto"] == "Novidade para a CyberFort"
    assert por_email["com@teste.com"]["corpo"].startswith("Olá, Maruen,\n\nUma conversa sobre a CyberFort.")
    assert por_email["sem@teste.com"]["assunto"] == "Novidade para a a sua empresa"


def test_contato_do_crm_guarda_a_empresa_do_cadastro_ao_entrar_na_campanha(db_session):
    campanha_id = _campanha_personalizada(db_session)
    decisor = _criar_decisor(db_session, "Carla Dias", email="carla@teste.com")

    adicionados = campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])

    assert adicionados[0].empresa == "Empresa de Carla Dias"
    db_session.get(Conta, decisor.conta_id).nome = "Nome mudou depois"
    db_session.commit()
    assert campanha_service.previa(db_session, TENANT_ID, campanha_id)["assunto"] == "Novidade para a Empresa de Carla Dias"  # cópia do momento


def test_destinatario_antigo_sem_empresa_guardada_ainda_usa_o_cadastro(db_session):
    campanha_id = _campanha_personalizada(db_session)
    decisor = _criar_decisor(db_session, "Antigo Souza", email="antigo@teste.com")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    destinatario = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]
    destinatario.empresa = None  # linha criada antes da coluna existir
    db_session.commit()

    assert campanha_service.previa(db_session, TENANT_ID, campanha_id)["assunto"] == "Novidade para a Empresa de Antigo Souza"


def test_lista_colada_com_acentos_corrompidos_e_consertada_na_entrada(db_session):
    campanha_id = _campanha_personalizada(db_session)

    adicionados = campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, campanha_id,
        [
            DestinatarioAvulsoSchema(nome="JoÃ£o Paulo", email="a@teste.com", empresa="Grupo BoticÃ¡rio"),
            DestinatarioAvulsoSchema(nome="Ana Lima", email="b@teste.com", empresa="ValCity â€” ServiÃ§os"),
            DestinatarioAvulsoSchema(nome="José SÃO PAULO", email="c@teste.com", empresa="CÂMBIO Ltda"),
        ],
    )

    assert (adicionados[0].nome, adicionados[0].empresa) == ("João Paulo", "Grupo Boticário")
    assert adicionados[1].empresa == "ValCity — Serviços"
    assert (adicionados[2].nome, adicionados[2].empresa) == ("José SÃO PAULO", "CÂMBIO Ltda")  # texto correto passa intacto

    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    assert campanha_service.previa(db_session, TENANT_ID, campanha_id)["corpo"].startswith("Olá, João,")


def test_destinatario_com_email_invalido_fica_nao_enviado_e_o_envio_continua(db_session):
    campanha_id = _criar_campanha_email(db_session)
    for i in range(3):
        decisor = _criar_decisor(db_session, f"Pessoa {i}", email=f"pessoa{i}@teste.com")
        campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    do_meio = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[1]
    do_meio.email = "https://www.linkedin.com/in/fulano"  # entrou assim por coluna deslocada numa lista colada
    db_session.commit()
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    fake_email = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    assert resultado == {"enviadas": 2, "falhas": 0, "adiadas": 0, "ignoradas": 1}
    assert [e["destinatario"] for e in fake_email.envios] == ["pessoa0@teste.com", "pessoa2@teste.com"]  # o servidor nem foi chamado para o inválido
    estados = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert [d.status for d in estados] == ["enviado", "nao_enviado", "enviado"]  # nem "falhou" (retentativa) nem tentativa no servidor
    assert estados[1].motivo_falha.startswith("E-mail inválido: https://www.linkedin.com")
    assert campanha_service.metricas(db_session, TENANT_ID, campanha_id)["nao_enviado"] == 1
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "concluida"


def test_lista_colada_ignora_o_que_nao_e_email_e_so_entra_com_telefone(db_session):
    campanha_id = _criar_campanha_email(db_session)

    adicionados = campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, campanha_id,
        [
            DestinatarioAvulsoSchema(nome="Link", email="https://www.linkedin.com/in/fulano"),
            DestinatarioAvulsoSchema(nome="Sigla", email="SM"),
            DestinatarioAvulsoSchema(nome="Certificações", email="CISM, CISSP"),
            DestinatarioAvulsoSchema(nome="Com telefone", email="PMI-RMP", telefone="11999990000"),
            DestinatarioAvulsoSchema(nome="Certo", email="certo@teste.com"),
        ],
    )

    assert [d.nome for d in adicionados] == ["Com telefone", "Certo"]
    assert adicionados[0].email is None and adicionados[0].telefone == "11999990000"  # o falso e-mail não vira endereço de envio


def test_contato_do_crm_cujo_unico_contato_nao_e_email_nao_entra_na_campanha(db_session):
    campanha_id = _criar_campanha_email(db_session)
    sem_email = _criar_decisor(db_session, "Sem Email", email="https://www.linkedin.com/in/sem-email")
    sem_email.telefone = None
    db_session.commit()
    certo = _criar_decisor(db_session, "Certo", email="certo@teste.com")

    adicionados = campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [sem_email.id, certo.id])

    assert [d.nome for d in adicionados] == ["Certo"]


def test_nao_enviado_nao_e_repetido_nem_selecionavel_no_proximo_envio(db_session):
    campanha_id = _criar_campanha_email(db_session)
    for i in range(2):
        decisor = _criar_decisor(db_session, f"Pessoa {i}", email=f"pessoa{i}@teste.com")
        campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    invalido = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]
    invalido.email = "SM"
    db_session.commit()
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    campanha_service.processar_pendentes(db_session, TENANT_ID, FakeEmailProvider(), FakeWhatsAppProvider())
    assert invalido.status == "nao_enviado"

    campanha_service.voltar_para_rascunho(db_session, TENANT_ID, None, campanha_id)

    assert db_session.get(type(invalido), invalido.id).status == "nao_enviado"  # editar a campanha não devolve à fila quem nunca teve destino
    with pytest.raises(ValidacaoFalhou):
        campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id, [invalido.id])


def test_destinatario_so_com_telefone_em_campanha_de_email_fica_nao_enviado(db_session):
    campanha_id = _criar_campanha_email(db_session)
    campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, campanha_id,
        [DestinatarioAvulsoSchema(nome="So telefone", telefone="11999990000"), DestinatarioAvulsoSchema(nome="Certo", email="certo@teste.com")],
    )
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)

    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, FakeEmailProvider(), FakeWhatsAppProvider())

    assert resultado == {"enviadas": 1, "falhas": 0, "adiadas": 0, "ignoradas": 1}
    estados = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)
    assert [d.status for d in estados] == ["nao_enviado", "enviado"]
    assert estados[0].motivo_falha.startswith("Sem e-mail ou telefone compatível")


def test_endereco_que_ja_voltou_em_outra_campanha_nao_recebe_de_novo(db_session):
    primeira = _criar_campanha_email(db_session)
    campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, primeira,
        [DestinatarioAvulsoSchema(nome="Voltou", email="Voltou@Teste.com")],
    )
    antigo = campanha_service.listar_destinatarios(db_session, TENANT_ID, primeira)[0]
    antigo.status = "enviado"
    antigo.bounce_em = datetime.now(UTC)  # o e-mail voltou como não entregue
    db_session.commit()

    segunda = _criar_campanha_email(db_session)
    campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, segunda,
        [DestinatarioAvulsoSchema(nome="Voltou de novo", email="voltou@teste.com"), DestinatarioAvulsoSchema(nome="Certo", email="certo@teste.com")],
    )
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, segunda)

    fake_email = FakeEmailProvider()
    resultado = campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider(), campanha_id=segunda)

    assert [e["destinatario"] for e in fake_email.envios] == ["certo@teste.com"]
    assert resultado["ignoradas"] == 1
    voltou = campanha_service.listar_destinatarios(db_session, TENANT_ID, segunda)[0]
    assert voltou.status == "nao_enviado" and voltou.motivo_falha.startswith("E-mail devolvido em envio anterior")


def test_email_de_campanha_sai_com_pixel_de_abertura_e_marca_o_destinatario(db_session):
    from app.core.config import settings

    campanha_id = _campanha_pronta_com_destinatarios(db_session, 1)
    fake_email = FakeEmailProvider()

    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    destinatario = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]
    assert fake_email.envios[0]["pixel_url"].startswith(f"{settings.url_base_api}/webhooks/email/aberto/{TENANT_ID}:c{destinatario.id}:")
    assert destinatario.pixel_incluido is True and destinatario.aberto_em is None


def test_pixel_registra_a_abertura_so_do_destinatario_certo_e_uma_vez(db_session):
    from app.services import rastreamento_service

    campanha_id = _campanha_pronta_com_destinatarios(db_session, 2)
    primeiro, segundo = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)

    rastreamento_service.registrar_abertura(db_session, rastreamento_service.gerar_token_abertura(TENANT_ID, primeiro.id, campanha=True))
    aberto_em = primeiro.aberto_em
    rastreamento_service.registrar_abertura(db_session, rastreamento_service.gerar_token_abertura(TENANT_ID, primeiro.id, campanha=True))

    assert aberto_em is not None and primeiro.aberto_em == aberto_em  # a primeira abertura é a que vale
    assert segundo.aberto_em is None


def test_pixel_com_token_adulterado_ou_de_outro_tenant_nao_registra_nada(db_session):
    from app.services import rastreamento_service

    campanha_id = _campanha_pronta_com_destinatarios(db_session, 1)
    destinatario = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]
    valido = rastreamento_service.gerar_token_abertura(TENANT_ID, destinatario.id, campanha=True)

    rastreamento_service.registrar_abertura(db_session, valido[:-1] + ("0" if valido[-1] != "0" else "1"))  # assinatura adulterada
    rastreamento_service.registrar_abertura(db_session, rastreamento_service.gerar_token_abertura("outro-tenant", destinatario.id, campanha=True))
    rastreamento_service.registrar_abertura(db_session, f"{TENANT_ID}:c{destinatario.id}")
    rastreamento_service.registrar_abertura(db_session, "lixo")

    assert destinatario.aberto_em is None


# --- editar destinatário e lista de bloqueio ----------------------------------------------------------------------------------------


def _avulsos(db_session, campanha_id: int, *itens: tuple[str, str | None, str | None]) -> list:
    return campanha_service.adicionar_avulsos(
        db_session, TENANT_ID, None, campanha_id,
        [DestinatarioAvulsoSchema(nome=nome, email=email, telefone=telefone) for nome, email, telefone in itens],
    )


def _enviar_todos(db_session, campanha_id: int, fake: FakeEmailProvider | None = None) -> FakeEmailProvider:
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    fake = fake or FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, fake, FakeWhatsAppProvider())
    return fake


def test_corrigir_o_email_de_quem_nao_foi_enviado_devolve_para_a_fila_e_reabre_a_campanha(db_session):
    campanha_id = _criar_campanha_email(db_session)
    from app.models.campanha import CampanhaDestinatario

    _avulsos(db_session, campanha_id, ("Certo", "certo@teste.com", None))
    errado = CampanhaDestinatario(  # entrou assim numa lista antiga, antes de o sistema recusar endereços fora do formato
        tenant_id=TENANT_ID, campanha_id=campanha_id, nome="Digitou errado", email="digitou-errado@", status="pendente"
    )
    db_session.add(errado)
    db_session.commit()
    fake = _enviar_todos(db_session, campanha_id)
    db_session.refresh(errado)
    assert errado.status == "nao_enviado"
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "concluida"

    corrigido = campanha_service.editar_destinatario(
        db_session, TENANT_ID, None, campanha_id, errado.id, "Digitou errado", "certo2@teste.com", None, None
    )

    assert corrigido.status == "pendente" and corrigido.email == "certo2@teste.com" and corrigido.motivo_falha is None
    assert campanha_service.obter(db_session, TENANT_ID, campanha_id).status == "rascunho"  # reaberta para o envio poder ser retomado
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    segundo = FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, segundo, FakeWhatsAppProvider())
    assert [e["destinatario"] for e in segundo.envios] == ["certo2@teste.com"]  # só o corrigido
    assert [e["destinatario"] for e in fake.envios] == ["certo@teste.com"]


def test_trocar_o_email_de_quem_ja_recebeu_exige_reenviar_e_zera_o_rastreio_do_endereco_antigo(db_session):
    campanha_id = _criar_campanha_email(db_session)
    _avulsos(db_session, campanha_id, ("Vai mudar", "antigo@teste.com", None))
    _enviar_todos(db_session, campanha_id)
    destinatario = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]
    destinatario.aberto_em = datetime.now(UTC)
    destinatario.entregue_em = datetime.now(UTC)
    db_session.commit()

    with pytest.raises(ValidacaoFalhou, match="já recebeu"):
        campanha_service.editar_destinatario(db_session, TENANT_ID, None, campanha_id, destinatario.id, "Vai mudar", "novo@teste.com", None, None)
    assert destinatario.email == "antigo@teste.com" and destinatario.status == "enviado"  # nada mudou na recusa

    novo = campanha_service.editar_destinatario(
        db_session, TENANT_ID, None, campanha_id, destinatario.id, "Vai mudar", "novo@teste.com", None, None, reenviar=True
    )

    assert novo.status == "pendente" and novo.email == "novo@teste.com"
    assert novo.aberto_em is None and novo.entregue_em is None and novo.enviado_em is None and novo.pixel_incluido is False


def test_editar_so_o_nome_ou_a_empresa_nao_mexe_no_status_de_quem_ja_recebeu(db_session):
    campanha_id = _criar_campanha_email(db_session)
    _avulsos(db_session, campanha_id, ("Maria", "maria@teste.com", None))
    _enviar_todos(db_session, campanha_id)
    destinatario = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]

    editado = campanha_service.editar_destinatario(
        db_session, TENANT_ID, None, campanha_id, destinatario.id, "Maria Souza", "MARIA@teste.com", None, "Acme"
    )

    assert editado.status == "enviado" and editado.nome == "Maria Souza" and editado.empresa == "Acme"  # maiúsculas no e-mail não contam como troca


def test_editar_destinatario_valida_os_dados_e_recusa_durante_o_envio(db_session):
    campanha_id = _criar_campanha_email(db_session)
    a, b = _avulsos(db_session, campanha_id, ("A", "a@teste.com", None), ("B", "b@teste.com", None))

    with pytest.raises(ValidacaoFalhou, match="nome"):
        campanha_service.editar_destinatario(db_session, TENANT_ID, None, campanha_id, a.id, "  ", "a@teste.com", None, None)
    with pytest.raises(ValidacaoFalhou, match="e-mail válido"):
        campanha_service.editar_destinatario(db_session, TENANT_ID, None, campanha_id, a.id, "A", "isso-nao-e-email", None, None)
    with pytest.raises(ValidacaoFalhou, match="e-mail ou o telefone"):
        campanha_service.editar_destinatario(db_session, TENANT_ID, None, campanha_id, a.id, "A", None, "  ", None)
    with pytest.raises(ValidacaoFalhou, match="outro destinatário"):
        campanha_service.editar_destinatario(db_session, TENANT_ID, None, campanha_id, a.id, "A", "B@teste.com", None, None)
    with pytest.raises(NaoEncontrado):
        campanha_service.editar_destinatario(db_session, TENANT_ID, None, campanha_id, 999999, "A", "a@teste.com", None, None)

    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    with pytest.raises(RegraNegocioViolada, match="sendo enviada"):
        campanha_service.editar_destinatario(db_session, TENANT_ID, None, campanha_id, a.id, "A", "a2@teste.com", None, None)


def test_trocar_o_email_pode_atualizar_o_cadastro_do_contato_no_crm(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Do CRM", email="antigo@teste.com")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    destinatario = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]

    campanha_service.editar_destinatario(
        db_session, TENANT_ID, None, campanha_id, destinatario.id, "Do CRM", "novo@teste.com", None, None, atualizar_contato_crm=True
    )

    db_session.expire_all()
    assert db_session.get(Decisor, decisor.id).email == "novo@teste.com"


def test_nao_quer_receber_cancela_o_destinatario_e_bloqueia_o_contato_em_todas_as_campanhas(db_session):
    from app.services import bloqueio_contato_service

    primeira = _criar_campanha_email(db_session)
    a, _ = _avulsos(db_session, primeira, ("Sem interesse", "Sem.Interesse@Teste.com", "+55 (11) 99999-0000"), ("Outro", "outro@teste.com", None))

    cancelado = campanha_service.nao_quer_receber(db_session, TENANT_ID, None, primeira, a.id, "Disse por telefone que não tem interesse")

    assert cancelado.status == "optout" and cancelado.motivo_falha == "Disse por telefone que não tem interesse"
    bloqueios = bloqueio_contato_service.listar(db_session, TENANT_ID)
    assert len(bloqueios) == 1 and bloqueios[0].email == "sem.interesse@teste.com" and bloqueios[0].telefone == "5511999990000"
    # repetir não duplica
    campanha_service.nao_quer_receber(db_session, TENANT_ID, None, primeira, a.id)
    assert len(bloqueio_contato_service.listar(db_session, TENANT_ID)) == 1

    # outra campanha, mesmo e-mail em outra caixa/minúsculas e mesmo telefone com outra formatação: não recebe
    segunda = _criar_campanha_email(db_session)
    _avulsos(
        db_session, segunda,
        ("Mesmo e-mail", "SEM.INTERESSE@teste.com", None),
        ("Mesmo telefone", "novo-email@teste.com", "11 99999-0000"),
        ("Pessoa diferente", "diferente@teste.com", None),
    )
    fake = _enviar_todos(db_session, segunda)

    assert [e["destinatario"] for e in fake.envios] == ["diferente@teste.com"]
    estados = {d.nome: (d.status, d.motivo_falha) for d in campanha_service.listar_destinatarios(db_session, TENANT_ID, segunda)}
    assert estados["Mesmo e-mail"][0] == "nao_enviado" and "Pediu para não receber" in estados["Mesmo e-mail"][1]
    assert estados["Mesmo telefone"][0] == "nao_enviado"
    assert estados["Pessoa diferente"][0] == "enviado"


def test_nao_quer_receber_de_contato_do_crm_aplica_o_cancelamento_completo(db_session):
    campanha_id = _criar_campanha_email(db_session)
    decisor = _criar_decisor(db_session, "Do CRM", email="crm@teste.com")
    campanha_service.adicionar_de_decisores(db_session, TENANT_ID, None, campanha_id, [decisor.id])
    destinatario = campanha_service.listar_destinatarios(db_session, TENANT_ID, campanha_id)[0]

    campanha_service.nao_quer_receber(db_session, TENANT_ID, None, campanha_id, destinatario.id)

    db_session.expire_all()
    assert db_session.get(Decisor, decisor.id).suprimido_em is not None  # não recebe nem cadência nem outras campanhas pelo cadastro


def test_nao_quer_receber_durante_o_envio_faz_o_envio_pular_o_destinatario(db_session):
    campanha_id = _criar_campanha_email(db_session)
    a, b, c = _avulsos(db_session, campanha_id, ("A", "a@teste.com", None), ("B", "b@teste.com", None), ("C", "c@teste.com", None))
    campanha_service.marcar_pronta(db_session, TENANT_ID, None, campanha_id)
    campanha_service.nao_quer_receber(db_session, TENANT_ID, None, campanha_id, b.id)

    fake = FakeEmailProvider()
    campanha_service.processar_pendentes(db_session, TENANT_ID, fake, FakeWhatsAppProvider())

    assert [e["destinatario"] for e in fake.envios] == ["a@teste.com", "c@teste.com"]


def test_liberar_o_bloqueio_volta_a_permitir_o_envio(db_session):
    from app.services import bloqueio_contato_service

    campanha_id = _criar_campanha_email(db_session)
    a, = _avulsos(db_session, campanha_id, ("A", "a@teste.com", None))
    campanha_service.nao_quer_receber(db_session, TENANT_ID, None, campanha_id, a.id)
    bloqueio = bloqueio_contato_service.listar(db_session, TENANT_ID)[0]

    bloqueio_contato_service.liberar(db_session, TENANT_ID, None, bloqueio.id)

    assert bloqueio_contato_service.listar(db_session, TENANT_ID) == []
    nova = _criar_campanha_email(db_session)
    _avulsos(db_session, nova, ("A de novo", "a@teste.com", None))
    assert [e["destinatario"] for e in _enviar_todos(db_session, nova).envios] == ["a@teste.com"]
    with pytest.raises(NaoEncontrado):
        bloqueio_contato_service.liberar(db_session, TENANT_ID, None, bloqueio.id)


def test_normalizacao_de_email_e_telefone_do_bloqueio():
    from app.services.bloqueio_contato_service import Bloqueados, normalizar_email, normalizar_telefone

    assert normalizar_email("  Fulano@Empresa.COM ") == "fulano@empresa.com" and normalizar_email("  ") is None
    assert normalizar_telefone("+55 (11) 99999-0000") == "5511999990000"
    assert normalizar_telefone("123") is None  # curto demais para ser telefone
    bloqueados = Bloqueados(emails={"a@x.com"}, telefones={"1199990000"})
    assert bloqueados.contem("A@X.com", None) and bloqueados.contem(None, "+55 11 9999-0000") and not bloqueados.contem("b@x.com", "21 8888-7777")
