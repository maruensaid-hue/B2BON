"""Escrita no CRM do cliente (D-087): PREDATOR e MAP → Salesforce, HubSpot,
Pipedrive e RD Station CRM, pelo contrato canônico.

Fluxo: o domínio chama `enfileirar(...)` na própria transação (flush, sem
commit — igual a eventos e auditoria) → uma linha `EnvioCrm` por conexão
que ligou aquela capacidade → `processar_fila` (cron) monta o DTO com o dado
ATUAL do banco (opt-out recente vale), chama o adapter e grava o vínculo.

Regras (inegociáveis, docs/b2bon/19 §4):
- Escrita desligada por padrão: opt-in por conexão e por capacidade
  (`escrita.predator`, `escrita.map`); interruptor geral `ESCRITA_CRM_ATIVA`.
- Fonte da verdade: o CRM do cliente. `garantir_*` só cria o que não existe;
  a B2B ON só atualiza campos próprios (`CamposProprios`).
- Contato com opt-out nunca é escrito (só o próprio opt-out vai ao CRM).
- Tenant de demonstração nunca escreve (nem enfileira).
- Idempotência por `VinculoExterno` (passo a passo) e chave única do envio.
- Cada escrita é auditada (o que, onde, id externo); erro nunca carrega segredo.
"""

import hashlib
import logging
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.contexts.integrations import registry
from app.contexts.integrations.adapters.http_base import ErroConector, ocultar_segredos
from app.contexts.integrations.contract import (
    AtividadeSaida,
    CamposProprios,
    CrmAdapter,
    EmpresaSaida,
    ErroCredencial,
    ErroTransitorio,
    NegocioSaida,
    OperacaoNaoSuportada,
    PessoaSaida,
    SinaisContaSaida,
    TarefaSaida,
    TipoAtividadeSaida,
    iterar_todos,
)
from app.contexts.shared.canonical.commercial import OpportunityStatus
from app.core.config import settings
from app.models.conexao_integracao import ConexaoIntegracao
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.integracao_crm import EnvioCrm, RegistroCrmExterno, VinculoExterno
from app.models.mensagem import Mensagem
from app.models.reuniao import Reuniao
from app.models.tenant import Tenant
from app.services import auditoria_service

logger = logging.getLogger(__name__)

CAPACIDADES = ("predator", "map")
OPERACOES = {
    "empresa": "predator",
    "pessoa": "predator",
    "atividade_mensagem": "predator",
    "reuniao_agendada": "predator",
    "reuniao_resultado": "predator",
    "optout": "predator",
    "sinais_conta": "map",
}
BACKOFF_MINUTOS = [1, 5, 15, 60, 360]
MAX_TENTATIVAS = len(BACKOFF_MINUTOS) + 1
ADIAMENTO_CONEXAO_INDISPONIVEL = timedelta(hours=1)
_TIPO_CANAL = {"email": TipoAtividadeSaida.EMAIL, "whatsapp": TipoAtividadeSaida.WHATSAPP, "linkedin": TipoAtividadeSaida.LINKEDIN}

PADRAO = {
    "predator": False,
    "map": False,
    "deduplicar": True,
    "pipeline_id": None,
    "estagio_id": None,
    "prazo_fechamento_dias": None,
    "donos": {},
    "campos": {},
}


class Pulo(Exception):
    """Envio que não deve acontecer (regra), não é falha: vira `pulado`."""


# --- Configuração ------------------------------------------------------------------
def config(conexao: ConexaoIntegracao) -> dict:
    atual = dict(PADRAO)
    atual.update({k: v for k, v in (conexao.escrita or {}).items() if k in PADRAO})
    return atual


def campos(conexao: ConexaoIntegracao) -> CamposProprios:
    return CamposProprios(**{k: v for k, v in (config(conexao)["campos"] or {}).items() if k in CamposProprios.model_fields and v})


