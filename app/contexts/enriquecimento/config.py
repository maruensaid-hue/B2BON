"""Configuração central, versionada, auditada e **aprovada** da pesquisa de decisores: parâmetros por plano (ou por tenant, quando há condição
contratual), orçamento global por provedor, política do provedor (tarifas, preço) e lotes de compra de créditos.

Regras:
* Nenhum número comercial tem valor padrão. Campo obrigatório ausente ⇒ a pesquisa é bloqueada com código estável.
* Criar ou alterar um valor gera uma **versão pendente**; ela só passa a valer quando um administrador a **aprova** (e só então a versão
  aprovada anterior é encerrada). Nada pendente destrava a pesquisa.
* Toda criação e toda aprovação são auditadas com motivo e responsável.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import precos
from app.models.enriquecimento_creditos import (
    EnriquecimentoConfigPlano,
    EnriquecimentoLoteCompra,
    EnriquecimentoOrcamentoGlobal,
    EnriquecimentoPoliticaProvedor,
)
from app.models.licenca import Licenca
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, PesquisaBloqueada, ValidacaoFalhou

PERIODICIDADES = ("mensal", "unica")
METODOS_CUSTO = ("lote_referencia", "media_ponderada")
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


def _int_nao_negativo(nome: str, valor) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValidacaoFalhou(f"{nome} deve ser um número inteiro.")
    if valor < 0:
        raise ValidacaoFalhou(f"{nome} não pode ser negativo.")
    return valor


def _aprovar_linha(db: Session, linha, filtro_irmas, ator_id: str | None, tenant_auditoria: str, evento: str, entidade: str, detalhes: dict) -> None:
    """Aprova uma versão pendente: grava quem/quando e encerra a versão aprovada anterior do mesmo escopo."""
    if linha.aprovado_em is not None:
        raise ValidacaoFalhou("Esta versão já foi aprovada.")
    agora = agora_utc()
    for irma in filtro_irmas:
        if irma.id != linha.id and irma.aprovado_em is not None and irma.valido_ate is None:
            irma.valido_ate = agora
    linha.aprovado_por, linha.aprovado_em, linha.valido_de = ator_id or "sistema", agora, agora
    auditoria_service.registrar(db, tenant_auditoria, evento, entidade, linha.id, ator_id, {"versao": linha.versao, **detalhes})
    db.commit()


# ------------------------------------------------------------------------------------------------------------------ plano / tenant


@dataclass(frozen=True)
class ConfigResolvida:
    """Configuração aprovada e vigente de um tenant, já com a origem (tenant | plano) e o que falta para ela ser utilizável."""

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


def _vigente_aprovada(db: Session, filtro) -> tuple[EnriquecimentoConfigPlano | None, bool]:
    """(linha aprovada vigente, existe_alguma_pendente)."""
    linhas = db.query(EnriquecimentoConfigPlano).filter(filtro).order_by(EnriquecimentoConfigPlano.versao.desc()).all()
    aprovada = next((c for c in linhas if c.aprovado_em is not None and c.valido_ate is None), None)
    return aprovada, any(c.aprovado_em is None for c in linhas)


def config_vigente(db: Session, tenant_id: str) -> tuple[ConfigResolvida | None, str | None]:
    """(config, None) quando há versão APROVADA vigente; (None, motivo) quando não há. Motivos: sem_plano_ativo, plano_sem_configuracao,
    plano_config_pendente_aprovacao. A condição contratual do tenant, se aprovada, prevalece sobre a do plano. Config incompleta é devolvida
    (com `faltando`) para a mensagem ser específica."""
    do_tenant, tenant_pendente = _vigente_aprovada(db, EnriquecimentoConfigPlano.tenant_id == tenant_id)
    if do_tenant is not None:
        return _resolvida(do_tenant, "tenant"), None
    plano_id = plano_ativo_do_tenant(db, tenant_id)
    if plano_id is None:
        return None, "sem_plano_ativo"
    do_plano, plano_pendente = _vigente_aprovada(db, EnriquecimentoConfigPlano.plano_id == plano_id)
    if do_plano is not None:
        return _resolvida(do_plano, "plano"), None
    return None, "plano_config_pendente_aprovacao" if (plano_pendente or tenant_pendente) else "plano_sem_configuracao"


def definir_config(db: Session, *, plano_id: int | None, tenant_id: str | None, campos: dict, ator_id: str | None, tenant_auditoria: str,
                   motivo: str | None, aprovar: bool = False) -> EnriquecimentoConfigPlano:
    """Nova versão (PENDENTE de aprovação) da configuração de um plano OU de um tenant (nunca os dois). `aprovar=True` só existe para uso
    interno/testes: a rota administrativa cria pendente e a aprovação é um passo à parte."""
    if (plano_id is None) == (tenant_id is None):
        raise ValidacaoFalhou("Informe o plano OU o tenant da configuração (exatamente um).")
    limpos = validar_campos(campos)
    filtro = EnriquecimentoConfigPlano.plano_id == plano_id if plano_id is not None else EnriquecimentoConfigPlano.tenant_id == tenant_id
    anteriores = db.query(EnriquecimentoConfigPlano).filter(filtro).order_by(EnriquecimentoConfigPlano.versao.desc()).all()
    nova = EnriquecimentoConfigPlano(
        plano_id=plano_id, tenant_id=tenant_id, versao=(anteriores[0].versao + 1) if anteriores else 1, motivo=motivo, criado_por=ator_id, **limpos,
    )
    db.add(nova)
    db.flush()
    auditoria_service.registrar(
        db, tenant_auditoria, "enriquecimento_config_definida", "enriquecimento_config_plano", nova.id, ator_id,
        {"plano_id": plano_id, "tenant_id": tenant_id, "versao": nova.versao, "motivo": motivo, "pendente_aprovacao": True, **limpos},
    )
    db.commit()
    if aprovar:
        aprovar_config(db, nova.id, ator_id, tenant_auditoria)
    return nova


def aprovar_config(db: Session, config_id: int, ator_id: str | None, tenant_auditoria: str) -> EnriquecimentoConfigPlano:
    linha = db.get(EnriquecimentoConfigPlano, config_id)
    if linha is None:
        raise NaoEncontrado("Configuração não encontrada.")
    if _faltando(linha):
        raise ValidacaoFalhou(f"Configuração incompleta, não pode ser aprovada (faltando: {', '.join(_faltando(linha))}).")
    filtro = EnriquecimentoConfigPlano.plano_id == linha.plano_id if linha.plano_id is not None else EnriquecimentoConfigPlano.tenant_id == linha.tenant_id
    irmas = db.query(EnriquecimentoConfigPlano).filter(filtro).all()
    _aprovar_linha(db, linha, irmas, ator_id, tenant_auditoria, "enriquecimento_config_aprovada", "enriquecimento_config_plano",
                   {"plano_id": linha.plano_id, "tenant_id": linha.tenant_id})
    return linha


# ------------------------------------------------------------------------------------------------------------------ orçamento global


@dataclass(frozen=True)
class OrcamentoGlobal:
    provedor: str
    id: int | None
    versao: int | None
    limite_creditos: int | None  # créditos DO PROVEDOR por mês-calendário
    alerta_percentual: int
    pendente_aprovacao: bool = False

    @property
    def configurado(self) -> bool:
        return self.limite_creditos is not None


def orcamento_vigente(db: Session, provedor: str) -> OrcamentoGlobal:
    linhas = (
        db.query(EnriquecimentoOrcamentoGlobal).filter(EnriquecimentoOrcamentoGlobal.provedor == provedor)
        .order_by(EnriquecimentoOrcamentoGlobal.versao.desc()).all()
    )
    aprovada = next((o for o in linhas if o.aprovado_em is not None and o.valido_ate is None), None)
    if aprovada is None:
        return OrcamentoGlobal(provedor=provedor, id=None, versao=None, limite_creditos=None, alerta_percentual=80,
                               pendente_aprovacao=any(o.aprovado_em is None for o in linhas))
    return OrcamentoGlobal(provedor=provedor, id=aprovada.id, versao=aprovada.versao, limite_creditos=aprovada.limite_creditos,
                           alerta_percentual=aprovada.alerta_percentual)


def definir_orcamento_global(db: Session, *, provedor: str, limite_creditos: int | None, alerta_percentual: int, ator_id: str | None,
                             tenant_auditoria: str, motivo: str, aprovar: bool = False) -> EnriquecimentoOrcamentoGlobal:
    """Nova versão (PENDENTE de aprovação) do orçamento global do provedor, em créditos do provedor por mês, todos os tenants somados."""
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
    nova = EnriquecimentoOrcamentoGlobal(
        provedor=provedor, versao=(anteriores[0].versao + 1) if anteriores else 1, limite_creditos=limite,
        alerta_percentual=alerta_percentual, motivo=motivo.strip(), criado_por=ator_id,
    )
    db.add(nova)
    db.flush()
    vigente = next((a for a in anteriores if a.aprovado_em is not None and a.valido_ate is None), None)
    auditoria_service.registrar(
        db, tenant_auditoria, "enriquecimento_orcamento_global_definido", "enriquecimento_orcamento_global", nova.id, ator_id,
        {"provedor": provedor, "versao": nova.versao, "limite_novo": limite, "limite_vigente": vigente.limite_creditos if vigente else None,
         "alerta_percentual": alerta_percentual, "motivo": motivo.strip(), "pendente_aprovacao": True},
    )
    db.commit()
    if aprovar:
        aprovar_orcamento_global(db, nova.id, ator_id, tenant_auditoria)
    return nova


def aprovar_orcamento_global(db: Session, orcamento_id: int, ator_id: str | None, tenant_auditoria: str) -> EnriquecimentoOrcamentoGlobal:
    linha = db.get(EnriquecimentoOrcamentoGlobal, orcamento_id)
    if linha is None:
        raise NaoEncontrado("Orçamento não encontrado.")
    if linha.limite_creditos is None:
        raise ValidacaoFalhou("Orçamento sem limite definido não pode ser aprovado.")
    irmas = db.query(EnriquecimentoOrcamentoGlobal).filter(EnriquecimentoOrcamentoGlobal.provedor == linha.provedor).all()
    anterior = next((o for o in irmas if o.aprovado_em is not None and o.valido_ate is None), None)
    _aprovar_linha(db, linha, irmas, ator_id, tenant_auditoria, "enriquecimento_orcamento_global_aprovado", "enriquecimento_orcamento_global",
                   {"provedor": linha.provedor, "limite_novo": linha.limite_creditos, "limite_anterior": anterior.limite_creditos if anterior else None})
    return linha


# ------------------------------------------------------------------------------------------------------------------ lotes de compra


def registrar_lote_compra(db: Session, *, provedor: str, referencia: str, quantidade_creditos: int, custo_total_brl, comprado_em: datetime,
                          ator_id: str | None, tenant_auditoria: str, observacao: str | None = None) -> EnriquecimentoLoteCompra:
    """Novo aporte de créditos do provedor: custo, quantidade, data e referência próprios. Nunca altera lotes anteriores nem o preço vigente
    (o preço só muda quando uma nova política é publicada e aprovada)."""
    if not provedor or not referencia or not referencia.strip():
        raise ValidacaoFalhou("Informe o provedor e a referência do lote.")
    if isinstance(quantidade_creditos, bool) or not isinstance(quantidade_creditos, int) or quantidade_creditos <= 0:
        raise ValidacaoFalhou("A quantidade de créditos do lote deve ser um inteiro positivo.")
    custo = precos.dec(custo_total_brl)
    if custo <= 0:
        raise ValidacaoFalhou("O custo total do lote deve ser positivo.")
    if db.query(EnriquecimentoLoteCompra).filter_by(provedor=provedor, referencia=referencia.strip()).first() is not None:
        raise ValidacaoFalhou("Já existe um lote com essa referência; registre o novo aporte com outra referência.")
    lote = EnriquecimentoLoteCompra(
        provedor=provedor, referencia=referencia.strip(), quantidade_creditos=quantidade_creditos, custo_total_brl=custo,
        custo_unitario_brl=precos.custo_unitario(custo, quantidade_creditos), comprado_em=comprado_em, observacao=observacao, criado_por=ator_id,
    )
    db.add(lote)
    db.flush()
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_lote_compra_registrado", "enriquecimento_lote_compra", lote.id, ator_id,
                                {"provedor": provedor, "referencia": lote.referencia, "quantidade": quantidade_creditos, "custo_total_brl": str(custo)})
    db.commit()
    return lote


# ------------------------------------------------------------------------------------------------------------------ política do provedor

CAMPOS_TARIFAS = ("creditos_busca_por_resultado", "creditos_email", "creditos_telefone")


@dataclass(frozen=True)
class PoliticaResolvida:
    """Política APROVADA e vigente do provedor: tarifas, relação com o crédito do cliente, custo e preço de venda."""

    provedor: str
    id: int
    versao: int
    creditos_busca_por_resultado: int | None
    creditos_email: int | None
    creditos_telefone: int | None
    revelar_emails: bool
    revelar_telefones: bool
    tamanho_pagina_busca: int | None
    creditos_cliente_por_credito_provedor: int | None
    markup_percentual: Decimal | None
    custo_unitario_brl: Decimal | None
    preco_unitario_brl: Decimal | None
    casas_exibicao: int
    faltando: tuple[str, ...] = field(default_factory=tuple)

    @property
    def utilizavel(self) -> bool:
        return not self.faltando

    @property
    def revelar(self) -> list[str]:
        return (["emails"] if self.revelar_emails else []) + (["phones"] if self.revelar_telefones else [])

    def creditos_maximos_por_empresa(self, decisores: int) -> int:
        """Teto de créditos DO PROVEDOR para consultar uma empresa pedindo `decisores`: a busca devolve até uma página inteira (cobrada por
        resultado) e a revelação cobra, por contato, a tarifa de cada dado a revelar. É um teto, não uma previsão: o consumo real vem da
        medição do provedor."""
        por_contato = (self.creditos_email if self.revelar_emails else 0) + (self.creditos_telefone if self.revelar_telefones else 0)
        return self.tamanho_pagina_busca * self.creditos_busca_por_resultado + decisores * por_contato


def _faltando_politica(linha: EnriquecimentoPoliticaProvedor, tamanho_minimo: int | None = None) -> tuple[str, ...]:
    faltando = [c for c in ("creditos_busca_por_resultado", "tamanho_pagina_busca", "creditos_cliente_por_credito_provedor", "custo_unitario_brl",
                            "preco_unitario_brl") if getattr(linha, c) is None]
    if not (linha.revelar_emails or linha.revelar_telefones):
        faltando.append("revelar_emails_ou_telefones")
    if linha.revelar_emails and linha.creditos_email is None:
        faltando.append("creditos_email")
    if linha.revelar_telefones and linha.creditos_telefone is None:
        faltando.append("creditos_telefone")
    return tuple(faltando)


def _politica_resolvida(linha: EnriquecimentoPoliticaProvedor) -> PoliticaResolvida:
    return PoliticaResolvida(
        provedor=linha.provedor, id=linha.id, versao=linha.versao, creditos_busca_por_resultado=linha.creditos_busca_por_resultado,
        creditos_email=linha.creditos_email, creditos_telefone=linha.creditos_telefone, revelar_emails=linha.revelar_emails,
        revelar_telefones=linha.revelar_telefones, tamanho_pagina_busca=linha.tamanho_pagina_busca,
        creditos_cliente_por_credito_provedor=linha.creditos_cliente_por_credito_provedor,
        markup_percentual=precos.dec(linha.markup_percentual) if linha.markup_percentual is not None else None,
        custo_unitario_brl=precos.dec(linha.custo_unitario_brl) if linha.custo_unitario_brl is not None else None,
        preco_unitario_brl=precos.dec(linha.preco_unitario_brl) if linha.preco_unitario_brl is not None else None,
        casas_exibicao=linha.casas_exibicao, faltando=_faltando_politica(linha),
    )


def politica_vigente(db: Session, provedor: str) -> tuple[PoliticaResolvida | None, str | None]:
    """(política, None) quando há versão APROVADA vigente; (None, motivo) senão: politica_provedor_nao_configurada ou
    politica_provedor_pendente_aprovacao."""
    linhas = (
        db.query(EnriquecimentoPoliticaProvedor).filter(EnriquecimentoPoliticaProvedor.provedor == provedor)
        .order_by(EnriquecimentoPoliticaProvedor.versao.desc()).all()
    )
    aprovada = next((p for p in linhas if p.aprovado_em is not None and p.valido_ate is None), None)
    if aprovada is not None:
        return _politica_resolvida(aprovada), None
    return None, "politica_provedor_pendente_aprovacao" if linhas else "politica_provedor_nao_configurada"


def obter_politica(db: Session, politica_id: int) -> PoliticaResolvida:
    linha = db.get(EnriquecimentoPoliticaProvedor, politica_id)
    if linha is None:
        raise NaoEncontrado("Política do provedor não encontrada.")
    return _politica_resolvida(linha)


def definir_politica(db: Session, *, provedor: str, creditos_busca_por_resultado: int | None, creditos_email: int | None,
                     creditos_telefone: int | None, revelar_emails: bool, revelar_telefones: bool, tamanho_pagina_busca: int | None,
                     creditos_cliente_por_credito_provedor: int | None, markup_percentual, metodo_custo: str, lote_compra_id: int | None,
                     casas_exibicao: int, fonte_tarifas: str, ator_id: str | None, tenant_auditoria: str, motivo: str,
                     tamanho_pagina_minimo: int | None = None, tamanho_pagina_maximo: int | None = None,
                     aprovar: bool = False) -> EnriquecimentoPoliticaProvedor:
    """Nova versão (PENDENTE de aprovação) da política do provedor. O custo unitário e o preço de venda são calculados AQUI e gravados como
    foto: `lote_referencia` usa o custo do lote informado; `media_ponderada` usa a média de todos os lotes registrados até agora."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo.")
    for nome, valor in (("creditos_busca_por_resultado", creditos_busca_por_resultado), ("creditos_email", creditos_email),
                        ("creditos_telefone", creditos_telefone)):
        _int_nao_negativo(nome, valor)
    if creditos_cliente_por_credito_provedor is not None:
        if isinstance(creditos_cliente_por_credito_provedor, bool) or not isinstance(creditos_cliente_por_credito_provedor, int) \
                or creditos_cliente_por_credito_provedor < 1:
            raise ValidacaoFalhou("creditos_cliente_por_credito_provedor deve ser um inteiro maior ou igual a 1.")
    if tamanho_pagina_busca is not None:
        if isinstance(tamanho_pagina_busca, bool) or not isinstance(tamanho_pagina_busca, int):
            raise ValidacaoFalhou("tamanho_pagina_busca deve ser um inteiro.")
        if tamanho_pagina_minimo is not None and tamanho_pagina_busca < tamanho_pagina_minimo:
            raise ValidacaoFalhou(f"tamanho_pagina_busca abaixo do mínimo aceito pelo provedor ({tamanho_pagina_minimo}).")
        if tamanho_pagina_maximo is not None and tamanho_pagina_busca > tamanho_pagina_maximo:
            raise ValidacaoFalhou(f"tamanho_pagina_busca acima do máximo aceito pelo provedor ({tamanho_pagina_maximo}).")
    if markup_percentual is None or precos.dec(markup_percentual) < 0:
        raise ValidacaoFalhou("Informe o markup percentual (zero ou mais).")
    if not isinstance(casas_exibicao, int) or isinstance(casas_exibicao, bool) or not 0 <= casas_exibicao <= 6:
        raise ValidacaoFalhou("casas_exibicao deve estar entre 0 e 6.")
    if metodo_custo not in METODOS_CUSTO:
        raise ValidacaoFalhou(f"metodo_custo deve ser um de: {', '.join(METODOS_CUSTO)}.")
    if metodo_custo == "lote_referencia":
        lote = db.get(EnriquecimentoLoteCompra, lote_compra_id) if lote_compra_id else None
        if lote is None or lote.provedor != provedor:
            raise ValidacaoFalhou("Informe um lote de compra deste provedor como referência de custo.")
        custo_unitario = precos.dec(lote.custo_unitario_brl)
    else:
        lotes = db.query(EnriquecimentoLoteCompra).filter_by(provedor=provedor).all()
        if not lotes:
            raise ValidacaoFalhou("Não há lotes de compra registrados para calcular a média ponderada.")
        custo_unitario = precos.media_ponderada([(precos.dec(lote.custo_total_brl), lote.quantidade_creditos) for lote in lotes])
        lote_compra_id = None
    anteriores = (
        db.query(EnriquecimentoPoliticaProvedor).filter(EnriquecimentoPoliticaProvedor.provedor == provedor)
        .order_by(EnriquecimentoPoliticaProvedor.versao.desc()).all()
    )
    nova = EnriquecimentoPoliticaProvedor(
        provedor=provedor, versao=(anteriores[0].versao + 1) if anteriores else 1, creditos_busca_por_resultado=creditos_busca_por_resultado,
        creditos_email=creditos_email, creditos_telefone=creditos_telefone, revelar_emails=bool(revelar_emails),
        revelar_telefones=bool(revelar_telefones), tamanho_pagina_busca=tamanho_pagina_busca,
        creditos_cliente_por_credito_provedor=creditos_cliente_por_credito_provedor, markup_percentual=precos.dec(markup_percentual),
        metodo_custo=metodo_custo, lote_compra_id=lote_compra_id, custo_unitario_brl=custo_unitario,
        preco_unitario_brl=precos.preco_unitario(custo_unitario, markup_percentual), casas_exibicao=casas_exibicao, fonte_tarifas=fonte_tarifas,
        motivo=motivo.strip(), criado_por=ator_id,
    )
    db.add(nova)
    db.flush()
    auditoria_service.registrar(
        db, tenant_auditoria, "enriquecimento_politica_definida", "enriquecimento_politica_provedor", nova.id, ator_id,
        {"provedor": provedor, "versao": nova.versao, "motivo": motivo.strip(), "metodo_custo": metodo_custo, "lote_compra_id": lote_compra_id,
         "custo_unitario_brl": str(custo_unitario), "preco_unitario_brl": str(nova.preco_unitario_brl), "markup_percentual": str(markup_percentual),
         "pendente_aprovacao": True},
    )
    db.commit()
    if aprovar:
        aprovar_politica(db, nova.id, ator_id, tenant_auditoria)
    return nova


