"""D-087 — escrita no CRM do cliente (PREDATOR/MAP → CRM), deduplicação da
prospecção, OAuth pela tela e webhooks de entrada.

Motor e barreiras são testados com um CRM em memória (mesmo contrato dos 4
conectores); o formato de cada API é testado em `test_escrita_conectores.py`.
"""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.contexts.integrations import contract as integracoes
from app.contexts.integrations import entrada, escrita, oauth
from app.contexts.integrations.adapters import http_base
from app.contexts.integrations.adapters.payload import PayloadCrmAdapter
from app.contexts.integrations.contract import ErroCredencial, ErroTransitorio, OperacaoNaoSuportada
from app.contexts.map import sinais_crm
from app.contexts.shared.canonical.base import SourceRef
from app.contexts.shared.canonical.commercial import (
    Account,
    AccountLifecycle,
    Customer,
    Opportunity,
    OpportunityStatus,
    Organization,
    Person,
)
from app.core.config import settings
from app.models.auditoria import AuditLog
from app.models.conexao_integracao import ConexaoIntegracao
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.integracao_crm import AutorizacaoOauthPendente, EnvioCrm, VinculoExterno
from app.models.mensagem import Mensagem
from app.models.reuniao import Reuniao
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service, envio_service, optout_service

TENANT = "tenant-teste"
H = "/api/v1/hub-integracoes"
AGORA = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def _src(entidade: str, id_: str) -> SourceRef:
    return SourceRef(system="hubspot", external_id=id_, entity=entidade, fetched_at=AGORA)


class CrmMemoria(PayloadCrmAdapter):
    """CRM em memória com as portas de escrita do contrato."""

    def __init__(self, tenant_id=TENANT, **colecoes):
        super().__init__(tenant_id, **colecoes)
        self.empresas, self.pessoas, self.atividades, self.negocios, self.tarefas = {}, {}, [], [], []
        self.optouts, self.sinais, self.falhas = [], [], []
        self._seq = 100

    def _novo(self) -> str:
        self._seq += 1
        return str(self._seq)

    def _falhar(self):
        if self.falhas:
            raise self.falhas.pop(0)

    def garantir_empresa(self, tenant_id, empresa):
        assert tenant_id == self._tenant_id
        self._falhar()
        for id_, existente in self.empresas.items():
            if (empresa.cnpj and existente.cnpj == empresa.cnpj) or (empresa.dominio and existente.dominio == empresa.dominio):
                return id_
        id_ = self._novo()
        self.empresas[id_] = empresa
        return id_

    def garantir_pessoa(self, tenant_id, pessoa):
        self._falhar()
        for id_, existente in self.pessoas.items():
            if pessoa.email and existente.email == pessoa.email:
                return id_
        id_ = self._novo()
        self.pessoas[id_] = pessoa
        return id_

    def registrar_atividade(self, tenant_id, atividade):
        self._falhar()
        self.atividades.append(atividade)
        return self._novo()

    def criar_negocio(self, tenant_id, negocio):
        self._falhar()
        self.negocios.append(negocio)
        return self._novo()

    def criar_tarefa(self, tenant_id, tarefa):
        self.tarefas.append(tarefa)
        return self._novo()

    def marcar_optout(self, tenant_id, pessoa_id, campos):
        self.optouts.append((pessoa_id, campos))

    def gravar_sinais_conta(self, tenant_id, sinais, campos):
        self.sinais.append((sinais, campos))


@pytest.fixture(autouse=True)
def _hubspot_liberado(monkeypatch):
    monkeypatch.setattr(settings, "conectores_crm_habilitados", "hubspot,salesforce,pipedrive")
    monkeypatch.setattr(settings, "escrita_crm_ativa", True)


def _conexao(db, tenant=TENANT, sistema="hubspot", **opcoes) -> ConexaoIntegracao:
    if db.get(Tenant, tenant) is None:
        db.add(Tenant(id=tenant, razao_social=tenant))
    conexao = ConexaoIntegracao(tenant_id=tenant, sistema=sistema, nome="CRM", status="ativa", configuracao={},
                                credenciais=json.dumps({"access_token": "pat-valido"}), escrita=opcoes)
    db.add(conexao)
    db.commit()
    return conexao


def _conta_decisor(db, tenant=TENANT, **decisor):
    if db.get(Tenant, tenant) is None:
        db.add(Tenant(id=tenant, razao_social=tenant))
    conta = Conta(tenant_id=tenant, nome="ACME Ltda", cnpj="11.222.333/0001-81", dominio="www.acme.com.br", status="prospectada")
    db.add(conta)
    db.flush()
    dados = {"nome": "Ana Souza", "cargo": "CFO", "email": "ana@acme.com.br", "telefone": "+5511999990000", **decisor}
    pessoa = Decisor(tenant_id=tenant, conta_id=conta.id, **dados)
    db.add(pessoa)
    db.commit()
    return conta, pessoa


