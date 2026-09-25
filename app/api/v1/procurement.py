"""Public Procurement — Buy Side (Fase 10, master prompt §37-§51).

Gate: módulo "procurement" (preço PENDING_DEFINITION, §71; nenhum plano o
inclui). Tudo do tenant comprador, CONFIDENTIAL. Aprovações são de admin.
Riscos são sinais analíticos para revisão, nunca conclusão jurídica.
"""

from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import Boolean, Date, DateTime, Float, Integer
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_llm_provider, get_tenant_id, limitar_ia_por_tenant
from app.contexts.procurement import contract as compras
from app.contexts.intelligence import contract as intel
from app.llm.base import LLMProvider
from app.models.documento_compras import DocumentoCompras
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

router = APIRouter(prefix="/procurement", tags=["public-procurement"])

RECURSOS = {
    "orgaos": "orgao_publico",
    "unidades": "unidade_compras",
    "planos": "plano_contratacao",
    "itens-pca": "item_pca",
    "demandas": "demanda_compra",
    "processos": "processo_contratacao",
    "eventos-processo": "evento_processo",
    "fornecedores": "fornecedor_compras",
    "contratos": "contrato_compra",
    "eventos-contrato": "evento_contrato_compra",
    "precos": "pesquisa_preco",
}
# Nunca vêm do corpo: identidade, tenant, trilha de aprovação.
_PROTEGIDOS = {"id", "tenant_id", "criado_em", "aprovado_por_usuario_id", "aprovado_em", "criado_por_usuario_id"}


def _usuario_id(ator_id: str | None) -> int | None:
    return int(ator_id) if ator_id and ator_id.isdigit() else None


def _entidade(recurso: str) -> str:
    if recurso not in RECURSOS:
        raise NaoEncontrado(f"Recurso {recurso} não existe")
    return RECURSOS[recurso]


def _coagir(entidade: str, dados: dict) -> dict:
    colunas = {c.name: c for c in compras.cadastros.ENTIDADES[entidade].__table__.columns}
    resultado = {}
    for campo, valor in dados.items():
        if campo in _PROTEGIDOS or campo not in colunas:
            raise ValidacaoFalhou(f"Campo não permitido: {campo}")
        tipo = colunas[campo].type
        try:
            if valor is None:
                resultado[campo] = None
            elif isinstance(tipo, DateTime):
                resultado[campo] = datetime.fromisoformat(valor) if isinstance(valor, str) else valor
            elif isinstance(tipo, Date):
                resultado[campo] = date.fromisoformat(valor) if isinstance(valor, str) else valor
            elif isinstance(tipo, Boolean):
                resultado[campo] = bool(valor)
            elif isinstance(tipo, Float):
                resultado[campo] = float(valor)
            elif isinstance(tipo, Integer):
                resultado[campo] = int(valor)
            else:
                resultado[campo] = valor
        except (TypeError, ValueError) as erro:
            raise ValidacaoFalhou(f"Valor inválido para {campo}.") from erro
    return resultado


# --- Inteligência (rotas fixas antes das genéricas) ------------------------------------


