"""Sourcing S3 (expand): tabelas unificadas, espelho, backfill e leitura dupla.

As tabelas antigas continuam a fonte da verdade. Aqui se prova que:
- toda escrita antiga chega às tabelas novas (espelho) com o lado certo;
- o backfill é idempotente, completa o que faltou e remove órfãos;
- a leitura dupla detecta divergência (ESTRITA = erro, COMPARAR = log);
- o lado nunca muda e nunca liga filha de um lado a pai do outro;
- falha de espelho não derruba a escrita do usuário (fora do modo ESTRITO).
"""

import logging

import pytest
from sqlalchemy import text

from app.contexts.bids import contract as bids
from app.contexts.procurement.repositorio import COMPRA
from app.contexts.sourcing import contract as sourcing
from app.core.config import settings
from app.models.documento_compras import DocumentoCompras
from app.models.licitacao import Licitacao
from app.models.processo_contratacao import ProcessoContratacao
from app.models.sourcing import DocumentoSourcing, LadoImutavel, ProcessoSourcing, RequisitoSourcing

TENANT = "tenant-teste"
B, P = "/api/v1/bids", "/api/v1/procurement"


def _venda(client) -> dict:
    lic = client.post(f"{B}/licitacoes", json={"titulo": "Edital S3", "objeto": "Notebooks", "modalidade": "PUBLIC_TENDER",
                                                "orgao_nome": "Prefeitura", "valor_estimado": 1234.567}).json()
    client.post(f"{B}/licitacoes/{lic['id']}/documentos", data={"tipo": "EDITAL"},
                files={"arquivo": ("e.txt", b"5.1 Apresentar certidao negativa.", "text/plain")})
    client.post(f"{B}/licitacoes/{lic['id']}/requisitos", json={"categoria": "HABILITACAO", "descricao": "Certidão negativa"})
    return lic


def _compra(client, db) -> dict:
    orgao = client.post(f"{P}/orgaos", json={"nome": "Prefeitura"}).json()
    proc = client.post(f"{P}/processos", json={"orgao_id": orgao["id"], "objeto": "Limpeza predial", "valor_estimado": 90000}).json()
    client.post(f"{P}/documentos", data={"tipo": "ETP", "processo_id": str(proc["id"])},
                files={"arquivo": ("etp.txt", b"Estudo tecnico preliminar.", "text/plain")})
    doc = db.query(DocumentoCompras).filter_by(processo_id=proc["id"]).one()
    doc.achados = [{"categoria": "PRAZO", "descricao": "Prazo de 30 dias", "evidencia": "30 dias", "pagina": 1, "status": "sugerido"}]
    db.commit()
    return proc


def test_escrita_antiga_chega_as_tabelas_novas_com_o_lado_certo(client, db_session):
    lic = _venda(client)
    proc = _compra(client, db_session)
    venda = db_session.query(ProcessoSourcing).filter_by(origem_tabela="licitacao", origem_id=lic["id"]).one()
    compra = db_session.query(ProcessoSourcing).filter_by(origem_tabela="processo_contratacao", origem_id=proc["id"]).one()
    assert (venda.lado, venda.segmento, venda.workflow, venda.classificacao, float(venda.valor_estimado)) == (
        "SELL", "PUBLIC", "PUBLIC_TENDER_SELL@1", "INTERNAL", 1234.57)
    assert (compra.lado, compra.ruleset, compra.classificacao) == ("BUY", "PUBLIC_PROCUREMENT_BR_14133@1", "CONFIDENTIAL")
    assert {d.lado for d in db_session.query(DocumentoSourcing)} == {"SELL", "BUY"}
    achado = db_session.query(RequisitoSourcing).filter_by(origem_tabela="documento_compras.achados").one()
    assert (achado.lado, achado.texto, achado.confianca, achado.processo_id) == ("BUY", "Prazo de 30 dias", "grounded", compra.id)
    # leitura pela API (repositórios em modo ESTRITO): bate
    assert client.get(f"{B}/licitacoes/{lic['id']}/workspace").status_code == 200
    assert client.get(f"{P}/processos/{proc['id']}/workspace").status_code == 200


