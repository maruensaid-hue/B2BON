from datetime import UTC, datetime, timedelta

import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.schemas.campanha import DestinatarioAvulsoSchema
from app.services import campanha_service, reputacao_service
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou
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