_ID_EXTERNO = re.compile(r"^[A-Za-z0-9_\-.:]{1,80}$")
# Estágio do Salesforce é o nome (StageName), com espaços: sem controle nem aspas.
_ESTAGIO = re.compile(r"^[^\x00-\x1f'\"\\]{1,120}$")
_CAMPO = re.compile(r"^[A-Za-z0-9_]{1,100}$")


def validar_config(sistema: str, dados: dict) -> dict:
    """Valida o que o admin grava em `escrita` (ValueError com mensagem)."""
    desconhecidas = set(dados) - set(PADRAO)
    if desconhecidas:
        raise ValueError(f"Opções de escrita desconhecidas: {sorted(desconhecidas)}")
    for chave in ("predator", "map", "deduplicar"):
        if chave in dados and not isinstance(dados[chave], bool):
            raise ValueError(f"'{chave}' deve ser verdadeiro ou falso.")
    for chave, padrao in (("pipeline_id", _ID_EXTERNO), ("estagio_id", _ESTAGIO)):
        valor = dados.get(chave)
        if valor not in (None, "") and not (isinstance(valor, str) and padrao.match(valor)):
            raise ValueError(f"'{chave}' inválido.")
    prazo = dados.get("prazo_fechamento_dias")
    if prazo is not None and not (isinstance(prazo, int) and not isinstance(prazo, bool) and 1 <= prazo <= 730):
        raise ValueError("'prazo_fechamento_dias' deve ser um número de dias entre 1 e 730.")
    donos = dados.get("donos") or {}
    if not isinstance(donos, dict) or not all(str(k).isdigit() and isinstance(v, str) and _ID_EXTERNO.match(v) for k, v in donos.items()):
        raise ValueError("'donos' deve mapear id de usuário da B2B ON → id do dono no CRM.")
    mapa = dados.get("campos") or {}
    if not isinstance(mapa, dict) or set(mapa) - set(CamposProprios.model_fields):
        raise ValueError(f"'campos' aceita apenas {sorted(CamposProprios.model_fields)}.")
    if not all(v in (None, "") or (isinstance(v, str) and _CAMPO.match(v)) for v in mapa.values()):
        raise ValueError("Nome de campo inválido (use o nome interno/de API do campo).")
    if sistema == "salesforce" and dados.get("predator") and dados.get("estagio_id") and not prazo:
        raise ValueError("No Salesforce o negócio exige data de fechamento: informe 'prazo_fechamento_dias'.")
    return {**{k: v for k, v in dados.items()}, "donos": {str(k): v for k, v in donos.items()}}


# --- Enfileiramento ----------------------------------------------------------------
def _e_demonstracao(db: Session, tenant_id: str) -> bool:
    tenant = db.get(Tenant, tenant_id)
    return tenant is None or tenant.demo_expira_em is not None


# Só CRMs EXTERNOS: a conexão "b2bon_crm" (o CRM da própria plataforma) não escreve
# nem deduplica — o PREDATOR já é o mesmo banco.
SISTEMAS_EXTERNOS = frozenset({"salesforce", "hubspot", "pipedrive", "rd_station"})


def conexoes_com(db: Session, tenant_id: str, chave: str) -> list[ConexaoIntegracao]:
    """Conexões ativas do tenant com a opção `chave` ligada (e conector externo liberado)."""
    conexoes = db.query(ConexaoIntegracao).filter(ConexaoIntegracao.tenant_id == tenant_id,
                                                  ConexaoIntegracao.sistema.in_(SISTEMAS_EXTERNOS)).all()
    return [c for c in conexoes if c.status != "pausada" and config(c).get(chave) and registry.conectavel(c.sistema)]