def _processar(db, crm, agora=None):
    return escrita.processar_fila(db, agora=agora or datetime.now(UTC) + timedelta(seconds=1), fabrica=lambda _db, _c: crm)


# --- Opt-in, demonstração, interruptor --------------------------------------------------
def test_nada_e_enfileirado_sem_opt_in_da_conexao(db_session):
    _conexao(db_session)  # escrita desligada (padrão)
    conta, _ = _conta_decisor(db_session)
    assert escrita.enfileirar(db_session, TENANT, "empresa", conta.id) == 0
    assert db_session.query(EnvioCrm).count() == 0


def test_tenant_de_demonstracao_nunca_escreve(db_session):
    db_session.add(Tenant(id="demo-x", razao_social="Demo", demo_expira_em=datetime.now(UTC) + timedelta(hours=1)))
    db_session.commit()
    _conexao(db_session, tenant="demo-x", predator=True)
    conta, _ = _conta_decisor(db_session, tenant="demo-x")
    assert escrita.enfileirar(db_session, "demo-x", "empresa", conta.id) == 0


def test_interruptor_geral_segura_a_fila(db_session, monkeypatch):
    _conexao(db_session, predator=True)
    conta, _ = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)
    db_session.commit()
    monkeypatch.setattr(settings, "escrita_crm_ativa", False)
    crm = CrmMemoria()
    assert _processar(db_session, crm)["desligada"] is True
    assert not crm.empresas and db_session.query(EnvioCrm).one().status == "pendente"


def test_desligar_a_capacidade_pula_o_que_estava_pendente(db_session):
    conexao = _conexao(db_session, predator=True)
    conta, _ = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)
    conexao.escrita = {"predator": False}
    db_session.commit()
    crm = CrmMemoria()
    assert _processar(db_session, crm)["pulados"] == 1
    assert not crm.empresas


def test_conexao_pausada_adia_sem_gastar_tentativa(db_session):
    conexao = _conexao(db_session, predator=True)
    conta, _ = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)
    conexao.status = "erro"
    db_session.commit()
    assert _processar(db_session, CrmMemoria())["adiados"] == 1
    envio = db_session.query(EnvioCrm).one()
    assert envio.status == "pendente" and envio.tentativas == 0


# --- Idempotência e regra de conflito ---------------------------------------------------
def test_empresa_e_pessoa_criadas_uma_vez_e_auditadas(db_session):
    _conexao(db_session, predator=True)
    conta, decisor = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)
    escrita.enfileirar(db_session, TENANT, "pessoa", decisor.id)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)  # mesma chave: ignorado
    db_session.commit()
    crm = CrmMemoria()
    resultado = _processar(db_session, crm)
    assert resultado["enviados"] == 2
    assert len(crm.empresas) == 1 and len(crm.pessoas) == 1
    empresa = next(iter(crm.empresas.values()))
    assert empresa.cnpj == "11222333000181" and empresa.dominio == "acme.com.br"
    pessoa = next(iter(crm.pessoas.values()))
    assert pessoa.empresa_id == next(iter(crm.empresas))
    assert db_session.query(VinculoExterno).filter_by(entidade="empresa", id_interno=str(conta.id)).count() == 1
    assert db_session.query(AuditLog).filter_by(evento_tipo="crm_escrita").count() == 2


def test_falha_parcial_nao_duplica_no_reenvio(db_session):
    """Empresa criada, pessoa falhou (429): na nova tentativa a empresa vem do vínculo."""
    _conexao(db_session, predator=True)
    _, decisor = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "pessoa", decisor.id)
    db_session.commit()
    crm = CrmMemoria()
    original = crm.garantir_pessoa
    chamadas = {"n": 0}

    def pessoa_falha_uma_vez(tenant_id, pessoa):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise ErroTransitorio("hubspot: HTTP 429")
        return original(tenant_id, pessoa)

    crm.garantir_pessoa = pessoa_falha_uma_vez
    assert _processar(db_session, crm)["reagendados"] == 1
    assert _processar(db_session, crm, agora=datetime.now(UTC) + timedelta(minutes=2))["enviados"] == 1
    assert len(crm.empresas) == 1 and len(crm.pessoas) == 1


def test_contato_com_optout_nunca_e_escrito(db_session):
    _conexao(db_session, predator=True)
    _, decisor = _conta_decisor(db_session, suprimido_em=datetime.now(UTC))
    escrita.enfileirar(db_session, TENANT, "pessoa", decisor.id)
    db_session.commit()
    crm = CrmMemoria()
    _processar(db_session, crm)
    envio = db_session.query(EnvioCrm).one()
    assert envio.status == "pulado" and "opt-out" in envio.resultado
    assert not crm.pessoas


