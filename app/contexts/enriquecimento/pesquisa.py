"""Pesquisa de decisores governada: prévia → confirmação → reserva → execução → liquidação/reconciliação.

Princípios (ver `docs/b2bon/GOVERNANCA_CREDITOS_ENRIQUECIMENTO.md`):

* o universo do ICP nunca dispara pesquisa: só o conjunto EXPLÍCITO de empresas da prévia chega ao provedor;
* o backend é a única autoridade: a confirmação recalcula e revalida tudo, e nada que o front mande altera plano, saldo, limite ou orçamento;
* nenhuma chamada ao provedor acontece antes de a reserva atômica (créditos do tenant e orçamento global) estar gravada;
* a estimativa é um TETO calculado com as tarifas aprovadas do provedor; o que se cobra é o consumo MEDIDO pela resposta dele;
* desfecho ambíguo (timeout, 5xx, resposta ilegível, medição ausente) nunca é repetido nem liberado: fica retido até reconciliação.
"""

import hashlib
import hmac
import json
import logging
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import ledger, precos
from app.contexts.enriquecimento.config import (
    ConfigResolvida,
    PoliticaResolvida,
    agora_utc,
    exigir_configuracao,
    fim_do_mes,
    inicio_do_mes,
    mensagem,
    orcamento_vigente,
    periodo_de,
)
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

    @property
    def irrestrito(self) -> bool:
        """O super admin da plataforma pesquisa sem os limites de plano e franquia (o dos clientes, representantes e vendedores continua valendo)."""
        return self.papel == "super_admin" and settings.enriquecimento_super_admin_sem_limites


def _bloqueio(codigo: str, texto: str) -> dict:
    return {"codigo": codigo, "mensagem": texto}


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