def enfileirar(db: Session, tenant_id: str, operacao: str, id_interno: int | str, chave: str | None = None,
               payload: dict | None = None, ator_id: str | None = None, conexao_id: int | None = None) -> int:
    """Uma entrada por conexão interessada; idempotente pela chave. Não faz
    commit (vai junto com a mudança de negócio de quem chama)."""
    capacidade = OPERACOES[operacao]
    if _e_demonstracao(db, tenant_id):
        return 0
    chave = chave or f"{operacao}:{id_interno}"
    criados = 0
    for conexao in conexoes_com(db, tenant_id, capacidade):
        if conexao_id is not None and conexao.id != conexao_id:
            continue
        if db.query(EnvioCrm.id).filter_by(conexao_id=conexao.id, chave=chave).first():
            continue
        db.add(EnvioCrm(tenant_id=tenant_id, conexao_id=conexao.id, operacao=operacao, id_interno=str(id_interno), chave=chave,
                        payload=payload or {}, status="pendente", tentativas=0, proxima_tentativa_em=datetime.now(UTC), ator_id=ator_id))
        criados += 1
    if criados:
        db.flush()
    return criados


def reprocessar(db: Session, tenant_id: str, envio_id: int, ator_id: str | None) -> EnvioCrm:
    envio = db.query(EnvioCrm).filter_by(id=envio_id, tenant_id=tenant_id).one_or_none()
    if envio is None:
        raise LookupError(f"Envio {envio_id} não encontrado")
    if envio.status not in ("desistido", "pulado"):
        raise ValueError("Só envios desistidos ou pulados podem ser reprocessados.")
    envio.status, envio.tentativas, envio.ultimo_erro = "pendente", 0, None
    envio.proxima_tentativa_em = datetime.now(UTC)
    auditoria_service.registrar(db, tenant_id, "crm_envio_reprocessado", "envio_crm", envio.id, ator_id, {"operacao": envio.operacao})
    db.commit()
    return envio


# --- Vínculos ----------------------------------------------------------------------
def vinculo(db: Session, conexao: ConexaoIntegracao, entidade: str, id_interno: int | str) -> str | None:
    registro = db.query(VinculoExterno).filter_by(conexao_id=conexao.id, entidade=entidade, id_interno=str(id_interno)).one_or_none()
    return registro.id_externo if registro else None


def _vincular(db: Session, conexao: ConexaoIntegracao, entidade: str, id_interno: int | str, id_externo: str) -> str:
    db.add(VinculoExterno(tenant_id=conexao.tenant_id, conexao_id=conexao.id, entidade=entidade, id_interno=str(id_interno), id_externo=str(id_externo)))
    db.flush()
    return str(id_externo)


def _uma_vez(db: Session, conexao: ConexaoIntegracao, entidade: str, id_interno: int | str, criar: Callable[[], str]) -> str:
    """Passo idempotente: se já existe vínculo, reaproveita; senão cria e vincula.
    Retentativa depois de falha parcial não duplica o que já foi criado."""
    existente = vinculo(db, conexao, entidade, id_interno)
    if existente:
        return existente
    id_externo = _vincular(db, conexao, entidade, id_interno, criar())
    db.commit()  # o vínculo sobrevive mesmo se o passo seguinte falhar
    return id_externo


# --- Montagem dos DTOs (dado atual do banco) ----------------------------------------
def _dono(cfg: dict, usuario_id) -> str | None:
    return (cfg.get("donos") or {}).get(str(usuario_id)) if usuario_id is not None else None


def _empresa(db: Session, adapter: CrmAdapter, conexao: ConexaoIntegracao, cfg: dict, conta: Conta) -> str:
    return _uma_vez(db, conexao, "empresa", conta.id, lambda: adapter.garantir_empresa(conexao.tenant_id, EmpresaSaida(
        nome=(conta.nome or conta.nome_fantasia or f"Conta {conta.id}")[:255],
        cnpj=re.sub(r"\D", "", conta.cnpj or "") or None,
        dominio=(conta.dominio or "").lower().removeprefix("www.") or None,
        dono_externo_id=_dono(cfg, conta.vendedor_usuario_id),
    )))


