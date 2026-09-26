"""Fase S0 (plano de sourcing): performance sem mudança de schema.

- Listas de licitações e de cadastros do comprador paginadas por cursor
  (keyset), sem perder nem repetir linha.
- Nenhuma leitura de lista, workspace ou sinal de risco carrega o arquivo
  binário ou o texto das páginas do documento.
- Sinais de risco não fazem uma consulta por processo.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import event

from app.models.documento_compras import DocumentoCompras
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.processo_contratacao import ProcessoContratacao

TENANT = "tenant-teste"


class _Sql:
    """Conta as consultas e guarda o SQL de cada uma."""

    def __init__(self, engine) -> None:
        self.consultas: list[str] = []
        self._engine = engine

    def __enter__(self):
        event.listen(self._engine, "before_cursor_execute", self._guardar)
        return self

    def __exit__(self, *exc):
        event.remove(self._engine, "before_cursor_execute", self._guardar)

    def _guardar(self, conn, cursor, sql, *args):
        self.consultas.append(sql)

    def leu_conteudo(self, tabela: str) -> bool:
        return any(f"{tabela}.conteudo" in sql or f"{tabela}.paginas_texto" in sql for sql in self.consultas)


def _todas_as_paginas(client, url: str, limite: int) -> list[dict]:
    itens, cursor = [], None
    while True:
        resposta = client.get(url, params={"limite": limite, **({"cursor": cursor} if cursor else {})})
        assert resposta.status_code == 200, resposta.text
        itens.extend(resposta.json())
        cursor = resposta.headers.get("X-Proximo-Cursor")
        if not cursor:
            return itens


def test_licitacoes_paginadas_por_cursor_na_ordem_de_prazo(client, db_session):
    base = datetime(2027, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    prazos = [base + timedelta(days=d) for d in (3, 1, 1, 2)] + [None, None, None]
    for i, prazo in enumerate(prazos):
        db_session.add(Licitacao(tenant_id=TENANT, titulo=f"L{i}", objeto="x", modalidade="PUBLIC_TENDER", fonte="MANUAL",
                                 status="IDENTIFICADA", prazo_proposta=prazo))
    db_session.add(Licitacao(tenant_id="outro-tenant", titulo="alheia", objeto="x", modalidade="PUBLIC_TENDER", fonte="MANUAL",
                             status="IDENTIFICADA"))
    db_session.commit()

    completa = client.get("/api/v1/bids/licitacoes").json()
    assert "X-Proximo-Cursor" not in client.get("/api/v1/bids/licitacoes").headers
    paginada = _todas_as_paginas(client, "/api/v1/bids/licitacoes", limite=2)
    assert [item["id"] for item in paginada] == [item["id"] for item in completa]
    assert len(paginada) == 7 and all(item["titulo"] != "alheia" for item in paginada)
    datas = [item["prazo_proposta"] for item in paginada]
    assert datas[4:] == [None, None, None] and datas[:4] == sorted(datas[:4])


def test_cadastros_do_comprador_paginados_e_limite_validado(client):
    for i in range(5):
        assert client.post("/api/v1/procurement/orgaos", json={"nome": f"Órgão {i}"}).status_code == 201
    primeira = client.get("/api/v1/procurement/orgaos", params={"limite": 2})
    assert len(primeira.json()) == 2 and primeira.headers.get("X-Proximo-Cursor")
    assert [o["nome"] for o in _todas_as_paginas(client, "/api/v1/procurement/orgaos", 2)] == [f"Órgão {i}" for i in range(5)]
    assert client.get("/api/v1/procurement/orgaos", params={"limite": 0}).status_code == 422
    assert client.get("/api/v1/procurement/orgaos", params={"limite": 501}).status_code == 422
    assert client.get("/api/v1/procurement/orgaos", params={"cursor": "nao-e-cursor"}).status_code == 422


def test_workspace_da_licitacao_nao_carrega_o_arquivo(client, db_session):
    licitacao = client.post("/api/v1/bids/licitacoes", json={"titulo": "Edital", "objeto": "software"}).json()
    for i in range(3):
        client.post(f"/api/v1/bids/licitacoes/{licitacao['id']}/documentos", data={"tipo": "ANEXO"},
                    files={"arquivo": (f"a{i}.txt", f"Anexo {i}: conteúdo grande do anexo.".encode(), "text/plain")})
    with _Sql(db_session.get_bind()) as sql:
        assert client.get(f"/api/v1/bids/licitacoes/{licitacao['id']}/workspace").status_code == 200
    assert not sql.leu_conteudo(DocumentoLicitacao.__tablename__)
    documento = db_session.query(DocumentoLicitacao).filter_by(licitacao_id=licitacao["id"]).first()
    assert client.get(f"/api/v1/bids/documentos/{documento.id}/arquivo").content.startswith(b"Anexo")  # download continua


def test_sinais_de_risco_sem_n_mais_1_e_sem_arquivo(client, db_session):
    orgao = client.post("/api/v1/procurement/orgaos", json={"nome": "Prefeitura"}).json()
    for i in range(12):
        processo = client.post("/api/v1/procurement/processos", json={"orgao_id": orgao["id"], "objeto": f"Objeto distinto {i}"}).json()
        db_session.query(ProcessoContratacao).filter_by(id=processo["id"]).update({"status": "APROVACAO"})
        client.post("/api/v1/procurement/documentos", data={"tipo": "ETP", "processo_id": str(processo["id"])},
                    files={"arquivo": (f"etp{i}.txt", f"ETP do processo {i}.".encode(), "text/plain")})
    db_session.commit()
    with _Sql(db_session.get_bind()) as sql:
        resposta = client.get("/api/v1/procurement/riscos")
    assert resposta.status_code == 200
    faltando = [s for s in resposta.json()["sinais"] if s["tipo"] == "MISSING_DOCUMENTATION"]
    assert len(faltando) == 12  # APROVACAO espera ETP, TR e pesquisa de preço: só ETP presente
    documentos = [q for q in sql.consultas if "documento_compras" in q]
    assert len(documentos) == 1, f"{len(documentos)} consultas de documento para 12 processos"
    assert not sql.leu_conteudo(DocumentoCompras.__tablename__)