def _hash_selecao(tenant_id: str, conta_ids: list[int], decisores: int, config: ConfigResolvida, politica: PoliticaResolvida, provedor: str,
                  emails: bool = True, telefones: bool = False) -> str:
    base = json.dumps({"t": tenant_id, "c": sorted(conta_ids), "d": decisores, "o": config.origem, "i": config.id, "v": config.versao,
                       "p": provedor, "pol": politica.id, "polv": politica.versao, "em": emails, "tel": telefones}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(base.encode()).hexdigest()


def _validar_parametros(config: ConfigResolvida, politica: PoliticaResolvida, provider: ContactEnrichmentProvider, decisores: int,
                        empresas: int) -> None:
    """Rejeita (nunca ajusta em silêncio) valores acima dos tetos conhecidos."""
    if isinstance(decisores, bool) or not isinstance(decisores, int) or decisores < 1:
        raise ValidacaoFalhou("Decisores por empresa deve ser um número inteiro maior que zero.")
    if decisores > config.decisores_por_empresa_max:
        raise ValidacaoFalhou(f"Decisores por empresa ({decisores}) excede o máximo do seu plano ({config.decisores_por_empresa_max}).")
    if decisores > politica.tamanho_pagina_busca:
        raise ValidacaoFalhou(f"Decisores por empresa ({decisores}) excede o que uma consulta ao provedor retorna ({politica.tamanho_pagina_busca}).")
    teto_provedor = provider.max_contatos_por_consulta
    if teto_provedor is not None and decisores > teto_provedor:
        raise ValidacaoFalhou(f"Decisores por empresa ({decisores}) excede o que o provedor entrega por consulta ({teto_provedor}).")
    if config.itens_por_lote_max is not None and empresas > config.itens_por_lote_max:
        raise ValidacaoFalhou(f"A seleção tem {empresas} empresa(s); o máximo por pesquisa no seu plano é {config.itens_por_lote_max}.")


def uso_do_periodo(db: Session, tenant_id: str, agora: datetime, ignorar_pesquisa_id: str | None = None, desde_sempre: bool = False) -> dict:
    """O que o tenant já confirmou neste mês (Brasília): pesquisas, empresas consultadas e decisores pedidos. Prévias, canceladas e as que falharam sem consumo não contam, nem a
    própria pesquisa que está sendo confirmada (`ignorar_pesquisa_id`): ela é o pedido, não o que já foi usado. Com `desde_sempre` (autorização única da POC),
    conta tudo o que o tenant já confirmou, de qualquer mês."""
    inicio, fim = inicio_do_mes(agora), fim_do_mes(agora)
    consulta = db.query(PesquisaDecisores).filter(
        PesquisaDecisores.tenant_id == tenant_id, PesquisaDecisores.confirmada_em.isnot(None),
        PesquisaDecisores.estado.notin_(("criada", "cancelada", "falha")), PesquisaDecisores.id != (ignorar_pesquisa_id or ""),
    )
    if not desde_sempre:
        consulta = consulta.filter(PesquisaDecisores.confirmada_em >= inicio, PesquisaDecisores.confirmada_em < fim)
    pesquisas = consulta.all()
    ids = [p.id for p in pesquisas]
    itens = db.query(PesquisaDecisoresEmpresa).filter(PesquisaDecisoresEmpresa.pesquisa_id.in_(ids or [""]),
                                                     PesquisaDecisoresEmpresa.decisores_solicitados > 0).all()
    return {"pesquisas": len(pesquisas), "empresas": len(itens), "contatos": sum(i.decisores_solicitados for i in itens)}


def _com_limite_de_pacote(db: Session, tenant_id: str, config: ConfigResolvida, agora: datetime) -> ConfigResolvida:
    """Pacote adicional válido (com crédito não consumido e dentro dos 30 dias) faz o limite de créditos por pesquisa passar a ser o do pacote, mesmo que a
    franquia do plano seja menor. Nunca reduz um limite maior que o plano já dê, e não mexe em plano sem limite. Termina quando o crédito acaba ou vence."""
    if config.limite_origem == "super_admin" or config.limite_creditos_pesquisa is None:
        return config
    limite, _ = ledger.limite_por_pacotes(db, tenant_id, agora)
    if limite is not None and limite > config.limite_creditos_pesquisa:
        return replace(config, limite_creditos_pesquisa=limite, limite_origem="pacote")
    return config


def _avaliar_limites(db: Session, tenant_id: str, config: ConfigResolvida, politica: PoliticaResolvida, provider: ContactEnrichmentProvider,
                     total_cliente: int, total_provedor: int, agora: datetime, empresas: int = 0, contatos: int = 0,
                     ignorar_pesquisa_id: str | None = None, irrestrito: bool = False) -> tuple[list[dict], dict]:
    """Bloqueios que dependem de estado (provedor, saldo, período, orçamento global) e os números usados. Quem chama já preparou o razão.
    Saldo e período são em créditos do CLIENTE; o orçamento global é em créditos do PROVEDOR."""
    bloqueios: list[dict] = []
    contexto: dict = {}
    if not provider.disponivel:
        bloqueios.append(_bloqueio("provedor_indisponivel", mensagem("provedor_indisponivel")))
    if config.limite_creditos_pesquisa is not None:
        contexto["limite_pesquisa"] = config.limite_creditos_pesquisa
        if total_cliente > config.limite_creditos_pesquisa:
            bloqueios.append(_bloqueio("limite_por_pesquisa", f"Esta pesquisa pode precisar de até {total_cliente} crédito(s) e o limite por pesquisa do "
                                                              f"seu {'pacote' if config.limite_origem == 'pacote' else 'plano'} é {config.limite_creditos_pesquisa}."))
    contexto["disponivel"] = ledger.disponivel(db, tenant_id)
    if total_cliente > contexto["disponivel"] and not irrestrito:  # o super admin não tem saldo a respeitar: a diferença é concedida na reserva
        bloqueios.append(_bloqueio("saldo_insuficiente", f"Esta pesquisa pode consumir até {total_cliente} crédito(s) de enriquecimento e há "
                                                         f"{contexto['disponivel']} disponível(is)."))
    unica = config.periodicidade == "unica"  # autorização única (POC): os limites de pesquisas/empresas/contatos valem para a vida do tenant
    uso = uso_do_periodo(db, tenant_id, agora, ignorar_pesquisa_id, desde_sempre=unica)
    contexto["uso_periodo"] = uso
    for rotulo, atual, pedido, limite in (("pesquisas", uso["pesquisas"], 1, config.limite_pesquisas_periodo),
                                          ("empresas", uso["empresas"], empresas, config.limite_empresas_periodo),
                                          ("contatos", uso["contatos"], contatos, config.limite_contatos_periodo)):
        if limite is not None and atual + pedido > limite:
            bloqueios.append(_bloqueio(f"limite_{rotulo}_periodo", f"O limite de {limite} {rotulo} {'na POC' if unica else 'no mês'} deixa {max(0, limite - atual)}; "
                                                                      f"esta pesquisa usaria {pedido}."))
    if config.limite_periodo_creditos is not None:
        usado = ledger.consumo_liquido(db, tenant_id, periodo_de(agora)) + ledger.reservado(db, tenant_id)
        contexto["periodo_restante"] = max(0, config.limite_periodo_creditos - usado)
        if total_cliente > contexto["periodo_restante"]:
            bloqueios.append(_bloqueio("limite_periodo", f"O limite de {config.limite_periodo_creditos} crédito(s) no período deixa "
                                                         f"{contexto['periodo_restante']} disponível(is); a pesquisa pode precisar de {total_cliente}."))
    if provider.pago:
        orcamento = orcamento_vigente(db, provider.nome_provedor)
        if not orcamento.configurado:
            codigo = "orcamento_global_pendente_aprovacao" if orcamento.pendente_aprovacao else "orcamento_global_nao_configurado"
            bloqueios.append(_bloqueio(codigo, mensagem(codigo)))
            contexto["global_nivel"] = "nao_configurado"
        else:
            situacao = ledger.situacao_global(db, provider.nome_provedor, agora)
            contexto["global_restante_provedor"] = situacao["restante"]
            contexto["global_nivel"] = situacao["nivel"]
            if total_provedor > situacao["restante"]:
                bloqueios.append(_bloqueio("orcamento_global_esgotado", "O limite global do provedor para o período não comporta esta pesquisa. "
                                                                        "Fale com o administrador."))
    return bloqueios, contexto


def _sugerir_ajustes(config: ConfigResolvida, politica: PoliticaResolvida, contexto: dict, elegiveis: int, decisores: int, emails: bool = True,
                     telefones: bool = False) -> list[dict]:
    """Alternativas calculadas só com limites, saldos e tarifas aprovadas, em créditos do cliente. Não prometem que cabem (o consumo real é medido
    pelo provedor) e não alteram a escolha do usuário."""
    fator = politica.creditos_cliente_por_credito_provedor

    def custo_empresa(d: int) -> int:
        return politica.creditos_maximos_por_empresa(d, emails, telefones) * fator

    capacidades = [contexto["disponivel"]]
    if contexto.get("limite_pesquisa") is not None:
        capacidades.append(contexto["limite_pesquisa"])
    if contexto.get("periodo_restante") is not None:
        capacidades.append(contexto["periodo_restante"])
    if contexto.get("global_restante_provedor") is not None:
        capacidades.append(contexto["global_restante_provedor"] * fator)
    capacidade = max(0, min(capacidades))
    sugestoes: list[dict] = []
    if not elegiveis:
        return sugestoes
    for menor in range(decisores - 1, 0, -1):
        if elegiveis * custo_empresa(menor) <= capacidade:
            sugestoes.append({"tipo": "reduzir_profundidade", "decisores_por_empresa": menor, "empresas_cobertas": elegiveis})
            break
    maximo_empresas = config.itens_por_lote_max if config.itens_por_lote_max is not None else 10**9
    if decisores > 1:
        mais = min(capacidade // custo_empresa(1), maximo_empresas)
        if mais > elegiveis:
            sugestoes.append({"tipo": "ampliar_abrangencia", "decisores_por_empresa": 1, "empresas_cobertas": mais})
    cabem = min(capacidade // custo_empresa(decisores), maximo_empresas)
    if 1 <= cabem < elegiveis:
        sugestoes.append({"tipo": "reduzir_selecao", "decisores_por_empresa": decisores, "empresas_cobertas": cabem})
    return sugestoes


def _existentes_do_provedor(db: Session, tenant_id: str, conta_ids: list[int], provedor: str, emails: bool = True, telefones: bool = False) -> dict[int, int]:
    """Decisores do provedor que JÁ têm todos os dados pedidos agora: quem veio de uma pesquisa só de e-mail não conta para uma pesquisa que pede telefone."""
    consulta = db.query(Decisor.conta_id, func.count(Decisor.id)).filter(Decisor.tenant_id == tenant_id, Decisor.conta_id.in_(conta_ids), Decisor.origem == provedor)
    if emails:
        consulta = consulta.filter(Decisor.email.isnot(None), Decisor.email != "")
    if telefones:
        consulta = consulta.filter(Decisor.telefone.isnot(None), Decisor.telefone != "")
    return {conta_id: total for conta_id, total in consulta.group_by(Decisor.conta_id).all()}


def _plano_de_itens(db: Session, tenant_id: str, contas: list[Conta], decisores: int, provedor: str, politica: PoliticaResolvida, emails: bool = True,
                    telefones: bool = False) -> list[dict]:
    """Para cada empresa selecionada: pendente (com o que falta buscar e o teto de créditos do provedor) ou deduplicada (com motivo)."""
    existentes = _existentes_do_provedor(db, tenant_id, [c.id for c in contas], provedor, emails, telefones)
    vistas: set[str] = set()
    plano = []
    for conta in contas:
        chave = _chave_empresa(conta)
        ja = existentes.get(conta.id, 0)
        if chave is not None and chave in vistas:
            plano.append({"conta": conta, "estado": "deduplicada", "motivo": "duplicada_na_selecao", "existentes": ja, "buscar": 0, "teto": 0})
            continue
        if chave is not None:
            vistas.add(chave)
        buscar = max(0, decisores - ja)
        if buscar == 0:
            plano.append({"conta": conta, "estado": "deduplicada", "motivo": "decisores_ja_obtidos_do_provedor", "existentes": ja, "buscar": 0, "teto": 0})
        else:
            plano.append({"conta": conta, "estado": "pendente", "motivo": None, "existentes": ja, "buscar": buscar,
                          "teto": politica.creditos_maximos_por_empresa(buscar, emails, telefones)})
    return plano


def _rotulo_dados(emails: bool, telefones: bool) -> str:
    return "e-mail e telefone" if emails and telefones else ("só telefone" if telefones else "só e-mail")


def _por_categoria(politica: PoliticaResolvida, elegiveis: list[dict], emails: bool = True, telefones: bool = False) -> dict:
    """Teto por categoria e por fonte, em créditos do provedor e do cliente. QSA da Receita e Brasil API não consomem crédito nesta operação."""
    fator = politica.creditos_cliente_por_credito_provedor
    busca = len(elegiveis) * politica.tamanho_pagina_busca * politica.creditos_busca_por_resultado
    por_contato = ((politica.creditos_email or 0) if emails else 0) + ((politica.creditos_telefone or 0) if telefones else 0)
    revelacao = sum(p["buscar"] for p in elegiveis) * por_contato
    return {
        "ia": {"creditos": 0, "observacao": "Esta operação não usa IA."},
        "enriquecimento": {
            "lusha_busca": {"creditos_provedor_max": busca, "creditos_cliente_max": busca * fator},
            "lusha_revelacao": {"creditos_provedor_max": revelacao, "creditos_cliente_max": revelacao * fator},
            "receita_qsa": {"creditos_cliente_max": 0, "observacao": "Fluxo separado, sem consumo de crédito."},
            "brasilapi": {"creditos_cliente_max": 0, "observacao": "Fluxo separado, sem consumo de crédito."},
        },
    }


def estimar(db: Session, *, solicitante: Solicitante, conta_ids: list[int], decisores_por_empresa: int | None,
            provider: ContactEnrichmentProvider, agora: datetime | None = None, revelar_emails: bool = True,
            revelar_telefones: bool = False) -> PesquisaDecisores:
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

    config, politica = exigir_configuracao(db, tenant_id, provider, sincronizar=True, irrestrito=solicitante.irrestrito)
    if decisores_por_empresa is None:
        if config.decisores_por_empresa_padrao is None:
            raise ValidacaoFalhou("Informe quantos decisores por empresa você quer pesquisar: o seu plano não define um valor padrão.")
        decisores, origem = config.decisores_por_empresa_padrao, "padrao_plano"
    else:
        decisores, origem = decisores_por_empresa, "informado_usuario"
    _validar_parametros(config, politica, provider, decisores, len(ids_unicos))
    if not isinstance(revelar_emails, bool) or not isinstance(revelar_telefones, bool):
        raise ValidacaoFalhou("Escolha os dados a revelar com verdadeiro/falso.")
    recusa = politica.motivo_de_recusa_dos_dados(revelar_emails, revelar_telefones)
    if recusa:
        raise ValidacaoFalhou(recusa)

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

    plano = _plano_de_itens(db, tenant_id, contas_ordenadas, decisores, provider.nome_provedor, politica, revelar_emails, revelar_telefones)
    elegiveis = [p for p in plano if p["estado"] == "pendente"]
    fator = politica.creditos_cliente_por_credito_provedor
    total_provedor = sum(p["teto"] for p in elegiveis)
    total_cliente = total_provedor * fator
    solicitados = sum(p["buscar"] for p in elegiveis)

    ledger.preparar(db, tenant_id, config, agora)
    config = _com_limite_de_pacote(db, tenant_id, config, agora)
    bloqueios, contexto = _avaliar_limites(db, tenant_id, config, politica, provider, total_cliente, total_provedor, agora, len(elegiveis), solicitados,
                                           irrestrito=solicitante.irrestrito)
    deduplicadas = len(plano) - len(elegiveis)
    valor_maximo = precos.valor(total_provedor, politica.preco_unitario_brl)
    incertezas = [
        f"É um TETO, não uma previsão: no máximo {total_provedor} crédito(s) do provedor ({total_cliente} de enriquecimento). O que se cobra é o "
        "consumo informado pelo próprio provedor em cada consulta, que pode ser menor (por exemplo, dado já revelado antes não é cobrado de novo).",
        "Não há como saber de antemão quantos contatos o provedor devolverá, nem se terão os dados escolhidos "
        f"({_rotulo_dados(revelar_emails, revelar_telefones)}); o link do perfil no LinkedIn vem junto quando o provedor o informa; "
        f"{solicitados} decisor(es) são pedidos no total e o retorno pode ser menor.",
        "A busca no provedor é cobrada por resultado de uma página inteira, mesmo pedindo poucos decisores.",
        f"O valor em reais é estimativa de apresentação (preço por crédito do provedor ≈ R$ {precos.exibir(politica.preco_unitario_brl, politica.casas_exibicao)}), "
        "sem arredondamento de cobrança.",
        f"A prévia vale por {settings.enriquecimento_previa_validade_min} minuto(s) e será revalidada por inteiro na confirmação.",
    ]
    if deduplicadas:
        incertezas.append(f"{deduplicadas} empresa(s) ficam fora da consulta por duplicidade ou decisores já obtidos; a economia não é garantida "
                          "(os decisores já obtidos podem não ter os cargos que você busca).")
    estimativa = {
        "creditos_maximos": total_cliente, "creditos_provedor_maximos": total_provedor, "valor_maximo_brl": str(precos.exibir(valor_maximo, politica.casas_exibicao)),
        "preco_credito_provedor_brl": str(precos.exibir(politica.preco_unitario_brl, politica.casas_exibicao)),
        "creditos_cliente_por_credito_provedor": fator, "decisores_solicitados": solicitados,
        "por_categoria": _por_categoria(politica, elegiveis, revelar_emails, revelar_telefones),
        "dados_a_revelar": {"emails": revelar_emails, "telefones": revelar_telefones, "rotulo": _rotulo_dados(revelar_emails, revelar_telefones),
                            "creditos_por_decisor": ((politica.creditos_email or 0) if revelar_emails else 0) * fator
                            + ((politica.creditos_telefone or 0) if revelar_telefones else 0) * fator},
        "empresas_selecionadas": len(plano), "empresas_a_consultar": len(elegiveis),
        "empresas_deduplicadas": deduplicadas, "decisores_por_empresa": decisores, "origem_decisores": origem,
        "disponivel": contexto["disponivel"], "limite_periodo_restante": contexto.get("periodo_restante"),
        "limites": {"decisores_por_empresa_max": config.decisores_por_empresa_max, "itens_por_lote_max": config.itens_por_lote_max,
                    "limite_periodo_creditos": config.limite_periodo_creditos, "limite_creditos_pesquisa": config.limite_creditos_pesquisa,
                    "limite_pesquisas_periodo": config.limite_pesquisas_periodo, "limite_empresas_periodo": config.limite_empresas_periodo,
                    "limite_contatos_periodo": config.limite_contatos_periodo, "limite_origem": config.limite_origem},
        "uso_no_periodo": contexto["uso_periodo"],
        "config": {"origem": config.origem, "versao": config.versao}, "politica": {"versao": politica.versao},
        "viavel": not bloqueios, "bloqueios": bloqueios,
        "ajustes_sugeridos": [] if not bloqueios else _sugerir_ajustes(config, politica, contexto, len(elegiveis), decisores, revelar_emails, revelar_telefones),
        "nota_ajustes": "Sugestões calculadas com os limites, saldos e tarifas de agora; não são promessa e serão revalidadas. Sua escolha não foi alterada.",
        "incertezas": incertezas,
    }
    pesquisa = PesquisaDecisores(
        id=uuid.uuid4().hex, tenant_id=tenant_id, usuario_id=solicitante.id, provedor=provider.nome_provedor, estado="criada",
        decisores_por_empresa=decisores, origem_decisores=origem, revelar_emails=revelar_emails, revelar_telefones=revelar_telefones,
        config_origem=config.origem, config_id=config.id,
        config_versao=config.versao, total_empresas=len(plano), total_maximo=total_cliente, provedor_reservados=0, politica_id=politica.id,
        estimativa=estimativa, selecao_hash=_hash_selecao(tenant_id, ids_unicos, decisores, config, politica, provider.nome_provedor, revelar_emails, revelar_telefones),
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
    logger.info("ENRIQUECIMENTO_PREVIA pesquisa=%s tenant=%s empresas=%s teto_provedor=%s viavel=%s", pesquisa.id, tenant_id, len(plano), total_provedor,
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
    config, politica = exigir_configuracao(db, tenant_id, provider, irrestrito=solicitante.irrestrito)
    if (config.origem, config.id, config.versao) != (pesquisa.config_origem, pesquisa.config_id, pesquisa.config_versao):
        raise PesquisaBloqueada("A configuração do seu plano mudou desde a prévia. Crie uma nova prévia.", "estimativa_desatualizada")
    if politica.id != pesquisa.politica_id:
        raise PesquisaBloqueada("As tarifas ou o preço do provedor mudaram desde a prévia. Crie uma nova prévia.", "estimativa_desatualizada")
    if provider.nome_provedor != pesquisa.provedor:
        raise PesquisaBloqueada("O provedor mudou desde a prévia. Crie uma nova prévia.", "estimativa_desatualizada")
    itens = itens_de(db, pesquisa.id)
    try:
        _validar_parametros(config, politica, provider, pesquisa.decisores_por_empresa, len(itens))
    except ValidacaoFalhou as erro:
        raise PesquisaBloqueada(str(erro), "parametros_fora_do_limite", [_bloqueio("parametros_fora_do_limite", str(erro))]) from None

    contas = {c.id: c for c in db.query(Conta).filter(Conta.tenant_id == pesquisa.tenant_id, Conta.id.in_([i.conta_id for i in itens])).all()}
    if len(contas) != len(itens):
        raise PesquisaBloqueada("Alguma empresa da seleção não está mais disponível. Crie uma nova prévia.", "estimativa_desatualizada")
    recusa = politica.motivo_de_recusa_dos_dados(pesquisa.revelar_emails, pesquisa.revelar_telefones)
    if recusa:
        raise PesquisaBloqueada(recusa + " Crie uma nova prévia.", "estimativa_desatualizada")
    plano = _plano_de_itens(db, tenant_id, [contas[i.conta_id] for i in itens], pesquisa.decisores_por_empresa, provider.nome_provedor, politica,
                            pesquisa.revelar_emails, pesquisa.revelar_telefones)
    atual = {p["conta"].id: p for p in plano}
    if {i.conta_id: i.decisores_solicitados for i in itens} != {cid: p["buscar"] for cid, p in atual.items()}:
        raise PesquisaBloqueada("Os decisores já obtidos mudaram desde a prévia. Crie uma nova prévia para ver a estimativa certa.",
                                "estimativa_desatualizada")
    fator = politica.creditos_cliente_por_credito_provedor
    total_provedor = sum(p["teto"] for p in plano)
    total_cliente = total_provedor * fator

    # Ordem fixa de travas: orçamento global (todos os tenants) → carteira do tenant.
    if provider.pago:
        ledger.travar_orcamento(db, provider.nome_provedor)
    ledger.preparar(db, tenant_id, config, agora)
    config = _com_limite_de_pacote(db, tenant_id, config, agora)
    elegiveis_agora = [p for p in plano if p["estado"] == "pendente"]
    bloqueios, _ = _avaliar_limites(db, tenant_id, config, politica, provider, total_cliente, total_provedor, agora, len(elegiveis_agora),
                                    sum(p["buscar"] for p in elegiveis_agora), pesquisa.id, irrestrito=solicitante.irrestrito)
    if bloqueios:
        raise PesquisaBloqueada(bloqueios[0]["mensagem"], bloqueios[0]["codigo"], bloqueios)

    _registrar_transicao(db, pesquisa, "validada", "confirmacao_validada", ator, anterior="criada")
    pesquisa.estado = "validada"
    if total_provedor > 0:
        faltante = total_cliente - ledger.disponivel(db, tenant_id)
        if solicitante.irrestrito and faltante > 0:
            # Super admin sem saldo: concede só o que falta para reservar o teto desta pesquisa (rastreável, idempotente); o consumo continua medido.
            ledger.lancar(db, tenant_id, "CONCESSAO", delta_saldo=faltante, origem="super_admin", motivo=f"Pesquisa {pesquisa.id} do super admin, sem limites de franquia",
                          ator_id=ator, idempotency_key=f"super_admin:{pesquisa.id}", agora=agora)
        ledger.lancar(db, tenant_id, "RESERVA", delta_reservado=total_cliente, provedor_delta_reservado=total_provedor, provedor=provider.nome_provedor,
                      pesquisa_id=pesquisa.id, origem="pesquisa_decisores", politica_id=politica.id,
                      motivo=f"Reserva (teto) da pesquisa {pesquisa.id}", ator_id=ator, idempotency_key=f"reserva:{pesquisa.id}", agora=agora)
        for item in itens:
            teto = atual[item.conta_id]["teto"]
            item.provedor_reservados, item.creditos_reservados = teto, teto * fator
        pesquisa.provedor_reservados, pesquisa.creditos_reservados = total_provedor, total_cliente
        _mudar_estado(db, pesquisa, "reservada", f"reservados {total_provedor} credito(s) do provedor ({total_cliente} do cliente)", ator)
        if provider.pago:
            situacao = ledger.situacao_global(db, provider.nome_provedor, agora)
            if situacao["nivel"] in ("alerta", "esgotado"):
                logger.warning("ENRIQUECIMENTO_ORCAMENTO_GLOBAL provedor=%s nivel=%s percentual=%s", provider.nome_provedor, situacao["nivel"],
                               situacao["percentual"])
    else:
        _mudar_estado(db, pesquisa, "concluida", "nada_a_consultar: todas as empresas deduplicadas", ator)
    logger.info("ENRIQUECIMENTO_RESERVA pesquisa=%s tenant=%s teto_provedor=%s", pesquisa.id, tenant_id, total_provedor)