def _pessoa(db: Session, adapter: CrmAdapter, conexao: ConexaoIntegracao, cfg: dict, decisor: Decisor, empresa_id: str, dono_usuario_id=None) -> str:
    if decisor.suprimido_em is not None:
        raise Pulo("contato com opt-out: não é enviado ao CRM")
    return _uma_vez(db, conexao, "pessoa", decisor.id, lambda: adapter.garantir_pessoa(conexao.tenant_id, PessoaSaida(
        nome=(decisor.nome or decisor.email or f"Contato {decisor.id}")[:255], email=decisor.email, telefone=decisor.telefone,
        cargo=decisor.cargo, empresa_id=empresa_id, dono_externo_id=_dono(cfg, dono_usuario_id),
    )))


def _obter(db: Session, modelo, tenant_id: str, id_interno: str):
    registro = db.query(modelo).filter_by(id=int(id_interno), tenant_id=tenant_id).one_or_none()
    if registro is None:
        raise Pulo(f"{modelo.__name__} {id_interno} não existe mais")
    return registro


def _executar(db: Session, adapter: CrmAdapter, conexao: ConexaoIntegracao, envio: EnvioCrm) -> str:
    cfg = config(conexao)
    tenant_id = conexao.tenant_id
    operacao = envio.operacao

    if operacao == "empresa":
        conta = _obter(db, Conta, tenant_id, envio.id_interno)
        return f"empresa {_empresa(db, adapter, conexao, cfg, conta)}"

    if operacao == "pessoa":
        decisor = _obter(db, Decisor, tenant_id, envio.id_interno)
        conta = _obter(db, Conta, tenant_id, str(decisor.conta_id))
        empresa_id = _empresa(db, adapter, conexao, cfg, conta)
        return f"pessoa {_pessoa(db, adapter, conexao, cfg, decisor, empresa_id, conta.vendedor_usuario_id)}"

    if operacao == "atividade_mensagem":
        mensagem = _obter(db, Mensagem, tenant_id, envio.id_interno)
        decisor = _obter(db, Decisor, tenant_id, str(mensagem.decisor_id))
        conta = _obter(db, Conta, tenant_id, str(decisor.conta_id))
        empresa_id = _empresa(db, adapter, conexao, cfg, conta)
        pessoa_id = _pessoa(db, adapter, conexao, cfg, decisor, empresa_id, conta.vendedor_usuario_id)
        canal = _TIPO_CANAL.get(mensagem.canal, TipoAtividadeSaida.NOTA)
        atividade = AtividadeSaida(
            tipo=canal, assunto=(mensagem.assunto or f"Mensagem de cadência B2B ON ({mensagem.canal})")[:255],
            descricao=(mensagem.conteudo or "")[:5000], ocorrida_em=mensagem.enviado_em or datetime.now(UTC),
            empresa_id=empresa_id, pessoa_id=pessoa_id, negocio_id=vinculo(db, conexao, "negocio", conta.id),
            dono_externo_id=_dono(cfg, conta.vendedor_usuario_id),
        )
        return f"atividade {_uma_vez(db, conexao, 'atividade', f'mensagem:{mensagem.id}', lambda: adapter.registrar_atividade(tenant_id, atividade))}"

    if operacao == "reuniao_agendada":
        reuniao = _obter(db, Reuniao, tenant_id, envio.id_interno)
        conta = _obter(db, Conta, tenant_id, str(reuniao.conta_id))
        decisor = _obter(db, Decisor, tenant_id, str(reuniao.decisor_id))
        dono = _dono(cfg, reuniao.vendedor_id) or _dono(cfg, conta.vendedor_usuario_id)
        empresa_id = _empresa(db, adapter, conexao, cfg, conta)
        pessoa_id = _pessoa(db, adapter, conexao, cfg, decisor, empresa_id, conta.vendedor_usuario_id)
        if not cfg.get("estagio_id"):
            raise Pulo("funil/estágio do negócio não configurado na conexão")
        quando = reuniao.horario_confirmado or reuniao.data_hora
        prazo = cfg.get("prazo_fechamento_dias")
        negocio = NegocioSaida(
            nome=f"{conta.nome_fantasia or conta.nome} — reunião B2B ON"[:255], empresa_id=empresa_id, pessoa_id=pessoa_id,
            pipeline_id=cfg.get("pipeline_id") or None, estagio_id=cfg["estagio_id"],
            previsao_fechamento=(quando.date() + timedelta(days=prazo)) if prazo and quando else None, dono_externo_id=dono,
        )
        negocio_id = _uma_vez(db, conexao, "negocio", conta.id, lambda: adapter.criar_negocio(tenant_id, negocio))
        atividade = AtividadeSaida(
            tipo=TipoAtividadeSaida.REUNIAO, assunto=f"Reunião com {conta.nome_fantasia or conta.nome}"[:255],
            descricao="Agendada pelo B2B ON PREDATOR." + (f" Link: {reuniao.link_reuniao}" if reuniao.link_reuniao else ""),
            ocorrida_em=quando or datetime.now(UTC), duracao_minutos=30,
            empresa_id=empresa_id, pessoa_id=pessoa_id, negocio_id=negocio_id, dono_externo_id=dono,
        )
        atividade_id = _uma_vez(db, conexao, "atividade", f"reuniao:{reuniao.id}", lambda: adapter.registrar_atividade(tenant_id, atividade))
        return f"negócio {negocio_id}, reunião {atividade_id}"

    if operacao == "reuniao_resultado":
        reuniao = _obter(db, Reuniao, tenant_id, envio.id_interno)
        conta = _obter(db, Conta, tenant_id, str(reuniao.conta_id))
        decisor = _obter(db, Decisor, tenant_id, str(reuniao.decisor_id))
        empresa_id = _empresa(db, adapter, conexao, cfg, conta)
        pessoa_id = vinculo(db, conexao, "pessoa", decisor.id) if decisor.suprimido_em is None else None
        linhas = [f"Reunião de {reuniao.data_hora:%d/%m/%Y %H:%M}: {reuniao.status}."]
        if reuniao.qualificada_confirmada is not None:
            linhas.append(f"Qualificada: {'sim' if reuniao.qualificada_confirmada else 'não'}" + (f" ({reuniao.motivo_qualificacao})" if reuniao.motivo_qualificacao else "") + ".")
        if reuniao.resumo_ia:
            linhas.append(f"Resumo: {reuniao.resumo_ia}")
        nota = AtividadeSaida(
            tipo=TipoAtividadeSaida.NOTA, assunto="Resultado da reunião (B2B ON)", descricao="\n".join(linhas)[:5000],
            ocorrida_em=datetime.now(UTC), empresa_id=empresa_id, pessoa_id=pessoa_id,
            negocio_id=vinculo(db, conexao, "negocio", conta.id), dono_externo_id=_dono(cfg, conta.vendedor_usuario_id),
        )
        return f"nota {_uma_vez(db, conexao, 'atividade', envio.chave, lambda: adapter.registrar_atividade(tenant_id, nota))}"

    if operacao == "optout":
        decisor = _obter(db, Decisor, tenant_id, envio.id_interno)
        pessoa_id = vinculo(db, conexao, "pessoa", decisor.id) or _pessoa_no_indice(db, conexao, decisor.email)
        if not pessoa_id:
            raise Pulo("contato não existe no CRM")
        adapter.marcar_optout(tenant_id, pessoa_id, campos(conexao))
        return f"opt-out na pessoa {pessoa_id}"

    if operacao == "sinais_conta":
        dados = envio.payload or {}
        sinais = SinaisContaSaida(empresa_id=envio.id_interno, score_risco=float(dados["score_risco"]), nivel_risco=str(dados["nivel_risco"]))
        mapa = campos(conexao)
        if not (mapa.score_risco or mapa.nivel_risco):
            raise Pulo("campos de risco da B2B ON não configurados na conexão")
        adapter.gravar_sinais_conta(tenant_id, sinais, mapa)
        resultado = f"sinais na conta {sinais.empresa_id}"
        if dados.get("criar_tarefa"):
            tarefa = TarefaSaida(
                assunto="Conta em risco de churn (B2B ON MAP)",
                descricao=f"Score de risco {sinais.score_risco:.0f}/100 ({sinais.nivel_risco}). {dados.get('motivo') or ''}".strip()[:2000],
                vencimento=date.today(), empresa_id=sinais.empresa_id, dono_externo_id=dados.get("dono_externo_id"),
            )
            chave_tarefa = dados.get("chave_tarefa") or envio.chave  # no máximo 1 tarefa por conta por mês
            if vinculo(db, conexao, "tarefa", chave_tarefa):
                return resultado + ", tarefa do mês já criada"
            try:
                tarefa_id = _uma_vez(db, conexao, "tarefa", chave_tarefa, lambda: adapter.criar_tarefa(tenant_id, tarefa))
                resultado += f", tarefa {tarefa_id}"
            except OperacaoNaoSuportada as motivo:
                resultado += f" (tarefa não criada: {motivo})"
        return resultado

    raise Pulo(f"operação desconhecida: {operacao}")


