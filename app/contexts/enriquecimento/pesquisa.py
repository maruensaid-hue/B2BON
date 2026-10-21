"""Pesquisa de decisores governada: prévia → confirmação → reserva → execução → liquidação/reconciliação.

Princípios (ver `docs/b2bon/GOVERNANCA_CREDITOS_ENRIQUECIMENTO.md`):

* o universo do ICP nunca dispara pesquisa: só o conjunto EXPLÍCITO de empresas da prévia chega ao provedor;
* o backend é a única autoridade: a confirmação recalcula e revalida tudo, e nada que o front mande altera plano, saldo, limite ou orçamento;
* nenhuma chamada ao provedor acontece antes de a reserva atômica (créditos do tenant e orçamento global) estar gravada;
* desfecho ambíguo (timeout, 5xx, resposta ilegível) nunca é repetido nem liberado: fica retido até reconciliação com o uso do provedor.
"""

import hashlib
import hmac
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import ledger
from app.contexts.enriquecimento.config import ConfigResolvida, agora_utc, config_vigente, periodo_de
from app.core.config import settings
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.enriquecimento_creditos import PesquisaDecisores, PesquisaDecisoresEmpresa, PesquisaDecisoresTransicao
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.services.errors import NaoAutorizado, NaoEncontrado, PesquisaBloqueada, ValidacaoFalhou

logger = logging.getLogger("b2bon.enriquecimento")

ESTADOS_PESQUISA = (
    "criada", "validada", "reservada", "enviada", "em_processamento", "concluida", "parcial", "falha", "cancelada", "reconciliada",
)
ESTADOS_TERMINAIS = ("concluida", "parcial", "falha", "cancelada", "reconciliada")
MAX_PREVIAS_ABERTAS = 50  # prévias não confirmadas e ainda válidas por tenant (proteção contra enchimento de tabela)
FALHAS_SEGUIDAS_PARA_PARAR = 3  # depois disso o envio pausa e o restante fica pendente (retomável), sem martelar o provedor
PAPEIS_GESTORES = ("admin", "super_admin")


@dataclass(frozen=True)
class Solicitante:
    id: int
    papel: str
    tenant_id: str

    @property
    def gestor(self) -> bool:
        return self.papel in PAPEIS_GESTORES


def _bloqueio(codigo: str, mensagem: str) -> dict:
    return {"codigo": codigo, "mensagem": mensagem}


def _chave_empresa(conta: Conta) -> str | None:
    """Identidade da empresa para deduplicar a seleção: CNPJ só com dígitos, senão domínio normalizado."""
    digitos = re.sub(r"\D", "", conta.cnpj or "")
    if digitos:
        return f"cnpj:{digitos}"
    dominio = (conta.dominio or "").strip().lower().removeprefix("www.")
    return f"dominio:{dominio}" if dominio else None


def _registrar_transicao(db: Session, pesquisa: PesquisaDecisores, novo: str, motivo: str | None, ator_id: str | None,
                         item: PesquisaDecisoresEmpresa | None = None, anterior: str | None = None) -> None:
    db.add(PesquisaDecisoresTransicao(
        pesquisa_id=pesquisa.id, tenant_id=pesquisa.tenant_id, item_id=item.id if item is not None else None,
        estado_anterior=anterior if anterior is not None else (item.estado if item is not None else pesquisa.estado), estado_novo=novo,
        motivo=motivo, ator_id=ator_id,
    ))


def _mudar_estado(db: Session, pesquisa: PesquisaDecisores, novo: str, motivo: str | None = None, ator_id: str | None = None) -> None:
    _registrar_transicao(db, pesquisa, novo, motivo, ator_id)
    pesquisa.estado = novo


def _mudar_estado_item(db: Session, pesquisa: PesquisaDecisores, item: PesquisaDecisoresEmpresa, novo: str, motivo: str | None = None,
                       ator_id: str | None = None) -> None:
    _registrar_transicao(db, pesquisa, novo, motivo, ator_id, item=item)
    item.estado = novo
    if motivo is not None:
        item.motivo = motivo[:500]


