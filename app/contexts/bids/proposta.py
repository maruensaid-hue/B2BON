"""Apoio à proposta (Phase C, plano unificado §9 e §12): esboço determinístico.

C0 — sem IA, 0 AI Credits. Monta, a partir do que já existe (requisitos
revisados, matriz de conformidade, respostas digitadas e cofre), o roteiro
da proposta/resposta: cada requisito com obrigatoriedade, conformidade,
nossa evidência e a resposta; as **pendências** que impedem enviar; os
documentos do cofre a anexar; e a prontidão. Não escreve texto em nome da
empresa: onde falta resposta, fica pendência.
"""

from sqlalchemy.orm import Session

from app.contexts.bids import conformidade, fluxo, licitacoes
from app.models.licitacao import Licitacao

FONTE = "bids.proposta.v1"
PENDENTES = ("NON_COMPLIANT", "UNKNOWN", "REQUIRES_REVIEW", "PARTIALLY_COMPLIANT")


def montar(db: Session, tenant_id: str, licitacao: Licitacao) -> dict:
    matriz = {linha["requisito_id"]: linha for linha in conformidade.calcular(db, tenant_id, licitacao)["linhas"]}
    segmento, tipo_processo = fluxo.classificar(licitacao.modalidade)
    itens, pendencias, anexos = [], [], {}
    for req in licitacoes.listar_requisitos(db, tenant_id, licitacao.id):
        linha = matriz.get(req.id)
        status = linha["status"] if linha else None
        itens.append({
            "requisito_id": req.id, "categoria": req.categoria, "requisito": req.descricao, "obrigatorio": req.obrigatorio,
            "revisao": req.status, "conformidade": status, "motivo": linha["motivo"] if linha else None,
            "nossa_evidencia": linha["evidencia"] if linha else [], "trecho_do_emissor": req.evidencia,
            "pagina": req.pagina, "clausula": req.clausula, "resposta": req.resposta,
        })
        if req.status == "sugerido":
            pendencias.append({"requisito_id": req.id, "tipo": "REVISAR", "mensagem": f"Revisar o requisito sugerido: {req.descricao}"})
        if req.categoria == "PERGUNTA" and not req.resposta:
            pendencias.append({"requisito_id": req.id, "tipo": "RESPONDER", "mensagem": f"Responder: {req.descricao}"})
        if req.obrigatorio is True and status in PENDENTES:
            pendencias.append({"requisito_id": req.id, "tipo": "COMPROVAR",
                               "mensagem": f"Obrigatório sem comprovação completa ({status}): {req.descricao}"})
        for evidencia in (linha["evidencia"] if linha and status == "COMPLIANT" else []):
            if evidencia.get("tipo") == "cofre":
                anexos[evidencia["id"]] = {"id": evidencia["id"], "nome": evidencia["nome"], "valido_ate": evidencia["valido_ate"]}
    com_pendencia = {p["requisito_id"] for p in pendencias}
    return {
        "licitacao": {"id": licitacao.id, "titulo": licitacao.titulo, "emissor": licitacao.orgao_nome, "objeto": licitacao.objeto,
                      "segmento": segmento.value, "tipo_processo": tipo_processo, "prazo_proposta": licitacao.prazo_proposta,
                      "status": licitacao.status},
        "itens": itens,
        "pendencias": pendencias,
        "anexos": list(anexos.values()),
        "prontidao": round(1 - len(com_pendencia) / len(itens), 2) if itens else None,  # None: sem requisito, sem medida
        "fonte": FONTE,
        "uso_ia": "nenhum (C0): esboço montado só com dados já revisados",
    }


def markdown(esboco: dict) -> str:
    lic = esboco["licitacao"]
    linhas = [f"# Proposta — {lic['titulo']}", "", f"- Emissor: {lic['emissor'] or 'não informado'}",
              f"- Tipo: {lic['tipo_processo']} ({lic['segmento']})",
              f"- Prazo: {lic['prazo_proposta']:%d/%m/%Y %H:%M}" if lic["prazo_proposta"] else "- Prazo: não informado",
              "", "## Requisitos e respostas", ""]
    for item in esboco["itens"]:
        marca = {True: "obrigatório", False: "desejável"}.get(item["obrigatorio"], "obrigatoriedade não identificada")
        onde = f"pág. {item['pagina']}" + (f", cláusula {item['clausula']}" if item["clausula"] else "") if item["pagina"] else "manual"
        linhas.append(f"### {item['categoria']} — {item['requisito']} ({marca}; {onde})")
        linhas.append(f"- Conformidade: {item['conformidade'] or 'fora da matriz'}" + (f" — {item['motivo']}" if item["motivo"] else ""))
        linhas.append(f"- Resposta: {item['resposta'] or '_pendente_'}")
        linhas.append("")
    if esboco["anexos"]:
        linhas += ["## Documentos a anexar (cofre)", ""] + [f"- {a['nome']}" for a in esboco["anexos"]] + [""]
    if esboco["pendencias"]:
        linhas += ["## Pendências antes de enviar", ""] + [f"- [ ] {p['mensagem']}" for p in esboco["pendencias"]] + [""]
    return "\n".join(linhas)