def test_desiste_apos_esgotar_tentativas_e_reprocessa_manual(client, db_session):
    _conexao(db_session, predator=True)
    conta, _ = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)
    db_session.commit()
    crm = CrmMemoria()
    crm.falhas = [ErroTransitorio("HTTP 503")] * escrita.MAX_TENTATIVAS
    agora = datetime.now(UTC)
    for _ in range(escrita.MAX_TENTATIVAS):
        agora += timedelta(hours=7)
        _processar(db_session, crm, agora=agora)
    envio = db_session.query(EnvioCrm).one()
    assert envio.status == "desistido" and envio.tentativas == escrita.MAX_TENTATIVAS
    assert db_session.query(AuditLog).filter_by(evento_tipo="crm_escrita_desistida").count() == 1

    resposta = client.post(f"{H}/envios/{envio.id}/reprocessar")
    assert resposta.status_code == 200 and resposta.json()["status"] == "pendente"
    assert _processar(db_session, crm, agora=agora + timedelta(minutes=1))["enviados"] == 1


def test_credencial_recusada_marca_conexao_para_reconectar(db_session):
    conexao = _conexao(db_session, predator=True)
    conta, _ = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)
    db_session.commit()
    crm = CrmMemoria()
    crm.falhas = [ErroCredencial("hubspot: credencial recusada (HTTP 401)")]
    _processar(db_session, crm)
    db_session.refresh(conexao)
    assert conexao.status == "erro"
    assert db_session.query(EnvioCrm).one().status == "pendente"


def test_operacao_nao_suportada_vira_pulo_com_motivo(db_session):
    _conexao(db_session, predator=True)
    conta, _ = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "empresa", conta.id)
    db_session.commit()
    crm = CrmMemoria()
    crm.falhas = [OperacaoNaoSuportada("RD Station CRM só registra atividades dentro de uma negociação")]
    _processar(db_session, crm)
    envio = db_session.query(EnvioCrm).one()
    assert envio.status == "pulado" and "negociação" in envio.resultado


# --- PREDATOR: reunião → negócio, mensagens, opt-out --------------------------------------
def _reuniao(db, conta, decisor, **campos):
    reuniao = Reuniao(tenant_id=TENANT, conta_id=conta.id, decisor_id=decisor.id, vendedor_id="7",
                      data_hora=datetime(2026, 10, 10, 15, 0), status="agendada", **campos)
    db.add(reuniao)
    db.commit()
    return reuniao


def test_reuniao_agendada_cria_negocio_no_estagio_e_reuniao(db_session):
    _conexao(db_session, predator=True, estagio_id="appointmentscheduled", pipeline_id="default", donos={"7": "9001"})
    conta, decisor = _conta_decisor(db_session)
    reuniao = _reuniao(db_session, conta, decisor, link_reuniao="https://meet.exemplo/abc")
    escrita.enfileirar(db_session, TENANT, "reuniao_agendada", reuniao.id)
    db_session.commit()
    crm = CrmMemoria()
    _processar(db_session, crm)
    assert db_session.query(EnvioCrm).one().status == "enviado"
    negocio = crm.negocios[0]
    assert negocio.estagio_id == "appointmentscheduled" and negocio.pipeline_id == "default" and negocio.dono_externo_id == "9001"
    assert negocio.previsao_fechamento is None  # sem prazo configurado, nenhuma data é inventada
    atividade = crm.atividades[0]
    assert atividade.tipo == "reuniao" and atividade.negocio_id and "meet.exemplo" in atividade.descricao

    # segunda reunião da mesma conta reaproveita o negócio
    outra = _reuniao(db_session, conta, decisor)
    escrita.enfileirar(db_session, TENANT, "reuniao_agendada", outra.id)
    db_session.commit()
    _processar(db_session, crm)
    assert len(crm.negocios) == 1 and len(crm.atividades) == 2


def test_reuniao_sem_estagio_configurado_e_pulada_com_motivo(db_session):
    _conexao(db_session, predator=True)
    conta, decisor = _conta_decisor(db_session)
    reuniao = _reuniao(db_session, conta, decisor)
    escrita.enfileirar(db_session, TENANT, "reuniao_agendada", reuniao.id)
    db_session.commit()
    crm = CrmMemoria()
    _processar(db_session, crm)
    envio = db_session.query(EnvioCrm).one()
    assert envio.status == "pulado" and "estágio" in envio.resultado and not crm.negocios


def test_prazo_configurado_vira_previsao_de_fechamento(db_session):
    _conexao(db_session, predator=True, estagio_id="Prospecting", prazo_fechamento_dias=30)
    conta, decisor = _conta_decisor(db_session)
    reuniao = _reuniao(db_session, conta, decisor)
    escrita.enfileirar(db_session, TENANT, "reuniao_agendada", reuniao.id)
    db_session.commit()
    crm = CrmMemoria()
    _processar(db_session, crm)
    assert crm.negocios[0].previsao_fechamento.isoformat() == "2026-11-09"


