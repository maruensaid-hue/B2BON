"""Supplier Intelligence, riscos e recomendação do Strategic Sourcing (Phase G, D-067) — C0.

Determinístico, sem IA e sem crédito: cada alerta aponta para o dado que o
gerou (`evidencia`), e a próxima ação é uma regra por etapa do fluxo. Só dados
do próprio comprador (tenant, lado BUY); nada daqui vai para o fornecedor nem
para o lado vendedor.
"""

from datetime import UTC, timedelta
from statistics import median

from sqlalchemy.orm import Session

from app.contexts.procurement import estrategico
from app.contexts.shared.texto import normalizar
from app.contexts.sourcing.contract import nativo, tipos

LADO = tipos.Lado.COMPRA  # o mesmo de `estrategico` (importado em ciclo: nada dele é lido na importação)
DIAS_PRAZO_PROXIMO = 3
ABAIXO_DA_MEDIANA = 0.7
ACIMA_DA_MEDIANA = 1.5
RECEBENDO = ("RECEBENDO_PROPOSTAS", "RECEBENDO_RESPOSTAS")


# --- Supplier Intelligence: histórico nos processos do próprio comprador -----------------------
def _chaves(p) -> list[tuple[str, object]]:
    chaves = [("fornecedor_id", p.fornecedor_id), ("empresa_rede_tenant_id", p.empresa_rede_tenant_id), ("cnpj", p.cnpj)]
    return [(campo, valor) for campo, valor in chaves if valor] or [("nome", p.nome)]


def historico(db: Session, tenant_id: str, participantes: list, excluir_processo_id: int | None = None) -> dict[int, dict]:
    """Participante → desempenho do mesmo fornecedor (cadastro, rede, CNPJ ou nome) nos OUTROS processos. Duas consultas."""
    alternativas: dict[str, set] = {}
    for p in participantes:
        for campo, valor in _chaves(p):
            alternativas.setdefault(campo, set()).add(valor)
    outros = [o for o in nativo.listar_qualquer(db, "participante", LADO, tenant_id, **alternativas)
              if o.processo_id != excluir_processo_id]
    com_proposta = {p.participante_id for p in nativo.listar(db, "proposta", LADO, tenant_id, participante_id=[o.id for o in outros])} \
        if outros else set()
    resultado = {}
    for p in participantes:
        chaves = set(_chaves(p))
        mesmos = [o for o in outros if chaves & set(_chaves(o))]
        resultado[p.id] = {
            "processos": len({o.processo_id for o in mesmos}),
            "respondeu": sum(1 for o in mesmos if o.id in com_proposta),
            "declinou": sum(1 for o in mesmos if o.status == "DECLINOU"),
            "adjudicado": sum(1 for o in mesmos if o.status == "ADJUDICADO"),
            "desqualificado": sum(1 for o in mesmos if o.status == "DESQUALIFICADO"),
        }
    return resultado


def historico_por_nome(db: Session, tenant_id: str, pergunta: str) -> list[dict]:
    """Ferramenta do agente: fornecedores do comprador cujo nome aparece na pergunta."""
    alvo = f" {normalizar(pergunta)} "
    vistos, achados = set(), []
    for p in nativo.listar(db, "participante", LADO, tenant_id, ordem="-id"):
        nome = normalizar(p.nome or "")
        if len(nome) >= 3 and f" {nome} " in alvo and nome not in vistos:
            vistos.add(nome)
            achados.append(p)
    dados = historico(db, tenant_id, achados)
    return [{"fornecedor": p.nome, **dados[p.id]} for p in achados]


# --- Riscos e próxima ação --------------------------------------------------------------------
def _prazo(processo):
    """Prazo em UTC sem fuso (o banco pode devolver com fuso no Postgres)."""
    prazo = processo.prazo
    return prazo.astimezone(UTC).replace(tzinfo=None) if prazo is not None and prazo.tzinfo else prazo


def _alerta(tipo: str, severidade: str, mensagem: str, **evidencia) -> dict:
    return {"tipo": tipo, "severidade": severidade, "mensagem": mensagem, "evidencia": evidencia}


