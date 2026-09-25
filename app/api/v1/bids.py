"""Bid Intelligence — Sell Side (Fase 9, master prompt §30-§36).

Gate: módulo "bids" (B2B ON Public Sector). Dado do próprio tenant,
classificado CONFIDENTIAL. Só a análise de documento usa IA (medida); o
resto é determinístico. Go/No-Go: a plataforma recomenda, o humano decide.
"""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_tenant_id, get_usuario_atual, limitar_ia_por_tenant
from app.contexts.bids import contract as bids
from app.core.config import settings
from app.llm.base import LLMProvider
from app.models.documento_cofre import DocumentoCofre
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

router = APIRouter(prefix="/bids", tags=["bid-intelligence"])

Modalidade = Literal[bids.tipos.MODALIDADES]  # type: ignore[valid-type]
TipoDocumento = Literal[bids.tipos.TIPOS_DOCUMENTO]  # type: ignore[valid-type]
Categoria = Literal[bids.tipos.CATEGORIAS_REQUISITO]  # type: ignore[valid-type]
StatusConformidade = Literal[bids.tipos.STATUS_CONFORMIDADE]  # type: ignore[valid-type]


class LicitacaoEntrada(BaseModel):
    titulo: str | None = Field(default=None, min_length=3, max_length=300)
    objeto: str | None = None
    orgao_nome: str | None = None
    orgao_cnpj: str | None = None
    conta_id: int | None = None
    oferta_id: int | None = None
    modalidade: Modalidade | None = None
    fonte_url: str | None = None
    data_publicacao: datetime | None = None
    prazo_proposta: datetime | None = None
    prazo_esclarecimento: datetime | None = None
    valor_estimado: float | None = Field(default=None, ge=0)
    responsavel_usuario_id: int | None = None
    concorrentes: list[str] | None = None
    parceiros: list[str] | None = None


class StatusEntrada(BaseModel):
    status: str


class ResultadoEntrada(BaseModel):
    ganhou: bool
    vencedor: str | None = None
    valor_proposta: float | None = Field(default=None, ge=0)
    motivo: str | None = None


class RequisitoEntrada(BaseModel):
    categoria: Categoria
    descricao: str = Field(min_length=3, max_length=500)
    documento_id: int | None = None
    pagina: int | None = Field(default=None, ge=1)
    clausula: str | None = None
    evidencia: str | None = None


class RevisaoRequisito(BaseModel):
    status: Literal["confirmado", "descartado"]
    descricao: str | None = Field(default=None, min_length=3, max_length=500)
    categoria: Categoria | None = None


class AjusteConformidade(BaseModel):
    status: StatusConformidade | None
    justificativa: str | None = None


class DecisaoEntrada(BaseModel):
    decisao: Literal["GO", "NO_GO"]
    justificativa: str | None = None


class ContratoEntrada(BaseModel):
    licitacao_id: int | None = None
    conta_id: int | None = None
    orgao_nome: str | None = None
    numero: str | None = None
    objeto: str = Field(min_length=3)
    valor: float | None = Field(default=None, ge=0)
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None
    renovavel: bool = False


class IngestaoPncp(BaseModel):
    data_inicial: str = Field(pattern=r"^\d{8}$")
    data_final: str = Field(pattern=r"^\d{8}$")
    modalidade: int | None = None
    pagina: int = Field(default=1, ge=1)


def _usuario_id(ator_id: str | None) -> int | None:
    return int(ator_id) if ator_id and ator_id.isdigit() else None


def _documento(db: Session, tenant_id: str, documento_id: int) -> DocumentoLicitacao:
    documento = db.query(DocumentoLicitacao).filter_by(id=documento_id, tenant_id=tenant_id).one_or_none()
    if documento is None:
        raise NaoEncontrado(f"Documento {documento_id} não encontrado")
    return documento


# --- Licitações -------------------------------------------------------------------


@router.get("/fontes")
def listar_fontes() -> list[dict]:
    return bids.fontes.fontes()


