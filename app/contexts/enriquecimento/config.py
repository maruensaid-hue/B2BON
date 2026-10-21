"""Configuração central e versionada da pesquisa de decisores: parâmetros por plano (ou por tenant, quando há condição contratual) e
orçamento global por provedor.

Nenhum número comercial tem valor padrão aqui. Campo obrigatório ausente => a pesquisa é bloqueada com código estável e o tenant é
encaminhado ao comercial; nunca se usa um número "razoável". Mudar um valor cria nova versão (a anterior ganha `valido_ate`) e é auditado.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enriquecimento_creditos import EnriquecimentoConfigPlano, EnriquecimentoOrcamentoGlobal
from app.models.licenca import Licenca
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

PERIODICIDADES = ("mensal", "unica")
CAMPOS_OBRIGATORIOS = (
    "franquia_creditos", "periodicidade", "decisores_por_empresa_padrao", "decisores_por_empresa_max", "itens_por_lote_max",
)
CAMPOS_NUMERICOS = (
    "franquia_creditos", "decisores_por_empresa_padrao", "decisores_por_empresa_max", "itens_por_lote_max", "limite_periodo_creditos",
)


def agora_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def periodo_de(momento: datetime) -> str:
    return momento.strftime("%Y-%m")


@dataclass(frozen=True)
class ConfigResolvida:
    """Configuração vigente de um tenant, já com a origem (tenant | plano) e o que falta para ela ser utilizável."""

    origem: str  # tenant | plano
    id: int
    versao: int
    franquia_creditos: int | None
    periodicidade: str | None
    decisores_por_empresa_padrao: int | None
    decisores_por_empresa_max: int | None
    itens_por_lote_max: int | None
    limite_periodo_creditos: int | None
    faltando: tuple[str, ...] = field(default_factory=tuple)

    @property
    def utilizavel(self) -> bool:
        return not self.faltando


def _int_nao_negativo(nome: str, valor) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValidacaoFalhou(f"{nome} deve ser um número inteiro.")
    if valor < 0:
        raise ValidacaoFalhou(f"{nome} não pode ser negativo.")
    return valor


def validar_campos(campos: dict) -> dict:
    """Valida e normaliza os campos de uma configuração. Nulo é aceito (= não definido); presente tem de ser coerente."""
    limpos = {nome: _int_nao_negativo(nome, campos.get(nome)) for nome in CAMPOS_NUMERICOS}
    periodicidade = campos.get("periodicidade")
    if periodicidade is not None and periodicidade not in PERIODICIDADES:
        raise ValidacaoFalhou(f"periodicidade deve ser uma de: {', '.join(PERIODICIDADES)}.")
    limpos["periodicidade"] = periodicidade
    for nome in ("decisores_por_empresa_padrao", "decisores_por_empresa_max", "itens_por_lote_max"):
        if limpos[nome] is not None and limpos[nome] < 1:
            raise ValidacaoFalhou(f"{nome} deve ser no mínimo 1.")
    padrao, maximo = limpos["decisores_por_empresa_padrao"], limpos["decisores_por_empresa_max"]
    if padrao is not None and maximo is not None and padrao > maximo:
        raise ValidacaoFalhou("O padrão de decisores por empresa não pode ser maior que o máximo.")
    return limpos


def _faltando(linha: EnriquecimentoConfigPlano) -> tuple[str, ...]:
    return tuple(c for c in CAMPOS_OBRIGATORIOS if getattr(linha, c) is None)


def _resolvida(linha: EnriquecimentoConfigPlano, origem: str) -> ConfigResolvida:
    return ConfigResolvida(
        origem=origem, id=linha.id, versao=linha.versao, franquia_creditos=linha.franquia_creditos, periodicidade=linha.periodicidade,
        decisores_por_empresa_padrao=linha.decisores_por_empresa_padrao, decisores_por_empresa_max=linha.decisores_por_empresa_max,
        itens_por_lote_max=linha.itens_por_lote_max, limite_periodo_creditos=linha.limite_periodo_creditos, faltando=_faltando(linha),
    )


def plano_ativo_do_tenant(db: Session, tenant_id: str) -> int | None:
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    return licenca.plano_id if licenca is not None and licenca.status == "ativa" else None


def config_vigente(db: Session, tenant_id: str) -> tuple[ConfigResolvida | None, str | None]:
    """(config, None) quando há linha vigente; (None, motivo) quando não há. Motivos: sem_plano_ativo, plano_sem_configuracao. A condição
    contratual do tenant, se existir, prevalece sobre o plano. Config incompleta é devolvida (com `faltando`) para a mensagem ser específica."""
    do_tenant = (
        db.query(EnriquecimentoConfigPlano)
        .filter(EnriquecimentoConfigPlano.tenant_id == tenant_id, EnriquecimentoConfigPlano.valido_ate.is_(None))
        .order_by(EnriquecimentoConfigPlano.versao.desc()).first()
    )
    if do_tenant is not None:
        return _resolvida(do_tenant, "tenant"), None
    plano_id = plano_ativo_do_tenant(db, tenant_id)
    if plano_id is None:
        return None, "sem_plano_ativo"
    do_plano = (
        db.query(EnriquecimentoConfigPlano)
        .filter(EnriquecimentoConfigPlano.plano_id == plano_id, EnriquecimentoConfigPlano.valido_ate.is_(None))
        .order_by(EnriquecimentoConfigPlano.versao.desc()).first()
    )
    if do_plano is None:
        return None, "plano_sem_configuracao"
    return _resolvida(do_plano, "plano"), None


def definir_config(db: Session, *, plano_id: int | None, tenant_id: str | None, campos: dict, ator_id: str | None, tenant_auditoria: str,
                   motivo: str | None) -> EnriquecimentoConfigPlano:
    """Nova versão da configuração de um plano OU de um tenant (nunca os dois). Administrativo; o chamador garante o papel."""
    if (plano_id is None) == (tenant_id is None):
        raise ValidacaoFalhou("Informe o plano OU o tenant da configuração (exatamente um).")
    limpos = validar_campos(campos)
    filtro = EnriquecimentoConfigPlano.plano_id == plano_id if plano_id is not None else EnriquecimentoConfigPlano.tenant_id == tenant_id
    anteriores = db.query(EnriquecimentoConfigPlano).filter(filtro).order_by(EnriquecimentoConfigPlano.versao.desc()).all()
    agora = agora_utc()
    for anterior in anteriores:
        if anterior.valido_ate is None:
            anterior.valido_ate = agora
    nova = EnriquecimentoConfigPlano(
        plano_id=plano_id, tenant_id=tenant_id, versao=(anteriores[0].versao + 1) if anteriores else 1, motivo=motivo,
        criado_por=ator_id, valido_de=agora, **limpos,
    )
    db.add(nova)
    db.flush()
    auditoria_service.registrar(
        db, tenant_auditoria, "enriquecimento_config_definida", "enriquecimento_config_plano", nova.id, ator_id,
        {"plano_id": plano_id, "tenant_id": tenant_id, "versao": nova.versao, "motivo": motivo, **limpos},
    )
    db.commit()
    return nova


@dataclass(frozen=True)
class OrcamentoGlobal:
    provedor: str
    id: int | None
    versao: int | None
    limite_creditos: int | None
    alerta_percentual: int

    @property
    def configurado(self) -> bool:
        return self.limite_creditos is not None


def orcamento_vigente(db: Session, provedor: str) -> OrcamentoGlobal:
    linha = (
        db.query(EnriquecimentoOrcamentoGlobal)
        .filter(EnriquecimentoOrcamentoGlobal.provedor == provedor, EnriquecimentoOrcamentoGlobal.valido_ate.is_(None))
        .order_by(EnriquecimentoOrcamentoGlobal.versao.desc()).first()
    )
    if linha is None:
        return OrcamentoGlobal(provedor=provedor, id=None, versao=None, limite_creditos=None, alerta_percentual=80)
    return OrcamentoGlobal(provedor=provedor, id=linha.id, versao=linha.versao, limite_creditos=linha.limite_creditos,
                           alerta_percentual=linha.alerta_percentual)


def definir_orcamento_global(db: Session, *, provedor: str, limite_creditos: int | None, alerta_percentual: int, ator_id: str | None,
                             tenant_auditoria: str, motivo: str) -> EnriquecimentoOrcamentoGlobal:
    """Nova versão do orçamento global do provedor (mensal, todos os tenants somados). Só administrativo e sempre com motivo."""
    if not provedor or not provedor.strip():
        raise ValidacaoFalhou("Informe o provedor.")
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo da alteração do orçamento global.")
    limite = _int_nao_negativo("limite_creditos", limite_creditos)
    if isinstance(alerta_percentual, bool) or not isinstance(alerta_percentual, int) or not 1 <= alerta_percentual <= 100:
        raise ValidacaoFalhou("alerta_percentual deve ser um inteiro entre 1 e 100.")
    anteriores = (
        db.query(EnriquecimentoOrcamentoGlobal).filter(EnriquecimentoOrcamentoGlobal.provedor == provedor)
        .order_by(EnriquecimentoOrcamentoGlobal.versao.desc()).all()
    )
    agora = agora_utc()
    for anterior in anteriores:
        if anterior.valido_ate is None:
            anterior.valido_ate = agora
    nova = EnriquecimentoOrcamentoGlobal(
        provedor=provedor, versao=(anteriores[0].versao + 1) if anteriores else 1, limite_creditos=limite,
        alerta_percentual=alerta_percentual, motivo=motivo.strip(), criado_por=ator_id, valido_de=agora,
    )
    db.add(nova)
    db.flush()
    anterior_vigente = next((a for a in anteriores if a.valido_ate == agora), None)
    auditoria_service.registrar(
        db, tenant_auditoria, "enriquecimento_orcamento_global_definido", "enriquecimento_orcamento_global", nova.id, ator_id,
        {"provedor": provedor, "versao": nova.versao, "limite_novo": limite, "limite_anterior": anterior_vigente.limite_creditos if anterior_vigente else None,
         "alerta_percentual": alerta_percentual, "motivo": motivo.strip()},
    )
    db.commit()
    return nova
