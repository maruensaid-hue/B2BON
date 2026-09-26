"""Cadastros do lado comprador, sempre filtrados pelo tenant e auditados.

Aprovação de demanda e de PCA é ato de administrador (papel), registrado
com quem aprovou e quando (Audit Trail, §41).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.procurement import fluxo, tipos
from app.contexts.shared import paginacao
from app.models.contrato_compra import ContratoCompra
from app.models.demanda_compra import DemandaCompra
from app.models.evento_contrato_compra import EventoContratoCompra
from app.models.evento_processo import EventoProcesso
from app.models.fornecedor_compras import FornecedorCompras
from app.models.item_pca import ItemPca
from app.models.orgao_publico import OrgaoPublico
from app.models.pesquisa_preco import PesquisaPreco
from app.models.plano_contratacao import PlanoContratacao
from app.models.processo_contratacao import ProcessoContratacao
from app.models.unidade_compras import UnidadeCompras
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

ENTIDADES = {
    "orgao_publico": OrgaoPublico,
    "unidade_compras": UnidadeCompras,
    "plano_contratacao": PlanoContratacao,
    "item_pca": ItemPca,
    "demanda_compra": DemandaCompra,
    "processo_contratacao": ProcessoContratacao,
    "evento_processo": EventoProcesso,
    "fornecedor_compras": FornecedorCompras,
    "contrato_compra": ContratoCompra,
    "evento_contrato_compra": EventoContratoCompra,
    "pesquisa_preco": PesquisaPreco,
}
# (campo, entidade referenciada): referências são sempre conferidas no mesmo tenant.
REFERENCIAS = {
    "orgao_id": OrgaoPublico, "unidade_id": UnidadeCompras, "plano_id": PlanoContratacao, "item_pca_id": ItemPca,
    "processo_id": ProcessoContratacao, "fornecedor_id": FornecedorCompras, "contrato_id": ContratoCompra,
}
STATUS_INICIAL = {
    "plano_contratacao": "ELABORACAO", "item_pca": "PLANEJADO", "demanda_compra": "RASCUNHO",
    "processo_contratacao": fluxo.PROCESSO.inicial, "evento_processo": "ABERTO", "contrato_compra": "VIGENTE",
}
STATUS_VALIDOS = {
    "plano_contratacao": tipos.STATUS_PLANO, "item_pca": tipos.STATUS_ITEM_PCA, "demanda_compra": tipos.STATUS_DEMANDA,
    "processo_contratacao": fluxo.PROCESSO.estados, "evento_processo": ("ABERTO", "CONCLUIDO", "CANCELADO"),
    "contrato_compra": tipos.STATUS_CONTRATO,
}
TIPOS_VALIDOS = {
    "evento_processo": tipos.TIPOS_EVENTO_PROCESSO, "evento_contrato_compra": tipos.TIPOS_EVENTO_CONTRATO,
    "pesquisa_preco": None,
}


def obter(db: Session, tenant_id: str, entidade: str, registro_id: int):
    modelo = ENTIDADES[entidade]
    registro = db.query(modelo).filter_by(id=registro_id, tenant_id=tenant_id).one_or_none()
    if registro is None:
        raise NaoEncontrado(f"{entidade.replace('_', ' ').capitalize()} {registro_id} não encontrado(a)")
    return registro


def _conferir_referencias(db: Session, tenant_id: str, dados: dict) -> None:
    for campo, modelo in REFERENCIAS.items():
        valor = dados.get(campo)
        if valor is not None and db.query(modelo).filter_by(id=valor, tenant_id=tenant_id).one_or_none() is None:
            raise NaoEncontrado(f"{campo} {valor} não encontrado")


def _validar(entidade: str, dados: dict, parcial: bool = False) -> None:
    status = dados.get("status")
    if status is not None and entidade in STATUS_VALIDOS and status not in STATUS_VALIDOS[entidade]:
        raise ValidacaoFalhou(f"Status inválido: {status}")
    tipo = dados.get("tipo")
    if TIPOS_VALIDOS.get(entidade) and (tipo is not None or not parcial) and tipo not in TIPOS_VALIDOS[entidade]:
        raise ValidacaoFalhou(f"Tipo inválido: {tipo}")
    if entidade == "pesquisa_preco" and not parcial:
        if dados.get("fonte_tipo") not in tipos.FONTES_PRECO:
            raise ValidacaoFalhou("Fonte do preço inválida.")
        if not dados.get("fonte_descricao"):
            raise ValidacaoFalhou("Todo preço precisa de fonte descrita.")


def criar(db: Session, tenant_id: str, usuario_id: int | None, entidade: str, dados: dict):
    _validar(entidade, dados)
    _conferir_referencias(db, tenant_id, dados)
    if entidade in STATUS_INICIAL:
        dados.setdefault("status", STATUS_INICIAL[entidade])
    if entidade == "contrato_compra" and dados.get("valor_atual") is None:
        dados["valor_atual"] = dados.get("valor_inicial")
    if entidade == "evento_contrato_compra" and dados.get("contrato_id") is not None:
        contrato = obter(db, tenant_id, "contrato_compra", dados["contrato_id"])
        dados["fornecedor_id"] = contrato.fornecedor_id
    registro = ENTIDADES[entidade](tenant_id=tenant_id, **dados)
    db.add(registro)
    db.flush()
    if entidade == "evento_contrato_compra" and registro.tipo == "ADITIVO" and registro.valor and registro.contrato_id:
        contrato = obter(db, tenant_id, "contrato_compra", registro.contrato_id)
        contrato.valor_atual = (contrato.valor_atual or 0) + registro.valor
    auditoria_service.registrar(db, tenant_id, f"{entidade}_criado", entidade, registro.id,
                                str(usuario_id) if usuario_id else None, {})
    db.commit()
    db.refresh(registro)
    return registro


def atualizar(db: Session, tenant_id: str, usuario_id: int | None, entidade: str, registro_id: int, dados: dict):
    _validar(entidade, dados, parcial=True)
    _conferir_referencias(db, tenant_id, dados)
    registro = obter(db, tenant_id, entidade, registro_id)
    if entidade in ("demanda_compra", "plano_contratacao") and dados.get("status") in ("APROVADA", "APROVADO"):
        raise RegraNegocioViolada("Aprovação é feita pela ação de aprovar (administrador).")
    if entidade == "processo_contratacao" and dados.get("status") is not None:
        fluxo.de(registro.modalidade).validar(dados["status"], "status", de=registro.status)
    for campo, valor in dados.items():
        setattr(registro, campo, valor)
    auditoria_service.registrar(db, tenant_id, f"{entidade}_atualizado", entidade, registro.id,
                                str(usuario_id) if usuario_id else None, {"campos": sorted(dados)})
    db.commit()
    db.refresh(registro)
    return registro


def aprovar(db: Session, tenant_id: str, usuario_id: int, entidade: str, registro_id: int):
    registro = obter(db, tenant_id, entidade, registro_id)
    registro.status = "APROVADA" if entidade == "demanda_compra" else "APROVADO"
    registro.aprovado_por_usuario_id = usuario_id
    registro.aprovado_em = datetime.now(UTC)
    auditoria_service.registrar(db, tenant_id, f"{entidade}_aprovado", entidade, registro.id, str(usuario_id), {})
    db.commit()
    db.refresh(registro)
    return registro


def listar(db: Session, tenant_id: str, entidade: str, cursor: str | None = None, limite: int | None = None,
           **filtros) -> paginacao.Pagina:
    """Ordem por id, keyset pelo último id devolvido."""
    quantidade = paginacao.limite(limite)
    modelo = ENTIDADES[entidade]
    consulta = db.query(modelo).filter_by(tenant_id=tenant_id)
    for campo, valor in filtros.items():
        if valor is not None:
            consulta = consulta.filter(getattr(modelo, campo) == valor)
    posicao = paginacao.decodificar(cursor)
    if posicao is not None:
        consulta = consulta.filter(modelo.id > int(posicao["id"]))
    linhas = consulta.order_by(modelo.id).limit(quantidade + 1).all()
    return paginacao.fatiar(linhas, quantidade, lambda registro: {"id": registro.id})


def como_dict(registro) -> dict:
    return {c.name: getattr(registro, c.name) for c in registro.__table__.columns if c.name not in ("conteudo", "paginas_texto")}