@router.get("/riscos")
def riscos(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return compras.riscos.sinais(db, tenant_id)


@router.get("/metricas")
def metricas(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    """Indicadores do lado comprador (Fase 16): ciclo, execução do PCA,
    fornecedores e risco de renovação. Nunca misturados com receita."""
    return compras.metricas.metricas(db, tenant_id)


@router.get("/proximas-acoes")
def proximas_acoes(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return compras.nba.acoes(db, tenant_id, compras.riscos.sinais(db, tenant_id))


@router.get("/fornecedores/ranking")
def ranking_fornecedores(categoria: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return compras.fornecedores.ranking_por_categoria(db, tenant_id, categoria)


@router.get("/fornecedores/{fornecedor_id}/360")
def fornecedor_360(fornecedor_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return compras.fornecedores.visao_360(db, tenant_id, compras.cadastros.obter(db, tenant_id, "fornecedor_compras", fornecedor_id))


@router.get("/contratos/{contrato_id}/inteligencia")
def contrato_inteligencia(contrato_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return compras.contratos.inteligencia(db, tenant_id, compras.cadastros.obter(db, tenant_id, "contrato_compra", contrato_id))


@router.get("/demandas/{demanda_id}/analise")
def analisar_demanda(demanda_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return compras.demandas.analisar(db, tenant_id, compras.cadastros.obter(db, tenant_id, "demanda_compra", demanda_id))


@router.get("/planos/{plano_id}/painel")
def painel_plano(plano_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return compras.planejamento.painel(db, tenant_id, compras.cadastros.obter(db, tenant_id, "plano_contratacao", plano_id))


@router.get("/processos/{processo_id}/workspace")
def workspace(processo_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return compras.workspace.montar(db, tenant_id, processo_id)


@router.post("/{recurso}/{registro_id}/aprovar")
def aprovar(recurso: str, registro_id: int, tenant_id: str = Depends(get_tenant_id),
            usuario: Usuario = Depends(exigir_papel("admin", "super_admin")), db: Session = Depends(get_db)) -> dict:
    entidade = _entidade(recurso)
    if entidade not in ("demanda_compra", "plano_contratacao"):
        raise NaoEncontrado("Só demandas e planos são aprovados.")
    return compras.cadastros.como_dict(compras.cadastros.aprovar(db, tenant_id, usuario.id, entidade, registro_id))


# --- Documentos --------------------------------------------------------------------


@router.post("/documentos", status_code=201)
async def enviar_documento(
    tipo: str = Form(...),
    processo_id: int | None = Form(None),
    contrato_id: int | None = Form(None),
    classificacao: str = Form("CONFIDENTIAL"),
    arquivo: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> dict:
    if tipo not in compras.tipos.TIPOS_DOCUMENTO:
        raise ValidacaoFalhou(f"Tipo inválido: {tipo}")
    if processo_id is not None:
        compras.cadastros.obter(db, tenant_id, "processo_contratacao", processo_id)
    if contrato_id is not None:
        compras.cadastros.obter(db, tenant_id, "contrato_compra", contrato_id)
    documento = compras.documentos.registrar(
        db, tenant_id, tipo, arquivo.filename or "documento", arquivo.content_type or "", await arquivo.read(),
        _usuario_id(ator_id), processo_id, contrato_id, classificacao,
    )
    auditoria_service.registrar(db, tenant_id, "documento_compras_enviado", "processo_contratacao" if processo_id else "documento_compras",
                                processo_id or documento.id, ator_id, {"documento_id": documento.id, "sha256": documento.sha256})
    db.commit()
    return compras.documentos.como_dict(documento)


def _documento(db: Session, tenant_id: str, documento_id: int) -> DocumentoCompras:
    documento = db.query(DocumentoCompras).filter_by(id=documento_id, tenant_id=tenant_id).one_or_none()
    if documento is None:
        raise NaoEncontrado(f"Documento {documento_id} não encontrado")
    return documento


@router.get("/documentos/{documento_id}/arquivo")
def baixar_documento(documento_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Response:
    documento = _documento(db, tenant_id, documento_id)
    return Response(content=documento.conteudo or b"", media_type=documento.tipo_mime,
                    headers={"Content-Disposition": f'attachment; filename="documento-{documento.id}"', "X-Content-SHA256": documento.sha256})


@router.get("/documentos/{documento_id}/estimativa")
def estimar_analise(documento_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    """AI Credits estimados antes de analisar (Fase 15)."""
    documento = _documento(db, tenant_id, documento_id)
    return intel.estimar(db, compras.documentos.FEATURE, {"paginas": len(documento.paginas_texto or [])})


@router.post("/documentos/{documento_id}/analisar", dependencies=[Depends(limitar_ia_por_tenant())])
def analisar_documento(documento_id: int, confirmar: bool = False, tenant_id: str = Depends(get_tenant_id),
                       ator_id: str | None = Depends(get_ator_id), llm: LLMProvider = Depends(get_llm_provider),
                       db: Session = Depends(get_db)) -> dict:
    """Documento longo passa do limiar: a primeira chamada devolve 409 com a
    estimativa (`requer_confirmacao`); com `confirmar=true`, executa."""
    documento = _documento(db, tenant_id, documento_id)
    resultado = compras.documentos.analisar(db, llm, tenant_id, _usuario_id(ator_id), documento, confirmado=confirmar)
    db.commit()
    return resultado


# --- CRUD genérico por recurso -------------------------------------------------------


@router.get("/{recurso}")
def listar(recurso: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return [compras.cadastros.como_dict(r) for r in compras.cadastros.listar(db, tenant_id, _entidade(recurso))]


@router.post("/{recurso}", status_code=201)
def criar(recurso: str, dados: dict = Body(...), tenant_id: str = Depends(get_tenant_id),
          ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    entidade = _entidade(recurso)
    corpo = _coagir(entidade, dados)
    if entidade in ("evento_processo", "evento_contrato_compra"):
        corpo["criado_por_usuario_id"] = _usuario_id(ator_id)
    if entidade == "demanda_compra":
        corpo.setdefault("solicitante_usuario_id", _usuario_id(ator_id))
    return compras.cadastros.como_dict(compras.cadastros.criar(db, tenant_id, _usuario_id(ator_id), entidade, corpo))


@router.get("/{recurso}/{registro_id}")
def obter(recurso: str, registro_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return compras.cadastros.como_dict(compras.cadastros.obter(db, tenant_id, _entidade(recurso), registro_id))


@router.patch("/{recurso}/{registro_id}")
def atualizar(recurso: str, registro_id: int, dados: dict = Body(...), tenant_id: str = Depends(get_tenant_id),
              ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    entidade = _entidade(recurso)
    return compras.cadastros.como_dict(
        compras.cadastros.atualizar(db, tenant_id, _usuario_id(ator_id), entidade, registro_id, _coagir(entidade, dados))
    )
