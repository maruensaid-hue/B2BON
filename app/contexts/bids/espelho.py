"""Espelho do lado vendedor nas tabelas unificadas (S3, D-055).

Mapeamento único de licitação, documento, requisito e contrato ganho para
`*_sourcing` com lado SELL. Usado pelos eventos do ORM (toda escrita nas
tabelas antigas é copiada na mesma transação) e pelo backfill idempotente.
A leitura dupla (`repositorio.py`) compara com estes mesmos mapeamentos.
"""

from datetime import datetime
from types import SimpleNamespace

from app.contexts.bids import fluxo
from app.contexts.sourcing.contract import espelho, tipos
from app.models.contrato_venda_publica import ContratoVendaPublica
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.requisito_licitacao import RequisitoLicitacao

LADO = tipos.Lado.VENDA


def _iso(valor):
    return valor.isoformat() if valor is not None else None


def processo(lic: Licitacao) -> dict:
    segmento, tipo_processo = fluxo.classificar(lic.modalidade)
    fluxo_licitacao, regras = fluxo.configuracao(lic.modalidade)
    return {
        "tenant_id": lic.tenant_id,
        "segmento": segmento.value,
        "tipo_processo": tipo_processo,
        "titulo": lic.titulo,
        "descricao": lic.objeto,
        "emissor_nome": lic.orgao_nome,
        "emissor_cnpj": lic.orgao_cnpj,
        "conta_id": lic.conta_id,
        "oferta_id": lic.oferta_id,
        "status": lic.status,
        "visibilidade": "PRIVADO",
        "classificacao": "INTERNAL",
        "ruleset": regras.codigo if regras else None,
        "workflow": fluxo_licitacao.codigo,
        "publicado_em": lic.data_publicacao,
        "prazo": lic.prazo_proposta,
        "valor_estimado": lic.valor_estimado,
        "moeda": "BRL",
        "valor_sigiloso": False,
        "responsavel_usuario_id": lic.responsavel_usuario_id,
        "fonte": lic.fonte,
        "fonte_id_externo": lic.fonte_id_externo,
        "fonte_url": lic.fonte_url,
        "metadados": {
            "modalidade": lic.modalidade, "prazo_esclarecimento": _iso(lic.prazo_esclarecimento),
            "concorrentes": lic.concorrentes, "parceiros": lic.parceiros, "vencedor": lic.vencedor,
            "valor_proposta": lic.valor_proposta, "motivo_resultado": lic.motivo_resultado,
        },
        "criado_em": espelho.carregado(lic, "criado_em"),
    }


def documento(doc: DocumentoLicitacao) -> dict:
    return {
        "tenant_id": doc.tenant_id, "processo_origem": ("licitacao", doc.licitacao_id), "tipo_documento": doc.tipo,
        "nome_arquivo": doc.nome_arquivo, "tipo_mime": doc.tipo_mime, "tamanho_bytes": doc.tamanho_bytes, "sha256": doc.sha256,
        "paginas": doc.paginas or 0, "fonte": doc.fonte, "fonte_url": doc.fonte_url, "classificacao": "INTERNAL", "versao": 1,
        "status_extracao": doc.status_analise, "analisado_em": doc.analisado_em, "enviado_por_usuario_id": doc.enviado_por_usuario_id,
        "criado_em": espelho.carregado(doc, "criado_em"),
    }


def requisito(req: RequisitoLicitacao) -> dict:
    return {
        "tenant_id": req.tenant_id, "processo_origem": ("licitacao", req.licitacao_id),
        "documento_origem": ("documento_licitacao", req.documento_id) if req.documento_id else None,
        "categoria": req.categoria, "texto": req.descricao, "fonte": "AI" if req.origem == "ia" else "MANUAL",
        "pagina": req.pagina, "clausula": req.clausula, "trecho": req.evidencia, "obrigatorio": req.obrigatorio,
        "resposta": req.resposta,
        "confianca": "grounded" if req.origem == "ia" else "manual", "status_revisao": req.status,
        "conformidade_manual": req.conformidade_manual, "justificativa_manual": req.justificativa_manual,
        "revisado_por_usuario_id": req.revisado_por_usuario_id, "revisado_em": req.revisado_em,
        "correlation_id": req.correlation_id, "criado_em": espelho.carregado(req, "criado_em"),
    }


