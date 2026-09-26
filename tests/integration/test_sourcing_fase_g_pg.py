"""Phase G em Postgres real: documento nativo (texto por página em JSON, arquivo
adiado), lado imutável nele, histórico do fornecedor (consulta com OR) e
prazo com fuso nos sinais. Roda quando `B2BON_TESTE_PG_URL` aponta para um
Postgres migrado."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, exc, text
from sqlalchemy.orm import sessionmaker

import app.contexts.procurement.contract  # noqa: F401
from app.contexts.procurement import estrategico, estrategico_ia
from app.models.usuario import Usuario

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


def test_documento_historico_e_sinais_no_postgres():
    engine = create_engine(URL)
    tenant = f"pg-g-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conexao:
        conexao.execute(text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant})
    Sessao = sessionmaker(bind=engine)
    try:
        with Sessao() as db:
            admin = Usuario(tenant_id=tenant, nome="Admin", email=f"{tenant}@x.com", papel="admin", ativo=True)
            db.add(admin)
            db.commit()
            antigo = estrategico.criar_processo(db, tenant, admin.id, {"tipo_processo": "RFP", "titulo": "Anterior"})
            estrategico.convidar(db, tenant, admin.id, antigo.id, {"nome": "Delta", "cnpj": "11222333000181"})

            prazo = datetime.now(UTC) - timedelta(hours=1)  # com fuso, já vencido
            rfp = estrategico.criar_processo(db, tenant, admin.id, {"tipo_processo": "RFP", "titulo": "Atual", "prazo": prazo})
            documento = estrategico_ia.enviar_documento(db, tenant, admin.id, rfp.id, "espec.txt", "text/plain",
                                                        "4.1 O fornecedor deverá operar 24x7.\fPágina dois.".encode())
            assert documento.paginas == 2 and documento.origem_id == documento.id
            documento_id = documento.id
            estrategico.adicionar_requisito(db, tenant, admin.id, rfp.id, {"categoria": "SLA", "texto": "Operação 24x7"})
            estrategico.convidar(db, tenant, admin.id, rfp.id, {"nome": "Delta S.A.", "cnpj": "11222333000181"})
            for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
                estrategico.mudar_status(db, tenant, admin.id, rfp.id, status)
            rfp_id = rfp.id
        with Sessao() as db:
            relido = estrategico_ia.obter_documento(db, tenant, documento_id)
            assert relido.paginas_texto == ["4.1 O fornecedor deverá operar 24x7.", "Página dois."]
            assert relido.conteudo.startswith(b"4.1")
            ws = estrategico.workspace(db, tenant, rfp_id)
            assert ws["participantes"][0]["historico"]["processos"] == 1  # mesmo CNPJ, nome diferente
            assert "PRAZO_ENCERRADO" in {a["tipo"] for a in ws["inteligencia"]["alertas"]}
            assert ws["inteligencia"]["proxima_acao"]["acao"] == "AVANCAR_AVALIACAO"
            with pytest.raises(exc.DBAPIError):
                db.execute(text("UPDATE documento_sourcing SET lado = 'SELL' WHERE tenant_id = :t"), {"t": tenant})
            db.rollback()
    finally:
        engine.dispose()