@router.get("/licitacoes")
def listar(status: str | None = None, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return [bids.licitacoes.como_dict(lic) for lic in bids.licitacoes.listar(db, tenant_id, status)]


@router.post("/licitacoes", status_code=201)
def criar(dados: LicitacaoEntrada, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
          db: Session = Depends(get_db)) -> dict:
    if not dados.titulo:
        raise ValidacaoFalhou("Informe o título.")
    corpo = dados.model_dump(exclude_none=True)
    corpo.setdefault("modalidade", "PUBLIC_TENDER")
    return bids.licitacoes.como_dict(bids.licitacoes.criar(db, tenant_id, _usuario_id(ator_id), corpo))


@router.patch("/licitacoes/{licitacao_id}")
def atualizar(licitacao_id: int, dados: LicitacaoEntrada, tenant_id: str = Depends(get_tenant_id),
              ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    corpo = dados.model_dump(exclude_unset=True)
    return bids.licitacoes.como_dict(bids.licitacoes.atualizar(db, tenant_id, _usuario_id(ator_id), licitacao_id, corpo))


@router.post("/licitacoes/{licitacao_id}/status")
def mudar_status(licitacao_id: int, dados: StatusEntrada, tenant_id: str = Depends(get_tenant_id),
                 ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return bids.licitacoes.como_dict(bids.licitacoes.mudar_status(db, tenant_id, _usuario_id(ator_id), licitacao_id, dados.status))


@router.post("/licitacoes/{licitacao_id}/resultado")
def resultado(licitacao_id: int, dados: ResultadoEntrada, tenant_id: str = Depends(get_tenant_id),
              ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return bids.licitacoes.como_dict(bids.licitacoes.registrar_resultado(
        db, tenant_id, _usuario_id(ator_id), licitacao_id, dados.ganhou, dados.vencedor, dados.valor_proposta, dados.motivo,
    ))


@router.get("/licitacoes/{licitacao_id}/workspace")
def workspace(licitacao_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return bids.workspace.montar(db, tenant_id, licitacao_id)


# --- Documentos e análise ---------------------------------------------------------------


@router.post("/licitacoes/{licitacao_id}/documentos", status_code=201)
async def enviar_documento(
    licitacao_id: int,
    tipo: TipoDocumento = Form(...),
    fonte_url: str | None = Form(None),
    arquivo: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> dict:
    bids.licitacoes.obter(db, tenant_id, licitacao_id)
    conteudo = await arquivo.read()
    documento = bids.documentos.registrar(
        db, tenant_id, licitacao_id, tipo, arquivo.filename or "documento", arquivo.content_type or "", conteudo,
        _usuario_id(ator_id), fonte="URL" if fonte_url else "UPLOAD", fonte_url=fonte_url,
    )
    auditoria_service.registrar(db, tenant_id, "documento_licitacao_enviado", "documento_licitacao", documento.id, ator_id,
                                {"sha256": documento.sha256, "paginas": documento.paginas})
    db.commit()
    return bids.documentos.como_dict(documento)


@router.get("/documentos/{documento_id}/arquivo")
def baixar_documento(documento_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> Response:
    documento = _documento(db, tenant_id, documento_id)
    return Response(content=documento.conteudo or b"", media_type=documento.tipo_mime,
                    headers={"Content-Disposition": f'attachment; filename="documento-{documento.id}"', "X-Content-SHA256": documento.sha256})


@router.post("/documentos/{documento_id}/analisar", dependencies=[Depends(limitar_ia_por_tenant())])
def analisar_documento(documento_id: int, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                       llm: LLMProvider = Depends(get_llm_provider), db: Session = Depends(get_db)) -> dict:
    documento = _documento(db, tenant_id, documento_id)
    resultado = bids.analise.analisar(db, llm, tenant_id, _usuario_id(ator_id), documento)
    auditoria_service.registrar(db, tenant_id, "documento_licitacao_analisado", "documento_licitacao", documento.id, ator_id, resultado)
    db.commit()
    return resultado


# --- Requisitos, matriz, Go/No-Go --------------------------------------------------------


@router.get("/licitacoes/{licitacao_id}/requisitos")
def listar_requisitos(licitacao_id: int, incluir_descartados: bool = False, tenant_id: str = Depends(get_tenant_id),
                      db: Session = Depends(get_db)) -> list[dict]:
    return [bids.licitacoes.requisito_dict(r) for r in bids.licitacoes.listar_requisitos(db, tenant_id, licitacao_id, incluir_descartados)]


@router.post("/licitacoes/{licitacao_id}/requisitos", status_code=201)
def criar_requisito(licitacao_id: int, dados: RequisitoEntrada, tenant_id: str = Depends(get_tenant_id),
                    ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return bids.licitacoes.requisito_dict(bids.licitacoes.criar_requisito_manual(
        db, tenant_id, _usuario_id(ator_id), licitacao_id, dados.categoria, dados.descricao, dados.documento_id,
        dados.pagina, dados.clausula, dados.evidencia,
    ))


@router.patch("/requisitos/{requisito_id}")
def revisar_requisito(requisito_id: int, dados: RevisaoRequisito, tenant_id: str = Depends(get_tenant_id),
                      ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return bids.licitacoes.requisito_dict(bids.licitacoes.revisar_requisito(
        db, tenant_id, _usuario_id(ator_id), requisito_id, dados.status, dados.descricao, dados.categoria,
    ))


@router.put("/requisitos/{requisito_id}/conformidade")
def ajustar_conformidade(requisito_id: int, dados: AjusteConformidade, tenant_id: str = Depends(get_tenant_id),
                         ator_id: str | None = Depends(get_ator_id), db: Session = Depends(get_db)) -> dict:
    return bids.licitacoes.requisito_dict(bids.licitacoes.ajustar_conformidade(
        db, tenant_id, _usuario_id(ator_id), requisito_id, dados.status, dados.justificativa,
    ))


@router.get("/licitacoes/{licitacao_id}/matriz")
def matriz(licitacao_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return bids.conformidade.calcular(db, tenant_id, bids.licitacoes.obter(db, tenant_id, licitacao_id))


@router.get("/licitacoes/{licitacao_id}/go-no-go")
def recomendacao_go_no_go(licitacao_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    lic = bids.licitacoes.obter(db, tenant_id, licitacao_id)
    return bids.go_no_go.recomendar(db, tenant_id, lic, bids.conformidade.calcular(db, tenant_id, lic))


@router.post("/licitacoes/{licitacao_id}/go-no-go", status_code=201)
def decidir_go_no_go(licitacao_id: int, dados: DecisaoEntrada, tenant_id: str = Depends(get_tenant_id),
                     usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> dict:
    """Só admin ou o responsável pela licitação decide (§35: humano autorizado)."""
    lic = bids.licitacoes.obter(db, tenant_id, licitacao_id)
    if usuario.papel not in ("admin", "super_admin") and usuario.id != lic.responsavel_usuario_id:
        raise NaoAutorizado("Só o responsável pela licitação ou um administrador decide o Go/No-Go.")
    registro = bids.licitacoes.decidir(db, tenant_id, usuario.id, licitacao_id, dados.decisao, dados.justificativa)
    return {"id": registro.id, "decisao": registro.decisao, "recomendacao": registro.recomendacao,
            "justificativa": registro.justificativa, "fatores": registro.fatores}


# --- Cofre ----------------------------------------------------------------------


@router.get("/cofre")
def listar_cofre(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return [bids.cofre.como_dict(d) for d in bids.cofre.listar(db, tenant_id)]


@router.get("/cofre/alertas")
def alertas_cofre(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return bids.cofre.alertas(db, tenant_id)


@router.post("/cofre", status_code=201)
async def adicionar_ao_cofre(
    tipo: str = Form(...),
    nome: str = Form(..., min_length=2),
    emissor: str | None = Form(None),
    escopo: str | None = Form(None),
    palavras_chave: str | None = Form(None),
    valido_desde: date | None = Form(None),
    valido_ate: date | None = Form(None),
    arquivo: UploadFile | None = File(None),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> dict:
    if tipo not in bids.tipos.TIPOS_COFRE:
        raise ValidacaoFalhou(f"Tipo inválido: {tipo}")
    if valido_desde and valido_ate and valido_ate < valido_desde:
        raise ValidacaoFalhou("Validade final antes da inicial.")
    conteudo = await arquivo.read() if arquivo is not None else None
    if conteudo and len(conteudo) > bids.documentos.TAMANHO_MAXIMO:
        raise ValidacaoFalhou("Arquivo acima de 15 MB.")
    documento = DocumentoCofre(
        tenant_id=tenant_id, tipo=tipo, nome=nome.strip(), emissor=emissor, escopo=escopo,
        palavras_chave=[p.strip() for p in (palavras_chave or "").split(",") if p.strip()],
        valido_desde=valido_desde, valido_ate=valido_ate,
        nome_arquivo=arquivo.filename if arquivo is not None else None,
        tipo_mime=arquivo.content_type if arquivo is not None else None,
        tamanho_bytes=len(conteudo) if conteudo else None, sha256=bids.cofre.hash_de(conteudo), conteudo=conteudo or None,
        enviado_por_usuario_id=_usuario_id(ator_id),
    )
    db.add(documento)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "documento_cofre_adicionado", "documento_cofre", documento.id, ator_id, {"tipo": tipo})
    db.commit()
    db.refresh(documento)
    return bids.cofre.como_dict(documento)


@router.delete("/cofre/{documento_id}", status_code=204)
def arquivar_do_cofre(documento_id: int, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                      db: Session = Depends(get_db)) -> None:
    documento = db.query(DocumentoCofre).filter_by(id=documento_id, tenant_id=tenant_id).one_or_none()
    if documento is None:
        raise NaoEncontrado(f"Documento {documento_id} não encontrado")
    documento.ativo = False
    auditoria_service.registrar(db, tenant_id, "documento_cofre_arquivado", "documento_cofre", documento.id, ator_id, {})
    db.commit()


# --- Prazos, concorrência, contratos, ingestão -----------------------------------------


@router.get("/prazos")
def listar_prazos(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return bids.prazos.listar(db, tenant_id)


@router.get("/concorrentes")
def concorrentes(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return bids.concorrencia.resumo(db, tenant_id)


@router.get("/contratos")
def listar_contratos(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    from app.models.contrato_venda_publica import ContratoVendaPublica

    return [bids.contratos.como_dict(c) for c in db.query(ContratoVendaPublica).filter_by(tenant_id=tenant_id).order_by(ContratoVendaPublica.id)]


@router.post("/contratos", status_code=201)
def criar_contrato(dados: ContratoEntrada, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                   db: Session = Depends(get_db)) -> dict:
    return bids.contratos.como_dict(bids.licitacoes.criar_contrato(db, tenant_id, _usuario_id(ator_id), dados.model_dump()))


@router.get("/contratos/sinais")
def sinais_contratos(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return bids.contratos.sinais(db, tenant_id)


def get_fonte_pncp() -> bids.FontePncp:
    return bids.FontePncp()


@router.post("/ingestao/pncp")
def ingerir_pncp(dados: IngestaoPncp, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                 fonte: bids.FontePncp = Depends(get_fonte_pncp), db: Session = Depends(get_db)) -> dict:
    """EXPERIMENTAL e desligado por padrão (PNCP_HABILITADO)."""
    if not settings.pncp_habilitado:
        raise RegraNegocioViolada("A ingestão do PNCP é experimental e não está habilitada neste ambiente.")
    externas = fonte.buscar(dados.data_inicial, dados.data_final, dados.modalidade, dados.pagina)
    return bids.licitacoes.ingerir(db, tenant_id, _usuario_id(ator_id), externas)
