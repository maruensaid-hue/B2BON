"""Espelho do lado comprador nas tabelas unificadas (S3, D-055).

Mapeamento único de processo, documento (e seus achados em JSON, que viram
requisitos por posição), contrato, evento do processo e evento de contrato
para `*_sourcing` com lado BUY. Só este contexto conhece estes modelos
(barreira Buy/Sell); o núcleo recebe os valores já mapeados.
"""

from datetime import datetime, time

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.contexts.sourcing.contract import espelho, tipos
from app.models.contrato_compra import ContratoCompra
from app.models.documento_compras import DocumentoCompras
from app.models.evento_contrato_compra import EventoContratoCompra
from app.models.evento_processo import EventoProcesso
from app.models.processo_contratacao import ProcessoContratacao

LADO = tipos.Lado.COMPRA
ORIGEM_ACHADOS = "documento_compras.achados"


def processo(p: ProcessoContratacao) -> dict:
    return {
        "tenant_id": p.tenant_id,
        "segmento": tipos.Segmento.PUBLICO.value,
        "tipo_processo": p.modalidade if p.modalidade in tipos.TIPOS_PROCESSO else "PUBLIC_TENDER",
        "titulo": (f"{p.numero} — " if p.numero else "") + (p.objeto or "")[:200],
        "descricao": p.objeto,
        "emissor_nome": None,  # o emissor é o próprio órgão do tenant (orgao_id em metadados)
        "emissor_cnpj": None,
        "conta_id": None,
        "oferta_id": None,
        "status": p.status,
        "visibilidade": "PRIVADO",
        "classificacao": "CONFIDENTIAL",
        "ruleset": "PUBLIC_PROCUREMENT_BR_14133@1",
        "workflow": "PUBLIC_PROCUREMENT_BUY@1",
        "publicado_em": p.publicado_em,
        "prazo": datetime.combine(p.prazo_previsto, time.min) if p.prazo_previsto else None,
        "valor_estimado": p.valor_estimado,
        "moeda": "BRL",
        "valor_sigiloso": bool(p.valor_sigiloso),
        "responsavel_usuario_id": p.responsavel_usuario_id,
        "fonte": "MANUAL",
        "fonte_id_externo": None,
        "fonte_url": None,
        "metadados": {"orgao_id": p.orgao_id, "unidade_id": p.unidade_id, "item_pca_id": p.item_pca_id, "numero": p.numero,
                      "modalidade": p.modalidade, "categoria": p.categoria, "demanda_ids": p.demanda_ids},
        "criado_em": espelho.carregado(p, "criado_em"),
    }


def documento(d: DocumentoCompras) -> dict:
    return {
        "tenant_id": d.tenant_id, "processo_origem": ("processo_contratacao", d.processo_id) if d.processo_id else None,
        "contrato_origem": ("contrato_compra", d.contrato_id) if d.contrato_id else None,
        "tipo_documento": d.tipo, "nome_arquivo": d.nome_arquivo, "tipo_mime": d.tipo_mime, "tamanho_bytes": d.tamanho_bytes,
        "sha256": d.sha256, "paginas": d.paginas or 0, "fonte": d.fonte, "fonte_url": d.fonte_url, "classificacao": d.classificacao,
        "versao": 1, "status_extracao": d.status_analise, "analisado_em": None,
        "enviado_por_usuario_id": d.enviado_por_usuario_id, "criado_em": espelho.carregado(d, "criado_em"),
    }


def requisitos_do_documento(d: DocumentoCompras) -> list[dict]:
    return [
        {"tenant_id": d.tenant_id, "processo_origem": ("processo_contratacao", d.processo_id) if d.processo_id else None,
         "documento_origem": ("documento_compras", d.id), "categoria": a.get("categoria") or "OUTRO",
         "texto": a.get("descricao") or "", "fonte": "AI", "pagina": a.get("pagina"), "clausula": a.get("clausula"),
         "trecho": a.get("evidencia"), "confianca": "grounded", "status_revisao": a.get("status") or "sugerido",
         "correlation_id": a.get("correlation_id")}
        for a in (d.achados or [])
    ]