def _hash_selecao(tenant_id: str, conta_ids: list[int], decisores: int, config: ConfigResolvida, provedor: str) -> str:
    base = json.dumps({"t": tenant_id, "c": sorted(conta_ids), "d": decisores, "o": config.origem, "i": config.id, "v": config.versao,
                       "p": provedor}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(base.encode()).hexdigest()


def _config_ou_bloqueio(db: Session, tenant_id: str) -> ConfigResolvida:
    config, motivo = config_vigente(db, tenant_id)
    if config is None:
        mensagens = {
            "sem_plano_ativo": "Seu tenant não tem plano ativo. Regularize a licença ou fale com o comercial para liberar a pesquisa de decisores.",
            "plano_sem_configuracao": "Seu plano ainda não tem a pesquisa de decisores configurada. Fale com o comercial para liberar.",
        }
        raise PesquisaBloqueada(mensagens[motivo], motivo, [_bloqueio(motivo, mensagens[motivo])])
    if not config.utilizavel:
        mensagem = ("A configuração da pesquisa de decisores do seu plano está incompleta. Fale com o comercial para concluir "
                    f"(faltando: {', '.join(config.faltando)}).")
        raise PesquisaBloqueada(mensagem, "config_incompleta", [_bloqueio("config_incompleta", mensagem)])
    return config


def _validar_parametros(config: ConfigResolvida, provider: ContactEnrichmentProvider, decisores: int, empresas: int) -> None:
    """Rejeita (nunca ajusta em silêncio) valores acima dos tetos conhecidos."""
    if isinstance(decisores, bool) or not isinstance(decisores, int) or decisores < 1:
        raise ValidacaoFalhou("Decisores por empresa deve ser um número inteiro maior que zero.")
    if decisores > config.decisores_por_empresa_max:
        raise ValidacaoFalhou(f"Decisores por empresa ({decisores}) excede o máximo do seu plano ({config.decisores_por_empresa_max}).")
    teto_provedor = provider.max_contatos_por_consulta
    if teto_provedor is not None and decisores > teto_provedor:
        raise ValidacaoFalhou(f"Decisores por empresa ({decisores}) excede o que o provedor entrega por consulta ({teto_provedor}).")
    if empresas > config.itens_por_lote_max:
        raise ValidacaoFalhou(f"A seleção tem {empresas} empresa(s); o máximo por pesquisa no seu plano é {config.itens_por_lote_max}.")


def _avaliar_limites(db: Session, tenant_id: str, config: ConfigResolvida, provider: ContactEnrichmentProvider, total: int,
                     agora: datetime) -> tuple[list[dict], dict]:
    """Bloqueios que dependem de estado (provedor, saldo, período, orçamento global) e os números usados. Quem chama já preparou o razão."""
    bloqueios: list[dict] = []
    contexto: dict = {}
    if not provider.disponivel:
        bloqueios.append(_bloqueio("provedor_indisponivel", "O provedor de contatos não está configurado neste ambiente."))
    contexto["disponivel"] = ledger.disponivel(db, tenant_id)
    if total > contexto["disponivel"]:
        bloqueios.append(_bloqueio("saldo_insuficiente", f"Esta pesquisa pode consumir até {total} crédito(s) de enriquecimento e há "
                                                         f"{contexto['disponivel']} disponível(is)."))
    if config.limite_periodo_creditos is not None:
        usado = ledger.consumo_liquido(db, tenant_id, periodo_de(agora)) + ledger.reservado(db, tenant_id)
        contexto["periodo_restante"] = max(0, config.limite_periodo_creditos - usado)
        if total > contexto["periodo_restante"]:
            bloqueios.append(_bloqueio("limite_periodo", f"O limite de {config.limite_periodo_creditos} crédito(s) no período deixa "
                                                         f"{contexto['periodo_restante']} disponível(is); a pesquisa pode precisar de {total}."))
    if provider.pago:
        situacao = ledger.situacao_global(db, provider.nome_provedor, agora)
        contexto["global_restante"] = situacao["restante"]
        contexto["global_nivel"] = situacao["nivel"]
        if situacao["nivel"] == "nao_configurado":
            bloqueios.append(_bloqueio("orcamento_global_nao_configurado", "As chamadas ao provedor estão bloqueadas até o administrador "
                                                                           "configurar o orçamento global. Fale com o administrador."))
        elif total > situacao["restante"]:
            bloqueios.append(_bloqueio("orcamento_global_esgotado", "O limite global do provedor para o período não comporta esta pesquisa. "
                                                                    "Fale com o administrador."))
    return bloqueios, contexto


def _sugerir_ajustes(config: ConfigResolvida, contexto: dict, elegiveis: int, decisores: int) -> list[dict]:
    """Alternativas calculadas só com limites e saldos conhecidos agora. Não prometem que cabem e não alteram a escolha do usuário."""
    capacidades = [contexto["disponivel"]]
    for chave in ("periodo_restante", "global_restante"):
        if contexto.get(chave) is not None:
            capacidades.append(contexto[chave])
    capacidade = max(0, min(capacidades))
    sugestoes: list[dict] = []
    if elegiveis and capacidade >= 1:
        for menor in range(decisores - 1, 0, -1):
            if elegiveis * menor <= capacidade:
                sugestoes.append({"tipo": "reduzir_profundidade", "decisores_por_empresa": menor, "empresas_cobertas": elegiveis})
                break
        if decisores > 1:
            mais = min(capacidade, config.itens_por_lote_max)
            if mais > elegiveis:
                sugestoes.append({"tipo": "ampliar_abrangencia", "decisores_por_empresa": 1, "empresas_cobertas": mais})
        cabem = min(capacidade // decisores, config.itens_por_lote_max)
        if 1 <= cabem < elegiveis:
            sugestoes.append({"tipo": "reduzir_selecao", "decisores_por_empresa": decisores, "empresas_cobertas": cabem})
    return sugestoes


def _existentes_do_provedor(db: Session, tenant_id: str, conta_ids: list[int], provedor: str) -> dict[int, int]:
    linhas = (
        db.query(Decisor.conta_id, func.count(Decisor.id))
        .filter(Decisor.tenant_id == tenant_id, Decisor.conta_id.in_(conta_ids), Decisor.origem == provedor)
        .group_by(Decisor.conta_id).all()
    )
    return {conta_id: total for conta_id, total in linhas}


def _plano_de_itens(db: Session, tenant_id: str, contas: list[Conta], decisores: int, provedor: str) -> list[dict]:
    """Para cada empresa selecionada: pendente (com o que falta buscar) ou deduplicada (com motivo)."""
    existentes = _existentes_do_provedor(db, tenant_id, [c.id for c in contas], provedor)
    vistas: set[str] = set()
    plano = []
    for conta in contas:
        chave = _chave_empresa(conta)
        ja = existentes.get(conta.id, 0)
        if chave is not None and chave in vistas:
            plano.append({"conta": conta, "estado": "deduplicada", "motivo": "duplicada_na_selecao", "existentes": ja, "buscar": 0})
            continue
        if chave is not None:
            vistas.add(chave)
        buscar = max(0, decisores - ja)
        if buscar == 0:
            plano.append({"conta": conta, "estado": "deduplicada", "motivo": "decisores_ja_obtidos_do_provedor", "existentes": ja, "buscar": 0})
        else:
            plano.append({"conta": conta, "estado": "pendente", "motivo": None, "existentes": ja, "buscar": buscar})
    return plano


def estimar(db: Session, *, solicitante: Solicitante, conta_ids: list[int], decisores_por_empresa: int | None,
            provider: ContactEnrichmentProvider, agora: datetime | None = None) -> PesquisaDecisores:
    """Cria a PRÉVIA (nada é reservado nem enviado ao provedor). O usuário revê a estimativa e só então confirma essa mesma prévia."""
    agora = agora or agora_utc()
    tenant_id = solicitante.tenant_id
    if not conta_ids or not isinstance(conta_ids, list):
        raise ValidacaoFalhou("Selecione ao menos uma empresa. A pesquisa de decisores só vale para empresas escolhidas explicitamente.")
    if len(conta_ids) > settings.enriquecimento_max_selecao_requisicao:
        raise ValidacaoFalhou(f"Seleção grande demais para uma requisição (máximo técnico de {settings.enriquecimento_max_selecao_requisicao}).")
    if any(isinstance(i, bool) or not isinstance(i, int) for i in conta_ids):
        raise ValidacaoFalhou("Identificadores de empresa inválidos.")
    ids_unicos = list(dict.fromkeys(conta_ids))

    config = _config_ou_bloqueio(db, tenant_id)
    if decisores_por_empresa is None:
        decisores, origem = config.decisores_por_empresa_padrao, "padrao_plano"
    else:
        decisores, origem = decisores_por_empresa, "informado_usuario"
    _validar_parametros(config, provider, decisores, len(ids_unicos))

    contas = db.query(Conta).filter(Conta.tenant_id == tenant_id, Conta.id.in_(ids_unicos)).all()
    por_id = {c.id: c for c in contas}
    if len(por_id) != len(ids_unicos):  # mesma resposta para "não existe" e "é de outro tenant" (sem enumeração)
        raise NaoEncontrado("Uma ou mais empresas da seleção não foram encontradas.")
    contas_ordenadas = [por_id[i] for i in ids_unicos]

    db.query(PesquisaDecisores).filter(
        PesquisaDecisores.tenant_id == tenant_id, PesquisaDecisores.estado == "criada", PesquisaDecisores.previa_expira_em <= agora,
    ).update({"estado": "cancelada", "motivo": "previa_expirada"}, synchronize_session=False)
    abertas = db.query(PesquisaDecisores).filter_by(tenant_id=tenant_id, estado="criada").count()
    if abertas >= MAX_PREVIAS_ABERTAS:
        raise ValidacaoFalhou("Há muitas prévias de pesquisa em aberto. Confirme ou cancele algumas antes de criar outra.")

    plano = _plano_de_itens(db, tenant_id, contas_ordenadas, decisores, provider.nome_provedor)
    elegiveis = [p for p in plano if p["estado"] == "pendente"]
    total = sum(p["buscar"] for p in elegiveis)

    ledger.preparar(db, tenant_id, config, agora)
    bloqueios, contexto = _avaliar_limites(db, tenant_id, config, provider, total, agora)
    deduplicadas = len(plano) - len(elegiveis)
    incertezas = [
        f"O consumo real depende do que o provedor devolver: no máximo {total} crédito(s) (1 crédito = 1 contato revelado); pode ser menor.",
        "Não há custo em reais por crédito definido no sistema: a estimativa é em créditos, não em dinheiro.",
        f"A prévia vale por {settings.enriquecimento_previa_validade_min} minuto(s) e será revalidada por inteiro na confirmação.",
    ]
    if deduplicadas:
        incertezas.append(f"{deduplicadas} empresa(s) ficam fora da consulta por duplicidade ou decisores já obtidos; a economia não é garantida "
                          "(os decisores já obtidos podem não ter os cargos que você busca).")
    estimativa = {
        "creditos_maximos": total, "empresas_selecionadas": len(plano), "empresas_a_consultar": len(elegiveis),
        "empresas_deduplicadas": deduplicadas, "decisores_por_empresa": decisores, "origem_decisores": origem,
        "disponivel": contexto["disponivel"], "limite_periodo_restante": contexto.get("periodo_restante"),
        "limites": {"decisores_por_empresa_max": config.decisores_por_empresa_max, "itens_por_lote_max": config.itens_por_lote_max,
                    "limite_periodo_creditos": config.limite_periodo_creditos},
        "config": {"origem": config.origem, "versao": config.versao},
        "viavel": not bloqueios, "bloqueios": bloqueios,
        "ajustes_sugeridos": [] if not bloqueios else _sugerir_ajustes(config, contexto, len(elegiveis), decisores),
        "nota_ajustes": "Sugestões calculadas com os limites e saldos de agora; não são promessa e serão revalidadas. Sua escolha não foi alterada.",
        "incertezas": incertezas,
    }
    pesquisa = PesquisaDecisores(
        id=uuid.uuid4().hex, tenant_id=tenant_id, usuario_id=solicitante.id, provedor=provider.nome_provedor, estado="criada",
        decisores_por_empresa=decisores, origem_decisores=origem, config_origem=config.origem, config_id=config.id,
        config_versao=config.versao, total_empresas=len(plano), total_maximo=total, estimativa=estimativa,
        selecao_hash=_hash_selecao(tenant_id, ids_unicos, decisores, config, provider.nome_provedor),
        previa_expira_em=agora + timedelta(minutes=settings.enriquecimento_previa_validade_min),
    )
    db.add(pesquisa)
    db.flush()
    for item in plano:
        db.add(PesquisaDecisoresEmpresa(
            pesquisa_id=pesquisa.id, tenant_id=tenant_id, conta_id=item["conta"].id, estado=item["estado"], motivo=item["motivo"],
            decisores_existentes=item["existentes"], decisores_solicitados=item["buscar"],
        ))
    _registrar_transicao(db, pesquisa, "criada", f"previa_criada viavel={not bloqueios}", str(solicitante.id), anterior="-")
    db.commit()
    logger.info("ENRIQUECIMENTO_PREVIA pesquisa=%s tenant=%s empresas=%s maximo=%s viavel=%s", pesquisa.id, tenant_id, len(plano), total,
                not bloqueios)
    return pesquisa


def obter(db: Session, tenant_id: str, solicitante: Solicitante, pesquisa_id: str) -> PesquisaDecisores:
    pesquisa = db.query(PesquisaDecisores).filter_by(id=pesquisa_id, tenant_id=tenant_id).one_or_none()
    if pesquisa is None or not (solicitante.gestor or pesquisa.usuario_id == solicitante.id):
        raise NaoEncontrado("Pesquisa não encontrada.")  # outro tenant e fora do escopo do vendedor respondem igual
    return pesquisa


def itens_de(db: Session, pesquisa_id: str) -> list[PesquisaDecisoresEmpresa]:
    return db.query(PesquisaDecisoresEmpresa).filter_by(pesquisa_id=pesquisa_id).order_by(PesquisaDecisoresEmpresa.id).all()


def _recusar_confirmacao(db: Session, pesquisa_id: str, tenant_id: str, ator_id: str, erro: PesquisaBloqueada) -> None:
    """Desfaz a transação de confirmação e deixa o rastro da recusa; a prévia continua `criada` (revisável)."""
    db.rollback()
    db.add(PesquisaDecisoresTransicao(pesquisa_id=pesquisa_id, tenant_id=tenant_id, estado_anterior="criada", estado_novo="criada",
                                      motivo=f"confirmacao_recusada:{erro.codigo}", ator_id=ator_id))
    db.commit()


def confirmar(db: Session, *, solicitante: Solicitante, pesquisa_id: str, selecao_hash: str, idempotency_key: str,
              provider: ContactEnrichmentProvider, agora: datetime | None = None) -> PesquisaDecisores:
    """Revalida tudo no servidor e reserva os créditos de forma atômica. Devolve a pesquisa `reservada` (ou `concluida` se nada precisar ser
    consultado). Idempotente: repetir com a mesma chave devolve o estado atual sem reservar de novo. NÃO chama o provedor — ver `executar`."""
    agora = agora or agora_utc()
    tenant_id, ator = solicitante.tenant_id, str(solicitante.id)
    if not idempotency_key or not 8 <= len(idempotency_key) <= 100:
        raise ValidacaoFalhou("Informe uma chave de idempotência de 8 a 100 caracteres.")
    pesquisa = obter(db, tenant_id, solicitante, pesquisa_id)
    if not solicitante.gestor and pesquisa.usuario_id != solicitante.id:
        raise NaoAutorizado("Só quem criou a prévia (ou um gestor) pode confirmá-la.")
    if pesquisa.estado != "criada":
        if pesquisa.idempotency_key == idempotency_key:
            return pesquisa
        raise PesquisaBloqueada("Esta pesquisa já foi confirmada ou encerrada.", "pesquisa_ja_processada")
    if not hmac.compare_digest(pesquisa.selecao_hash, selecao_hash or ""):
        raise PesquisaBloqueada("A seleção ou os parâmetros mudaram desde a revisão. Revise a prévia de novo.", "selecao_alterada")
    if pesquisa.previa_expira_em <= agora:
        pesquisa.estado, pesquisa.motivo = "cancelada", "previa_expirada"
        db.commit()
        raise PesquisaBloqueada("A prévia expirou. Crie uma nova para revisar a estimativa.", "previa_expirada")

    try:
        alterados = db.query(PesquisaDecisores).filter(
            PesquisaDecisores.id == pesquisa.id, PesquisaDecisores.tenant_id == tenant_id, PesquisaDecisores.estado == "criada",
        ).update({"estado": "validada", "idempotency_key": idempotency_key, "confirmada_por": solicitante.id, "confirmada_em": agora},
                 synchronize_session=False)
        if alterados == 0:  # outra confirmação ganhou a corrida
            db.rollback()
            db.refresh(pesquisa)
            if pesquisa.idempotency_key == idempotency_key:
                return pesquisa
            raise PesquisaBloqueada("Esta pesquisa já foi confirmada ou encerrada.", "pesquisa_ja_processada")
        db.flush()
    except IntegrityError:
        db.rollback()
        raise PesquisaBloqueada("Essa chave de idempotência já foi usada em outra pesquisa.", "chave_idempotencia_em_uso") from None
    db.refresh(pesquisa)

    try:
        _validar_e_reservar(db, solicitante, pesquisa, provider, agora)
    except PesquisaBloqueada as erro:
        _recusar_confirmacao(db, pesquisa_id, tenant_id, ator, erro)
        raise
    db.commit()
    return pesquisa


def _validar_e_reservar(db: Session, solicitante: Solicitante, pesquisa: PesquisaDecisores, provider: ContactEnrichmentProvider,
                        agora: datetime) -> None:
    tenant_id, ator = pesquisa.tenant_id, str(solicitante.id)
    config = _config_ou_bloqueio(db, tenant_id)
    if (config.origem, config.id, config.versao) != (pesquisa.config_origem, pesquisa.config_id, pesquisa.config_versao):
        raise PesquisaBloqueada("A configuração do seu plano mudou desde a prévia. Crie uma nova prévia.", "estimativa_desatualizada")
    if provider.nome_provedor != pesquisa.provedor:
        raise PesquisaBloqueada("O provedor mudou desde a prévia. Crie uma nova prévia.", "estimativa_desatualizada")
    itens = itens_de(db, pesquisa.id)
    try:
        _validar_parametros(config, provider, pesquisa.decisores_por_empresa, len(itens))
    except ValidacaoFalhou as erro:
        raise PesquisaBloqueada(str(erro), "parametros_fora_do_limite", [_bloqueio("parametros_fora_do_limite", str(erro))]) from None

    contas = {c.id: c for c in db.query(Conta).filter(Conta.tenant_id == pesquisa.tenant_id, Conta.id.in_([i.conta_id for i in itens])).all()}
    if len(contas) != len(itens):
        raise PesquisaBloqueada("Alguma empresa da seleção não está mais disponível. Crie uma nova prévia.", "estimativa_desatualizada")
    plano = _plano_de_itens(db, tenant_id, [contas[i.conta_id] for i in itens], pesquisa.decisores_por_empresa, provider.nome_provedor)
    atual = {p["conta"].id: p["buscar"] for p in plano}
    if {i.conta_id: i.decisores_solicitados for i in itens} != atual:
        raise PesquisaBloqueada("Os decisores já obtidos mudaram desde a prévia. Crie uma nova prévia para ver a estimativa certa.",
                                "estimativa_desatualizada")
    total = sum(atual.values())

    # Ordem fixa de travas: orçamento global (todos os tenants) → carteira do tenant.
    if provider.pago:
        ledger.travar_orcamento(db, provider.nome_provedor)
    ledger.preparar(db, tenant_id, config, agora)
    bloqueios, _ = _avaliar_limites(db, tenant_id, config, provider, total, agora)
    if bloqueios:
        raise PesquisaBloqueada(bloqueios[0]["mensagem"], bloqueios[0]["codigo"], bloqueios)

    _registrar_transicao(db, pesquisa, "validada", "confirmacao_validada", ator, anterior="criada")
    pesquisa.estado = "validada"
    if total > 0:
        ledger.lancar(db, tenant_id, "RESERVA", delta_reservado=total, provedor=provider.nome_provedor, pesquisa_id=pesquisa.id,
                      origem="pesquisa_decisores", motivo=f"Reserva da pesquisa {pesquisa.id}", ator_id=ator, idempotency_key=f"reserva:{pesquisa.id}",
                      agora=agora)
        for item in itens:
            item.creditos_reservados = item.decisores_solicitados
        pesquisa.creditos_reservados = total
        _mudar_estado(db, pesquisa, "reservada", f"reservados {total} credito(s)", ator)
        if provider.pago:
            situacao = ledger.situacao_global(db, provider.nome_provedor, agora)
            if situacao["nivel"] in ("alerta", "esgotado"):
                logger.warning("ENRIQUECIMENTO_ORCAMENTO_GLOBAL provedor=%s nivel=%s percentual=%s", provider.nome_provedor, situacao["nivel"],
                               situacao["percentual"])
    else:
        _mudar_estado(db, pesquisa, "concluida", "nada_a_consultar: todas as empresas deduplicadas", ator)
    logger.info("ENRIQUECIMENTO_RESERVA pesquisa=%s tenant=%s reservados=%s", pesquisa.id, tenant_id, total)