def alertas(processo, requisitos: list, participantes: list, propostas: list, avaliacoes: list, esclarecimentos: list,
            hist: dict[int, dict], agora) -> list[dict]:
    resultado = []
    sugeridos = [r.id for r in requisitos if r.status_revisao == "sugerido"]
    if sugeridos:
        resultado.append(_alerta("REQUISITOS_SUGERIDOS", "atencao", f"{len(sugeridos)} requisito(s) sugerido(s) pela IA aguardando revisão.",
                                 requisitos=sugeridos))
    pendentes = [e.id for e in esclarecimentos if not e.resposta]
    if pendentes:
        resultado.append(_alerta("ESCLARECIMENTO_PENDENTE", "atencao", f"{len(pendentes)} pergunta(s) de fornecedor sem resposta.",
                                 esclarecimentos=pendentes))
    ultimas = estrategico.ultimas_rodadas(propostas)
    prazo = _prazo(processo)
    if processo.status in RECEBENDO and prazo:
        if prazo < agora:
            resultado.append(_alerta("PRAZO_ENCERRADO", "atencao", "O prazo de resposta passou; avance para a avaliação.",
                                     prazo=prazo.isoformat()))
        elif prazo - agora <= timedelta(days=DIAS_PRAZO_PROXIMO) and len(ultimas) < 2:
            resultado.append(_alerta("BAIXA_PARTICIPACAO", "atencao", f"Prazo em até {DIAS_PRAZO_PROXIMO} dias com {len(ultimas)} resposta(s).",
                                     prazo=prazo.isoformat(), respostas=len(ultimas)))
    if processo.status in ("EM_AVALIACAO", "EM_NEGOCIACAO", "EM_APROVACAO") and len(ultimas) == 1:
        resultado.append(_alerta("PROPOSTA_UNICA", "atencao", "Uma única proposta: a comparação de mercado fica limitada.",
                                 participante_id=next(iter(ultimas))))
    obrigatorios = {r.id for r in requisitos if r.obrigatorio is True and r.status_revisao == "confirmado"}
    ids_ultimas = {p.id: p.participante_id for p in ultimas.values()}
    for a in avaliacoes:
        if a.proposta_id in ids_ultimas and a.requisito_id in obrigatorios and a.status == "NON_COMPLIANT":
            resultado.append(_alerta("OBRIGATORIO_NAO_ATENDIDO", "alto", "Proposta não atende requisito obrigatório.",
                                     participante_id=ids_ultimas[a.proposta_id], requisito_id=a.requisito_id))
    valores = {pid: float(p.valor_total) for pid, p in ultimas.items() if p.valor_total is not None}
    if len(valores) >= 3:
        mediana = median(valores.values())
        for pid, valor in valores.items():
            if mediana and valor < ABAIXO_DA_MEDIANA * mediana:
                resultado.append(_alerta("PRECO_MUITO_ABAIXO", "atencao", "Valor bem abaixo da mediana: verifique a exequibilidade.",
                                         participante_id=pid, valor=valor, mediana=mediana))
            elif mediana and valor > ACIMA_DA_MEDIANA * mediana:
                resultado.append(_alerta("PRECO_MUITO_ACIMA", "info", "Valor bem acima da mediana das propostas.",
                                         participante_id=pid, valor=valor, mediana=mediana))
    nomes = {p.id: p for p in participantes}
    for pid, dados in hist.items():
        if pid in nomes and nomes[pid].status not in ("DECLINOU", "DESQUALIFICADO") and (dados["desqualificado"] or dados["declinou"] >= 2):
            resultado.append(_alerta("HISTORICO_FORNECEDOR", "info", "Fornecedor com desqualificação ou declínios em processos anteriores.",
                                     participante_id=pid, **{k: dados[k] for k in ("desqualificado", "declinou")}))
    return resultado


