from app.models.oferta import Oferta
from app.services import oferta_service
from app.services.errors import ValidacaoFalhou

TENANT_ID = "tenant-teste"


def _criar_oferta(db_session) -> Oferta:
    oferta = Oferta(tenant_id=TENANT_ID, nome="Oferta Teste", descricao="desc")
    db_session.add(oferta)
    db_session.commit()
    return oferta


def test_salvar_material_com_content_type_pdf_mentindo_e_rejeitado(db_session):
    """Fase 7A, hardening — o content-type é declarado pelo cliente;
    magic bytes reais precisam bater, não só o header."""
    oferta = _criar_oferta(db_session)

    try:
        oferta_service.salvar_material(
            db_session, TENANT_ID, None, oferta.id, "falso.pdf", "application/pdf", b"isto nao e um pdf de verdade"
        )
        assert False, "deveria ter levantado ValidacaoFalhou"
    except ValidacaoFalhou:
        pass


def test_salvar_material_pdf_real_e_aceito(db_session):
    oferta = _criar_oferta(db_session)

    material = oferta_service.salvar_material(
        db_session, TENANT_ID, None, oferta.id, "real.pdf", "application/pdf", b"%PDF-1.4 conteudo real"
    )

    assert material.tipo_mime == "application/pdf"


def test_salvar_material_docx_real_e_aceito(db_session):
    oferta = _criar_oferta(db_session)

    material = oferta_service.salvar_material(
        db_session,
        TENANT_ID,
        None,
        oferta.id,
        "real.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"PK\x03\x04conteudo real",
    )

    assert material.tipo_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_salvar_material_sanitiza_nome_de_arquivo_com_aspas(db_session):
    oferta = _criar_oferta(db_session)

    material = oferta_service.salvar_material(
        db_session, TENANT_ID, None, oferta.id, 'malicioso".pdf', "application/pdf", b"%PDF-1.4 x"
    )

    assert '"' not in material.nome_arquivo


def test_salvar_material_sanitiza_separador_de_path(db_session):
    oferta = _criar_oferta(db_session)

    material = oferta_service.salvar_material(
        db_session, TENANT_ID, None, oferta.id, "../../etc/passwd", "application/pdf", b"%PDF-1.4 x"
    )

    assert "/" not in material.nome_arquivo
    assert "\\" not in material.nome_arquivo