def test_rfp_privado_vira_segmento_enterprise(client, db_session):
    lic = client.post(f"{B}/licitacoes", json={"titulo": "RFP ACME", "modalidade": "PRIVATE_RFP"}).json()
    novo = db_session.query(ProcessoSourcing).filter_by(origem_tabela="licitacao", origem_id=lic["id"]).one()
    assert (novo.segmento, novo.tipo_processo, novo.workflow, novo.ruleset) == (
        "ENTERPRISE", "RFP", "ENTERPRISE_RFP_SELL@2", "PRIVATE_RFP@1")


def test_leitura_dupla_detecta_divergencia(client, db_session, monkeypatch, caplog):
    lic = _venda(client)
    db_session.execute(text("UPDATE processo_sourcing SET titulo = 'adulterado' WHERE origem_tabela = 'licitacao'"))
    db_session.commit()
    with pytest.raises(sourcing.paridade.DivergenciaSourcing, match="titulo"):
        bids.repositorio.VENDA.obter_processo(db_session, TENANT, lic["id"])

    monkeypatch.setattr(settings, "sourcing_leitura_dupla", "COMPARAR")
    with caplog.at_level(logging.WARNING, logger="b2bon.sourcing"):
        assert bids.repositorio.VENDA.obter_processo(db_session, TENANT, lic["id"]).titulo == "Edital S3"  # fonte: a antiga
    assert "SOURCING_DIVERGENCIA" in caplog.text

    monkeypatch.setattr(settings, "sourcing_leitura_dupla", "DESLIGADA")
    caplog.clear()
    bids.repositorio.VENDA.obter_processo(db_session, TENANT, lic["id"])
    assert "SOURCING_DIVERGENCIA" not in caplog.text


def test_backfill_completa_e_idempotente_e_remove_orfaos(client, db_session):
    lic = _venda(client)
    proc = _compra(client, db_session)
    for tabela in ("requisito_sourcing", "documento_sourcing", "evento_sourcing", "contrato_sourcing", "processo_sourcing"):
        db_session.execute(text(f"DELETE FROM {tabela}"))  # como se os dados fossem anteriores à S3
    db_session.execute(text(
        "INSERT INTO processo_sourcing (tenant_id, lado, segmento, tipo_processo, titulo, status, visibilidade, classificacao, "
        "workflow, moeda, valor_sigiloso, fonte, origem_tabela, origem_id) VALUES "
        "('tenant-teste', 'SELL', 'PUBLIC', 'RFP', 'órfão', 'X', 'PRIVADO', 'INTERNAL', 'W', 'BRL', 0, 'MANUAL', 'licitacao', 999999)"))
    db_session.commit()

    primeiro = sourcing.espelho.sincronizar_todos(db_session)
    segundo = sourcing.espelho.sincronizar_todos(db_session)
    assert primeiro["SELL"]["licitacao"] == {"espelhados": 1, "orfaos_removidos": 1}
    assert segundo["SELL"]["licitacao"] == {"espelhados": 1, "orfaos_removidos": 0}
    assert primeiro["BUY"]["processo_contratacao"]["espelhados"] == 1
    assert db_session.query(ProcessoSourcing).count() == 2 and db_session.query(RequisitoSourcing).count() == 2
    # leitura dupla estrita passa depois do backfill
    bids.repositorio.VENDA.requisitos(db_session, TENANT, lic["id"])
    COMPRA.documentos(db_session, TENANT, proc["id"])
    assert bids.repositorio.VENDA.tipos_de_documento(db_session, TENANT) == {lic["id"]: {"EDITAL"}}


def test_backfill_pelo_cron(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "cron-s3")
    _venda(client)
    resposta = client.post("/api/v1/cron/sourcing-sincronizar", headers={"X-Cron-Secret": "cron-s3"})
    assert resposta.status_code == 200 and resposta.json()["SELL"]["licitacao"]["espelhados"] == 1
    assert client.post("/api/v1/cron/sourcing-sincronizar").status_code == 403


