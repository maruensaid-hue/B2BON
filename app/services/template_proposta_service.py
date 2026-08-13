from io import BytesIO

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.negocio import Negocio
from app.models.template_proposta import ItemTemplateProposta, TemplateProposta
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TIPOS_LOGO_PERMITIDOS = {"image/png", "image/jpeg"}
TAMANHO_MAXIMO_LOGO_BYTES = 2 * 1024 * 1024


def _texto_seguro(texto: str) -> str:
    """A fonte core "Helvetica" do fpdf2 só suporta Latin-1/cp1252 — texto
    digitado ou colado pelo vendedor (Word, WhatsApp) frequentemente traz
    aspas curvas, travessão longo, reticências etc. fora desse alcance, o
    que derruba a geração inteira com `FPDFUnicodeEncodingException`. Troca
    o que não é suportado por "?" em vez de deixar a exceção estourar."""
    return texto.encode("latin-1", errors="replace").decode("latin-1")


def obter_ou_criar(db: Session, tenant_id: str) -> TemplateProposta:
    template = db.query(TemplateProposta).filter_by(tenant_id=tenant_id).one_or_none()
    if template is None:
        template = TemplateProposta(tenant_id=tenant_id)
        db.add(template)
        db.commit()
        db.refresh(template)
    return template


def atualizar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    texto_introdutorio: str | None,
    termo_aceite: str | None,
    mostrar_tabela_produtos: bool,
    mostrar_tabela_servicos: bool,
) -> TemplateProposta:
    template = obter_ou_criar(db, tenant_id)
    template.texto_introdutorio = texto_introdutorio
    template.termo_aceite = termo_aceite
    template.mostrar_tabela_produtos = mostrar_tabela_produtos
    template.mostrar_tabela_servicos = mostrar_tabela_servicos

    auditoria_service.registrar(db, tenant_id, "template_proposta_atualizado", "template_proposta", template.id, ator_id, {})
    db.commit()
    db.refresh(template)
    return template


def salvar_logo(db: Session, tenant_id: str, ator_id: str | None, conteudo: bytes, tipo_mime: str) -> TemplateProposta:
    if tipo_mime not in TIPOS_LOGO_PERMITIDOS:
        raise ValidacaoFalhou(f"Tipo de arquivo não suportado: {tipo_mime}. Envie PNG ou JPEG.")
    if len(conteudo) > TAMANHO_MAXIMO_LOGO_BYTES:
        limite_mb = TAMANHO_MAXIMO_LOGO_BYTES // (1024 * 1024)
        raise ValidacaoFalhou(f"Logo maior que o limite de {limite_mb}MB.")

    template = obter_ou_criar(db, tenant_id)
    template.logo_conteudo = conteudo
    template.logo_tipo_mime = tipo_mime

    auditoria_service.registrar(db, tenant_id, "template_proposta_logo_atualizada", "template_proposta", template.id, ator_id, {})
    db.commit()
    db.refresh(template)
    return template


def listar_itens(db: Session, tenant_id: str, tipo: str | None = None) -> list[ItemTemplateProposta]:
    template = obter_ou_criar(db, tenant_id)
    query = db.query(ItemTemplateProposta).filter_by(tenant_id=tenant_id, template_id=template.id)
    if tipo is not None:
        query = query.filter_by(tipo=tipo)
    return query.order_by(ItemTemplateProposta.ordem).all()