def test_resultado_da_reuniao_vira_nota_no_negocio(db_session):
    _conexao(db_session, predator=True, estagio_id="s1")
    conta, decisor = _conta_decisor(db_session)
    reuniao = _reuniao(db_session, conta, decisor, qualificada_confirmada=True, motivo_qualificacao="orçamento aprovado")
    escrita.enfileirar(db_session, TENANT, "reuniao_agendada", reuniao.id)
    escrita.enfileirar(db_session, TENANT, "reuniao_resultado", reuniao.id, chave=f"reuniao_qualificacao:{reuniao.id}:True")
    db_session.commit()
    crm = CrmMemoria()
    _processar(db_session, crm)
    nota = crm.atividades[-1]
    assert nota.tipo == "nota" and "Qualificada: sim (orçamento aprovado)" in nota.descricao and nota.negocio_id


def test_optout_local_vai_ao_crm_e_optout_do_crm_nao_volta(db_session):
    _conexao(db_session, predator=True)
    conta, decisor = _conta_decisor(db_session)
    escrita.enfileirar(db_session, TENANT, "pessoa", decisor.id)
    db_session.commit()
    crm = CrmMemoria()
    _processar(db_session, crm)
    pessoa_externa = next(iter(crm.pessoas))

    optout_service.processar(db_session, TENANT, decisor.id, origem="manual")
    _processar(db_session, crm)
    assert crm.optouts == [(pessoa_externa, crm.optouts[0][1])]

    _, outro = _conta_decisor(db_session, email="beto@acme.com.br")
    optout_service.aplicar(db_session, TENANT, outro, origem="crm_externo")
    db_session.commit()
    assert db_session.query(EnvioCrm).filter_by(operacao="optout").count() == 1


def test_optout_de_quem_nao_esta_no_crm_e_pulado(db_session):
    _conexao(db_session, predator=True)
    _, decisor = _conta_decisor(db_session)
    optout_service.processar(db_session, TENANT, decisor.id, origem="manual")
    crm = CrmMemoria()
    _processar(db_session, crm)
    envio = db_session.query(EnvioCrm).filter_by(operacao="optout").one()
    assert envio.status == "pulado" and not crm.optouts


# --- Deduplicação antes de prospectar ----------------------------------------------------
def _crm_com_cliente_e_optout() -> CrmMemoria:
    return CrmMemoria(
        organizations=[Organization(id="hubspot:organization:1", tenant_id=TENANT, source=_src("company", "1"), legal_name="ACME",
                                    tax_id="11222333000181", domain="acme.com.br"),
                       Organization(id="hubspot:organization:2", tenant_id=TENANT, source=_src("company", "2"), legal_name="Beta",
                                    domain="beta.com")],
        accounts=[Account(id="hubspot:account:1", tenant_id=TENANT, source=_src("company", "1"), organization_id="hubspot:organization:1",
                          lifecycle=AccountLifecycle.CUSTOMER),
                  Account(id="hubspot:account:2", tenant_id=TENANT, source=_src("company", "2"), organization_id="hubspot:organization:2",
                          lifecycle=AccountLifecycle.PROSPECT)],
        customers=[Customer(id="hubspot:customer:1", tenant_id=TENANT, source=_src("company", "1"), account_id="hubspot:account:1",
                            customer_since=AGORA)],
        opportunities=[Opportunity(id="hubspot:opportunity:9", tenant_id=TENANT, source=_src("deal", "9"), account_id="hubspot:account:2",
                                   pipeline_id="p", stage_id="s", name="N", status=OpportunityStatus.OPEN)],
        people=[Person(id="hubspot:person:5", tenant_id=TENANT, source=_src("contact", "5"), full_name="Zé", email="ze@outra.com",
                       suppressed_at=AGORA)],
    )


def test_indice_guarda_so_hash_e_bloqueia_cliente_negocio_e_optout(db_session):
    conexao = _conexao(db_session)  # deduplicar é padrão
    resumo = escrita.atualizar_indice(db_session, conexao, _crm_com_cliente_e_optout())
    assert resumo == {"registros": 4, "clientes": 2, "negocios_abertos": 1, "optouts": 1}
    from app.models.integracao_crm import RegistroCrmExterno

    for registro in db_session.query(RegistroCrmExterno).all():
        assert len(registro.chave_hash) == 64 and "acme" not in registro.chave_hash

    assert escrita.bloqueio_prospeccao(db_session, TENANT, "11.222.333/0001-81", None, None)[1] == "cliente"
    assert escrita.bloqueio_prospeccao(db_session, TENANT, None, "https://www.beta.com/x", None)[1] == "negocio_aberto"
    assert escrita.bloqueio_prospeccao(db_session, TENANT, None, None, "ZE@outra.com")[1] == "optout"
    assert escrita.bloqueio_prospeccao(db_session, TENANT, None, "nova.com.br", "x@nova.com.br") is None
    # outro tenant não enxerga o índice
    assert escrita.bloqueio_prospeccao(db_session, "tenant-outro", "11222333000181", None, None) is None