def proxima_acao(processo, fluxo_processo, requisitos: list, itens: list, participantes: list, propostas: list,
                 avaliacoes: list, esclarecimentos: list, agora) -> dict | None:
    """Regra por etapa; devolve a primeira pendência. A execução é sempre do comprador."""
    if processo.status in fluxo_processo.finais:
        return None
    decide_ja = "EM_APROVACAO" in fluxo_processo.proximos(processo.status, "aprovacao")  # RFQ: da cotação direto à aprovação
    ativos = [p for p in participantes if p.status not in ("DECLINOU", "DESQUALIFICADO")]
    vigentes = [r for r in requisitos if r.status_revisao == "confirmado"]
    sugeridos = [r for r in requisitos if r.status_revisao == "sugerido"]
    ultimas = estrategico.ultimas_rodadas(propostas)
    avaliaveis = [r for r in vigentes if r.categoria != "PERGUNTA"]
    avaliadas = {(a.proposta_id, a.requisito_id) for a in avaliacoes if a.status}
    sem_avaliacao = sum(1 for p in ultimas.values() for r in avaliaveis if (p.id, r.id) not in avaliadas)
    regras = [
        (bool(sugeridos) and processo.status in ("RASCUNHO", "PUBLICADO"), "REVISAR_REQUISITOS", f"Revise {len(sugeridos)} requisito(s) sugerido(s)."),
        (processo.status == "RASCUNHO" and not vigentes and not itens, "CADASTRAR_REQUISITOS",
         "Cadastre requisitos ou itens, ou envie a especificação para a IA sugerir."),
        (processo.status == "RASCUNHO", "PUBLICAR", "Publique o processo."),
        (not participantes and processo.status in ("PUBLICADO", *RECEBENDO), "CONVIDAR", "Convide fornecedores (use a descoberta)."),
        (processo.status == "PUBLICADO", "ABRIR_PROPOSTAS", "Abra o processo para receber respostas."),
        (any(not e.resposta for e in esclarecimentos), "RESPONDER_ESCLARECIMENTOS", "Responda as perguntas dos fornecedores."),
        (processo.status in RECEBENDO and bool(ultimas) and decide_ja
         and (all(p.id in ultimas for p in ativos) or bool(_prazo(processo)) and _prazo(processo) < agora),
         "DECIDIR", "Respostas recebidas: compare as propostas e solicite a aprovação da escolha."),
        (processo.status in RECEBENDO and bool(ativos) and all(p.id in ultimas for p in ativos), "AVANCAR_AVALIACAO",
         "Todos os participantes responderam: avance para a avaliação."),
        (processo.status in RECEBENDO and bool(_prazo(processo)) and _prazo(processo) < agora, "AVANCAR_AVALIACAO",
         "O prazo passou: avance para a avaliação."),
        (processo.status in RECEBENDO, "AGUARDAR_RESPOSTAS", f"{len(ultimas)} de {len(participantes)} participante(s) responderam."),
        (processo.status in ("EM_AVALIACAO", "EM_NEGOCIACAO") and sem_avaliacao > 0, "AVALIAR",
         f"{sem_avaliacao} avaliação(ões) por requisito pendente(s)."),
        (processo.status in ("EM_AVALIACAO", "EM_NEGOCIACAO"), "DECIDIR", "Compare as propostas e solicite a aprovação da escolha."),
        (processo.status == "EM_APROVACAO", "AGUARDAR_APROVACAO", "Aguardando a decisão de um administrador."),
        (processo.status == "ADJUDICADO", "CONTRATAR", "Registre o contrato com o adjudicado."),
    ]
    return next(({"acao": acao, "motivo": motivo} for condicao, acao, motivo in regras if condicao), None)


def pendencias(db: Session, tenant_id: str, limite: int = 20) -> list[dict]:
    """Ferramenta do agente: processos em aberto com a próxima ação e os alertas."""
    itens = []
    for processo in estrategico.listar(db, tenant_id)[:limite * 2]:
        ws = estrategico.workspace(db, tenant_id, processo.id)
        if ws["fluxo"]["final"]:
            continue
        itens.append({"processo_id": processo.id, "titulo": processo.titulo, "status": processo.status,
                      "proxima_acao": ws["inteligencia"]["proxima_acao"], "alertas": ws["inteligencia"]["alertas"]})
        if len(itens) >= limite:
            break
    return itens