# --- Despacho ----------------------------------------------------------------------
FabricaAdapter = Callable[[Session, ConexaoIntegracao], CrmAdapter]


def _adiar(envio: EnvioCrm, agora: datetime, motivo: str) -> None:
    envio.proxima_tentativa_em = agora + ADIAMENTO_CONEXAO_INDISPONIVEL
    envio.ultimo_erro = motivo


def processar_fila(db: Session, agora: datetime | None = None, limite: int = 200, fabrica: FabricaAdapter | None = None) -> dict:
    agora = agora or datetime.now(UTC)
    resultado = {"enviados": 0, "pulados": 0, "reagendados": 0, "desistidos": 0, "adiados": 0}
    if not settings.escrita_crm_ativa:
        resultado["desligada"] = True
        return resultado
    fabrica = fabrica or registry.obter_adapter
    pendentes = (
        db.query(EnvioCrm)
        .filter(EnvioCrm.status == "pendente", EnvioCrm.proxima_tentativa_em <= agora.replace(tzinfo=None))
        .order_by(EnvioCrm.id)
        .limit(limite)
        .all()
    )
    adapters: dict[int, CrmAdapter] = {}
    for envio in pendentes:
        conexao = db.query(ConexaoIntegracao).filter_by(id=envio.conexao_id, tenant_id=envio.tenant_id).one_or_none()
        if conexao is None or not config(conexao).get(OPERACOES.get(envio.operacao, "")) or _e_demonstracao(db, envio.tenant_id):
            envio.status, envio.resultado = "pulado", "escrita desligada nesta conexão"
            resultado["pulados"] += 1
            db.commit()
            continue
        if conexao.status != "ativa" or not registry.conectavel(conexao.sistema):
            _adiar(envio, agora, "conexão pausada, com erro de credencial ou conector desabilitado")
            resultado["adiados"] += 1
            db.commit()
            continue
        try:
            adapter = adapters.get(conexao.id) or adapters.setdefault(conexao.id, fabrica(db, conexao))
            texto = _executar(db, adapter, conexao, envio)
            envio.status, envio.resultado, envio.enviado_em, envio.ultimo_erro = "enviado", texto[:500], agora, None
            auditoria_service.registrar(db, envio.tenant_id, "crm_escrita", "envio_crm", envio.id, envio.ator_id,
                                        {"sistema": conexao.sistema, "conexao_id": conexao.id, "operacao": envio.operacao, "resultado": texto[:300]})
            resultado["enviados"] += 1
        except (Pulo, OperacaoNaoSuportada) as motivo:
            db.rollback()
            envio.status, envio.resultado = "pulado", str(motivo)[:500]
            resultado["pulados"] += 1
        except Exception as erro:  # noqa: BLE001 — registra, reagenda; não derruba a fila
            db.rollback()
            texto = ocultar_segredos(f"{type(erro).__name__}: {erro}")[:500]
            envio.tentativas += 1
            envio.ultimo_erro = texto
            if isinstance(erro, ErroCredencial):
                conexao.status, conexao.ultimo_erro = "erro", texto
            definitivo = isinstance(erro, ErroConector) and erro.status not in (None, 404, 409, 423)
            if envio.tentativas >= MAX_TENTATIVAS or (definitivo and envio.tentativas >= 2):
                envio.status = "desistido"
                auditoria_service.registrar(db, envio.tenant_id, "crm_escrita_desistida", "envio_crm", envio.id, None,
                                            {"sistema": conexao.sistema, "operacao": envio.operacao, "erro": texto[:300]})
                resultado["desistidos"] += 1
            else:
                envio.proxima_tentativa_em = agora + timedelta(minutes=BACKOFF_MINUTOS[min(envio.tentativas, len(BACKOFF_MINUTOS)) - 1])
                resultado["reagendados"] += 1
            if not isinstance(erro, (ErroTransitorio, ErroCredencial, ErroConector, httpx.TransportError)):
                logger.exception("Falha inesperada na escrita CRM (envio %s)", envio.id)
        db.commit()
    return resultado