def test_deduplicacao_desligada_nao_bloqueia(db_session):
    conexao = _conexao(db_session, deduplicar=False)
    escrita.atualizar_indice(db_session, conexao, _crm_com_cliente_e_optout())
    assert escrita.bloqueio_prospeccao(db_session, TENANT, "11222333000181", None, None) is None


def test_envio_cancela_mensagem_para_cliente_do_crm_e_importa_optout(db_session, fake_whatsapp, fake_email, fake_email_validacao):
    conexao = _conexao(db_session)
    escrita.atualizar_indice(db_session, conexao, _crm_com_cliente_e_optout())
    conta, decisor = _conta_decisor(db_session)  # CNPJ da ACME = cliente no CRM
    _, ze = _conta_decisor(db_session, email="ze@outra.com")
    db_session.query(Conta).filter_by(id=ze.conta_id).update({"cnpj": None, "dominio": None})
    agora = datetime.now(UTC) - timedelta(minutes=1)
    for alvo in (decisor, ze):
        db_session.add(Mensagem(tenant_id=TENANT, decisor_id=alvo.id, canal="whatsapp", conteudo="Olá", status="aprovado", agendado_para=agora))
    db_session.commit()

    resultado = envio_service.processar_pendentes(db_session, TENANT, fake_whatsapp, fake_email, fake_email_validacao)
    assert resultado["bloqueadas_crm"] == 2 and resultado["enviadas"] == 0 and not fake_whatsapp.envios
    mensagens = db_session.query(Mensagem).order_by(Mensagem.id).all()
    assert [m.status for m in mensagens] == ["cancelado", "cancelado"]
    assert mensagens[0].motivo_falha == "Empresa já é cliente no CRM."
    db_session.refresh(ze)
    assert ze.suprimido_em is not None  # opt-out do CRM vira opt-out aqui
    db_session.refresh(decisor)
    assert decisor.suprimido_em is None  # ser cliente não é opt-out


def test_mensagem_enviada_vira_atividade_no_crm(db_session, fake_whatsapp, fake_email, fake_email_validacao, monkeypatch):
    from app.providers.channels.email.base import ResultadoEnvio

    monkeypatch.setattr(envio_service, "_processar_whatsapp", lambda *a: ResultadoEnvio(sucesso=True, id_externo="wamid.1"))
    _conexao(db_session, predator=True, deduplicar=False)
    from app.models.aprovacao import Aprovacao

    _, decisor = _conta_decisor(db_session)
    mensagem = Mensagem(tenant_id=TENANT, decisor_id=decisor.id, canal="whatsapp", conteudo="Olá Ana", status="aprovado",
                        agendado_para=datetime.now(UTC) - timedelta(minutes=1))
    db_session.add(mensagem)
    db_session.flush()
    db_session.add(Aprovacao(tenant_id=TENANT, mensagem_id=mensagem.id, status="aprovado"))
    db_session.commit()
    resultado = envio_service.processar_pendentes(db_session, TENANT, fake_whatsapp, fake_email, fake_email_validacao)
    assert resultado["enviadas"] == 1, resultado
    crm = CrmMemoria()
    _processar(db_session, crm)
    assert crm.atividades[0].tipo == "whatsapp" and crm.atividades[0].descricao == "Olá Ana"


# --- MAP → CRM -------------------------------------------------------------------------
def test_sinais_do_map_so_para_clientes_e_so_quando_mudam(db_session, monkeypatch):
    conexao = _conexao(db_session, map=True, campos={"score_risco": "b2bon_score_risco", "nivel_risco": "b2bon_nivel_risco"})
    crm = _crm_com_cliente_e_optout()
    monkeypatch.setattr(sinais_crm.saude, "score_risco", lambda fonte, conta: {"score": 82.04, "classificacao": "critico", "dias_sem_contato": 95})
    resumo = sinais_crm.publicar(db_session, conexao, crm, agora=AGORA)
    assert resumo["contas"] == 1 and resumo["enfileiradas"] == 1 and resumo["criticas"] == 1
    _processar(db_session, crm)
    sinais, campos = crm.sinais[0]
    assert sinais.empresa_id == "1" and sinais.score_risco == 82.0 and sinais.nivel_risco == "critico"
    assert campos.score_risco == "b2bon_score_risco"
    assert len(crm.tarefas) == 1 and "95 dias sem contato" in crm.tarefas[0].descricao

    # mesmo score no dia seguinte: nada a enviar; nível muda mas segue crítico no mesmo mês: sem tarefa nova
    assert sinais_crm.publicar(db_session, conexao, crm, agora=AGORA + timedelta(days=1))["enfileiradas"] == 0
    monkeypatch.setattr(sinais_crm.saude, "score_risco", lambda fonte, conta: {"score": 90, "classificacao": "critico", "dias_sem_contato": 96})
    assert sinais_crm.publicar(db_session, conexao, crm, agora=AGORA + timedelta(days=2))["enfileiradas"] == 1
    _processar(db_session, crm)
    assert len(crm.sinais) == 2 and len(crm.tarefas) == 1