def contrato(c: ContratoCompra) -> dict:
    return {
        "tenant_id": c.tenant_id, "processo_origem": ("processo_contratacao", c.processo_id) if c.processo_id else None,
        "contraparte_nome": None, "conta_id": None, "fornecedor_id": c.fornecedor_id, "numero": c.numero, "objeto": c.objeto,
        "categoria": c.categoria, "valor_inicial": c.valor_inicial, "valor_atual": c.valor_atual,
        "vigencia_inicio": c.vigencia_inicio, "vigencia_fim": c.vigencia_fim, "renovavel": None,
        "necessidade_continuada": bool(c.necessidade_continuada), "status": c.status, "sla": c.sla, "garantia": c.garantia,
        "metadados": {"orgao_id": c.orgao_id}, "criado_em": espelho.carregado(c, "criado_em"),
    }


def evento(e: EventoProcesso) -> dict:
    return {
        "tenant_id": e.tenant_id, "processo_origem": ("processo_contratacao", e.processo_id), "tipo": e.tipo,
        "descricao": e.descricao, "status": e.status, "prazo": e.prazo, "responsavel_usuario_id": e.responsavel_usuario_id,
        "criado_por_usuario_id": e.criado_por_usuario_id, "concluido_em": e.concluido_em,
        "criado_em": espelho.carregado(e, "criado_em"),
    }


def evento_contrato(e: EventoContratoCompra) -> dict:
    return {
        "tenant_id": e.tenant_id, "contrato_origem": ("contrato_compra", e.contrato_id) if e.contrato_id else None,
        "fornecedor_id": e.fornecedor_id, "tipo": e.tipo, "descricao": e.descricao, "valor": e.valor, "nota": e.nota,
        "data": e.data, "criado_por_usuario_id": e.criado_por_usuario_id, "criado_em": espelho.carregado(e, "criado_em"),
    }


MAPA = {
    ProcessoContratacao: ("processo", "processo_contratacao", processo),
    ContratoCompra: ("contrato", "contrato_compra", contrato),
    DocumentoCompras: ("documento", "documento_compras", documento),
    EventoProcesso: ("evento", "evento_processo", evento),
    EventoContratoCompra: ("evento_contrato", "evento_contrato_compra", evento_contrato),
}


def _gravar_linha(conexao, alvo) -> None:
    tabela, origem, mapear = MAPA[type(alvo)]
    espelho.gravar(conexao, tabela, LADO, origem, alvo.id, mapear(alvo))
    if isinstance(alvo, DocumentoCompras):
        espelho.substituir_requisitos(conexao, LADO, ORIGEM_ACHADOS, alvo.id, requisitos_do_documento(alvo))


def _gravar(conexao, alvo) -> None:
    _, origem, _ = MAPA[type(alvo)]
    espelho.protegido(conexao, f"{origem}:{alvo.id}", lambda: _gravar_linha(conexao, alvo))


def _apagar(conexao, alvo) -> None:
    tabela, origem, _ = MAPA[type(alvo)]
    espelho.protegido(conexao, f"{origem}:{alvo.id}", lambda: espelho.apagar(conexao, tabela, LADO, origem, alvo.id))


for _modelo in MAPA:
    event.listen(_modelo, "after_insert", lambda mapper, conexao, alvo: _gravar(conexao, alvo))
    event.listen(_modelo, "after_update", lambda mapper, conexao, alvo: _gravar(conexao, alvo))
    event.listen(_modelo, "after_delete", lambda mapper, conexao, alvo: _apagar(conexao, alvo))


def sincronizar(db: Session, tenant_id: str | None = None, lote: int = 500) -> dict:
    """Backfill idempotente do lado comprador (pais antes de filhas), em lotes."""
    relatorio = {}
    conexao = db.connection()
    for modelo, (tabela, origem, _) in MAPA.items():
        consulta = db.query(modelo)
        if tenant_id:
            consulta = consulta.filter(modelo.tenant_id == tenant_id)
        ids, ultimo = set(), 0
        while True:
            linhas = consulta.filter(modelo.id > ultimo).order_by(modelo.id).limit(lote).all()
            if not linhas:
                break
            for linha in linhas:
                _gravar_linha(conexao, linha)
                ids.add(linha.id)
            ultimo = linhas[-1].id
            db.commit()
            conexao = db.connection()
        orfaos = 0 if tenant_id else espelho.apagar_orfaos(conexao, tabela, LADO, origem, ids)
        if modelo is DocumentoCompras and not tenant_id:
            orfaos += espelho.apagar_orfaos(conexao, "requisito", LADO, ORIGEM_ACHADOS, ids)
        db.commit()
        conexao = db.connection()
        relatorio[origem] = {"espelhados": len(ids), "orfaos_removidos": orfaos}
    return relatorio


espelho.registrar_sincronizador(LADO, sincronizar)