def aprovar_politica(db: Session, politica_id: int, ator_id: str | None, tenant_auditoria: str) -> EnriquecimentoPoliticaProvedor:
    linha = db.get(EnriquecimentoPoliticaProvedor, politica_id)
    if linha is None:
        raise NaoEncontrado("Política não encontrada.")
    if _faltando_politica(linha):
        raise ValidacaoFalhou(f"Política incompleta, não pode ser aprovada (faltando: {', '.join(_faltando_politica(linha))}).")
    irmas = db.query(EnriquecimentoPoliticaProvedor).filter(EnriquecimentoPoliticaProvedor.provedor == linha.provedor).all()
    _aprovar_linha(db, linha, irmas, ator_id, tenant_auditoria, "enriquecimento_politica_aprovada", "enriquecimento_politica_provedor",
                   {"provedor": linha.provedor, "preco_unitario_brl": str(linha.preco_unitario_brl)})
    return linha


# ------------------------------------------------------------------------------------------------------------------ disponibilidade

_MENSAGENS = {
    "provedor_indisponivel": "O provedor de contatos não está configurado neste ambiente.",
    "sem_plano_ativo": "O seu tenant não tem plano ativo. Regularize a licença ou fale com o comercial para liberar a pesquisa de decisores.",
    "plano_sem_configuracao": "O seu plano ainda não tem a pesquisa de decisores configurada. Fale com o comercial para liberar.",
    "plano_config_pendente_aprovacao": "A configuração da pesquisa de decisores do seu plano aguarda aprovação. Fale com o comercial.",
    "config_incompleta": "A configuração da pesquisa de decisores do seu plano está incompleta. Fale com o comercial para concluir.",
    "politica_provedor_nao_configurada": "A política do provedor de contatos (tarifas e preço) ainda não foi configurada. Fale com o administrador.",
    "politica_provedor_pendente_aprovacao": "A política do provedor de contatos aguarda aprovação. Fale com o administrador.",
    "politica_provedor_incompleta": "A política do provedor de contatos está incompleta. Fale com o administrador.",
    "orcamento_global_nao_configurado": "As chamadas ao provedor estão bloqueadas até o administrador configurar e aprovar o orçamento global.",
    "orcamento_global_pendente_aprovacao": "O orçamento global do provedor aguarda aprovação. Fale com o administrador.",
}