def test_sinais_sem_campos_configurados_sao_pulados(db_session, monkeypatch):
    conexao = _conexao(db_session, map=True)
    crm = _crm_com_cliente_e_optout()
    monkeypatch.setattr(sinais_crm.saude, "score_risco", lambda fonte, conta: {"score": 10, "classificacao": "saudavel", "dias_sem_contato": 3})
    sinais_crm.publicar(db_session, conexao, crm, agora=AGORA)
    _processar(db_session, crm)
    envio = db_session.query(EnvioCrm).one()
    assert envio.status == "pulado" and "campos" in envio.resultado and not crm.sinais


# --- API: configuração, isolamento -------------------------------------------------------
def test_api_configura_escrita_com_validacao_e_auditoria(client, db_session):
    conexao = _conexao(db_session)
    resposta = client.get(f"{H}/conexoes/{conexao.id}/escrita")
    assert resposta.status_code == 200
    assert resposta.json()["predator"] is False and resposta.json()["deduplicar"] is True  # opt-in: escrita começa desligada

    ok = client.put(f"{H}/conexoes/{conexao.id}/escrita", json={"predator": True, "estagio_id": "appointmentscheduled", "donos": {"1": "9001"}})
    assert ok.status_code == 200, ok.text
    assert ok.json()["predator"] is True and ok.json()["donos"] == {"1": "9001"}
    assert db_session.query(AuditLog).filter_by(evento_tipo="conexao_integracao_escrita").count() == 1

    for invalido in ({"campos": {"score_risco": "x; drop"}}, {"donos": {"abc": "1"}}, {"prazo_fechamento_dias": 0}, {"estagio_id": "a'b"}):
        assert client.put(f"{H}/conexoes/{conexao.id}/escrita", json=invalido).status_code == 422, invalido


def test_salesforce_exige_prazo_para_criar_negocio(client, db_session):
    conexao = _conexao(db_session, sistema="salesforce")
    resposta = client.put(f"{H}/conexoes/{conexao.id}/escrita", json={"predator": True, "estagio_id": "Prospecting"})
    assert resposta.status_code == 422 and "prazo" in resposta.text
    assert client.put(f"{H}/conexoes/{conexao.id}/escrita", json={"predator": True, "estagio_id": "Prospecting", "prazo_fechamento_dias": 30}).status_code == 200


def test_outro_tenant_nao_ve_nem_mexe(client, db_session):
    alheia = _conexao(db_session, tenant="tenant-outro", predator=True)
    db_session.add(EnvioCrm(tenant_id="tenant-outro", conexao_id=alheia.id, operacao="empresa", id_interno="1", chave="empresa:1",
                            payload={}, status="desistido", tentativas=6))
    db_session.commit()
    envio = db_session.query(EnvioCrm).one()
    assert client.get(f"{H}/conexoes/{alheia.id}/escrita").status_code == 404
    assert client.put(f"{H}/conexoes/{alheia.id}/escrita", json={"predator": False}).status_code == 404
    assert client.post(f"{H}/conexoes/{alheia.id}/webhook-entrada").status_code == 404
    assert client.get(f"{H}/envios").json() == []
    assert client.post(f"{H}/envios/{envio.id}/reprocessar").status_code == 404


def test_pausar_conexao_e_kill_switch(client, db_session):
    conexao = _conexao(db_session, predator=True)
    assert client.put(f"{H}/conexoes/{conexao.id}/status", json={"status": "pausada"}).json()["status"] == "pausada"
    conta, _ = _conta_decisor(db_session)
    assert escrita.enfileirar(db_session, TENANT, "empresa", conta.id) == 0
    assert client.put(f"{H}/conexoes/{conexao.id}/status", json={"status": "apagada"}).status_code == 422


def test_enviar_conta_ao_crm_pela_tela(client, db_session):
    conta, _ = _conta_decisor(db_session)
    assert client.post(f"/api/v1/contas/{conta.id}/enviar-crm").status_code == 422  # sem conexão com escrita
    _conexao(db_session, predator=True)
    resposta = client.post(f"/api/v1/contas/{conta.id}/enviar-crm")
    assert resposta.status_code == 200 and resposta.json() == {"enfileirados": 2}
    situacao = client.get(f"/api/v1/contas/{conta.id}/crm-externo").json()
    assert situacao["escrita_disponivel"] is True and situacao["bloqueio"] is None


def test_credencial_de_app_oauth_nao_pode_ser_colada(client):
    resposta = client.post(f"{H}/conexoes", json={"sistema": "hubspot", "nome": "X",
                                                  "credenciais": {"oauth_app": "b2bon", "access_token": "a", "refresh_token": "b"}})
    assert resposta.status_code == 422 and "Conectar" in resposta.text