def test_lado_nunca_muda_nem_mistura(client, db_session):
    lic = _venda(client)
    proc = _compra(client, db_session)
    novo = db_session.query(ProcessoSourcing).filter_by(origem_tabela="licitacao", origem_id=lic["id"]).one()
    novo.lado = "BUY"
    with pytest.raises(LadoImutavel):
        db_session.commit()
    db_session.rollback()
    with pytest.raises(Exception, match="nao pode mudar"):
        db_session.execute(text("UPDATE processo_sourcing SET lado = 'BUY' WHERE origem_tabela = 'licitacao'"))
    db_session.rollback()
    with pytest.raises(sourcing.espelho.EspelhoInconsistente):  # filha de venda apontando para processo de compra
        sourcing.espelho.gravar(db_session.connection(), "documento", sourcing.tipos.Lado.VENDA, "documento_licitacao", 424242,
                                {"tenant_id": TENANT, "processo_origem": ("processo_contratacao", proc["id"])})
    db_session.rollback()
    assert sourcing.paridade.tipos_de_documento(db_session, sourcing.tipos.Lado.VENDA, TENANT, "processo_contratacao") == {}


def test_falha_de_espelho_nao_derruba_a_escrita(client, db_session, monkeypatch, caplog):
    monkeypatch.setattr(settings, "sourcing_leitura_dupla", "COMPARAR")

    def quebra(*args, **kwargs):
        raise RuntimeError("banco novo fora")

    monkeypatch.setattr(sourcing.espelho, "gravar", quebra)
    with caplog.at_level(logging.ERROR, logger="b2bon.sourcing"):
        resposta = client.post(f"{B}/licitacoes", json={"titulo": "Mesmo assim"})
    assert resposta.status_code == 201
    assert db_session.query(Licitacao).filter_by(titulo="Mesmo assim").count() == 1
    assert "SOURCING_ESPELHO_FALHOU" in caplog.text
    monkeypatch.undo()
    monkeypatch.setattr(settings, "sourcing_leitura_dupla", "COMPARAR")
    assert sourcing.espelho.sincronizar_todos(db_session)["SELL"]["licitacao"]["espelhados"] == 1  # o backfill corrige


def test_processo_apagado_leva_as_filhas_nas_tabelas_novas(client, db_session):
    proc = _compra(client, db_session)
    db_session.query(DocumentoCompras).filter_by(processo_id=proc["id"]).delete(synchronize_session=False)  # sem evento
    db_session.commit()
    sourcing.espelho.sincronizar_todos(db_session)  # a rede de segurança remove o órfão
    assert db_session.query(DocumentoSourcing).filter_by(lado="BUY").count() == 0
    assert db_session.query(RequisitoSourcing).filter_by(lado="BUY").count() == 0
    processo = db_session.get(ProcessoContratacao, proc["id"])
    db_session.delete(processo)
    db_session.commit()
    assert db_session.query(ProcessoSourcing).filter_by(lado="BUY").count() == 0


def test_leitura_dupla_nao_faz_uma_consulta_por_requisito(client, db_session):
    """COMPARAR em produção: conferir 40 requisitos custa poucas consultas fixas, não uma por linha."""
    from sqlalchemy import event

    lic = _venda(client)
    for i in range(40):
        client.post(f"{B}/licitacoes/{lic['id']}/requisitos", json={"categoria": "HABILITACAO", "descricao": f"Requisito {i}"})
    consultas: list[str] = []
    motor = db_session.get_bind()
    contar = lambda *args: consultas.append(args[2])  # noqa: E731
    event.listen(motor, "before_cursor_execute", contar)
    try:
        assert len(bids.repositorio.VENDA.requisitos(db_session, TENANT, lic["id"])) == 41
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    assert len(consultas) <= 5, f"{len(consultas)} consultas para 41 requisitos"
