"""Espelho do lado vendedor nas tabelas unificadas (S3, D-055).

Mapeamento único de licitação, documento, requisito e contrato ganho para
`*_sourcing` com lado SELL. Usado pelos eventos do ORM (toda escrita nas
tabelas antigas é copiada na mesma transação) e pelo backfill idempotente.
A leitura dupla (`repositorio.py`) compara com estes mesmos mapeamentos.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session

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
    empresa = fluxo.empresa(lic.modalidade)
    regras = fluxo.regras_de(lic.modalidade)
    return {
        "tenant_id": lic.tenant_id,
        "segmento": tipos.Segmento.EMPRESA.value if empresa else tipos.Segmento.PUBLICO.value,
        "tipo_processo": "RFP" if empresa else (lic.modalidade if lic.modalidade in tipos.TIPOS_PROCESSO else "PUBLIC_TENDER"),
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
        "workflow": fluxo.de(lic.modalidade).codigo,
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
        "pagina": req.pagina, "clausula": req.clausula, "trecho": req.evidencia,
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
MAPA = {
    Licitacao: ("processo", "licitacao", processo),
    DocumentoLicitacao: ("documento", "documento_licitacao", documento),
    RequisitoLicitacao: ("requisito", "requisito_licitacao", requisito),
    ContratoVendaPublica: ("contrato", "contrato_venda_publica", contrato),
}


def _gravar(conexao, alvo) -> None:
    tabela, origem, mapear = MAPA[type(alvo)]
    espelho.protegido(conexao, f"{origem}:{alvo.id}",
                      lambda: espelho.gravar(conexao, tabela, LADO, origem, alvo.id, mapear(alvo)))


def _apagar(conexao, alvo) -> None:
    tabela, origem, _ = MAPA[type(alvo)]
    espelho.protegido(conexao, f"{origem}:{alvo.id}", lambda: espelho.apagar(conexao, tabela, LADO, origem, alvo.id))


for _modelo in MAPA:
    event.listen(_modelo, "after_insert", lambda mapper, conexao, alvo: _gravar(conexao, alvo))
    event.listen(_modelo, "after_update", lambda mapper, conexao, alvo: _gravar(conexao, alvo))
    event.listen(_modelo, "after_delete", lambda mapper, conexao, alvo: _apagar(conexao, alvo))


def sincronizar(db: Session, tenant_id: str | None = None, lote: int = 500) -> dict:
    """Backfill idempotente: regrava tudo do lado vendedor, pais antes de filhas,
    e remove o que perdeu a origem. Em lotes, com commit por lote."""
    relatorio = {}
    conexao = db.connection()
    for modelo, (tabela, origem, mapear) in MAPA.items():
        consulta = db.query(modelo)
        if tenant_id:
            consulta = consulta.filter(modelo.tenant_id == tenant_id)
        ids, ultimo = set(), 0
        while True:
            linhas = consulta.filter(modelo.id > ultimo).order_by(modelo.id).limit(lote).all()
            if not linhas:
                break
            for linha in linhas:
                espelho.gravar(conexao, tabela, LADO, origem, linha.id, mapear(linha))
                ids.add(linha.id)
            ultimo = linhas[-1].id
            db.commit()
            conexao = db.connection()
        orfaos = 0 if tenant_id else espelho.apagar_orfaos(conexao, tabela, LADO, origem, ids)
        db.commit()
        conexao = db.connection()
        relatorio[origem] = {"espelhados": len(ids), "orfaos_removidos": orfaos}
    return relatorio


espelho.registrar_sincronizador(LADO, sincronizar)