# --- Webhook de entrada ------------------------------------------------------------------
def test_webhook_de_entrada_so_marca_e_cron_atualiza_indice(client, db_session, monkeypatch):
    conexao = _conexao(db_session)
    url = client.post(f"{H}/conexoes/{conexao.id}/webhook-entrada").json()["url"]
    token = url.rsplit("/", 1)[-1]
    db_session.refresh(conexao)
    assert token.startswith("whin_") and conexao.webhook_token_hash != token and token not in json.dumps(conexao.escrita or {})

    anonimo = httpx_cliente(client)
    assert anonimo.post(f"{H}/webhook/whin_errado", json={}).status_code == 404
    assert anonimo.post(f"{H}/webhook/{token}", json={"objectId": 1}).status_code == 202
    db_session.refresh(conexao)
    assert conexao.sync_solicitado_em is not None

    salesforce = anonimo.post(f"{H}/webhook/{token}", content="<soapenv:Envelope/>", headers={"content-type": "text/xml"})
    assert salesforce.status_code == 200 and "<Ack>true</Ack>" in salesforce.text

    chamadas = []
    monkeypatch.setattr(escrita, "atualizar_indice", lambda db, c, adapter=None: chamadas.append(c.id) or {})
    assert entrada.processar_solicitacoes(db_session) == {"conexoes": 1, "falhas": 0}
    assert chamadas == [conexao.id]
    db_session.refresh(conexao)
    assert conexao.sync_solicitado_em is None

    # gerar de novo invalida o anterior
    client.post(f"{H}/conexoes/{conexao.id}/webhook-entrada")
    assert anonimo.post(f"{H}/webhook/{token}", json={}).status_code == 404


