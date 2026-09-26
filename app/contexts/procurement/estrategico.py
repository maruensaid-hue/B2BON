"""Enterprise Strategic Sourcing — lado comprador privado (Phase E, D-065).

Fluxo (§11): necessidade → projeto de sourcing → descoberta de fornecedores
→ RFI/RFP/RFQ → respostas → avaliação por requisito → comparação → shortlist
→ negociação por rodadas → aprovação humana → adjudicação → contrato.

Tudo sobre os engines compartilhados: modelo unificado via repositório
nativo do núcleo (lado BUY fixo), workflow resolvido por tipo de processo,
Evaluation Engine na direção PROPOSTA, Matching Engine na descoberta.
Determinístico (C0): nenhuma chamada de IA aqui; a decisão é sempre humana.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.network.contract import privacidade
from app.contexts.procurement import fluxo
from app.contexts.shared import matching
from app.contexts.sourcing.contract import nativo, tipos
from app.models.fornecedor_compras import FornecedorCompras
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

LADO = tipos.Lado.COMPRA
CATEGORIAS = ("REQUISITO_TECNICO", "REQUISITO_COMERCIAL", "QUALIFICACAO", "SLA", "GARANTIA", "PRAZO", "PERGUNTA", "OUTRO")
STATUS_PARTICIPANTE = ("CONVIDADO", "RESPONDEU", "DECLINOU", "QUALIFICADO", "DESQUALIFICADO", "SHORTLIST", "ADJUDICADO",
                       "NAO_SELECIONADO")
PENDENTES = ("NON_COMPLIANT", "UNKNOWN", "REQUIRES_REVIEW", "PARTIALLY_COMPLIANT")


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _auditar(db: Session, tenant_id: str, usuario_id: int | None, evento: str, processo_id: int, detalhes: dict | None = None) -> None:
    auditoria_service.registrar(db, tenant_id, evento, "processo_sourcing", processo_id, str(usuario_id) if usuario_id else None,
                                detalhes or {})


# --- Processo -------------------------------------------------------------------------------
def criar_processo(db: Session, tenant_id: str, usuario_id: int | None, dados: dict):
    tipo = dados.get("tipo_processo")
    if tipo not in fluxo.TIPOS_EMPRESA:
        raise ValidacaoFalhou(f"Tipo de processo inválido: {tipo}")
    fluxo_processo, regras = fluxo.configuracao_empresa(tipo)
    processo = nativo.criar(
        db, "processo", LADO, tenant_id, segmento=tipos.Segmento.EMPRESA.value, tipo_processo=tipo, titulo=dados["titulo"],
        descricao=dados.get("descricao"), status=fluxo_processo.inicial, visibilidade="PRIVADO", classificacao="CONFIDENTIAL",
        workflow=fluxo_processo.codigo, ruleset=regras.codigo if regras else None, prazo=dados.get("prazo"),
        valor_estimado=dados.get("valor_estimado"), moeda=dados.get("moeda") or "BRL", valor_sigiloso=True,
        responsavel_usuario_id=usuario_id, fonte="MANUAL", metadados={}, criado_em=_agora(),
    )
    _auditar(db, tenant_id, usuario_id, "sourcing_processo_criado", processo.id, {"tipo": tipo})
    db.commit()
    return processo


def obter(db: Session, tenant_id: str, processo_id: int):
    processo = nativo.obter(db, "processo", LADO, tenant_id, processo_id)
    if processo.segmento != tipos.Segmento.EMPRESA.value:  # o processo público do comprador é o do Procurement
        raise NaoEncontrado(f"Processo {processo_id} não encontrado(a)")
    return processo


def listar(db: Session, tenant_id: str) -> list:
    return nativo.listar(db, "processo", LADO, tenant_id, ordem="-id", segmento=tipos.Segmento.EMPRESA.value)


def _fluxo(processo):
    return fluxo.configuracao_empresa(processo.tipo_processo)[0]


def mudar_status(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, status: str):
    processo = obter(db, tenant_id, processo_id)
    _fluxo(processo).validar(status, "status", de=processo.status)
    if status == "PUBLICADO" and not nativo.listar(db, "requisito", LADO, tenant_id, processo_id=processo.id) \
            and not nativo.listar(db, "item", LADO, tenant_id, processo_id=processo.id):
        raise RegraNegocioViolada("Cadastre ao menos um requisito ou item antes de publicar.")
    anterior = processo.status
    nativo.atualizar(db, processo, status=status, publicado_em=processo.publicado_em or (_agora() if status == "PUBLICADO" else None))
    _auditar(db, tenant_id, usuario_id, "sourcing_status", processo.id, {"de": anterior, "para": status})
    db.commit()
    return processo


def _editavel(processo) -> None:
    if processo.status not in ("RASCUNHO", "PUBLICADO"):
        raise RegraNegocioViolada("Requisitos e itens só mudam antes de receber propostas.")


# --- Requisitos (critérios) e itens (RFQ) ---------------------------------------------------
def adicionar_requisito(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, dados: dict):
    processo = obter(db, tenant_id, processo_id)
    _editavel(processo)
    if dados.get("categoria") not in CATEGORIAS:
        raise ValidacaoFalhou(f"Categoria inválida: {dados.get('categoria')}")
    peso = dados.get("peso")
    if peso is not None and peso <= 0:
        raise ValidacaoFalhou("Peso deve ser positivo.")
    requisito = nativo.criar(
        db, "requisito", LADO, tenant_id, processo_id=processo.id, categoria=dados["categoria"], texto=dados["texto"].strip()[:1000],
        fonte="MANUAL", obrigatorio=dados.get("obrigatorio"), peso=peso, confianca="manual", status_revisao="confirmado",
        revisado_por_usuario_id=usuario_id, revisado_em=_agora(), criado_em=_agora(),
    )
    db.commit()
    return requisito


def adicionar_item(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, dados: dict):
    processo = obter(db, tenant_id, processo_id)
    _editavel(processo)
    if not dados.get("quantidade") or dados["quantidade"] <= 0:
        raise ValidacaoFalhou("Quantidade deve ser positiva.")
    item = nativo.criar(db, "item", LADO, tenant_id, processo_id=processo.id, descricao=dados["descricao"].strip()[:300],
                        quantidade=dados["quantidade"], unidade=dados.get("unidade"), especificacao=dados.get("especificacao"))
    db.commit()
    return item


# --- Descoberta e convite (§16): só dado permitido ------------------------------------------
def descobrir(db: Session, tenant_id: str, processo_id: int, necessidade: str | None = None, ufs: list[str] | None = None,
              certificacoes: list[str] | None = None, limite: int = 20) -> dict:
    """Candidatos do cadastro interno do comprador (INTERNAL) e da Business Network (NETWORK: só perfis
    que o comprador pode ver — no diretório ou conexões, sem bloqueados; só campos públicos)."""
    processo = obter(db, tenant_id, processo_id)
    alvo = necessidade or f"{processo.titulo} {processo.descricao or ''}"
    ja = nativo.listar(db, "participante", LADO, tenant_id, processo_id=processo.id)
    convidados_internos = {p.fornecedor_id for p in ja if p.fornecedor_id}
    convidados_rede = {p.empresa_rede_tenant_id for p in ja if p.empresa_rede_tenant_id}
    candidatos = []
    for f in db.query(FornecedorCompras).filter_by(tenant_id=tenant_id).all():
        if f.id in convidados_internos:
            continue
        resultado = matching.combinar(matching.criterios_fornecedor(alvo, ufs or [], certificacoes or [],
                                                                     [*(f.categorias or []), f.razao_social], None, []))
        candidatos.append({"origem": "INTERNAL", "fornecedor_id": f.id, "nome": f.razao_social, "cnpj": f.cnpj,
                           "pontuacao": resultado.pontuacao, "motivos": resultado.motivos, "faltantes": resultado.faltantes})
    for perfil in privacidade.perfis_visiveis(db, tenant_id):
        if perfil.tenant_id in convidados_rede:
            continue
        oferta = [*(perfil.produtos_servicos or []), *(perfil.tecnologias or []), perfil.setor or "", perfil.descricao or ""]
        resultado = matching.combinar(matching.criterios_fornecedor(alvo, ufs or [], certificacoes or [], oferta, perfil.sede_uf,
                                                                     perfil.certificacoes or []))
        candidatos.append({"origem": "NETWORK", "empresa_rede_tenant_id": perfil.tenant_id, "nome": perfil.nome_exibicao,
                           "setor": perfil.setor, "sede_uf": perfil.sede_uf, "verificada": perfil.status_verificacao == "verificada",
                           "pontuacao": resultado.pontuacao, "motivos": resultado.motivos, "faltantes": resultado.faltantes})
    candidatos = [c for c in candidatos if c["pontuacao"] > 0]
    candidatos.sort(key=lambda c: -c["pontuacao"])
    return {"necessidade": alvo, "candidatos": candidatos[:limite],
            "aviso": "Aderência calculada só com dados permitidos: cadastro do próprio comprador e perfil público da rede."}


def convidar(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, dados: dict):
    processo = obter(db, tenant_id, processo_id)
    if processo.status in _fluxo(processo).finais:
        raise RegraNegocioViolada("Processo encerrado não recebe participantes.")
    if dados.get("fornecedor_id"):
        fornecedor = db.query(FornecedorCompras).filter_by(id=dados["fornecedor_id"], tenant_id=tenant_id).one_or_none()
        if fornecedor is None:
            raise ValidacaoFalhou("Fornecedor não encontrado no seu cadastro.")
        campos = {"fornecedor_id": fornecedor.id, "nome": fornecedor.razao_social, "cnpj": fornecedor.cnpj, "origem_descoberta": "INTERNAL"}
    elif dados.get("empresa_rede_tenant_id"):
        perfil = next((p for p in privacidade.perfis_visiveis(db, tenant_id) if p.tenant_id == dados["empresa_rede_tenant_id"]), None)
        if perfil is None:  # fora do diretório, bloqueada ou inexistente: não se convida o que não se pode ver
            raise ValidacaoFalhou("Empresa não disponível para convite.")
        campos = {"empresa_rede_tenant_id": perfil.tenant_id, "nome": perfil.nome_exibicao, "origem_descoberta": "NETWORK"}
    elif dados.get("nome"):
        campos = {"nome": dados["nome"].strip()[:200], "cnpj": dados.get("cnpj"), "origem_descoberta": "MANUAL"}
    else:
        raise ValidacaoFalhou("Informe o fornecedor (cadastro, rede ou nome).")
    participante = nativo.criar(db, "participante", LADO, tenant_id, processo_id=processo.id, status="CONVIDADO", **campos)
    _auditar(db, tenant_id, usuario_id, "sourcing_participante_convidado", processo.id, {"participante_id": participante.id})
    db.commit()
    return participante


def _participante(db: Session, tenant_id: str, processo, participante_id: int):
    participante = nativo.obter(db, "participante", LADO, tenant_id, participante_id)
    if participante.processo_id != processo.id:
        raise ValidacaoFalhou("Participante de outro processo.")
    return participante


def definir_participante(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, participante_id: int, status: str,
                         motivo: str | None):
    """Qualificação, desqualificação, declínio e shortlist: decisão humana, com motivo quando exclui."""
    processo = obter(db, tenant_id, processo_id)
    participante = _participante(db, tenant_id, processo, participante_id)
    if status not in ("QUALIFICADO", "DESQUALIFICADO", "DECLINOU", "SHORTLIST"):
        raise ValidacaoFalhou(f"Situação inválida: {status}")
    if status in ("DESQUALIFICADO", "DECLINOU") and not (motivo and motivo.strip()):
        raise ValidacaoFalhou("Informe o motivo.")
    if status == "SHORTLIST" and participante.status in ("DESQUALIFICADO", "DECLINOU"):
        raise RegraNegocioViolada("Participante desqualificado ou que declinou não entra na shortlist.")
    nativo.atualizar(db, participante, status=status, motivo=(motivo or "").strip() or None)
    _auditar(db, tenant_id, usuario_id, "sourcing_participante_" + status.lower(), processo.id, {"participante_id": participante.id})
    db.commit()
    return participante


# --- Respostas, propostas e rodadas (§13–§15) -----------------------------------------------
def registrar_proposta(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, dados: dict, canal: str = "COMPRADOR"):
    """Resposta (RFI) ou proposta (RFP/RFQ) recebida. Cada nova proposta do mesmo participante é uma rodada."""
    processo = obter(db, tenant_id, processo_id)
    if processo.status not in ("RECEBENDO_PROPOSTAS", "RECEBENDO_RESPOSTAS", "EM_NEGOCIACAO"):
        raise RegraNegocioViolada("O processo não está recebendo propostas nem em negociação.")
    participante = _participante(db, tenant_id, processo, dados["participante_id"])
    if participante.status in ("DESQUALIFICADO", "DECLINOU"):
        raise RegraNegocioViolada("Participante desqualificado ou que declinou não envia proposta.")
    if processo.status == "EM_NEGOCIACAO" and participante.status != "SHORTLIST" and processo.tipo_processo != "RFQ":
        raise RegraNegocioViolada("Na negociação, só quem está na shortlist envia nova rodada.")
    anteriores = nativo.listar(db, "proposta", LADO, tenant_id, processo_id=processo.id, participante_id=participante.id)
    itens = {i.id: i for i in nativo.listar(db, "item", LADO, tenant_id, processo_id=processo.id)}
    requisitos = {r.id for r in nativo.listar(db, "requisito", LADO, tenant_id, processo_id=processo.id)}
    precos = dados.get("itens") or []
    if any(p["item_id"] not in itens for p in precos) or any(r["requisito_id"] not in requisitos for r in dados.get("respostas") or []):
        raise ValidacaoFalhou("Item ou requisito de outro processo.")
    valor = dados.get("valor_total")
    if valor is None and precos:
        valor = round(sum(float(itens[p["item_id"]].quantidade) * p["preco_unitario"] for p in precos), 2)
    proposta = nativo.criar(
        db, "proposta", LADO, tenant_id, processo_id=processo.id, participante_id=participante.id, rodada=len(anteriores) + 1,
        tipo="RESPOSTA" if processo.tipo_processo in ("RFI", "EOI", "VENDOR_QUALIFICATION") else "PROPOSTA",
        valor_total=valor, moeda=dados.get("moeda") or processo.moeda, prazo_entrega_dias=dados.get("prazo_entrega_dias"),
        condicoes_pagamento=dados.get("condicoes_pagamento"), impostos_inclusos=dados.get("impostos_inclusos"),
        validade=dados.get("validade"), observacoes=dados.get("observacoes"), criado_por_usuario_id=usuario_id, canal=canal,
    )
    for preco in precos:
        nativo.criar(db, "proposta_item", LADO, tenant_id, proposta_id=proposta.id, item_id=preco["item_id"],
                     preco_unitario=preco["preco_unitario"])
    for resposta in dados.get("respostas") or []:
        nativo.criar(db, "avaliacao", LADO, tenant_id, proposta_id=proposta.id, requisito_id=resposta["requisito_id"],
                     resposta=(resposta.get("resposta") or "").strip()[:5000] or None)
    if participante.status == "CONVIDADO":
        nativo.atualizar(db, participante, status="RESPONDEU")
    _auditar(db, tenant_id, usuario_id, "sourcing_proposta_registrada", processo.id,
             {"participante_id": participante.id, "rodada": proposta.rodada, "canal": canal})  # sem valores no log
    db.commit()
    return proposta


def avaliar(db: Session, tenant_id: str, usuario_id: int | None, proposta_id: int, requisito_id: int, status: str,
            nota: float | None, justificativa: str | None):
    """Evaluation Engine, direção PROPOSTA: o avaliador humano decide o status de cada requisito."""
    proposta = nativo.obter(db, "proposta", LADO, tenant_id, proposta_id)
    requisito = nativo.obter(db, "requisito", LADO, tenant_id, requisito_id)
    if requisito.processo_id != proposta.processo_id:
        raise ValidacaoFalhou("Requisito de outro processo.")
    if status not in tipos.STATUS_CONFORMIDADE:
        raise ValidacaoFalhou(f"Status de conformidade inválido: {status}")
    if nota is not None and not 0 <= nota <= 10:
        raise ValidacaoFalhou("Nota vai de 0 a 10.")
    if status == "NON_COMPLIANT" and not (justificativa and justificativa.strip()):
        raise ValidacaoFalhou("Informe a justificativa de não atendimento.")
    existentes = nativo.listar(db, "avaliacao", LADO, tenant_id, proposta_id=proposta.id, requisito_id=requisito.id)
    campos = {"status": status, "nota": nota, "justificativa": (justificativa or "").strip() or None,
              "revisado_por_usuario_id": usuario_id, "revisado_em": _agora()}
    avaliacao = (nativo.atualizar(db, existentes[0], **campos) if existentes
                 else nativo.criar(db, "avaliacao", LADO, tenant_id, proposta_id=proposta.id, requisito_id=requisito.id, **campos))
    db.commit()
    return avaliacao


# --- Comparação (§20): C0, a decisão é humana -----------------------------------------------
def comparar(db: Session, tenant_id: str, processo_id: int) -> dict:
    processo = obter(db, tenant_id, processo_id)
    requisitos = nativo.listar(db, "requisito", LADO, tenant_id, processo_id=processo.id)
    itens = nativo.listar(db, "item", LADO, tenant_id, processo_id=processo.id)
    participantes = {p.id: p for p in nativo.listar(db, "participante", LADO, tenant_id, processo_id=processo.id)}
    propostas = nativo.listar(db, "proposta", LADO, tenant_id, processo_id=processo.id)
    ultimas = {}
    for p in propostas:  # última rodada de cada participante
        if p.participante_id not in ultimas or p.rodada > ultimas[p.participante_id].rodada:
            ultimas[p.participante_id] = p
    ids = [p.id for p in ultimas.values()]
    avaliacoes = nativo.listar(db, "avaliacao", LADO, tenant_id, proposta_id=ids) if ids else []
    precos = nativo.listar(db, "proposta_item", LADO, tenant_id, proposta_id=ids) if ids else []
    por_proposta: dict[int, dict] = {}
    for a in avaliacoes:
        por_proposta.setdefault(a.proposta_id, {})[a.requisito_id] = a
    linhas = []
    for participante_id, proposta in ultimas.items():
        participante = participantes[participante_id]
        aval = por_proposta.get(proposta.id, {})
        obrigatorios = [r for r in requisitos if r.obrigatorio is True and r.categoria != "PERGUNTA"]
        falhas = [r.id for r in obrigatorios if aval.get(r.id) and aval[r.id].status == "NON_COMPLIANT"]
        pendentes = [r.id for r in requisitos if r.categoria != "PERGUNTA" and (r.id not in aval or aval[r.id].status is None)]
        notas = [(float(r.peso or 1), float(aval[r.id].nota)) for r in requisitos if r.id in aval and aval[r.id].nota is not None]
        linhas.append({
            "participante_id": participante_id, "participante": participante.nome, "situacao": participante.status,
            "proposta_id": proposta.id, "rodada": proposta.rodada,
            "tecnico": {
                "obrigatorios": len(obrigatorios),
                "obrigatorios_atendidos": sum(1 for r in obrigatorios if aval.get(r.id) and aval[r.id].status == "COMPLIANT"),
                "obrigatorios_nao_atendidos": falhas,
                "nota_ponderada": round(sum(p * n for p, n in notas) / sum(p for p, _ in notas), 2) if notas else None,
                "requisitos_sem_avaliacao": pendentes,
            },
            "comercial": {
                "valor_total": float(proposta.valor_total) if proposta.valor_total is not None else None, "moeda": proposta.moeda,
                "prazo_entrega_dias": proposta.prazo_entrega_dias, "condicoes_pagamento": proposta.condicoes_pagamento,
                "impostos_inclusos": proposta.impostos_inclusos, "validade": proposta.validade,
                "itens_cotados": sum(1 for x in precos if x.proposta_id == proposta.id), "itens_total": len(itens),
            },
            "risco": "Obrigatório não atendido: desclassificação provável." if falhas else None,
        })
    validos = [linha for linha in linhas if not linha["tecnico"]["obrigatorios_nao_atendidos"] and linha["situacao"] != "DESQUALIFICADO"]
    com_valor = [linha for linha in validos if linha["comercial"]["valor_total"] is not None]
    com_nota = [linha for linha in validos if linha["tecnico"]["nota_ponderada"] is not None]
    return {
        "processo_id": processo.id, "tipo_processo": processo.tipo_processo, "linhas": linhas,
        "destaques": {  # destaques, não recomendação: quem decide é o comprador
            "menor_valor": min(com_valor, key=lambda linha: linha["comercial"]["valor_total"])["participante_id"] if com_valor else None,
            "maior_nota": max(com_nota, key=lambda linha: linha["tecnico"]["nota_ponderada"])["participante_id"] if com_nota else None,
        },
        "aviso": "Comparação determinística para apoiar a decisão humana; não há escolha automática de vencedor.",
    }


# --- Aprovação, adjudicação e contrato ------------------------------------------------------
def solicitar_aprovacao(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, participante_id: int,
                        justificativa: str | None):
    processo = obter(db, tenant_id, processo_id)
    if "EM_APROVACAO" not in _fluxo(processo).estados:
        raise RegraNegocioViolada("Este tipo de processo coleta respostas e não tem adjudicação.")
    if not (justificativa and justificativa.strip()):
        raise ValidacaoFalhou("Informe a justificativa da escolha.")
    participante = _participante(db, tenant_id, processo, participante_id)
    if participante.status in ("DESQUALIFICADO", "DECLINOU"):
        raise RegraNegocioViolada("Participante desqualificado ou que declinou não pode ser adjudicado.")
    if not nativo.listar(db, "proposta", LADO, tenant_id, processo_id=processo.id, participante_id=participante.id):
        raise RegraNegocioViolada("Participante sem proposta registrada.")
    _fluxo(processo).validar("EM_APROVACAO", "aprovacao", de=processo.status)
    metadados = dict(processo.metadados or {})
    metadados["aprovacao"] = {"participante_id": participante.id, "justificativa": justificativa.strip(),
                              "solicitada_por": usuario_id, "solicitada_em": _agora().isoformat(), "situacao": "PENDENTE",
                              "status_anterior": processo.status}
    nativo.atualizar(db, processo, status="EM_APROVACAO", metadados=metadados)
    _auditar(db, tenant_id, usuario_id, "sourcing_aprovacao_solicitada", processo.id, {"participante_id": participante.id})
    db.commit()
    return processo


def decidir_aprovacao(db: Session, tenant_id: str, usuario, processo_id: int, aprovar: bool, motivo: str | None):
    """Portão humano: só administrador decide; recusa exige motivo e devolve o processo à etapa anterior."""
    if usuario.papel not in ("admin", "super_admin"):
        raise NaoAutorizado("Só um administrador aprova a adjudicação.")
    processo = obter(db, tenant_id, processo_id)
    pedido = (processo.metadados or {}).get("aprovacao") or {}
    if processo.status != "EM_APROVACAO" or pedido.get("situacao") != "PENDENTE":
        raise RegraNegocioViolada("Não há aprovação pendente.")
    if not aprovar and not (motivo and motivo.strip()):
        raise ValidacaoFalhou("Informe o motivo da recusa.")
    destino = "ADJUDICADO" if aprovar else pedido.get("status_anterior", "EM_AVALIACAO")
    fluxo_processo = _fluxo(processo)
    if not aprovar and destino not in fluxo_processo.proximos("EM_APROVACAO", "aprovacao"):
        destino = next(e for e in fluxo_processo.proximos("EM_APROVACAO", "aprovacao") if e != "ADJUDICADO")
    fluxo_processo.validar(destino, "aprovacao", de=processo.status)
    metadados = dict(processo.metadados)
    metadados["aprovacao"] = {**pedido, "situacao": "APROVADA" if aprovar else "RECUSADA", "decidida_por": usuario.id,
                              "decidida_em": _agora().isoformat(), "motivo": (motivo or "").strip() or None}
    nativo.atualizar(db, processo, status=destino, metadados=metadados)
    if aprovar:
        for participante in nativo.listar(db, "participante", LADO, tenant_id, processo_id=processo.id):
            if participante.id == pedido["participante_id"]:
                nativo.atualizar(db, participante, status="ADJUDICADO")
            elif participante.status not in ("DESQUALIFICADO", "DECLINOU"):
                nativo.atualizar(db, participante, status="NAO_SELECIONADO")
    _auditar(db, tenant_id, usuario.id, "sourcing_aprovacao_" + ("aprovada" if aprovar else "recusada"), processo.id,
             {"participante_id": pedido["participante_id"]})
    db.commit()
    return processo


def contratar(db: Session, tenant_id: str, usuario_id: int | None, processo_id: int, dados: dict):
    processo = obter(db, tenant_id, processo_id)
    _fluxo(processo).validar("CONTRATADO", "contrato", de=processo.status)
    vencedor = next((p for p in nativo.listar(db, "participante", LADO, tenant_id, processo_id=processo.id) if p.status == "ADJUDICADO"),
                    None)
    if vencedor is None:
        raise RegraNegocioViolada("Nenhum participante adjudicado.")
    ultima = nativo.listar(db, "proposta", LADO, tenant_id, ordem="-rodada", limite=1, processo_id=processo.id,
                           participante_id=vencedor.id)[0]
    inicio, fim = dados.get("vigencia_inicio"), dados.get("vigencia_fim")
    if inicio and fim and fim < inicio:
        raise ValidacaoFalhou("Fim da vigência antes do início.")
    valor = dados.get("valor") if dados.get("valor") is not None else ultima.valor_total
    contrato = nativo.criar(
        db, "contrato", LADO, tenant_id, processo_id=processo.id, contraparte_nome=vencedor.nome, fornecedor_id=vencedor.fornecedor_id,
        numero=dados.get("numero"), objeto=dados.get("objeto") or processo.titulo, valor_inicial=valor, valor_atual=valor,
        vigencia_inicio=inicio, vigencia_fim=fim, status="VIGENTE", sla=dados.get("sla"), garantia=dados.get("garantia"),
        metadados={"participante_id": vencedor.id, "proposta_id": ultima.id}, criado_em=_agora(),
    )
    nativo.atualizar(db, processo, status="CONTRATADO")
    _auditar(db, tenant_id, usuario_id, "sourcing_contrato_criado", processo.id, {"contrato_id": contrato.id})
    db.commit()
    return contrato


# --- Workspace ------------------------------------------------------------------------------
def serializar(registro, campos: tuple[str, ...]) -> dict:
    return {c: (float(v) if isinstance(v, Decimal) else v) for c in campos for v in [getattr(registro, c)]}


CAMPOS_PROCESSO = ("id", "tipo_processo", "titulo", "descricao", "status", "workflow", "ruleset", "prazo", "valor_estimado", "moeda",
                   "publicado_em", "criado_em")
CAMPOS_REQUISITO = ("id", "categoria", "texto", "obrigatorio", "peso")
CAMPOS_ITEM = ("id", "descricao", "quantidade", "unidade", "especificacao")
CAMPOS_PARTICIPANTE = ("id", "nome", "cnpj", "origem_descoberta", "status", "motivo", "fornecedor_id", "empresa_rede_tenant_id", "email",
                       "token_gerado_em")
CAMPOS_PROPOSTA = ("id", "participante_id", "rodada", "tipo", "valor_total", "moeda", "prazo_entrega_dias", "condicoes_pagamento",
                   "impostos_inclusos", "validade", "observacoes", "canal", "recebida_em")
CAMPOS_CONTRATO = ("id", "contraparte_nome", "numero", "objeto", "valor_inicial", "vigencia_inicio", "vigencia_fim", "status")


def como_dict(processo) -> dict:
    return serializar(processo, CAMPOS_PROCESSO)


def workspace(db: Session, tenant_id: str, processo_id: int) -> dict:
    processo = obter(db, tenant_id, processo_id)
    fluxo_processo, regras = fluxo.configuracao_empresa(processo.tipo_processo)
    propostas = nativo.listar(db, "proposta", LADO, tenant_id, processo_id=processo.id)
    ids = [p.id for p in propostas]
    avaliacoes = nativo.listar(db, "avaliacao", LADO, tenant_id, proposta_id=ids) if ids else []
    return {
        "processo": como_dict(processo),
        "fluxo": {
            "codigo": fluxo_processo.codigo, "ruleset": {"codigo": regras.codigo, "fonte": regras.fonte} if regras else None,
            "proximos_status": list(fluxo_processo.proximos(processo.status, "status")),
            "aceita_aprovacao": "EM_APROVACAO" in fluxo_processo.proximos(processo.status, "aprovacao"),
            "aceita_contrato": bool(fluxo_processo.proximos(processo.status, "contrato")),
            "final": processo.status in fluxo_processo.finais,
            "recebe_propostas": processo.status in ("RECEBENDO_PROPOSTAS", "RECEBENDO_RESPOSTAS", "EM_NEGOCIACAO"),
            "com_itens": processo.tipo_processo == "RFQ",
        },
        "aprovacao": (processo.metadados or {}).get("aprovacao"),
        "requisitos": [serializar(r, CAMPOS_REQUISITO) for r in nativo.listar(db, "requisito", LADO, tenant_id, processo_id=processo.id)],
        "itens": [serializar(i, CAMPOS_ITEM) for i in nativo.listar(db, "item", LADO, tenant_id, processo_id=processo.id)],
        "participantes": [serializar(p, CAMPOS_PARTICIPANTE)
                          for p in nativo.listar(db, "participante", LADO, tenant_id, processo_id=processo.id)],
        "propostas": [{**serializar(p, CAMPOS_PROPOSTA), "avaliacoes": [
            {"requisito_id": a.requisito_id, "resposta": a.resposta, "status": a.status,
             "nota": float(a.nota) if a.nota is not None else None, "justificativa": a.justificativa}
            for a in avaliacoes if a.proposta_id == p.id]} for p in propostas],
        "contratos": [serializar(c, CAMPOS_CONTRATO) for c in nativo.listar(db, "contrato", LADO, tenant_id, processo_id=processo.id)],
        # Phase F: perguntas dos fornecedores (o comprador vê quem perguntou) e anexos das propostas (sem o arquivo)
        "esclarecimentos": [{"id": e.id, "participante_id": e.participante_id, "pergunta": e.pergunta, "resposta": e.resposta}
                            for e in nativo.listar(db, "esclarecimento", LADO, tenant_id, processo_id=processo.id)],
        "anexos": [{"id": a.id, "proposta_id": a.proposta_id, "nome_arquivo": a.nome_arquivo, "tamanho_bytes": a.tamanho_bytes}
                   for a in (nativo.listar(db, "anexo", LADO, tenant_id, proposta_id=ids) if ids else [])],
    }