def mensagem(codigo: str) -> str:
    return _MENSAGENS[codigo]


def exigir_configuracao(db: Session, tenant_id: str, provider) -> tuple[ConfigResolvida, PoliticaResolvida]:
    """Configuração do plano e política do provedor, aprovadas e completas, ou `PesquisaBloqueada` com o motivo. Não olha saldo nem orçamento."""
    if not provider.disponivel:
        raise PesquisaBloqueada(mensagem("provedor_indisponivel"), "provedor_indisponivel",
                                [{"codigo": "provedor_indisponivel", "mensagem": mensagem("provedor_indisponivel")}])
    config, motivo = config_vigente(db, tenant_id)
    if config is None:
        raise PesquisaBloqueada(mensagem(motivo), motivo, [{"codigo": motivo, "mensagem": mensagem(motivo)}])
    if not config.utilizavel:
        texto = f"{mensagem('config_incompleta')} (faltando: {', '.join(config.faltando)})"
        raise PesquisaBloqueada(texto, "config_incompleta", [{"codigo": "config_incompleta", "mensagem": texto}])
    politica, motivo = politica_vigente(db, provider.nome_provedor)
    if politica is None:
        raise PesquisaBloqueada(mensagem(motivo), motivo, [{"codigo": motivo, "mensagem": mensagem(motivo)}])
    if not politica.utilizavel:
        texto = f"{mensagem('politica_provedor_incompleta')} (faltando: {', '.join(politica.faltando)})"
        raise PesquisaBloqueada(texto, "politica_provedor_incompleta", [{"codigo": "politica_provedor_incompleta", "mensagem": texto}])
    return config, politica


def motivos_de_indisponibilidade(db: Session, tenant_id: str, provider) -> list[dict]:
    """TODOS os motivos pelos quais a pesquisa de decisores está indisponível agora para o tenant (lista vazia = liberada para tentar).
    Mostrado na interface; não inclui números do orçamento global."""
    motivos: list[str] = []
    if not provider.disponivel:
        motivos.append("provedor_indisponivel")
    config, motivo = config_vigente(db, tenant_id)
    if config is None:
        motivos.append(motivo)
    elif not config.utilizavel:
        motivos.append("config_incompleta")
    politica, motivo = politica_vigente(db, provider.nome_provedor)
    if politica is None:
        motivos.append(motivo)
    elif not politica.utilizavel:
        motivos.append("politica_provedor_incompleta")
    if provider.pago:
        orcamento = orcamento_vigente(db, provider.nome_provedor)
        if not orcamento.configurado:
            motivos.append("orcamento_global_pendente_aprovacao" if orcamento.pendente_aprovacao else "orcamento_global_nao_configurado")
    return [{"codigo": m, "mensagem": mensagem(m)} for m in motivos]
