"""Persistência do conteúdo das páginas (`conteudo_pagina_site`): limites no backend, higiene do texto, idempotência e concorrência."""

from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.predator import prospeccao
from app.models.conta import Conta
from app.models.conteudo_pagina_site import ConteudoPaginaSite
from app.models.tenant import Tenant

TENANT = "tenant-conteudo-paginas"
T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


@pytest.fixture()
def conta(db_session):
    db_session.add(Tenant(id=TENANT, razao_social="Conteúdo"))
    conta = Conta(tenant_id=TENANT, nome="Alpha", dominio="alpha.com.br", status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def _guardar(db, conta, paginas, quando=T0):
    prospeccao._guardar_paginas(db, TENANT, conta.id, paginas, quando)
    db.commit()


def _linhas(db, conta) -> dict[str, str]:
    db.expire_all()
    return {p.url: p.conteudo for p in db.query(ConteudoPaginaSite).filter_by(conta_id=conta.id)}


def test_nul_e_controle_sao_removidos_e_o_texto_e_cortado_no_tamanho_maximo(db_session, conta):
    sujo = "Olá\x00 mundo\x07\n\tlinha 2\x1b" + "x" * 9000
    _guardar(db_session, conta, [("https://alpha.com.br", sujo)])

    guardado = _linhas(db_session, conta)["https://alpha.com.br"]

    assert "\x00" not in guardado and "\x07" not in guardado and "\x1b" not in guardado
    assert guardado.startswith("Olá mundo\n\tlinha 2") and len(guardado) == prospeccao.MAX_CHARS_CONTEUDO_GUARDADO


def test_pagina_vazia_ou_so_de_controle_nao_e_gravada_nem_apaga_o_conteudo_bom(db_session, conta):
    _guardar(db_session, conta, [("https://alpha.com.br", "conteúdo bom")])

    _guardar(db_session, conta, [("https://alpha.com.br", "\x00\x00 "), ("https://alpha.com.br/vazia", "")], T0 + timedelta(hours=1))

    assert _linhas(db_session, conta) == {"https://alpha.com.br": "conteúdo bom"}


def test_nova_coleta_substitui_e_repetir_a_mesma_coleta_nao_duplica(db_session, conta):
    _guardar(db_session, conta, [("https://alpha.com.br", "v1")])
    _guardar(db_session, conta, [("https://alpha.com.br", "v1")], T0 + timedelta(minutes=1))
    assert _linhas(db_session, conta) == {"https://alpha.com.br": "v1"}

    _guardar(db_session, conta, [("https://alpha.com.br", "v2")], T0 + timedelta(minutes=2))
    assert _linhas(db_session, conta) == {"https://alpha.com.br": "v2"}


def test_coleta_antiga_que_termina_depois_nao_sobrescreve_a_mais_nova(db_session, conta):
    _guardar(db_session, conta, [("https://alpha.com.br", "coleta nova")], T0 + timedelta(minutes=5))

    _guardar(db_session, conta, [("https://alpha.com.br", "coleta antiga, terminou depois")], T0)  # iniciada antes, gravada depois

    assert _linhas(db_session, conta) == {"https://alpha.com.br": "coleta nova"}


def test_limite_de_oito_paginas_por_conta_vale_na_gravacao_e_poda_as_mais_antigas(db_session, conta):
    antigas = [(f"https://alpha.com.br/a{i}", f"antiga {i}") for i in range(8)]
    novas = [(f"https://alpha.com.br/n{i}", f"nova {i}") for i in range(8)]
    _guardar(db_session, conta, antigas, T0)
    _guardar(db_session, conta, novas, T0 + timedelta(hours=1))  # o site mudou de estrutura: 8 URLs diferentes

    linhas = _linhas(db_session, conta)

    assert len(linhas) == 8 and set(linhas.values()) == {f"nova {i}" for i in range(8)}


def test_mais_de_oito_paginas_numa_unica_coleta_guarda_so_as_oito_primeiras(db_session, conta):
    _guardar(db_session, conta, [(f"https://alpha.com.br/p{i}", f"p{i}") for i in range(12)])
    assert sorted(_linhas(db_session, conta)) == sorted(f"https://alpha.com.br/p{i}" for i in range(8))


def test_insercao_concorrente_da_mesma_url_nao_vira_erro_nem_duplica(db_session, conta, monkeypatch):
    """A segunda coleta não enxerga a linha que a primeira acabou de inserir (snapshot antigo): a restrição única segura e vira atualização."""
    db_session.add(ConteudoPaginaSite(tenant_id=TENANT, conta_id=conta.id, url="https://alpha.com.br", conteudo="da outra coleta",
                                      coletado_em=(T0 + timedelta(minutes=1)).replace(tzinfo=None)))
    db_session.commit()
    monkeypatch.setattr(prospeccao, "_consultar_paginas_guardadas", lambda db, conta_id: {})

    _guardar(db_session, conta, [("https://alpha.com.br", "desta coleta, mais antiga")], T0)  # mais antiga: não sobrescreve
    assert _linhas(db_session, conta) == {"https://alpha.com.br": "da outra coleta"}

    _guardar(db_session, conta, [("https://alpha.com.br", "desta coleta, mais nova")], T0 + timedelta(minutes=9))
    assert _linhas(db_session, conta) == {"https://alpha.com.br": "desta coleta, mais nova"}
    assert db_session.query(ConteudoPaginaSite).filter_by(conta_id=conta.id).count() == 1


def test_tenant_do_conteudo_e_o_da_conta(db_session, conta):
    _guardar(db_session, conta, [("https://alpha.com.br", "x")])
    assert {p.tenant_id for p in db_session.query(ConteudoPaginaSite).filter_by(conta_id=conta.id)} == {TENANT}