def adicionar_item(db: Session, tenant_id: str, ator_id: str | None, tipo: str, descricao: str, valor: float | None) -> ItemTemplateProposta:
    if tipo not in {"produto", "servico"}:
        raise ValidacaoFalhou("Tipo do item precisa ser 'produto' ou 'servico'.")
    template = obter_ou_criar(db, tenant_id)
    maior_ordem = (
        db.query(ItemTemplateProposta.ordem)
        .filter_by(tenant_id=tenant_id, template_id=template.id, tipo=tipo)
        .order_by(ItemTemplateProposta.ordem.desc())
        .first()
    )
    item = ItemTemplateProposta(
        tenant_id=tenant_id,
        template_id=template.id,
        tipo=tipo,
        ordem=(maior_ordem[0] + 1) if maior_ordem else 0,
        descricao=descricao,
        valor=valor,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _obter_item(db: Session, tenant_id: str, item_id: int) -> ItemTemplateProposta:
    item = db.query(ItemTemplateProposta).filter_by(id=item_id, tenant_id=tenant_id).one_or_none()
    if item is None:
        raise NaoEncontrado(f"Item {item_id} não encontrado")
    return item


def atualizar_item(db: Session, tenant_id: str, item_id: int, descricao: str, valor: float | None) -> ItemTemplateProposta:
    item = _obter_item(db, tenant_id, item_id)
    item.descricao = descricao
    item.valor = valor
    db.commit()
    db.refresh(item)
    return item


def remover_item(db: Session, tenant_id: str, item_id: int) -> None:
    item = _obter_item(db, tenant_id, item_id)
    db.delete(item)
    db.commit()


def _obter_negocio(db: Session, tenant_id: str, negocio_id: int) -> Negocio:
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")
    return negocio


def gerar_pdf(
    db: Session,
    tenant_id: str,
    negocio_id: int,
    itens_produtos: list[dict],
    itens_servicos: list[dict],
    texto_introdutorio: str | None = None,
    termo_aceite: str | None = None,
    mostrar_tabela_produtos: bool | None = None,
    mostrar_tabela_servicos: bool | None = None,
) -> bytes:
    """Monta o PDF da proposta a partir do modelo salvo (logo sempre do
    template) — texto introdutório, termo de aceite e os toggles de tabela
    usam o valor passado por parâmetro quando informado (`None` cai no
    valor salvo no modelo), assim como os itens de produtos/serviços.
    Nada disso grava de volta no modelo — vale só para esta proposta."""
    template = obter_ou_criar(db, tenant_id)
    negocio = _obter_negocio(db, tenant_id, negocio_id)
    conta = db.query(Conta).filter_by(id=negocio.conta_id, tenant_id=tenant_id).one_or_none()

    texto_final = texto_introdutorio if texto_introdutorio is not None else template.texto_introdutorio
    termo_final = termo_aceite if termo_aceite is not None else template.termo_aceite
    mostrar_produtos_final = (
        mostrar_tabela_produtos if mostrar_tabela_produtos is not None else template.mostrar_tabela_produtos
    )
    mostrar_servicos_final = (
        mostrar_tabela_servicos if mostrar_tabela_servicos is not None else template.mostrar_tabela_servicos
    )

    pdf = FPDF()
    pdf.add_page()

    if template.logo_conteudo:
        pdf.image(BytesIO(template.logo_conteudo), w=40)
        pdf.ln(4)

    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 10, text="Proposta Comercial", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    nome_cliente = (conta.nome_fantasia or conta.nome) if conta else negocio.conta_id
    pdf.cell(0, 8, text=_texto_seguro(f"Cliente: {nome_cliente}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, text=_texto_seguro(f"Oportunidade: {negocio.nome} - R${negocio.valor:,.2f}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    if texto_final:
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, text=_texto_seguro(texto_final))
        pdf.ln(4)

    if mostrar_produtos_final and itens_produtos:
        pdf.set_font("Helvetica", size=13)
        pdf.cell(0, 8, text="Produtos", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        for item in itens_produtos:
            valor = item.get("valor")
            linha = f"- {item.get('descricao', '')}" + (f" - R${valor:,.2f}" if valor is not None else "")
            pdf.cell(0, 7, text=_texto_seguro(linha), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    if mostrar_servicos_final and itens_servicos:
        pdf.set_font("Helvetica", size=13)
        pdf.cell(0, 8, text="Serviços", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        for item in itens_servicos:
            valor = item.get("valor")
            linha = f"- {item.get('descricao', '')}" + (f" - R${valor:,.2f}" if valor is not None else "")
            pdf.cell(0, 7, text=_texto_seguro(linha), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    if termo_final:
        pdf.set_font("Helvetica", size=13)
        pdf.cell(0, 8, text="Termo de aceite", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, text=_texto_seguro(termo_final))

    return bytes(pdf.output())
