"""S2: repositórios por lado — isolamento de tenant e de lado.

Mesmo tenant com os dois módulos: o repositório de venda nunca devolve
processo nem documento do comprador, e vice-versa (a barreira vale dentro
do tenant, não só entre tenants).
"""

import pytest

from app.contexts.bids import contract as bids
from app.contexts.procurement.repositorio import COMPRA
from app.models.documento_compras import DocumentoCompras
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.processo_contratacao import ProcessoContratacao
from app.services.errors import NaoEncontrado

A, B = "tenant-repo-a", "tenant-repo-b"


@pytest.fixture()
def dados(db_session):
    ids = {}
    for tenant in (A, B):
        lic = Licitacao(tenant_id=tenant, titulo=f"Venda {tenant}", objeto="x", modalidade="RFP", fonte="MANUAL", status="IDENTIFICADA")
        proc = ProcessoContratacao(tenant_id=tenant, orgao_id=1, objeto=f"Compra {tenant}", status="PLANEJAMENTO")
        db_session.add_all([lic, proc])
        db_session.flush()
        db_session.add_all([
            DocumentoLicitacao(tenant_id=tenant, licitacao_id=lic.id, tipo="EDITAL", nome_arquivo="e.txt", tipo_mime="text/plain",
                               tamanho_bytes=1, sha256=f"v{tenant}", conteudo=b"v", paginas_texto=["v"], paginas=1, fonte="UPLOAD",
                               status_analise="PENDENTE"),
            DocumentoCompras(tenant_id=tenant, processo_id=proc.id, tipo="ETP", nome_arquivo="c.txt", tipo_mime="text/plain",
                             tamanho_bytes=1, sha256=f"c{tenant}", conteudo=b"c", paginas_texto=["c"], paginas=1, fonte="UPLOAD",
                             classificacao="CONFIDENTIAL", achados=[], status_analise="PENDENTE"),
        ])
        ids[tenant] = (lic.id, proc.id)
    db_session.commit()
    return ids


def test_repositorio_de_venda_so_ve_a_venda_do_proprio_tenant(db_session, dados):
    venda = bids.repositorio.VENDA
    assert [p.titulo for p in venda.listar_processos(db_session, A).itens] == [f"Venda {A}"]
    with pytest.raises(NaoEncontrado):
        venda.obter_processo(db_session, A, dados[B][0])
    assert [d.tipo for d in venda.documentos(db_session, A, dados[A][0])] == ["EDITAL"]
    assert venda.documentos(db_session, A, dados[B][0]) == []
    assert venda.tipos_de_documento(db_session, A) == {dados[A][0]: {"EDITAL"}}  # nunca "ETP" do comprador


def test_repositorio_de_compra_so_ve_a_compra_do_proprio_tenant(db_session, dados):
    assert [p.objeto for p in COMPRA.listar_processos(db_session, A).itens] == [f"Compra {A}"]
    with pytest.raises(NaoEncontrado):
        COMPRA.obter_processo(db_session, A, dados[B][1])
    assert [d.tipo for d in COMPRA.documentos(db_session, A, dados[A][1])] == ["ETP"]
    assert COMPRA.tipos_de_documento(db_session, A) == {dados[A][1]: {"ETP"}}  # nunca "EDITAL" do vendedor


def test_leituras_de_fora_do_contexto_sao_so_do_lado_vendedor(db_session, dados):
    from datetime import UTC, datetime, timedelta

    agora = datetime.now(UTC).replace(tzinfo=None)
    venda = bids.repositorio.VENDA
    inicio, fim = agora - timedelta(days=1), agora + timedelta(days=1)
    assert venda.contar_processos(db_session, inicio, fim, A) == 1
    assert venda.contar_processos(db_session, inicio, fim) == 2  # total da plataforma: só contagem
    assert [p.tenant_id for p in venda.processos_criados(db_session, A, inicio, fim)] == [A]
    assert venda.contratos_vigentes(db_session, A) == [] and venda.decisoes_go_no_go(db_session, A, inicio, fim) == []
