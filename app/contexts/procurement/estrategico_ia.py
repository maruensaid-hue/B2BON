"""Intelligence do Strategic Sourcing (Phase G, D-067) — Requirement AI e Evaluation AI do comprador privado.

Tudo pela arquitetura de IA existente: AI Gateway → Model Router → Usage
Ledger → AI Credits, uma execução de crédito por operação (workloads do
catálogo: `procurement_document_intelligence` e
`procurement_complex_comparison`). A IA só sugere; nada entra sem revisão.

Grounding (o mesmo contrato do Bid Intelligence):
- Requirement AI: Requirement Engine compartilhado, perfil `especificacao_compra`;
  só entra requisito com trecho literal da especificação, página calculada pelo
  sistema, obrigatoriedade lida do próprio trecho. Vira requisito **sugerido**,
  invisível ao fornecedor e fora da comparação até um humano confirmar.
- Evaluation AI: cada proposta vai numa chamada própria, só com o texto dela
  (respostas, observações, anexos) — nunca o de outro fornecedor. Sugestão sem
  trecho literal da própria proposta é descartada; falta de evidência é
  UNKNOWN, nunca "não atende". A avaliação só vale quando o avaliador registra.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.intelligence.contract import ContextoIA, estimar, execucao, gerar, prompt_seguro
from app.contexts.procurement import estrategico
from app.contexts.shared import grounding, texto
from app.contexts.shared.documentos import extrair_paginas
from app.contexts.sourcing import contract as sourcing
from app.contexts.sourcing.contract import nativo, tipos
from app.core.observability import correlation_id_atual
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

LADO = estrategico.LADO
FEATURE_ESPECIFICACAO = "sourcing.analise_especificacao"
FEATURE_AVALIACAO = "sourcing.avaliacao_propostas"
MAXIMO_DOCUMENTOS = 20
MAXIMO_PROPOSTAS = 10
CARACTERES_POR_PROPOSTA = 40_000
STATUS_SUGERIVEIS = ("COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT")

_SISTEMA_ESPECIFICACAO = (
    "Você apoia o comprador de uma empresa a montar um processo de compra privado (RFI, RFP, RFQ). Extraia da "
    "especificação os requisitos técnicos e comerciais, qualificação exigida, SLAs, garantias, prazos e as perguntas "
    "que os fornecedores devem responder. Responda SOMENTE com um array JSON de itens "
    '{"categoria": uma de ' + ", ".join(estrategico.CATEGORIAS) + ', "descricao": frase curta em português, "citacao": '
    'trecho COPIADO LITERALMENTE do documento, "clausula": número do item como aparece no documento ou null}. '
    "Sem trecho literal, não inclua. Se não houver nada, responda []."
)
_SISTEMA_AVALIACAO = (
    "Você apoia o avaliador de um processo de compra. Recebe os requisitos (com id) e a proposta de UM fornecedor. "
    "Para cada requisito que a proposta trata, responda SOMENTE com um array JSON de itens "
    '{"requisito_id": id, "status": COMPLIANT | PARTIALLY_COMPLIANT | NON_COMPLIANT, "citacao": trecho COPIADO '
    'LITERALMENTE da proposta que sustenta o status, "justificativa": frase curta}. Requisito que a proposta não trata: '
    "não inclua (não é não atendimento). Não compare com outros fornecedores. Se não houver nada, responda []."
)


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def perfil() -> sourcing.requisitos.PerfilExtracao:
    return sourcing.requisitos.PerfilExtracao(nome="especificacao_compra", sistema=_SISTEMA_ESPECIFICACAO,
                                              categorias=estrategico.CATEGORIAS, max_tokens=6000)


# --- Documento de especificação do processo ---------------------------------------------------
def enviar_documento(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, nome_arquivo: str, tipo_mime: str,
                     conteudo: bytes, classificacao: str = "CONFIDENTIAL"):
    processo = estrategico.obter(db, tenant_id, processo_id)
    if classificacao not in ("CONFIDENTIAL", "RESTRICTED"):
        raise ValidacaoFalhou(f"Classificação inválida: {classificacao}")
    arquivo = sourcing.documentos.preparar(conteudo, tipo_mime)
    existentes = nativo.listar(db, "documento", LADO, tenant_id, processo_id=processo.id)
    if any(d.sha256 == arquivo.sha256 for d in existentes):
        raise RegraNegocioViolada("Este arquivo já foi enviado.")
    if len(existentes) >= MAXIMO_DOCUMENTOS:
        raise RegraNegocioViolada(f"Limite de {MAXIMO_DOCUMENTOS} documentos por processo.")
    documento = nativo.criar(
        db, "documento", LADO, tenant_id, processo_id=processo.id, tipo_documento="ESPECIFICACAO", nome_arquivo=nome_arquivo[:255],
        tipo_mime=tipo_mime, tamanho_bytes=arquivo.tamanho_bytes, sha256=arquivo.sha256, paginas=len(arquivo.paginas),
        paginas_texto=arquivo.paginas, conteudo=conteudo, fonte="UPLOAD", classificacao=classificacao,
        status_extracao=arquivo.status_inicial, enviado_por_usuario_id=usuario_id, criado_em=_agora(),
    )
    estrategico._auditar(db, tenant_id, usuario_id, "sourcing_documento_enviado", processo.id,
                         {"documento_id": documento.id, "sha256": documento.sha256})
    db.commit()
    return documento


def obter_documento(db: Session, tenant_id: str, documento_id: int):
    documento = nativo.obter(db, "documento", LADO, tenant_id, documento_id)
    estrategico.obter(db, tenant_id, documento.processo_id)  # só documento de processo do Strategic Sourcing
    return documento


def estimar_analise(db: Session, tenant_id: str, documento_id: int) -> dict:
    documento = obter_documento(db, tenant_id, documento_id)
    return estimar(db, FEATURE_ESPECIFICACAO, {"paginas": documento.paginas})


def analisar_documento(db: Session, llm: LLMProvider, tenant_id: str, usuario_id: int | None, documento_id: int,
                       confirmado: bool = False) -> dict:
    documento = obter_documento(db, tenant_id, documento_id)
    processo = estrategico.obter(db, tenant_id, documento.processo_id)
    estrategico._editavel(processo)
    sourcing.documentos.exigir_analisavel(documento.status_extracao, documento.classificacao)
    paginas: list[str] = documento.paginas_texto or []
    base = ContextoIA(tenant_id=tenant_id, feature=FEATURE_ESPECIFICACAO, usuario_id=usuario_id, entidade_tipo="documento_sourcing",
                      entidade_id=documento.id)
    extracao = sourcing.requisitos.extrair(db, llm, base, paginas, perfil(), f"ESPECIFICACAO {documento.nome_arquivo}", confirmado)
    existentes = {texto.normalizar(r.texto) for r in nativo.listar(db, "requisito", LADO, tenant_id, processo_id=processo.id)}
    sugeridos = 0
    for item in extracao.itens:
        chave = texto.normalizar(item.descricao)
        if chave in existentes:
            continue
        existentes.add(chave)
        nativo.criar(
            db, "requisito", LADO, tenant_id, processo_id=processo.id, documento_id=documento.id, categoria=item.categoria,
            texto=item.descricao[:1000], fonte="AI", pagina=item.pagina, clausula=item.clausula, trecho=item.evidencia,
            obrigatorio=item.obrigatorio, confianca="grounded", status_revisao="sugerido", correlation_id=correlation_id_atual(),
            criado_em=_agora(),
        )
        sugeridos += 1
    nativo.atualizar(db, documento, status_extracao="ANALISADO", analisado_em=_agora())
    db.commit()
    return {"documento_id": documento.id, "sugeridos": sugeridos, "descartados_sem_evidencia": extracao.sem_evidencia,
            "paginas_analisadas": extracao.paginas_analisadas, "paginas_total": extracao.paginas_total,
            "analise_parcial": extracao.parcial}


def revisar_requisito(db: Session, tenant_id: str, usuario_id: int | None, requisito_id: int, confirmar: bool,
                      peso: float | None = None, obrigatorio: bool | None = None):
    """Revisão humana da sugestão: confirmar (passa a valer no processo) ou descartar."""
    requisito = nativo.obter(db, "requisito", LADO, tenant_id, requisito_id)
    processo = estrategico.obter(db, tenant_id, requisito.processo_id)
    estrategico._editavel(processo)
    if requisito.status_revisao != "sugerido":
        raise RegraNegocioViolada("Requisito já revisado.")
    if peso is not None and peso <= 0:
        raise ValidacaoFalhou("Peso deve ser positivo.")
    campos = {"status_revisao": "confirmado" if confirmar else "descartado", "revisado_por_usuario_id": usuario_id,
              "revisado_em": _agora()}
    if confirmar:
        campos.update(peso=peso, obrigatorio=obrigatorio if obrigatorio is not None else requisito.obrigatorio)
    nativo.atualizar(db, requisito, **campos)
    estrategico._auditar(db, tenant_id, usuario_id, "sourcing_requisito_" + ("confirmado" if confirmar else "descartado"),
                         processo.id, {"requisito_id": requisito.id})
    db.commit()
    return requisito


# --- Evaluation AI: sugestão por proposta, ancorada na própria proposta ------------------------
def estimar_avaliacao(db: Session, tenant_id: str, processo_id: int) -> dict:
    processo = estrategico.obter(db, tenant_id, processo_id)
    ultimas = estrategico.ultimas_rodadas(nativo.listar(db, "proposta", LADO, tenant_id, processo_id=processo.id))
    return estimar(db, FEATURE_AVALIACAO, {"propostas": min(len(ultimas), MAXIMO_PROPOSTAS)})


def _texto_da_proposta(db: Session, tenant_id: str, proposta, respostas: list, requisitos: dict) -> tuple[str, str]:
    """(texto rotulado para a IA, só o que o fornecedor escreveu). O grounding usa o segundo: o rótulo cita o
    texto do requisito, que não pode servir de evidência de que a proposta o atende."""
    partes = [("Observações", proposta.observacoes), ("Condições de pagamento", proposta.condicoes_pagamento)]
    partes += [(f"Resposta ao requisito {a.requisito_id}", a.resposta) for a in respostas if a.resposta and a.requisito_id in requisitos]
    for anexo in nativo.listar(db, "anexo", LADO, tenant_id, proposta_id=proposta.id):
        partes.append((f"Anexo {anexo.nome_arquivo}", "\n".join(extrair_paginas(anexo.conteudo, anexo.tipo_mime))))
    partes = [(rotulo, conteudo) for rotulo, conteudo in partes if conteudo and conteudo.strip()]
    return "\n".join(f"{rotulo}: {conteudo}" for rotulo, conteudo in partes), "\n".join(c for _, c in partes)


def sugerir_avaliacoes(db: Session, llm: LLMProvider, tenant_id: str, usuario_id: int | None, processo_id: int,
                       confirmado: bool = False) -> dict:
    processo = estrategico.obter(db, tenant_id, processo_id)
    if processo.status not in ("EM_AVALIACAO", "EM_NEGOCIACAO"):
        raise RegraNegocioViolada("A sugestão de avaliação é feita com o processo em avaliação ou negociação.")
    requisitos = {r.id: r for r in estrategico.requisitos_vigentes(db, tenant_id, processo.id) if r.categoria != "PERGUNTA"}
    if not requisitos:
        raise RegraNegocioViolada("O processo não tem requisitos confirmados para avaliar.")
    participantes = {p.id: p for p in nativo.listar(db, "participante", LADO, tenant_id, processo_id=processo.id)}
    ultimas = [p for pid, p in estrategico.ultimas_rodadas(nativo.listar(db, "proposta", LADO, tenant_id, processo_id=processo.id)).items()
               if participantes[pid].status not in ("DESQUALIFICADO", "DECLINOU")]
    if not ultimas:
        raise RegraNegocioViolada("Não há propostas para avaliar.")
    analisadas = ultimas[:MAXIMO_PROPOSTAS]
    respostas = nativo.listar(db, "avaliacao", LADO, tenant_id, proposta_id=[p.id for p in analisadas])
    catalogo = "\n".join(f"- id {r.id} [{r.categoria}{', obrigatório' if r.obrigatorio else ''}]: {r.texto}" for r in requisitos.values())
    base = ContextoIA(tenant_id=tenant_id, feature=FEATURE_AVALIACAO, usuario_id=usuario_id, entidade_tipo="processo_sourcing",
                      entidade_id=processo.id)
    fontes: dict[int, str] = {}
    chamadas = []
    # Processo inteiro = uma execução de crédito, uma chamada por proposta (cada uma só com o próprio texto).
    with execucao(db, base, parametros={"propostas": len(analisadas)}, confirmado=confirmado) as ctx:
        for proposta in analisadas:
            rotulado, fontes[proposta.id] = _texto_da_proposta(db, tenant_id, proposta,
                                                               [a for a in respostas if a.proposta_id == proposta.id], requisitos)
            if not rotulado:
                continue
            chamadas.append((proposta, gerar(db, llm, ctx, LLMRequest(
                system=_SISTEMA_AVALIACAO,
                prompt=f"Requisitos:\n{catalogo}\n\n" + prompt_seguro.bloco_dados_externos(
                    f"proposta rodada {proposta.rodada}", rotulado[:CARACTERES_POR_PROPOSTA]),
                max_tokens=4000,
            ))))
    db.commit()  # liquidação do crédito da execução
    sugestoes, descartadas = [], 0
    for proposta, resposta in chamadas:
        vistos: set[int] = set()
        for item in grounding.itens_json(resposta.content):
            requisito_id, status = item.get("requisito_id"), str(item.get("status") or "").upper()
            citacao = str(item.get("citacao") or "").strip()[:2000]
            if (requisito_id not in requisitos or requisito_id in vistos or status not in STATUS_SUGERIVEIS
                    or not texto.contem_literal(fontes[proposta.id], citacao)):
                descartadas += 1
                continue
            vistos.add(requisito_id)
            sugestoes.append({"proposta_id": proposta.id, "participante_id": proposta.participante_id,
                              "participante": participantes[proposta.participante_id].nome, "requisito_id": requisito_id,
                              "status": status, "citacao": citacao,
                              "justificativa": str(item.get("justificativa") or "").strip()[:500] or None})
    return {
        "processo_id": processo.id, "sugestoes": sugestoes, "descartadas_sem_evidencia": descartadas,
        "propostas_analisadas": len(chamadas), "parcial": len(ultimas) > MAXIMO_PROPOSTAS or any(
            len(f) > CARACTERES_POR_PROPOSTA for f in fontes.values()),
        "status_possiveis": [s for s in tipos.STATUS_CONFORMIDADE],
        "aviso": "Sugestões da IA, cada uma com o trecho da própria proposta. A avaliação só vale quando o avaliador a registra.",
    }


def documento_dict(documento) -> dict:
    return {"id": documento.id, "nome_arquivo": documento.nome_arquivo, "paginas": documento.paginas, "sha256": documento.sha256,
            "classificacao": documento.classificacao, "status_extracao": documento.status_extracao,
            "analisado_em": documento.analisado_em}
