"""Gerenciador de recursos de enriquecimento: decide QUAIS fontes consultar, em que ordem, e protege cada uma (cota técnica, cache, disjuntor).

Não é uma segunda contabilidade. A franquia comercial do cliente continua no razão (`ledger`); aqui só existe a franquia TÉCNICA de cada fornecedor
(ex.: os 50 créditos mensais do plano gratuito do Hunter), que nunca aumenta nem diminui o que o cliente contratou.

Cascata (da mais barata para a mais cara; a paga só entra no que sobrar, em `execucao.executar`):

1. ``banco``: decisores que a empresa já tem no cadastro do tenant (QSA, site institucional, importação, consultas anteriores) com os dados pedidos.
   Custo zero, sem chamada externa, e não gera cobrança: quem já existe no cadastro não é um decisor novo.
2. ``hunter`` (camada ``freemium``): só se estiver ativo, com chave, dentro da cota do mês, fora do disjuntor e sem consulta válida recente.

Tudo aqui é melhor esforço: falha de uma fonte gratuita nunca derruba a pesquisa, apenas deixa o restante para a fonte seguinte. Cada consulta fica em
`enriquecimento_consulta` (sem dado pessoal), que serve de cache por empresa e alimenta os indicadores.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.enriquecimento.config import agora_utc
from app.core.config import settings
from app.graph.client import Neo4jClient
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.enriquecimento_fontes import EnriquecimentoConsulta, EnriquecimentoFonte
from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos, ResultadoBuscaContatos
from app.providers.email_validation.dominio import DominioEmailVerificationProvider

logger = logging.getLogger("b2bon.enriquecimento.gerenciador")

CAMADA_EXISTENTE, CAMADA_GRATUITA, CAMADA_FREEMIUM, CAMADA_PREMIUM = "existente", "gratuita", "freemium", "premium"
FONTE_BANCO, FONTE_HUNTER = "banco", "hunter"

# (codigo, camada, prioridade, limite_mensal, ativo). O limite do Hunter é o do plano gratuito publicado pelo fornecedor (50 créditos/mês); ele nasce
# DESLIGADO: quem liga é o administrador, depois de confirmar com o fornecedor que o uso comercial é permitido (`permite_uso_comercial`).
FONTES_PADRAO = (
    (FONTE_BANCO, CAMADA_EXISTENTE, 10, None, True),
    (FONTE_HUNTER, CAMADA_FREEMIUM, 30, 50, False),
)

FALHAS_PARA_ABRIR_DISJUNTOR = 3
SUSPENSAO_POR_FALHAS = timedelta(minutes=30)
SUSPENSAO_CHAVE_INVALIDA = timedelta(hours=24)  # chave recusada não se resolve sozinha: reavalia só no dia seguinte (e o log avisa o administrador)
ESTADOS_QUE_VALEM_COMO_CACHE = ("ok", "sem_resultados")


@dataclass(frozen=True)
class Necessidade:
    """O que a empresa ainda precisa receber. `exige_telefone` desliga as fontes que não entregam telefone."""

    quantidade: int
    exige_email: bool = True
    exige_telefone: bool = False


@dataclass
class ResultadoCascata:
    atendidos_pelo_banco: int = 0  # decisores já cadastrados que cobrem a necessidade (sem custo e sem cobrança)
    novos_gratuitos: int = 0  # decisores novos criados por fontes gratuitas/freemium nesta chamada (estes são cobrados da franquia do cliente)
    restante: int = 0  # o que ainda falta e só a fonte paga pode cobrir
    consultas: list[str] = field(default_factory=list)  # fontes efetivamente chamadas (diagnóstico; nunca vai ao cliente)

    @property
    def encontrados(self) -> int:
        return self.atendidos_pelo_banco + self.novos_gratuitos


def periodo_de(agora: datetime) -> str:
    return agora.strftime("%Y-%m")


def _inicio_do_proximo_mes(agora: datetime) -> datetime:
    return (agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)


def garantir_padrao(db: Session) -> None:
    """Cria as fontes que faltam (idempotente, seguro com duas requisições ao mesmo tempo: a segunda cai na restrição única)."""
    existentes = {f.codigo for f in db.query(EnriquecimentoFonte.codigo).all()}
    for codigo, camada, prioridade, limite, ativo in FONTES_PADRAO:
        if codigo in existentes:
            continue
        try:
            with db.begin_nested():
                db.add(EnriquecimentoFonte(codigo=codigo, camada=camada, prioridade=prioridade, limite_mensal=limite, ativo=ativo))
                db.flush()
        except IntegrityError:
            continue


def obter_fonte(db: Session, codigo: str) -> EnriquecimentoFonte | None:
    garantir_padrao(db)
    return db.query(EnriquecimentoFonte).filter_by(codigo=codigo).one_or_none()


def _rolar_periodo(db: Session, fonte: EnriquecimentoFonte, agora: datetime) -> None:
    periodo = periodo_de(agora)
    if fonte.periodo != periodo:
        # `periodo` nulo (fonte nunca usada) tem de entrar: em SQL, NULL != 'x' não é verdadeiro.
        db.query(EnriquecimentoFonte).filter(EnriquecimentoFonte.id == fonte.id, or_(EnriquecimentoFonte.periodo.is_(None), EnriquecimentoFonte.periodo != periodo)).update(
            {"periodo": periodo, "consumido_periodo": 0}, synchronize_session=False)
        db.refresh(fonte)


def fonte_liberada(db: Session, fonte: EnriquecimentoFonte | None, agora: datetime) -> str | None:
    """None = pode consultar. Senão, o motivo (curto, sem dado pessoal) pelo qual a fonte foi pulada."""
    if fonte is None or not fonte.ativo:
        return "desativada"
    if fonte.permite_uso_comercial is False:
        return "uso_comercial_nao_permitido"
    if fonte.suspensa_ate is not None and fonte.suspensa_ate > agora:
        return "suspensa"
    _rolar_periodo(db, fonte, agora)
    if fonte.limite_mensal is not None and fonte.consumido_periodo >= fonte.limite_mensal:
        return "cota_esgotada"
    return None


def reservar_cota(db: Session, fonte: EnriquecimentoFonte, creditos: int, agora: datetime) -> bool:
    """Reserva `creditos` da cota técnica de forma atômica: duas execuções ao mesmo tempo nunca passam do limite."""
    if fonte.limite_mensal is None:
        return True
    _rolar_periodo(db, fonte, agora)
    feito = db.query(EnriquecimentoFonte).filter(
        EnriquecimentoFonte.id == fonte.id, EnriquecimentoFonte.consumido_periodo + creditos <= fonte.limite_mensal,
    ).update({"consumido_periodo": EnriquecimentoFonte.consumido_periodo + creditos}, synchronize_session=False)
    db.refresh(fonte)
    return bool(feito)


def ajustar_cota(db: Session, fonte: EnriquecimentoFonte, reservado: int, consumido: int) -> None:
    """Troca o que foi reservado pelo que o fornecedor informou ter consumido (nunca fica negativo)."""
    if fonte.limite_mensal is None or reservado == consumido:
        return
    db.query(EnriquecimentoFonte).filter(EnriquecimentoFonte.id == fonte.id).update(
        {"consumido_periodo": EnriquecimentoFonte.consumido_periodo + (consumido - reservado)}, synchronize_session=False)
    db.refresh(fonte)
    if fonte.consumido_periodo < 0:
        fonte.consumido_periodo = 0


def _registrar_resultado_na_fonte(db: Session, fonte: EnriquecimentoFonte, estado: str, detalhe: str | None, agora: datetime) -> None:
    """Disjuntor: falha seguida abre; sucesso (ou "sem resultados", que é resposta válida) fecha."""
    fonte.ultima_consulta_em = agora
    if estado in ESTADOS_QUE_VALEM_COMO_CACHE:
        fonte.falhas_seguidas, fonte.suspensa_ate = 0, None
        return
    fonte.falhas_seguidas += 1
    if detalhe and detalhe.endswith("chave_invalida"):
        fonte.suspensa_ate = agora + SUSPENSAO_CHAVE_INVALIDA
        logger.error("ENRIQUECIMENTO_FONTE_CHAVE_INVALIDA fonte=%s: a credencial foi recusada; suspensa por 24 h", fonte.codigo)
    elif detalhe and detalhe.endswith("sem_creditos"):
        fonte.suspensa_ate = _inicio_do_proximo_mes(agora)
        logger.warning("ENRIQUECIMENTO_FONTE_SEM_CREDITOS fonte=%s: saldo do fornecedor acabou; suspensa até o próximo mês", fonte.codigo)
    elif fonte.falhas_seguidas >= FALHAS_PARA_ABRIR_DISJUNTOR:
        fonte.suspensa_ate = agora + SUSPENSAO_POR_FALHAS
        logger.warning("ENRIQUECIMENTO_DISJUNTOR_ABERTO fonte=%s após %s falhas seguidas", fonte.codigo, fonte.falhas_seguidas)


def registrar_consulta(db: Session, tenant_id: str, conta_id: int, fonte: str, camada: str, estado: str, *, motivo: str | None = None, encontrados: int = 0,
                       item_id: int | None = None, novos: int = 0, creditos_fonte: int = 0, duracao_ms: int = 0, agora: datetime | None = None) -> EnriquecimentoConsulta:
    linha = EnriquecimentoConsulta(tenant_id=tenant_id, conta_id=conta_id, item_id=item_id, fonte=fonte, camada=camada, estado=estado, motivo=motivo, encontrados=encontrados,
                                   novos=novos, creditos_fonte=creditos_fonte, duracao_ms=duracao_ms, criado_em=agora or agora_utc())
    db.add(linha)
    db.flush()
    return linha


def consulta_valida_recente(db: Session, tenant_id: str, conta_id: int, fonte: str, agora: datetime) -> bool:
    """Cache por empresa e fonte: se a fonte já respondeu (com resultado ou sem) dentro da validade, não se consulta de novo."""
    limite = agora - timedelta(days=settings.enriquecimento_cache_dias)
    return db.query(EnriquecimentoConsulta.id).filter(
        EnriquecimentoConsulta.tenant_id == tenant_id, EnriquecimentoConsulta.conta_id == conta_id, EnriquecimentoConsulta.fonte == fonte,
        EnriquecimentoConsulta.estado.in_(ESTADOS_QUE_VALEM_COMO_CACHE), EnriquecimentoConsulta.criado_em >= limite,
    ).first() is not None


def contar_do_banco(db: Session, tenant_id: str, conta: Conta, necessidade: Necessidade, ignorar_origem: str | None = None) -> int:
    """Decisores já cadastrados que têm o que a pesquisa pede. E-mail deduzido (`inferido`) não vale: o envio não o usa. `ignorar_origem` evita
    contar duas vezes o que a pesquisa já contabilizou como "obtido do mesmo provedor"."""
    consulta = db.query(Decisor).filter(Decisor.tenant_id == tenant_id, Decisor.conta_id == conta.id)
    if ignorar_origem:
        consulta = consulta.filter((Decisor.origem.is_(None)) | (Decisor.origem != ignorar_origem))
    total = 0
    for decisor in consulta.all():
        if necessidade.exige_email and (not decisor.email or decisor.email_status == "inferido"):
            continue
        if necessidade.exige_telefone and not decisor.telefone:
            continue
        total += 1
    return total


def _candidatos_validos(candidatos: list[ContatoCandidato], verificador: DominioEmailVerificationProvider, necessidade: Necessidade) -> list[ContatoCandidato]:
    """Só entra o que serve ao envio: nome, cargo, e-mail que não é deduzido nem de domínio que certamente não recebe e-mail."""
    validos = []
    for candidato in candidatos:
        if not candidato.nome or not candidato.cargo:
            continue
        if necessidade.exige_email:
            if not candidato.email or candidato.email_status == "inferido" or verificador.classificar(candidato.email).descarta:
                continue
        validos.append(candidato)
    return validos


def provedores_gratuitos() -> list[ContactEnrichmentProvider]:
    """Fontes externas gratuitas/freemium disponíveis neste ambiente (sem chave, a lista fica vazia e a cascata usa só o cadastro)."""
    from app.providers.contact_enrichment.hunter import ProvedorHunter

    provedores: list[ContactEnrichmentProvider] = []
    if settings.hunter_api_key:
        provedores.append(ProvedorHunter(settings.hunter_api_key))
    return provedores


def completar(db: Session, tenant_id: str, conta: Conta, necessidade: Necessidade, *, graph: Neo4jClient, ator_id: str | None = None,
              provedores: list[ContactEnrichmentProvider] | None = None, ignorar_origem: str | None = None, agora: datetime | None = None,
              verificador: DominioEmailVerificationProvider | None = None, item_id: int | None = None) -> ResultadoCascata:
    """Executa as camadas gratuitas para UMA empresa e diz quanto ainda falta. Não faz commit (quem chama decide a transação) e nunca levanta por
    causa de uma fonte: cada falha vira linha em `enriquecimento_consulta` e a cascata segue."""
    # Import tardio: o contrato do PREDATOR puxa uma cadeia de contextos que, importada primeiro, quebra por ciclo já existente.
    from app.contexts.predator.contract import registrar_candidatos

    agora = agora or agora_utc()
    resultado = ResultadoCascata(restante=necessidade.quantidade)
    if necessidade.quantidade <= 0:
        return resultado

    resultado.atendidos_pelo_banco = min(contar_do_banco(db, tenant_id, conta, necessidade, ignorar_origem), necessidade.quantidade)
    resultado.restante = necessidade.quantidade - resultado.atendidos_pelo_banco
    if resultado.atendidos_pelo_banco:
        registrar_consulta(db, tenant_id, conta.id, FONTE_BANCO, CAMADA_EXISTENTE, "ok", encontrados=resultado.atendidos_pelo_banco, item_id=item_id, agora=agora)

    verificador = verificador or DominioEmailVerificationProvider()
    for provedor in provedores if provedores is not None else provedores_gratuitos():
        if resultado.restante <= 0:
            break
        codigo = provedor.nome_provedor
        fonte = obter_fonte(db, codigo)
        camada = fonte.camada if fonte else CAMADA_FREEMIUM
        motivo = fonte_liberada(db, fonte, agora) or (None if provedor.disponivel else "sem_credencial")
        if motivo is None and necessidade.exige_telefone:
            motivo = "exige_telefone"  # esta fonte não entrega telefone: pedir só o que ela consegue entregar evitaria cobrar por dado que não veio
        if motivo is None and consulta_valida_recente(db, tenant_id, conta.id, codigo, agora):
            motivo = "cache"
        if motivo is not None:
            registrar_consulta(db, tenant_id, conta.id, codigo, camada, "ignorada", motivo=motivo, item_id=item_id, agora=agora)
            continue
        if not reservar_cota(db, fonte, 1, agora):  # uma consulta custa 1 crédito de fornecedor; o consumo real é acertado depois da resposta
            registrar_consulta(db, tenant_id, conta.id, codigo, camada, "ignorada", motivo="cota_esgotada", item_id=item_id, agora=agora)
            continue

        inicio = time.monotonic()
        filtro = FiltroContatos(nome_empresa=conta.nome_fantasia or conta.nome, dominio=conta.dominio, cnpj=conta.cnpj, limite_contatos=resultado.restante)
        try:
            resposta = provedor.buscar_contatos_governado(filtro)
        except Exception:  # noqa: BLE001 — fonte gratuita nunca derruba a pesquisa
            logger.exception("ENRIQUECIMENTO_FONTE_EXCECAO fonte=%s conta=%s", codigo, conta.id)
            resposta = ResultadoBuscaContatos(estado="ambiguo", detalhe="excecao_no_adaptador")
        duracao = int((time.monotonic() - inicio) * 1000)
        consumo = resposta.creditos_provedor if resposta.creditos_provedor is not None else 1
        ajustar_cota(db, fonte, 1, consumo)
        resultado.consultas.append(codigo)

        validos = _candidatos_validos(resposta.contatos, verificador, necessidade)[: resultado.restante]
        novos = registrar_candidatos(db, tenant_id, conta, validos, graph) if resposta.estado == "ok" and validos else 0
        estado = "ok" if resposta.estado == "ok" else ("sem_resultados" if resposta.estado == "sem_resultados" else "erro")
        _registrar_resultado_na_fonte(db, fonte, estado, resposta.detalhe, agora)
        registrar_consulta(db, tenant_id, conta.id, codigo, camada, estado, motivo=resposta.detalhe, encontrados=len(validos), novos=novos, creditos_fonte=consumo,
                           duracao_ms=duracao, item_id=item_id, agora=agora)
        resultado.novos_gratuitos += novos
        # Quem já existia no cadastro (mesmo nome) não é decisor novo: não cobre a necessidade nem gera cobrança; o que sobra segue para a próxima fonte.
        resultado.restante = max(0, resultado.restante - novos)
    return resultado