# --- Índice de deduplicação (CRM → PREDATOR) ----------------------------------------
def _hash(tenant_id: str, tipo: str, valor: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{tipo}:{valor}".encode()).hexdigest()


def _normalizar(tipo: str, valor: str | None) -> str | None:
    if not valor:
        return None
    if tipo == "cnpj":
        digitos = re.sub(r"\D", "", valor)
        return digitos if len(digitos) == 14 else None
    if tipo == "dominio":
        return valor.strip().lower().removeprefix("http://").removeprefix("https://").removeprefix("www.").split("/")[0] or None
    return valor.strip().lower() or None


def chaves(tenant_id: str, cnpj: str | None = None, dominio: str | None = None, email: str | None = None) -> dict[str, str]:
    resultado = {}
    for tipo, valor in (("cnpj", cnpj), ("dominio", dominio), ("email", email)):
        normal = _normalizar(tipo, valor)
        if normal:
            resultado[tipo] = _hash(tenant_id, tipo, normal)
    return resultado


def atualizar_indice(db: Session, conexao: ConexaoIntegracao, adapter: CrmAdapter | None = None) -> dict:
    """Lê do CRM o que importa para não abordar errado (cliente, negócio
    aberto, opt-out) e regrava o índice da conexão (só hashes)."""
    adapter = adapter or registry.obter_adapter(db, conexao)
    tenant_id = conexao.tenant_id
    organizacoes = iterar_todos(adapter.list_organizations, tenant_id)
    contas = iterar_todos(adapter.list_accounts, tenant_id)
    org_da_conta = {c.id: c.organization_id for c in contas}
    clientes = {org_da_conta.get(c.account_id) for c in iterar_todos(adapter.list_customers, tenant_id)}
    abertos = {org_da_conta.get(o.account_id) for o in iterar_todos(adapter.list_opportunities, tenant_id) if o.status == OpportunityStatus.OPEN}
    registros: dict[tuple[str, str], RegistroCrmExterno] = {}

    def _registrar(tipo: str, valor: str | None, id_externo: str, **flags) -> None:
        normal = _normalizar(tipo, valor)
        if not normal:
            return
        chave = (tipo, _hash(tenant_id, tipo, normal))
        atual = registros.get(chave)
        if atual is None:
            registros[chave] = RegistroCrmExterno(tenant_id=tenant_id, conexao_id=conexao.id, tipo_chave=tipo, chave_hash=chave[1],
                                                  id_externo=id_externo, cliente=False, negocio_aberto=False, optout=False, atualizado_em=datetime.now(UTC))
            atual = registros[chave]
        for nome, valor_flag in flags.items():
            setattr(atual, nome, getattr(atual, nome) or valor_flag)

    for org in organizacoes:
        flags = {"cliente": org.id in clientes, "negocio_aberto": org.id in abertos}
        _registrar("cnpj", org.tax_id, org.source.external_id, **flags)
        _registrar("dominio", org.domain, org.source.external_id, **flags)
    for pessoa in iterar_todos(adapter.list_people, tenant_id):
        flags = {"cliente": pessoa.organization_id in clientes, "negocio_aberto": pessoa.organization_id in abertos,
                 "optout": pessoa.suppressed_at is not None}
        _registrar("email", pessoa.email, pessoa.source.external_id, **flags)

    db.query(RegistroCrmExterno).filter_by(conexao_id=conexao.id).delete()
    db.add_all(registros.values())
    conexao.ultimo_sync_em = datetime.now(UTC)
    db.commit()
    valores = list(registros.values())
    return {"registros": len(valores), "clientes": sum(r.cliente for r in valores), "negocios_abertos": sum(r.negocio_aberto for r in valores),
            "optouts": sum(r.optout for r in valores)}


def registrar_falha_leitura(db: Session, conexao: ConexaoIntegracao, erro: Exception) -> None:
    conexao.ultimo_erro = ocultar_segredos(f"{type(erro).__name__}: {erro}")[:500]
    if isinstance(erro, ErroCredencial):
        conexao.status = "erro"
    db.commit()
    logger.warning("Falha ao ler o CRM da conexão %s: %s", conexao.id, conexao.ultimo_erro)


def rotina_diaria(db: Session) -> dict:
    """Cron diário: refaz o índice de deduplicação de toda conexão que o usa."""
    resultado = {"indices": 0, "falhas": 0}
    conexoes = db.query(ConexaoIntegracao).filter(ConexaoIntegracao.status == "ativa", ConexaoIntegracao.sistema.in_(SISTEMAS_EXTERNOS)).all()
    for conexao in conexoes:
        if not config(conexao).get("deduplicar") or not registry.conectavel(conexao.sistema) or _e_demonstracao(db, conexao.tenant_id):
            continue
        try:
            atualizar_indice(db, conexao)
            resultado["indices"] += 1
        except Exception as erro:  # noqa: BLE001 — uma conexão quebrada não para as outras
            db.rollback()
            registrar_falha_leitura(db, conexao, erro)
            resultado["falhas"] += 1
    return resultado


def _pessoa_no_indice(db: Session, conexao: ConexaoIntegracao, email: str | None) -> str | None:
    hashes = chaves(conexao.tenant_id, email=email)
    if not hashes:
        return None
    registro = db.query(RegistroCrmExterno).filter_by(conexao_id=conexao.id, tipo_chave="email", chave_hash=hashes["email"]).first()
    return registro.id_externo if registro else None


def bloqueio_prospeccao(db: Session, tenant_id: str, cnpj: str | None, dominio: str | None, email: str | None,
                        conexao_ids: list[int] | None = None) -> tuple[str, str] | None:
    """(motivo, código) se o CRM do cliente diz para NÃO abordar; senão None.
    Ordem: opt-out do contato > já é cliente > negócio aberto."""
    if conexao_ids is None:
        conexao_ids = [c.id for c in conexoes_com(db, tenant_id, "deduplicar")]
    hashes = chaves(tenant_id, cnpj=cnpj, dominio=dominio, email=email)
    if not conexao_ids or not hashes:
        return None
    registros = (
        db.query(RegistroCrmExterno)
        .filter(RegistroCrmExterno.tenant_id == tenant_id, RegistroCrmExterno.conexao_id.in_(conexao_ids),
                RegistroCrmExterno.chave_hash.in_(list(hashes.values())))
        .all()
    )
    if any(r.optout and r.tipo_chave == "email" for r in registros):
        return "Contato com opt-out no CRM do cliente.", "optout"
    if any(r.cliente for r in registros):
        return "Empresa já é cliente no CRM.", "cliente"
    if any(r.negocio_aberto for r in registros):
        return "Empresa com negócio aberto no CRM.", "negocio_aberto"
    return None
