"""Verificação de e-mail pelo domínio: o que descarta com certeza, o que nunca descarta e o que nunca confirma."""

import dns.exception
import dns.resolver
import pytest

from app.providers.email_validation import dominio as m
from app.providers.email_validation.dominio import DominioEmailVerificationProvider


def _verificador(respostas: dict[str, str], chamadas: list[str] | None = None, relogio=None) -> DominioEmailVerificationProvider:
    def consulta(dominio: str) -> str:
        if chamadas is not None:
            chamadas.append(dominio)
        return respostas[dominio]

    return DominioEmailVerificationProvider(consulta, relogio=relogio or (lambda: 0.0))


@pytest.mark.parametrize("email", [None, "", "semarroba", "a@b", "a b@c.com"])
def test_sintaxe_invalida_e_descartada_sem_consultar_dns(email):
    chamadas: list[str] = []
    resultado = _verificador({}, chamadas).classificar(email)

    assert resultado.estado == m.SINTAXE_INVALIDA and resultado.descarta and chamadas == []


def test_dominio_descartavel_e_descartado_sem_consultar_dns():
    chamadas: list[str] = []
    resultado = _verificador({}, chamadas).classificar("alguem@Mailinator.com")

    assert resultado.estado == m.DESCARTAVEL and resultado.descarta and chamadas == []


@pytest.mark.parametrize(
    ("resposta", "estado"),
    [(m.INEXISTENTE, m.DOMINIO_INEXISTENTE), (m.SEM_REGISTRO, m.SEM_SERVIDOR_DE_EMAIL)],
)
def test_dominio_sem_como_receber_e_mail_e_descartado(resposta, estado):
    resultado = _verificador({"empresa.com.br": resposta}).classificar("ana@empresa.com.br")

    assert resultado.estado == estado and resultado.descarta and resultado.motivo


@pytest.mark.parametrize("resposta", [m.TEM_MX, m.TEM_ENDERECO])
def test_dominio_que_recebe_e_mail_e_valido_mas_nunca_confirmado(resposta):
    resultado = _verificador({"empresa.com.br": resposta}).classificar("ana@empresa.com.br")

    assert resultado.estado == m.DOMINIO_VALIDO and not resultado.descarta
    assert not hasattr(m, "CONFIRMADO")  # não existe estado "confirmado": a caixa não é checada


def test_falha_de_dns_e_indeterminada_e_nao_descarta_nem_fica_guardada():
    chamadas: list[str] = []
    verificador = _verificador({"empresa.com.br": m.FALHA_DE_DNS}, chamadas)

    primeiro = verificador.classificar("ana@empresa.com.br")
    segundo = verificador.classificar("ana@empresa.com.br")

    assert primeiro.estado == m.INDETERMINADO and not primeiro.descarta
    assert segundo.estado == m.INDETERMINADO and len(chamadas) == 2  # falha não é lembrada


def test_resposta_valida_e_reaproveitada_ate_vencer():
    chamadas: list[str] = []
    agora = [0.0]
    verificador = _verificador({"empresa.com.br": m.TEM_MX}, chamadas, relogio=lambda: agora[0])

    verificador.classificar("ana@empresa.com.br")
    verificador.classificar("bia@empresa.com.br")
    assert chamadas == ["empresa.com.br"]

    agora[0] = 7 * 3600
    verificador.classificar("cris@empresa.com.br")
    assert chamadas == ["empresa.com.br", "empresa.com.br"]


def test_verificar_so_reprova_o_que_e_certo():
    verificador = _verificador({"ok.com": m.TEM_MX, "morto.com": m.INEXISTENTE, "nuvem.com": m.FALHA_DE_DNS})

    assert verificador.verificar("a@ok.com").valido is True
    assert verificador.verificar("a@nuvem.com").valido is True  # indeterminado não reprova
    reprovado = verificador.verificar("a@morto.com")
    assert reprovado.valido is False and "inexistente" in reprovado.motivo


class _Registro:
    def __init__(self, exchange: str) -> None:
        self.exchange = exchange


def _resolvedor_falso(monkeypatch, respostas: dict[tuple[str, str], object]) -> None:
    """Troca o `Resolver` do dnspython: cada (domínio, tipo) devolve uma lista ou levanta a exceção indicada."""

    class Falso:
        timeout = lifetime = None

        def resolve(self, dominio, tipo):
            resposta = respostas.get((dominio, tipo), dns.resolver.NoAnswer())
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

    monkeypatch.setattr(dns.resolver, "Resolver", Falso)


def test_consulta_real_com_mx(monkeypatch):
    _resolvedor_falso(monkeypatch, {("empresa.com", "MX"): [_Registro("mx.empresa.com.")]})
    assert m.consultar_dns("empresa.com") == m.TEM_MX


def test_consulta_real_mx_nulo_recusa_e_mail(monkeypatch):
    _resolvedor_falso(monkeypatch, {("empresa.com", "MX"): [_Registro(".")]})
    assert m.consultar_dns("empresa.com") == m.SEM_REGISTRO


def test_consulta_real_sem_mx_usa_o_endereco(monkeypatch):
    _resolvedor_falso(monkeypatch, {("empresa.com", "A"): ["1.2.3.4"]})
    assert m.consultar_dns("empresa.com") == m.TEM_ENDERECO


def test_consulta_real_sem_mx_nem_endereco(monkeypatch):
    _resolvedor_falso(monkeypatch, {})
    assert m.consultar_dns("empresa.com") == m.SEM_REGISTRO


def test_consulta_real_nxdomain(monkeypatch):
    _resolvedor_falso(monkeypatch, {("empresa.com", "MX"): dns.resolver.NXDOMAIN()})
    assert m.consultar_dns("empresa.com") == m.INEXISTENTE


@pytest.mark.parametrize("erro", [dns.exception.Timeout(), dns.resolver.NoNameservers(), RuntimeError("rede")])
def test_consulta_real_com_falha_nunca_vira_invalido(monkeypatch, erro):
    _resolvedor_falso(monkeypatch, {("empresa.com", "MX"): erro})
    assert m.consultar_dns("empresa.com") == m.FALHA_DE_DNS
