"""Alertas de novas oportunidades de licitação por regra/ICP (V5.2.1, Fase 4). Sem IA: correspondência determinística e explicável.

Fluxo: o coletor grava o fato público no corpus (`corpus`) e cada mudança vira um evento (`evento_licitacao_publica`). Para cada tenant com regra ativa,
`avaliar_tenant` lê os eventos novos desde o seu cursor, avalia o estado ATUAL do edital contra as regras e grava **um alerta por (tenant, edital)**.
`entregar` manda **um resumo** (digest) por e-mail de sistema aos administradores — desligado por padrão (`ALERTAS_LICITACAO_EMAIL_HABILITADO`).

Propriedades
- **Explicável**: o alerta guarda os fatores que o produziram (`fatores`: palavras que casaram, UF, valor, modalidade, prazo). A pontuação é
  "% dos pontos dos critérios que a regra definiu"; dado que a fonte não informa (UF, valor) não exclui, mas não pontua. **É compatibilidade com a
  regra, não elegibilidade nem chance de vitória.**
- **Sem ruído**: palavras-chave (ou portfólio) são obrigatórias — senão a regra casaria com todo edital da UF; exclusões por palavra; relevância mínima;
  edital já encerrado/suspenso/cancelado ou com prazo vencido não gera alerta novo; um alerta por edital mesmo com várias regras; resumo, não uma
  mensagem por edital; frequência diária = no máximo um resumo a cada ~24 h.
- **Idempotente e retomável**: cursor por tenant; unicidade (tenant, edital) no banco; falha no meio desfaz o lote e a reexecução converge.
- **Atualização**: retificação de prazo/valor e mudança de situação (suspensão, anulação, revogação) de um edital já alertado atualizam o alerta,
  o marcam como "atualização não vista" (exceto se dispensado) e voltam a notificar.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.bids import corpus, licitacoes
from app.contexts.bids.tipos import MODALIDADES
from app.core.config import settings
from app.models.alerta_licitacao import AlertaLicitacao, EstadoAlertasLicitacao, RegraAlertaLicitacao
from app.models.icp import ICP
from app.models.licitacao_publica import EventoLicitacaoPublica, LicitacaoPublica
from app.models.oferta import Oferta
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

logger = logging.getLogger(__name__)

PESO_PALAVRAS, PESO_UF, PESO_VALOR, PESO_MODALIDADE, PESO_PRAZO = 60, 20, 10, 5, 5
FREQUENCIAS = ("imediata", "diaria")
ESTADOS = ("novo", "visto", "dispensado", "acompanhado")
MAX_TENTATIVAS_ENTREGA = 3
MAX_ALERTAS_NO_RESUMO = 10
INTERVALO_RESUMO_DIARIO = timedelta(hours=20)
LOTE_EVENTOS = 1000
_PALAVRAS_VAZIAS = {"para", "com", "sem", "por", "uma", "uns", "das", "dos", "nas", "nos", "que", "como", "mais", "menos", "ltda", "eireli", "the", "and"}


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()


def _contem(palavra_normalizada: str, texto_normalizado: str) -> bool:
    """A palavra começa em fronteira de palavra (aceita plural/derivação: 'licenca' casa 'licencas'; 'ti' não casa dentro de 'gestao')."""
    return re.search(rf"(?<![a-z0-9]){re.escape(palavra_normalizada)}", texto_normalizado) is not None


# --- Regras ---------------------------------------------------------------------------------------------------------------------------------


def _limpar_lista(valores, maximo=30, tamanho=60) -> list[str]:
    limpos = []
    for v in valores or []:
        texto = str(v).strip()
        if texto and texto.lower() not in {x.lower() for x in limpos}:
            if len(texto) > tamanho:
                raise ValidacaoFalhou(f"Cada palavra pode ter no máximo {tamanho} caracteres.")
            limpos.append(texto)
    if len(limpos) > maximo:
        raise ValidacaoFalhou(f"No máximo {maximo} itens por lista.")
    return limpos


def _validar(db: Session, tenant_id: str, dados: dict) -> dict:
    nome = (dados.get("nome") or "").strip()
    if not nome or len(nome) > 80:
        raise ValidacaoFalhou("Informe um nome de até 80 caracteres para a regra.")
    palavras = _limpar_lista(dados.get("palavras_chave"))
    excluir = _limpar_lista(dados.get("palavras_excluir"))
    usar_portfolio = bool(dados.get("usar_portfolio"))
    if not palavras and not usar_portfolio:
        raise ValidacaoFalhou("Informe ao menos uma palavra-chave ou ative o portfólio: sem isso a regra casaria com todo edital.")
    ufs = sorted({str(u).strip().upper() for u in dados.get("ufs") or [] if str(u).strip()})
    if any(len(u) != 2 or not u.isalpha() for u in ufs):
        raise ValidacaoFalhou("UF inválida: use a sigla de duas letras (ex.: SP).")
    modalidades = sorted({str(m) for m in dados.get("modalidades") or []})
    if any(m not in MODALIDADES for m in modalidades):
        raise ValidacaoFalhou("Modalidade inválida.")
    minimo, maximo = dados.get("valor_minimo"), dados.get("valor_maximo")
    if (minimo is not None and minimo < 0) or (maximo is not None and maximo < 0):
        raise ValidacaoFalhou("Os valores não podem ser negativos.")
    if minimo is not None and maximo is not None and minimo > maximo:
        raise ValidacaoFalhou("O valor mínimo não pode ser maior que o máximo.")
    dias = dados.get("dias_minimos_prazo")
    if dias is not None and not 0 <= int(dias) <= 365:
        raise ValidacaoFalhou("Dias mínimos de prazo: entre 0 e 365.")
    relevancia = int(dados.get("relevancia_minima", 40))
    if not 0 <= relevancia <= 100:
        raise ValidacaoFalhou("A relevância mínima fica entre 0 e 100.")
    frequencia = dados.get("frequencia") or "diaria"
    if frequencia not in FREQUENCIAS:
        raise ValidacaoFalhou("Frequência inválida: use 'imediata' ou 'diaria'.")
    icp_id = dados.get("icp_id")
    if icp_id is not None and db.query(ICP.id).filter_by(id=icp_id, tenant_id=tenant_id).first() is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")  # nunca aceitar ICP de outro tenant
    return {"nome": nome, "ativa": bool(dados.get("ativa", True)), "icp_id": icp_id, "palavras_chave": palavras, "palavras_excluir": excluir,
            "ufs": ufs, "modalidades": modalidades, "valor_minimo": minimo, "valor_maximo": maximo,
            "dias_minimos_prazo": int(dias) if dias is not None else None, "usar_portfolio": usar_portfolio, "relevancia_minima": relevancia,
            "frequencia": frequencia}


def _reiniciar_cursor(db: Session, tenant_id: str) -> None:
    """Regra nova/alterada precisa enxergar o corpus que já existe: volta o cursor a zero (a unicidade por edital impede alerta duplicado)."""
    estado = db.get(EstadoAlertasLicitacao, tenant_id)
    if estado is not None:
        estado.ultimo_evento_id = 0


def listar_regras(db: Session, tenant_id: str) -> list[RegraAlertaLicitacao]:
    return db.query(RegraAlertaLicitacao).filter_by(tenant_id=tenant_id).order_by(RegraAlertaLicitacao.id).all()


def _regra(db: Session, tenant_id: str, regra_id: int) -> RegraAlertaLicitacao:
    regra = db.query(RegraAlertaLicitacao).filter_by(id=regra_id, tenant_id=tenant_id).one_or_none()
    if regra is None:
        raise NaoEncontrado(f"Regra {regra_id} não encontrada")
    return regra


def criar_regra(db: Session, tenant_id: str, ator_id: str | None, dados: dict) -> RegraAlertaLicitacao:
    valores = _validar(db, tenant_id, dados)
    if db.query(RegraAlertaLicitacao.id).filter_by(tenant_id=tenant_id, nome=valores["nome"]).first() is not None:
        raise ValidacaoFalhou("Já existe uma regra com esse nome.")
    regra = RegraAlertaLicitacao(tenant_id=tenant_id, **valores)
    db.add(regra)
    db.flush()
    _reiniciar_cursor(db, tenant_id)
    auditoria_service.registrar(db, tenant_id, "regra_alerta_licitacao_criada", "regra_alerta_licitacao", regra.id, ator_id, {"nome": regra.nome})
    db.commit()
    db.refresh(regra)
    return regra


def atualizar_regra(db: Session, tenant_id: str, ator_id: str | None, regra_id: int, dados: dict) -> RegraAlertaLicitacao:
    regra = _regra(db, tenant_id, regra_id)
    valores = _validar(db, tenant_id, {**regra_dict(regra), **dados})
    conflito = db.query(RegraAlertaLicitacao.id).filter(RegraAlertaLicitacao.tenant_id == tenant_id, RegraAlertaLicitacao.nome == valores["nome"],
                                                        RegraAlertaLicitacao.id != regra.id).first()
    if conflito is not None:
        raise ValidacaoFalhou("Já existe uma regra com esse nome.")
    for campo, valor in valores.items():
        setattr(regra, campo, valor)
    _reiniciar_cursor(db, tenant_id)
    auditoria_service.registrar(db, tenant_id, "regra_alerta_licitacao_atualizada", "regra_alerta_licitacao", regra.id, ator_id, {"nome": regra.nome})
    db.commit()
    db.refresh(regra)
    return regra


def excluir_regra(db: Session, tenant_id: str, ator_id: str | None, regra_id: int) -> None:
    regra = _regra(db, tenant_id, regra_id)
    auditoria_service.registrar(db, tenant_id, "regra_alerta_licitacao_excluida", "regra_alerta_licitacao", regra.id, ator_id, {"nome": regra.nome})
    db.delete(regra)
    db.commit()


def regra_dict(r: RegraAlertaLicitacao) -> dict:
    return {"id": r.id, "nome": r.nome, "ativa": r.ativa, "icp_id": r.icp_id, "palavras_chave": r.palavras_chave or [], "palavras_excluir": r.palavras_excluir or [],
            "ufs": r.ufs or [], "modalidades": r.modalidades or [], "valor_minimo": r.valor_minimo, "valor_maximo": r.valor_maximo,
            "dias_minimos_prazo": r.dias_minimos_prazo, "usar_portfolio": r.usar_portfolio, "relevancia_minima": r.relevancia_minima,
            "frequencia": r.frequencia, "criado_em": r.criado_em, "atualizado_em": r.atualizado_em}


# --- Correspondência (função pura) ----------------------------------------------------------------------------------------------------------


@dataclass
class Correspondencia:
    score: int
    fatores: list[dict] = field(default_factory=list)


def _tokens_portfolio(db: Session, tenant_id: str) -> list[str]:
    oferta = db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).order_by(Oferta.id.desc()).first()
    if oferta is None:
        return []
    tokens = []
    for bruto in re.split(r"[^A-Za-z0-9À-ÿ]+", oferta.nome or ""):
        t = normalizar(bruto)
        if len(t) >= 4 and t not in _PALAVRAS_VAZIAS and t not in tokens:
            tokens.append(t)
    return tokens


def avaliar_item(regra: dict, publica: LicitacaoPublica, agora: datetime, ufs_do_icp: list[str] | None = None, tokens_portfolio: list[str] | None = None) -> Correspondencia | None:
    """`None` = não casa. Critério não satisfeito (UF/valor/modalidade/prazo/palavra excluída/sem palavra-chave) exclui; dado que a fonte não informa
    apenas deixa de pontuar. `regra` é o `regra_dict` (permite testar sem banco)."""
    texto = normalizar(f"{publica.titulo or ''} {publica.objeto or ''} {publica.orgao_nome or ''}")
    for excluida in regra.get("palavras_excluir") or []:
        if _contem(normalizar(excluida), texto):
            return None
    explicitas = [normalizar(p) for p in regra.get("palavras_chave") or []]
    portfolio = [t for t in (tokens_portfolio or []) if t not in explicitas] if regra.get("usar_portfolio") else []
    candidatas = explicitas + portfolio
    casadas = [p for p in candidatas if _contem(p, texto)]
    if candidatas and not casadas:
        return None
    fatores: list[dict] = []
    possiveis = obtidos = 0
    if candidatas:
        pontos = min(PESO_PALAVRAS, 40 + 10 * (len(casadas) - 1))
        possiveis += PESO_PALAVRAS
        obtidos += pontos
        origem = [p for p in casadas if p in portfolio]
        detalhe = "o edital cita: " + ", ".join(casadas) + (f" (do portfólio: {', '.join(origem)})" if origem else "")
        fatores.append({"fator": "palavras_chave", "pontos": pontos, "maximo": PESO_PALAVRAS, "detalhe": detalhe})
    ufs = regra.get("ufs") or ufs_do_icp or []
    if ufs:
        possiveis += PESO_UF
        if publica.uf is None:
            fatores.append({"fator": "uf", "pontos": 0, "maximo": PESO_UF, "detalhe": "a fonte não informou a UF; não foi possível verificar"})
        elif publica.uf in ufs:
            obtidos += PESO_UF
            fatores.append({"fator": "uf", "pontos": PESO_UF, "maximo": PESO_UF, "detalhe": f"UF {publica.uf} está entre as UFs da regra"})
        else:
            return None
    minimo, maximo = regra.get("valor_minimo"), regra.get("valor_maximo")
    if minimo is not None or maximo is not None:
        possiveis += PESO_VALOR
        if publica.valor_estimado is None:
            fatores.append({"fator": "valor", "pontos": 0, "maximo": PESO_VALOR, "detalhe": "valor estimado não informado pela fonte"})
        elif (minimo is None or publica.valor_estimado >= minimo) and (maximo is None or publica.valor_estimado <= maximo):
            obtidos += PESO_VALOR
            fatores.append({"fator": "valor", "pontos": PESO_VALOR, "maximo": PESO_VALOR, "detalhe": f"valor estimado R$ {publica.valor_estimado:,.2f} dentro da faixa"})
        else:
            return None
    if regra.get("modalidades"):
        possiveis += PESO_MODALIDADE
        if publica.modalidade in regra["modalidades"]:
            obtidos += PESO_MODALIDADE
            fatores.append({"fator": "modalidade", "pontos": PESO_MODALIDADE, "maximo": PESO_MODALIDADE, "detalhe": f"modalidade {publica.modalidade}"})
        else:
            return None
    if publica.prazo_proposta is not None and publica.prazo_proposta < agora:
        return None  # prazo de proposta já venceu: não adianta alertar
    dias_minimos = regra.get("dias_minimos_prazo")
    if dias_minimos is not None:
        possiveis += PESO_PRAZO
        if publica.prazo_proposta is None:
            fatores.append({"fator": "prazo", "pontos": 0, "maximo": PESO_PRAZO, "detalhe": "prazo da proposta não informado pela fonte"})
        else:
            dias = (publica.prazo_proposta - agora).days
            if dias < dias_minimos:
                return None
            obtidos += PESO_PRAZO
            fatores.append({"fator": "prazo", "pontos": PESO_PRAZO, "maximo": PESO_PRAZO, "detalhe": f"faltam {dias} dias para a proposta (mínimo {dias_minimos})"})
    score = round(100 * obtidos / possiveis) if possiveis else 0
    if score < int(regra.get("relevancia_minima", 0)):
        return None
    return Correspondencia(score, fatores)


# --- Avaliação incremental ------------------------------------------------------------------------------------------------------------------


def _notifica_atualizacao(eventos: list[EventoLicitacaoPublica]) -> bool:
    """Só situação que exige atenção (suspensa/anulada/revogada/cancelada) ou retificação de prazo/valor voltam a notificar."""
    for e in eventos:
        if e.tipo == "situacao_alterada" and licitacoes.situacao_externa_exige_atencao((e.mudancas.get("situacao_externa") or [None, None])[1]):
            return True
        if e.tipo == "retificada" and ({"prazo_proposta", "valor_estimado"} & set(e.mudancas)):
            return True
    return False


def avaliar_tenant(db: Session, tenant_id: str, agora: datetime | None = None, limite: int = LOTE_EVENTOS) -> dict:
    agora = agora or _agora()
    resumo = {"avaliados": 0, "criados": 0, "atualizados": 0, "sem_regra": False}
    regras = [regra_dict(r) for r in db.query(RegraAlertaLicitacao).filter_by(tenant_id=tenant_id, ativa=True).order_by(RegraAlertaLicitacao.id).all()]
    if not regras:
        resumo["sem_regra"] = True
        return resumo
    estado = db.get(EstadoAlertasLicitacao, tenant_id)
    if estado is None:
        estado = EstadoAlertasLicitacao(tenant_id=tenant_id, ultimo_evento_id=0)
        db.add(estado)
        db.flush()
    eventos = (db.query(EventoLicitacaoPublica).filter(EventoLicitacaoPublica.id > estado.ultimo_evento_id)
               .order_by(EventoLicitacaoPublica.id).limit(limite).all())
    estado.avaliado_em = agora
    if not eventos:
        db.commit()
        return resumo
    por_corpus: dict[int, list[EventoLicitacaoPublica]] = {}
    for e in eventos:
        por_corpus.setdefault(e.licitacao_publica_id, []).append(e)
    publicas = {p.id: p for p in db.query(LicitacaoPublica).filter(LicitacaoPublica.id.in_(list(por_corpus))).all()}
    icps = {i.id: list(i.ufs or []) for i in db.query(ICP).filter_by(tenant_id=tenant_id).all()}
    portfolio = _tokens_portfolio(db, tenant_id) if any(r["usar_portfolio"] for r in regras) else []
    padrao_entrega = "pendente" if settings.alertas_licitacao_email_habilitado else "desligada"
    existentes = {a.corpus_id: a for a in db.query(AlertaLicitacao).filter(AlertaLicitacao.tenant_id == tenant_id, AlertaLicitacao.corpus_id.in_(list(por_corpus))).all()}
    for corpus_id, evs in por_corpus.items():
        publica = publicas.get(corpus_id)
        if publica is None:
            continue
        resumo["avaliados"] += 1
        alerta = existentes.get(corpus_id)
        if alerta is not None:
            if publica.versao > alerta.versao_corpus:
                alerta.versao_corpus, alerta.situacao_externa, alerta.motivo = publica.versao, publica.situacao_externa, "atualizada"
                if alerta.estado != "dispensado":
                    alerta.atualizacao_nao_vista = True
                    if _notifica_atualizacao(evs):
                        alerta.entrega_estado, alerta.entrega_tentativas, alerta.entrega_ultimo_erro = padrao_entrega, 0, None
                resumo["atualizados"] += 1
            continue
        if licitacoes.situacao_externa_exige_atencao(publica.situacao_externa):
            continue  # já nasceu suspenso/anulado/revogado: não vira oportunidade nova
        melhor, casaram = None, []
        for regra in regras:
            ufs_icp = icps.get(regra["icp_id"]) if regra["icp_id"] else None
            c = avaliar_item(regra, publica, agora, ufs_icp, portfolio)
            if c is not None:
                casaram.append(regra)
                if melhor is None or c.score > melhor.score:
                    melhor = c
        if melhor is None:
            continue
        novo = AlertaLicitacao(tenant_id=tenant_id, corpus_id=corpus_id, score=melhor.score, fatores=melhor.fatores,
                               regras=[{"id": r["id"], "nome": r["nome"], "frequencia": r["frequencia"]} for r in casaram], motivo="nova", estado="novo",
                               versao_corpus=publica.versao, situacao_externa=publica.situacao_externa, entrega_estado=padrao_entrega)
        try:
            with db.begin_nested():
                db.add(novo)
                db.flush()
        except IntegrityError:
            continue  # outra execução criou o mesmo alerta; é idempotente
        resumo["criados"] += 1
    estado.ultimo_evento_id = eventos[-1].id
    db.commit()
    return resumo


# --- Entrega (resumo por e-mail de sistema) -------------------------------------------------------------------------------------------------


def _admins(db: Session, tenant_id: str) -> list[Usuario]:
    return db.query(Usuario).filter(Usuario.tenant_id == tenant_id, Usuario.ativo.is_(True), Usuario.papel.in_(("admin", "super_admin"))).all()


def _linha_resumo(alerta: AlertaLicitacao, publica: LicitacaoPublica) -> str:
    local = " / ".join(x for x in (publica.municipio, publica.uf) if x)
    valor = f" — R$ {publica.valor_estimado:,.2f}" if publica.valor_estimado is not None else ""
    prazo = f" — proposta até {publica.prazo_proposta:%d/%m/%Y}" if publica.prazo_proposta else ""
    marca = f"[ATUALIZADO: {publica.situacao_externa}] " if alerta.motivo == "atualizada" else ""
    return f"• {marca}{publica.titulo[:120]} ({publica.orgao_nome or 'órgão não informado'}{', ' + local if local else ''}){valor}{prazo}\n  Compatibilidade {alerta.score}% · Fonte oficial: {publica.url or 'indisponível'}"


def entregar(db: Session, tenant_id: str, email_provider: EmailProvider, agora: datetime | None = None) -> dict:
    agora = agora or _agora()
    if not settings.alertas_licitacao_email_habilitado:
        return {"estado": "desligada", "enviados": 0}
    pendentes = (db.query(AlertaLicitacao).filter(AlertaLicitacao.tenant_id == tenant_id, AlertaLicitacao.entrega_estado.in_(("pendente", "falhou")),
                                                  AlertaLicitacao.entrega_tentativas < MAX_TENTATIVAS_ENTREGA, AlertaLicitacao.estado != "dispensado")
                 .order_by(AlertaLicitacao.score.desc(), AlertaLicitacao.id).all())
    if not pendentes:
        return {"estado": "nada_a_enviar", "enviados": 0}
    estado = db.get(EstadoAlertasLicitacao, tenant_id)
    ha_imediata = any(any(r.get("frequencia") == "imediata" for r in a.regras) for a in pendentes)
    ja_enviou_hoje = estado is not None and estado.ultimo_resumo_em is not None and agora - estado.ultimo_resumo_em < INTERVALO_RESUMO_DIARIO
    if ja_enviou_hoje and not ha_imediata:
        return {"estado": "aguardando_resumo_diario", "enviados": 0}
    destinatarios = _admins(db, tenant_id)
    if not destinatarios:
        for a in pendentes:
            a.entrega_estado = "sem_destinatario"
        db.commit()
        return {"estado": "sem_destinatario", "enviados": 0}
    publicas = {p.id: p for p in db.query(LicitacaoPublica).filter(LicitacaoPublica.id.in_([a.corpus_id for a in pendentes])).all()}
    principais = pendentes[:MAX_ALERTAS_NO_RESUMO]
    restante = len(pendentes) - len(principais)
    corpo_base = "\n\n".join(_linha_resumo(a, publicas[a.corpus_id]) for a in principais if a.corpus_id in publicas)
    if restante:
        corpo_base += f"\n\n… e mais {restante} oportunidade(s) no painel."
    rodape = f"\n\nVeja, filtre e acompanhe em {settings.url_base_frontend}/bids/alertas\n\nA compatibilidade mostra o quanto o edital atende aos critérios das suas regras de alerta; não indica elegibilidade nem chance de vitória. Confira sempre o edital na fonte oficial."
    assunto = f"B2B ON: {len(pendentes)} oportunidade(s) de licitação para você"
    enviou, erro = False, None
    for usuario in destinatarios:
        try:
            resultado = email_provider.enviar(usuario.email, assunto, f"Olá, {usuario.nome}!\n\n{corpo_base}{rodape}", "B2B ON",
                                              settings.sendgrid_remetente_email, tenant_id)
            if getattr(resultado, "sucesso", True):
                enviou = True
            else:
                erro = str(getattr(resultado, "motivo_falha", "") or "o provedor recusou o envio")[:300]
        except Exception as falha:  # noqa: BLE001 — uma falha de e-mail nunca derruba o ciclo dos outros tenants
            erro = f"{type(falha).__name__}"
            logger.warning("Falha ao enviar resumo de alertas do tenant %s", tenant_id, exc_info=True)
    for a in pendentes:
        if enviou:
            a.entrega_estado, a.entregue_em, a.entrega_ultimo_erro = "enviada", agora, None
        else:
            a.entrega_tentativas += 1
            a.entrega_estado = "desistida" if a.entrega_tentativas >= MAX_TENTATIVAS_ENTREGA else "falhou"
            a.entrega_ultimo_erro = erro
    if enviou and estado is not None:
        estado.ultimo_resumo_em = agora
    db.commit()
    return {"estado": "enviado" if enviou else "falhou", "enviados": len(pendentes) if enviou else 0}


# --- Consulta e ações do usuário ------------------------------------------------------------------------------------------------------------


def _alerta(db: Session, tenant_id: str, alerta_id: int) -> AlertaLicitacao:
    alerta = db.query(AlertaLicitacao).filter_by(id=alerta_id, tenant_id=tenant_id).one_or_none()
    if alerta is None:
        raise NaoEncontrado(f"Alerta {alerta_id} não encontrado")
    return alerta


def como_dict(alerta: AlertaLicitacao, publica: LicitacaoPublica | None) -> dict:
    return {"id": alerta.id, "corpus_id": alerta.corpus_id, "score": alerta.score, "fatores": alerta.fatores or [], "regras": alerta.regras or [],
            "motivo": alerta.motivo, "estado": alerta.estado, "atualizacao_nao_vista": alerta.atualizacao_nao_vista,
            "situacao_externa": alerta.situacao_externa, "entrega_estado": alerta.entrega_estado, "entregue_em": alerta.entregue_em,
            "criado_em": alerta.criado_em, "atualizado_em": alerta.atualizado_em, "visto_em": alerta.visto_em,
            "edital": corpus.como_dict(publica) if publica is not None else None}


def listar(db: Session, tenant_id: str, estado: str | None = None, score_minimo: int | None = None, regra_id: int | None = None,
           limite: int = 100) -> list[dict]:
    consulta = db.query(AlertaLicitacao).filter_by(tenant_id=tenant_id)
    if estado:
        if estado not in ESTADOS:
            raise ValidacaoFalhou("Estado inválido.")
        consulta = consulta.filter(AlertaLicitacao.estado == estado)
    if score_minimo is not None:
        consulta = consulta.filter(AlertaLicitacao.score >= score_minimo)
    alertas = consulta.order_by(AlertaLicitacao.atualizacao_nao_vista.desc(), AlertaLicitacao.id.desc()).limit(max(1, min(limite, 500))).all()
    if regra_id is not None:
        alertas = [a for a in alertas if any(r.get("id") == regra_id for r in a.regras or [])]
    publicas = {p.id: p for p in db.query(LicitacaoPublica).filter(LicitacaoPublica.id.in_([a.corpus_id for a in alertas])).all()} if alertas else {}
    return [como_dict(a, publicas.get(a.corpus_id)) for a in alertas]


def resumo(db: Session, tenant_id: str) -> dict:
    por_estado = {e: 0 for e in ESTADOS}
    for e, n in db.query(AlertaLicitacao.estado, func.count(AlertaLicitacao.id)).filter_by(tenant_id=tenant_id).group_by(AlertaLicitacao.estado).all():
        por_estado[e] = n
    nao_vistas = db.query(AlertaLicitacao).filter_by(tenant_id=tenant_id, atualizacao_nao_vista=True).count()
    return {"por_estado": por_estado, "atualizacoes_nao_vistas": nao_vistas, "regras_ativas": db.query(RegraAlertaLicitacao).filter_by(tenant_id=tenant_id, ativa=True).count()}


def marcar_visto(db: Session, tenant_id: str, alerta_id: int, agora: datetime | None = None) -> dict:
    alerta = _alerta(db, tenant_id, alerta_id)
    if alerta.estado == "novo":
        alerta.estado = "visto"
    alerta.visto_em = agora or _agora()
    alerta.atualizacao_nao_vista = False
    db.commit()
    return como_dict(alerta, db.get(LicitacaoPublica, alerta.corpus_id))


def dispensar(db: Session, tenant_id: str, ator_id: str | None, alerta_id: int) -> dict:
    alerta = _alerta(db, tenant_id, alerta_id)
    alerta.estado, alerta.atualizacao_nao_vista = "dispensado", False
    auditoria_service.registrar(db, tenant_id, "alerta_licitacao_dispensado", "alerta_licitacao", alerta.id, ator_id, {"corpus_id": alerta.corpus_id})
    db.commit()
    return como_dict(alerta, db.get(LicitacaoPublica, alerta.corpus_id))


def acompanhar(db: Session, tenant_id: str, usuario_id: int | None, alerta_id: int) -> tuple[dict, dict]:
    """Cria a cópia privada da licitação (idempotente) e marca o alerta como acompanhado."""
    alerta = _alerta(db, tenant_id, alerta_id)
    licitacao, _ = licitacoes.acompanhar(db, tenant_id, usuario_id, alerta.corpus_id)
    alerta = _alerta(db, tenant_id, alerta_id)
    alerta.estado, alerta.atualizacao_nao_vista = "acompanhado", False
    db.commit()
    return como_dict(alerta, db.get(LicitacaoPublica, alerta.corpus_id)), licitacoes.como_dict(licitacao)
