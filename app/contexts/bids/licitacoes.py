"""Bid Opportunity, requisitos e decisões (Fase 9). Tudo do próprio tenant."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.bids import conformidade, go_no_go, repositorio
from app.contexts.bids.fontes.base import LicitacaoExterna
from app.contexts.bids.tipos import CATEGORIAS_REQUISITO, MODALIDADES, STATUS_CONFORMIDADE, STATUS_LICITACAO
from app.contexts.shared import paginacao
from app.models.contrato_venda_publica import ContratoVendaPublica
from app.models.decisao_go_no_go import DecisaoGoNoGo
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.requisito_licitacao import RequisitoLicitacao
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

CAMPOS_EDITAVEIS = (
    "titulo", "objeto", "orgao_nome", "orgao_cnpj", "conta_id", "oferta_id", "modalidade", "fonte_url",
    "data_publicacao", "prazo_proposta", "prazo_esclarecimento", "valor_estimado", "responsavel_usuario_id",
    "concorrentes", "parceiros",
)


def _ator(usuario_id: int | None) -> str | None:
    return str(usuario_id) if usuario_id is not None else None


def obter(db: Session, tenant_id: str, licitacao_id: int) -> Licitacao:
    return repositorio.VENDA.obter_processo(db, tenant_id, licitacao_id)


def listar(db: Session, tenant_id: str, status: str | None = None, cursor: str | None = None,
           limite: int | None = None) -> paginacao.Pagina[Licitacao]:
    return repositorio.VENDA.listar_processos(db, tenant_id, cursor, limite, status=status)


def _validar(dados: dict) -> None:
    if "modalidade" in dados and dados["modalidade"] not in MODALIDADES:
        raise ValidacaoFalhou(f"Modalidade inválida: {dados['modalidade']}")


def criar(db: Session, tenant_id: str, usuario_id: int | None, dados: dict) -> Licitacao:
    _validar(dados)
    licitacao = Licitacao(tenant_id=tenant_id, fonte="MANUAL", status="IDENTIFICADA",
                          **{k: v for k, v in dados.items() if k in CAMPOS_EDITAVEIS})
    db.add(licitacao)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "licitacao_criada", "licitacao", licitacao.id, _ator(usuario_id), {"fonte": "MANUAL"})
    db.commit()
    db.refresh(licitacao)
    return licitacao


def atualizar(db: Session, tenant_id: str, usuario_id: int | None, licitacao_id: int, dados: dict) -> Licitacao:
    _validar(dados)
    licitacao = obter(db, tenant_id, licitacao_id)
    for campo, valor in dados.items():
        if campo in CAMPOS_EDITAVEIS:
            setattr(licitacao, campo, valor)
    auditoria_service.registrar(db, tenant_id, "licitacao_atualizada", "licitacao", licitacao.id, _ator(usuario_id),
                                {"campos": sorted(k for k in dados if k in CAMPOS_EDITAVEIS)})
    db.commit()
    db.refresh(licitacao)
    return licitacao


def ingerir(db: Session, tenant_id: str, usuario_id: int | None, externas: list[LicitacaoExterna]) -> dict:
    """Tender ingestion idempotente por (tenant, fonte, id externo)."""
    criadas, atualizadas = [], []
    for ext in externas:
        existente = db.query(Licitacao).filter_by(tenant_id=tenant_id, fonte=ext.fonte, fonte_id_externo=ext.id_externo).one_or_none()
        campos = {
            "titulo": ext.titulo, "objeto": ext.objeto, "orgao_nome": ext.orgao_nome, "orgao_cnpj": ext.orgao_cnpj,
            "modalidade": ext.modalidade, "data_publicacao": ext.data_publicacao, "prazo_proposta": ext.prazo_proposta,
            "valor_estimado": ext.valor_estimado, "fonte_url": ext.url,
        }
        if existente is None:
            licitacao = Licitacao(tenant_id=tenant_id, fonte=ext.fonte, fonte_id_externo=ext.id_externo, status="IDENTIFICADA", **campos)
            db.add(licitacao)
            db.flush()
            criadas.append(licitacao.id)
        else:
            for campo, valor in campos.items():
                setattr(existente, campo, valor)
            atualizadas.append(existente.id)
    auditoria_service.registrar(db, tenant_id, "licitacoes_ingeridas", "licitacao", 0, _ator(usuario_id),
                                {"criadas": len(criadas), "atualizadas": len(atualizadas)})
    db.commit()
    return {"criadas": criadas, "atualizadas": atualizadas}


def mudar_status(db: Session, tenant_id: str, usuario_id: int | None, licitacao_id: int, status: str) -> Licitacao:
    if status not in STATUS_LICITACAO:
        raise ValidacaoFalhou(f"Status inválido: {status}")
    if status in ("GO", "NO_GO"):
        raise RegraNegocioViolada("GO/NO_GO é registrado pela decisão Go/No-Go, com a recomendação e a justificativa.")
    if status in ("GANHA", "PERDIDA"):
        raise RegraNegocioViolada("Use o registro de resultado para informar vencedor e valor.")
    licitacao = obter(db, tenant_id, licitacao_id)
    anterior, licitacao.status = licitacao.status, status
    auditoria_service.registrar(db, tenant_id, "licitacao_status", "licitacao", licitacao.id, _ator(usuario_id),
                                {"de": anterior, "para": status})
    db.commit()
    db.refresh(licitacao)
    return licitacao


def registrar_resultado(
    db: Session, tenant_id: str, usuario_id: int | None, licitacao_id: int, ganhou: bool,
    vencedor: str | None, valor_proposta: float | None, motivo: str | None,
) -> Licitacao:
    licitacao = obter(db, tenant_id, licitacao_id)
    licitacao.status = "GANHA" if ganhou else "PERDIDA"
    licitacao.vencedor = vencedor
    licitacao.valor_proposta = valor_proposta
    licitacao.motivo_resultado = motivo
    auditoria_service.registrar(db, tenant_id, "licitacao_resultado", "licitacao", licitacao.id, _ator(usuario_id),
                                {"status": licitacao.status, "vencedor": vencedor})
    db.commit()
    db.refresh(licitacao)
    return licitacao


# --- Requisitos ----------------------------------------------------------------


def listar_requisitos(db: Session, tenant_id: str, licitacao_id: int, incluir_descartados: bool = False) -> list[RequisitoLicitacao]:
    obter(db, tenant_id, licitacao_id)
    return repositorio.VENDA.requisitos(db, tenant_id, licitacao_id, incluir_descartados)


def criar_requisito_manual(
    db: Session, tenant_id: str, usuario_id: int | None, licitacao_id: int, categoria: str, descricao: str,
    documento_id: int | None, pagina: int | None, clausula: str | None, evidencia: str | None,
) -> RequisitoLicitacao:
    """Requisito digitado por humano. Se aponta para documento, a evidência
    tem de estar no texto dele (mesma regra de proveniência da IA)."""
    obter(db, tenant_id, licitacao_id)
    if categoria not in CATEGORIAS_REQUISITO:
        raise ValidacaoFalhou(f"Categoria inválida: {categoria}")
    if documento_id is not None:
        from app.contexts.shared.texto import localizar_pagina

        documento = db.query(DocumentoLicitacao).filter_by(id=documento_id, tenant_id=tenant_id, licitacao_id=licitacao_id).one_or_none()
        if documento is None:
            raise NaoEncontrado(f"Documento {documento_id} não encontrado nesta licitação")
        if not evidencia:
            raise ValidacaoFalhou("Informe o trecho do documento que comprova o requisito.")
        encontrada = localizar_pagina(documento.paginas_texto or [], evidencia)
        if encontrada is None:
            raise ValidacaoFalhou("O trecho informado não foi encontrado no documento.")
        pagina = encontrada
    requisito = RequisitoLicitacao(
        tenant_id=tenant_id, licitacao_id=licitacao_id, documento_id=documento_id, categoria=categoria,
        descricao=descricao.strip()[:500], evidencia=evidencia, pagina=pagina if documento_id else None,
        clausula=clausula, origem="manual", status="confirmado", revisado_por_usuario_id=usuario_id,
        revisado_em=datetime.now(UTC),
    )
    db.add(requisito)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "requisito_licitacao_criado", "requisito_licitacao", requisito.id, _ator(usuario_id), {})
    db.commit()
    db.refresh(requisito)
    return requisito


def _obter_requisito(db: Session, tenant_id: str, requisito_id: int) -> RequisitoLicitacao:
    requisito = db.query(RequisitoLicitacao).filter_by(id=requisito_id, tenant_id=tenant_id).one_or_none()
    if requisito is None:
        raise NaoEncontrado(f"Requisito {requisito_id} não encontrado")
    return requisito


def revisar_requisito(
    db: Session, tenant_id: str, usuario_id: int | None, requisito_id: int, status: str,
    descricao: str | None = None, categoria: str | None = None,
) -> RequisitoLicitacao:
    if status not in ("confirmado", "descartado"):
        raise ValidacaoFalhou("Status deve ser 'confirmado' ou 'descartado'.")
    if categoria is not None and categoria not in CATEGORIAS_REQUISITO:
        raise ValidacaoFalhou(f"Categoria inválida: {categoria}")
    requisito = _obter_requisito(db, tenant_id, requisito_id)
    editou = (descricao is not None and descricao.strip() != requisito.descricao) or (categoria not in (None, requisito.categoria))
    if descricao:
        requisito.descricao = descricao.strip()[:500]
    if categoria:
        requisito.categoria = categoria
    requisito.status = status
    requisito.revisado_por_usuario_id = usuario_id
    requisito.revisado_em = datetime.now(UTC)
    if requisito.origem == "ia":
        from app.contexts.bids.analise import FEATURE_EDITAL, FEATURE_TR
        from app.contexts.intelligence.contract import aprendizado

        documento = db.get(DocumentoLicitacao, requisito.documento_id) if requisito.documento_id else None
        feature = FEATURE_TR if documento is not None and documento.tipo == "TR" else FEATURE_EDITAL
        aprendizado.registrar(db, tenant_id, feature, "REJEITADO" if status == "descartado" else ("EDITADO" if editou else "APROVADO"),
                              entidade_tipo="requisito_licitacao", entidade_id=requisito.id, usuario_id=usuario_id,
                              dados={"categoria": requisito.categoria})
    auditoria_service.registrar(db, tenant_id, f"requisito_licitacao_{status}", "requisito_licitacao", requisito.id, _ator(usuario_id), {})
    db.commit()
    db.refresh(requisito)
    return requisito


def ajustar_conformidade(
    db: Session, tenant_id: str, usuario_id: int | None, requisito_id: int, status: str | None, justificativa: str | None,
) -> RequisitoLicitacao:
    """Ajuste humano da matriz: exige justificativa; `status=None` volta ao calculado."""
    requisito = _obter_requisito(db, tenant_id, requisito_id)
    if status is not None:
        if status not in STATUS_CONFORMIDADE:
            raise ValidacaoFalhou(f"Status de conformidade inválido: {status}")
        if not justificativa or not justificativa.strip():
            raise ValidacaoFalhou("Informe a justificativa do ajuste.")
    requisito.conformidade_manual = status
    requisito.justificativa_manual = justificativa.strip() if status and justificativa else None
    requisito.revisado_por_usuario_id = usuario_id
    requisito.revisado_em = datetime.now(UTC)
    auditoria_service.registrar(db, tenant_id, "conformidade_ajustada", "requisito_licitacao", requisito.id, _ator(usuario_id),
                                {"status": status})
    db.commit()
    db.refresh(requisito)
    return requisito


# --- Go/No-Go e contratos ---------------------------------------------------------


def decidir(
    db: Session, tenant_id: str, usuario_id: int | None, licitacao_id: int, decisao: str, justificativa: str | None,
) -> DecisaoGoNoGo:
    """Decisão humana. Divergir da recomendação exige justificativa."""
    if decisao not in ("GO", "NO_GO"):
        raise ValidacaoFalhou("Decisão deve ser GO ou NO_GO.")
    licitacao = obter(db, tenant_id, licitacao_id)
    recomendacao = go_no_go.recomendar(db, tenant_id, licitacao, conformidade.calcular(db, tenant_id, licitacao))
    if recomendacao["recomendacao"] != decisao and not (justificativa and justificativa.strip()):
        raise ValidacaoFalhou(
            f"A recomendação é {recomendacao['recomendacao']}. Para decidir {decisao}, informe a justificativa."
        )
    registro = DecisaoGoNoGo(
        tenant_id=tenant_id, licitacao_id=licitacao.id, recomendacao=recomendacao["recomendacao"],
        fatores=[{k: v for k, v in f.items()} for f in recomendacao["fatores"]], decisao=decisao,
        justificativa=(justificativa or "").strip() or None, decidido_por_usuario_id=usuario_id,
    )
    db.add(registro)
    licitacao.status = decisao
    db.flush()
    auditoria_service.registrar(db, tenant_id, "go_no_go_decidido", "licitacao", licitacao.id, _ator(usuario_id),
                                {"decisao": decisao, "recomendacao": recomendacao["recomendacao"]})
    db.commit()
    db.refresh(registro)
    return registro


def criar_contrato(db: Session, tenant_id: str, usuario_id: int | None, dados: dict) -> ContratoVendaPublica:
    if dados.get("licitacao_id") is not None:
        licitacao = obter(db, tenant_id, dados["licitacao_id"])
        dados["orgao_nome"] = dados.get("orgao_nome") or licitacao.orgao_nome
        dados["conta_id"] = dados.get("conta_id") or licitacao.conta_id
    if dados.get("vigencia_inicio") and dados.get("vigencia_fim") and dados["vigencia_fim"] < dados["vigencia_inicio"]:
        raise ValidacaoFalhou("Fim da vigência antes do início.")
    contrato = ContratoVendaPublica(tenant_id=tenant_id, status="VIGENTE", **dados)
    db.add(contrato)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "contrato_venda_publica_criado", "contrato_venda_publica", contrato.id, _ator(usuario_id), {})
    db.commit()
    db.refresh(contrato)
    return contrato


def como_dict(lic: Licitacao) -> dict:
    return {
        "id": lic.id, "titulo": lic.titulo, "objeto": lic.objeto, "orgao_nome": lic.orgao_nome, "orgao_cnpj": lic.orgao_cnpj,
        "conta_id": lic.conta_id, "oferta_id": lic.oferta_id, "modalidade": lic.modalidade, "fonte": lic.fonte,
        "fonte_id_externo": lic.fonte_id_externo, "fonte_url": lic.fonte_url, "data_publicacao": lic.data_publicacao,
        "prazo_proposta": lic.prazo_proposta, "prazo_esclarecimento": lic.prazo_esclarecimento,
        "valor_estimado": lic.valor_estimado, "status": lic.status, "responsavel_usuario_id": lic.responsavel_usuario_id,
        "concorrentes": lic.concorrentes or [], "parceiros": lic.parceiros or [], "vencedor": lic.vencedor,
        "valor_proposta": lic.valor_proposta, "motivo_resultado": lic.motivo_resultado, "criado_em": lic.criado_em,
    }


def requisito_dict(r: RequisitoLicitacao) -> dict:
    return {
        "id": r.id, "licitacao_id": r.licitacao_id, "documento_id": r.documento_id, "categoria": r.categoria,
        "descricao": r.descricao, "evidencia": r.evidencia, "pagina": r.pagina, "clausula": r.clausula,
        "origem": r.origem, "status": r.status, "conformidade_manual": r.conformidade_manual,
        "justificativa_manual": r.justificativa_manual, "criado_em": r.criado_em,
    }