def contrato(c: ContratoVendaPublica) -> dict:
    return {
        "tenant_id": c.tenant_id, "processo_origem": ("licitacao", c.licitacao_id) if c.licitacao_id else None,
        "contraparte_nome": c.orgao_nome, "conta_id": c.conta_id, "fornecedor_id": None, "numero": c.numero, "objeto": c.objeto,
        "categoria": None, "valor_inicial": c.valor, "valor_atual": c.valor, "vigencia_inicio": c.vigencia_inicio,
        "vigencia_fim": c.vigencia_fim, "renovavel": c.renovavel, "necessidade_continuada": None, "status": c.status,
        "sla": None, "garantia": None, "metadados": None, "criado_em": espelho.carregado(c, "criado_em"),
    }


# modelo antigo → (tabela nova, origem_tabela, mapeamento)
# --- Volta (Phase J1, preparação da S6): linha unificada → registro no formato antigo ------------
# Mesmos ids (os de origem) e campos que `licitacoes.como_dict`, `documentos.como_dict` e `requisito_dict`
# leem; o arquivo e o texto das páginas não estão nas tabelas novas (TD-088).
def _float(valor):
    return float(valor) if valor is not None else None


def _data(valor):
    return datetime.fromisoformat(valor) if isinstance(valor, str) else valor


def licitacao_de(linha: dict) -> SimpleNamespace:
    extras = linha.get("metadados") or {}
    return SimpleNamespace(
        id=linha["origem_id"], tenant_id=linha["tenant_id"], titulo=linha["titulo"], objeto=linha["descricao"],
        orgao_nome=linha["emissor_nome"], orgao_cnpj=linha["emissor_cnpj"], conta_id=linha["conta_id"], oferta_id=linha["oferta_id"],
        modalidade=extras.get("modalidade"), fonte=linha["fonte"], fonte_id_externo=linha["fonte_id_externo"], fonte_url=linha["fonte_url"],
        data_publicacao=linha["publicado_em"], prazo_proposta=linha["prazo"], prazo_esclarecimento=_data(extras.get("prazo_esclarecimento")),
        valor_estimado=_float(linha["valor_estimado"]), status=linha["status"], responsavel_usuario_id=linha["responsavel_usuario_id"],
        concorrentes=extras.get("concorrentes"), parceiros=extras.get("parceiros"), vencedor=extras.get("vencedor"),
        valor_proposta=_float(extras.get("valor_proposta")), motivo_resultado=extras.get("motivo_resultado"), criado_em=linha["criado_em"],
    )


def documento_de(linha: dict, licitacao_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=linha["origem_id"], tenant_id=linha["tenant_id"], licitacao_id=licitacao_id, tipo=linha["tipo_documento"],
        nome_arquivo=linha["nome_arquivo"], tipo_mime=linha["tipo_mime"], tamanho_bytes=linha["tamanho_bytes"], sha256=linha["sha256"],
        paginas=linha["paginas"], fonte=linha["fonte"], fonte_url=linha["fonte_url"], status_analise=linha["status_extracao"],
        analisado_em=linha["analisado_em"], enviado_por_usuario_id=linha["enviado_por_usuario_id"], criado_em=linha["criado_em"],
    )


def requisito_de(linha: dict, licitacao_id: int, documento_id: int | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=linha["origem_id"], tenant_id=linha["tenant_id"], licitacao_id=licitacao_id, documento_id=documento_id,
        categoria=linha["categoria"], descricao=linha["texto"], evidencia=linha["trecho"], pagina=linha["pagina"],
        clausula=linha["clausula"], obrigatorio=linha["obrigatorio"], resposta=linha["resposta"],
        origem="ia" if linha["fonte"] == "AI" else "manual", status=linha["status_revisao"],
        conformidade_manual=linha["conformidade_manual"], justificativa_manual=linha["justificativa_manual"],
        revisado_por_usuario_id=linha["revisado_por_usuario_id"], revisado_em=linha["revisado_em"],
        correlation_id=linha["correlation_id"], criado_em=linha["criado_em"],
    )


MAPA = {
    Licitacao: ("processo", "licitacao", processo),
    DocumentoLicitacao: ("documento", "documento_licitacao", documento),
    RequisitoLicitacao: ("requisito", "requisito_licitacao", requisito),
    ContratoVendaPublica: ("contrato", "contrato_venda_publica", contrato),
}


sincronizar = espelho.instalar(LADO, MAPA)