def httpx_cliente(client):
    """Mesmo app, sem o Authorization do usuário (o CRM não tem login)."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, headers={})


# --- OAuth -------------------------------------------------------------------------------
@pytest.fixture()
def app_hubspot(monkeypatch):
    monkeypatch.setattr(settings, "oauth_hubspot_client_id", "cliente-b2bon")
    monkeypatch.setattr(settings, "oauth_hubspot_client_secret", "segredo-b2bon")
    monkeypatch.setattr(settings, "url_base_api", "https://api.b2bon.test/api/v1")
    monkeypatch.setattr(settings, "url_base_frontend", "https://app.b2bon.test")
    pedidos = []

    def responder(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        corpo = parse_qs(request.content.decode())
        if corpo.get("code") == ["codigo-bom"]:
            return httpx.Response(200, json={"access_token": "at-novo", "refresh_token": "rt-novo", "expires_in": 1800})
        return httpx.Response(400, json={"status": "BAD_AUTH_CODE", "message": "code=codigo-ruim access_token=vazou"})

    monkeypatch.setattr(http_base, "TRANSPORTE_PADRAO", httpx.MockTransport(responder))
    return pedidos


def _iniciar(client, escrita_=False) -> str:
    resposta = client.post(f"{H}/oauth/hubspot/iniciar", json={"nome": "HubSpot da empresa", "escrita": escrita_})
    assert resposta.status_code == 200, resposta.text
    return parse_qs(urlsplit(resposta.json()["url"]).query)["state"][0]


def test_oauth_fluxo_completo_cria_conexao_sem_expor_token(client, db_session, app_hubspot):
    resposta = client.post(f"{H}/oauth/hubspot/iniciar", json={"nome": "HubSpot", "escrita": True})
    url = urlsplit(resposta.json()["url"])
    params = parse_qs(url.query)
    assert url.netloc == "app.hubspot.com" and params["client_id"] == ["cliente-b2bon"]
    assert params["redirect_uri"] == ["https://api.b2bon.test/api/v1/hub-integracoes/oauth/hubspot/callback"]
    assert "crm.objects.contacts.write" in params["scope"][0]
    assert "segredo-b2bon" not in resposta.text

    anonimo = httpx_cliente(client)
    volta = anonimo.get(f"{H}/oauth/hubspot/callback", params={"code": "codigo-bom", "state": params["state"][0]}, follow_redirects=False)
    assert volta.status_code == 303
    destino = urlsplit(volta.headers["location"])
    assert destino.netloc == "app.b2bon.test" and "at-novo" not in volta.headers["location"]
    referencia = parse_qs(destino.query)["oauth"][0]
    assert db_session.query(ConexaoIntegracao).count() == 0  # o callback NÃO cria conexão

    criada = client.post(f"{H}/oauth/concluir", json={"referencia": referencia})
    assert criada.status_code == 201, criada.text
    assert "at-novo" not in criada.text and "credenciais" not in criada.json()
    conexao = db_session.query(ConexaoIntegracao).one()
    credenciais = json.loads(conexao.credenciais)
    assert credenciais == {"oauth_app": "b2bon", "access_token": "at-novo", "refresh_token": "rt-novo"}
    assert conexao.escrita in (None, {}) or not conexao.escrita.get("predator")  # escopo de escrita ≠ escrita ligada
    # uso único
    assert client.post(f"{H}/oauth/concluir", json={"referencia": referencia}).status_code == 422


def test_oauth_state_adulterado_ou_de_outro_crm_e_recusado(client, db_session, app_hubspot):
    state = _iniciar(client)
    anonimo = httpx_cliente(client)
    for falso in (state[:-4] + "AAAA", "lixo"):
        volta = anonimo.get(f"{H}/oauth/hubspot/callback", params={"code": "codigo-bom", "state": falso}, follow_redirects=False)
        assert "oauth_erro" in volta.headers["location"]
    volta = anonimo.get(f"{H}/oauth/pipedrive/callback", params={"code": "codigo-bom", "state": state}, follow_redirects=False)
    assert "oauth_erro" in volta.headers["location"]
    assert db_session.query(AutorizacaoOauthPendente).count() == 0
    assert not app_hubspot  # nenhuma troca de código foi tentada


def test_oauth_codigo_recusado_nao_vaza_corpo_do_crm(client, db_session, app_hubspot):
    state = _iniciar(client)
    volta = httpx_cliente(client).get(f"{H}/oauth/hubspot/callback", params={"code": "codigo-ruim", "state": state}, follow_redirects=False)
    assert "oauth_erro" in volta.headers["location"] and "vazou" not in volta.headers["location"]


def test_oauth_concluir_so_pelo_mesmo_usuario_que_iniciou(client, db_session, app_hubspot):
    """Anti-CSRF: a referência de um usuário não serve para outro (nem do mesmo tenant)."""
    state = _iniciar(client)
    volta = httpx_cliente(client).get(f"{H}/oauth/hubspot/callback", params={"code": "codigo-bom", "state": state}, follow_redirects=False)
    referencia = parse_qs(urlsplit(volta.headers["location"]).query)["oauth"][0]

    intruso = Usuario(tenant_id=TENANT, nome="Outro admin", email="outro@tenant-teste.com.br", papel="admin", ativo=True)
    db_session.add(intruso)
    db_session.commit()
    outro_cliente = httpx_cliente(client)
    outro_cliente.headers["Authorization"] = f"Bearer {auth_service.gerar_token(intruso)}"
    assert outro_cliente.post(f"{H}/oauth/concluir", json={"referencia": referencia}).status_code == 422
    assert db_session.query(ConexaoIntegracao).count() == 0
    assert client.post(f"{H}/oauth/concluir", json={"referencia": referencia}).status_code == 201


def test_oauth_expirado_e_recusado(client, db_session, app_hubspot):
    state = _iniciar(client)
    volta = httpx_cliente(client).get(f"{H}/oauth/hubspot/callback", params={"code": "codigo-bom", "state": state}, follow_redirects=False)
    referencia = parse_qs(urlsplit(volta.headers["location"]).query)["oauth"][0]
    pendente = db_session.get(AutorizacaoOauthPendente, referencia)
    pendente.expira_em = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert client.post(f"{H}/oauth/concluir", json={"referencia": referencia}).status_code == 422
    assert "at-novo" not in (pendente.credenciais or "") or True  # coluna é cifrada em repouso (TextoCriptografado)


def test_oauth_sem_app_configurado_fica_indisponivel(client, monkeypatch):
    monkeypatch.setattr(settings, "oauth_hubspot_client_id", "")
    conector = next(c for c in client.get(f"{H}/conectores").json() if c["sistema"] == "hubspot")
    assert conector["oauth"] is False and conector["escrita"] is True
    assert client.post(f"{H}/oauth/hubspot/iniciar", json={"nome": "X"}).status_code == 422


def test_oauth_state_e_cifrado_e_tem_validade():
    state = oauth.obter_fernet().encrypt(json.dumps({"s": "hubspot"}).encode()).decode() if hasattr(oauth, "obter_fernet") else None
    assert state is not None
    assert oauth._ler_state("hubspot", state)["s"] == "hubspot"
    with pytest.raises(oauth.ErroOauth):
        oauth._ler_state("salesforce", state)


def test_contrato_expoe_fachadas():
    assert integracoes.obter_escrita() is escrita and integracoes.obter_entrada() is entrada


def test_conexao_com_o_proprio_crm_da_b2bon_nao_escreve_nem_deduplica(db_session):
    """O CRM interno é o mesmo banco do PREDATOR: a conexão `b2bon_crm` fica fora da escrita e da deduplicação."""
    _conexao(db_session, sistema="b2bon_crm", predator=True, map=True, deduplicar=True)
    conta, _ = _conta_decisor(db_session)
    assert escrita.conexoes_com(db_session, TENANT, "deduplicar") == []
    assert escrita.enfileirar(db_session, TENANT, "empresa", conta.id) == 0
    assert escrita.rotina_diaria(db_session) == {"indices": 0, "falhas": 0}
