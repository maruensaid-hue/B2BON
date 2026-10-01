"""Tax Engine (D-074, D-075, D-076): imposto atribuível a uma receita, calculado tributo a tributo pelo Tax Profile vigente.

Regime informado pelo PO: Lucro Presumido. Nenhuma alíquota fica no código e nenhuma alíquota efetiva única vira regra:

- PIS/COFINS cumulativos e ISS: receita × alíquota (ISS por município e código de serviço).
- IRPJ e CSLL: receita → base presumida (percentual de presunção do tipo de receita) → × alíquota → imposto. A presunção
  é base, nunca imposto. Regra de 2026 (versionada no perfil): acréscimo de 10% no percentual de presunção sobre a parcela
  da receita acima do limite (R$ 5 milhões/ano, proporcional ao período de apuração).
- Adicional de IRPJ: 10% sobre a parte da base do IRPJ do período de apuração acima de R$ 20.000 × meses do período
  (trimestre = R$ 60.000), rateada pelos recebimentos na ordem em que entram no período.
- CBS/IBS (2026): a alíquota-teste é informativa; só entra na carga com a situação PAYABLE registrada pela
  contabilidade (COMPENSATED, WAIVED_BY_COMPLIANCE e PENDING_COMPLIANCE_CONFIRMATION = zero) — o 1% nunca é somado sozinho.

Os cálculos consideram as receitas do B2B ON apuradas por este motor (o que a comissão pode atribuir).

Componente sem valor (alíquota ou presunção ainda não informada) deixa a apuração aguardando o Tax Profile; os demais
tributos aparecem como simulação no detalhe.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.contexts.comissoes.tipos import PERIODOS_APURACAO, QUALQUER, BaseTributo, SituacaoReforma, Status, Tributo
from app.models.apuracao_comissao import ApuracaoComissao, PerfilTributario
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

CENTAVO = Decimal("0.01")
TRIBUTOS = {t.value for t in Tributo}
BASES = {b.value for b in BaseTributo}


def _d(valor) -> Decimal:
    return Decimal(str(valor))


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, ROUND_HALF_UP)


def aplicavel(db: Session, tipo_receita: str, dia: date) -> PerfilTributario | None:
    """Perfil vigente no dia, específico do tipo de receita antes do genérico ("*")."""
    candidatos = db.query(PerfilTributario).filter(
        PerfilTributario.vigente_de <= dia, or_(PerfilTributario.vigente_ate.is_(None), PerfilTributario.vigente_ate > dia),
        PerfilTributario.tipo_receita.in_((tipo_receita, QUALQUER)),
    ).all()
    candidatos.sort(key=lambda p: (p.tipo_receita == QUALQUER, -p.vigente_de.toordinal(), -p.id))
    return candidatos[0] if candidatos else None


def _normalizar(componente: dict) -> dict:
    """Formato D-075. Componente legado da D-074 ({"nome", "aliquota"}) vale como OTHER_TAX sobre a receita."""
    if "tributo" in componente:
        return {"base": BaseTributo.RECEITA.value, **componente}
    return {"tributo": Tributo.OUTRO.value, "rotulo": componente.get("nome"), "aliquota": componente.get("aliquota"),
            "base": BaseTributo.RECEITA.value}


def _inicio_periodo(dia: date, meses: int) -> date:
    return date(dia.year, (dia.month - 1) // meses * meses + 1, 1)


def _anteriores(db: Session, apuracao: ApuracaoComissao, meses: int) -> list[ApuracaoComissao]:
    """Recebimentos anteriores (ordem: data, id) no mesmo período de apuração."""
    inicio = _inicio_periodo(apuracao.recebido_em, meses)
    candidatos = db.query(ApuracaoComissao).filter(
        ApuracaoComissao.id != apuracao.id, ApuracaoComissao.recebido_em >= inicio, ApuracaoComissao.recebido_em <= apuracao.recebido_em,
        ApuracaoComissao.status != Status.ESTORNADA.value).all()
    return [a for a in candidatos if (a.recebido_em, a.id) < (apuracao.recebido_em, apuracao.id or 0)]


def _excedente(anterior: Decimal, atual: Decimal, limite: Decimal) -> Decimal:
    """Parte de `atual` que passa do limite, dado o acumulado `anterior` no período."""
    return max(anterior + atual - limite, Decimal(0)) - max(anterior - limite, Decimal(0))


def _base_presumida(db: Session, componente: dict, apuracao: ApuracaoComissao) -> tuple[Decimal, dict]:
    """Receita × presunção. Regra de 2026 (acréscimo de presunção, versionada no perfil): a parcela da receita acima do
    limite do período (limite anual × meses do período ÷ 12, sobre a receita acumulada sujeita aos coeficientes) usa a
    presunção acrescida de `percentual` — 32% × 1,10 = 35,2%, não 32% + 10 pontos."""
    bruto, presuncao = _d(apuracao.receita_bruta), _d(componente["presuncao"])
    acrescimo = componente.get("acrescimo_presuncao")
    if not acrescimo:
        return _q(bruto * presuncao), {}
    meses = PERIODOS_APURACAO[acrescimo.get("periodo") or "TRIMESTRAL"]
    limite = _d(acrescimo["limite_anual"]) * meses / 12
    anterior = sum((_d(a.receita_bruta) for a in _anteriores(db, apuracao, meses)), Decimal(0))
    excedente = _excedente(anterior, bruto, limite)
    acrescida = presuncao * (1 + _d(acrescimo["percentual"]))
    base = _q((bruto - excedente) * presuncao + excedente * acrescida)
    return base, {"receita_acima_do_limite": float(excedente), "presuncao_acrescida": float(acrescida)}


def _base_irpj_anterior(db: Session, apuracao: ApuracaoComissao, meses: int) -> Decimal:
    """Base de cálculo do IRPJ já atribuída a recebimentos anteriores do mesmo período de apuração."""
    return sum((_d(((a.detalhe or {}).get("tributos") or {}).get("base_irpj") or 0) for a in _anteriores(db, apuracao, meses)), Decimal(0))


def _situacao_reforma(componente: dict) -> str:
    if componente.get("situacao"):
        return componente["situacao"]
    if componente.get("compensado"):
        return SituacaoReforma.COMPENSADO.value
    if componente.get("dispensado"):
        return SituacaoReforma.DISPENSADO.value
    return SituacaoReforma.PENDENTE.value


def calcular(db: Session, perfil: PerfilTributario, apuracao: ApuracaoComissao) -> tuple[Decimal | None, dict]:
    """(imposto atribuível ou None se o perfil tiver valor pendente, detalhe por tributo)."""
    bruto = _d(apuracao.receita_bruta)
    linhas, pendencias, total, base_irpj = [], [], Decimal(0), None
    componentes = [_normalizar(c) for c in perfil.componentes]
    for componente in componentes:
        if componente["tributo"] == Tributo.IRPJ.value and componente.get("presuncao") is not None:
            base_irpj, _ = _base_presumida(db, componente, apuracao)
    for componente in componentes:
        tributo, base_tipo = componente["tributo"], componente["base"]
        linha = {"tributo": tributo, "base_tipo": base_tipo, "rotulo": componente.get("rotulo")}
        valor: Decimal | None = None
        if base_tipo == BaseTributo.TESTE_REFORMA.value:
            teste = _q(bruto * _d(componente.get("aliquota_teste") or 0))
            situacao = _situacao_reforma(componente)
            caixa = componente.get("aliquota_caixa_efetiva")
            valor = _q(bruto * _d(caixa if caixa is not None else componente.get("aliquota_teste") or 0)) \
                if situacao == SituacaoReforma.DEVIDO.value else Decimal(0)  # 1% nunca somado automaticamente
            linha.update(aliquota_teste=componente.get("aliquota_teste"), valor_teste=float(teste), situacao=situacao)
        elif componente.get("aliquota") is None:
            pendencias.append(f"{tributo}: alíquota")
        elif base_tipo == BaseTributo.RECEITA.value:
            valor = _q(bruto * _d(componente["aliquota"]))
        elif base_tipo == BaseTributo.PRESUNCAO.value:
            if componente.get("presuncao") is None:
                pendencias.append(f"{tributo}: percentual de presunção para {apuracao.tipo_receita}")
            else:
                base, extra = _base_presumida(db, componente, apuracao)
                valor, linha["base"] = _q(base * _d(componente["aliquota"])), float(base)
                linha.update(extra)
        else:  # PRESUNCAO_EXCEDENTE: adicional de IRPJ sobre a base do IRPJ acima de R$ limite_mensal × meses do período
            meses = PERIODOS_APURACAO.get(componente.get("periodo"))
            limite = _d(componente["limite_mensal"]) * meses if componente.get("limite_mensal") is not None and meses else (
                _d(componente["limite_periodo"]) if componente.get("limite_periodo") is not None and meses else None)
            if limite is None or base_irpj is None:
                pendencias.append(f"{tributo}: limite, período de apuração e base do IRPJ")
            else:
                excedente = _excedente(_base_irpj_anterior(db, apuracao, meses), base_irpj, limite)
                valor, linha["base"], linha["limite_periodo"] = _q(excedente * _d(componente["aliquota"])), float(excedente), float(limite)
        linha["valor"] = float(valor) if valor is not None else None
        linhas.append(linha)
        if valor is not None:
            total += valor
    detalhe = {"regime": perfil.regime, "versao_legal": perfil.versao_legal, "municipio": perfil.municipio,
               "item_lista_servico": perfil.item_lista_servico, "codigo_servico": perfil.codigo_servico, "tributos": linhas,
               "base_irpj": float(base_irpj) if base_irpj is not None else None}
    if pendencias:
        return None, {**detalhe, "pendencias": pendencias, "simulacao_parcial": float(total)}
    return _q(total), detalhe


def _validar(componentes: list[dict]) -> None:
    if not componentes:
        raise ValidacaoFalhou("Informe os tributos do perfil.")
    vistos = set()
    for bruto in componentes:
        c = _normalizar(bruto)
        tributo, base = c.get("tributo"), c.get("base")
        if tributo not in TRIBUTOS or base not in BASES:
            raise ValidacaoFalhou(f"Tributo deve ser um de {sorted(TRIBUTOS)} e base um de {sorted(BASES)}.")
        if tributo in vistos and tributo != Tributo.OUTRO.value:
            raise ValidacaoFalhou(f"{tributo} aparece duas vezes no perfil.")
        vistos.add(tributo)
        for campo in ("aliquota", "aliquota_teste", "aliquota_caixa_efetiva"):
            if c.get(campo) is not None and not 0 <= float(c[campo]) < 1:
                raise ValidacaoFalhou(f"{tributo}: {campo} entre 0 e 1.")
        if c.get("presuncao") is not None and not 0 < float(c["presuncao"]) <= 1:
            raise ValidacaoFalhou(f"{tributo}: presunção entre 0 e 1.")
        if base == BaseTributo.PRESUNCAO.value and "presuncao" not in c:
            raise ValidacaoFalhou(f"{tributo}: base presumida exige o campo presuncao (vazio = ainda não informado).")
        if base == BaseTributo.TESTE_REFORMA.value:
            if tributo not in (Tributo.CBS.value, Tributo.IBS.value):
                raise ValidacaoFalhou("Alíquota-teste da reforma só para CBS e IBS.")
            situacoes = {s.value for s in SituacaoReforma}
            if c.get("situacao") not in (None, *situacoes):
                raise ValidacaoFalhou(f"Situação CBS/IBS: {', '.join(sorted(situacoes))}.")
        if base == BaseTributo.PRESUNCAO_EXCEDENTE.value:
            if c.get("periodo") not in (None, *PERIODOS_APURACAO):
                raise ValidacaoFalhou(f"Período de apuração: {', '.join(PERIODOS_APURACAO)}.")
            if c.get("limite_mensal") is not None and float(c["limite_mensal"]) < 0:
                raise ValidacaoFalhou("Limite mensal do adicional não negativo.")
        acrescimo = c.get("acrescimo_presuncao")
        if acrescimo is not None and (not isinstance(acrescimo, dict) or acrescimo.get("percentual") is None
                                      or acrescimo.get("limite_anual") is None or float(acrescimo["percentual"]) < 0
                                      or float(acrescimo["limite_anual"]) < 0
                                      or (acrescimo.get("periodo") or "TRIMESTRAL") not in PERIODOS_APURACAO):
            raise ValidacaoFalhou("Acréscimo de presunção: percentual, limite_anual e período válidos.")


def criar(db: Session, dados: dict, ator_id: str | None) -> PerfilTributario:
    componentes = dados.get("componentes") or []
    _validar(componentes)
    vigente_de, vigente_ate = dados["vigente_de"], dados.get("vigente_ate")
    if vigente_ate is not None and vigente_ate <= vigente_de:
        raise ValidacaoFalhou("O fim da vigência precisa ser depois do início.")
    tipo = dados.get("tipo_receita") or QUALQUER
    municipio, codigo, item = dados.get("municipio"), dados.get("codigo_servico"), dados.get("item_lista_servico")
    for aberto in db.query(PerfilTributario).filter_by(tipo_receita=tipo, municipio=municipio, codigo_servico=codigo, item_lista_servico=item, vigente_ate=None).all():
        if aberto.vigente_de >= vigente_de:
            raise ValidacaoFalhou(f"Já existe perfil para {tipo} vigente desde {aberto.vigente_de}; encerre-o antes.")
        aberto.vigente_ate = vigente_de  # o novo perfil substitui o aberto a partir da sua vigência
    perfil = PerfilTributario(regime=dados["regime"], vigente_de=vigente_de, vigente_ate=vigente_ate, tipo_receita=tipo,
                              municipio=municipio, codigo_servico=codigo, item_lista_servico=item, versao_legal=dados.get("versao_legal"),
                              componentes=componentes, aliquota_efetiva=None,
                              metodo_calculo=dados.get("metodo_calculo") or "POR_TRIBUTO", fonte=dados.get("fonte"),
                              observacoes=dados.get("observacoes"), criado_por=ator_id)
    db.add(perfil)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "perfil_tributario_criado", "perfil_tributario", perfil.id,
                                ator_id, {"dados": {k: str(v) for k, v in dados.items() if k != "componentes"},
                                          "componentes": componentes, "origem": "admin"})
    return perfil


def pendencias(perfil: PerfilTributario) -> list[str]:
    """Valores que o perfil ainda não tem (para a tela de parâmetros)."""
    faltam = []
    for c in map(_normalizar, perfil.componentes):
        if c["base"] == BaseTributo.TESTE_REFORMA.value:
            continue
        if c.get("aliquota") is None:
            faltam.append(f"{c['tributo']}: alíquota")
        if c["base"] == BaseTributo.PRESUNCAO.value and c.get("presuncao") is None:
            faltam.append(f"{c['tributo']}: presunção")
    return faltam


def como_dict(perfil: PerfilTributario) -> dict:
    return {"id": perfil.id, "regime": perfil.regime, "vigente_de": perfil.vigente_de.isoformat(),
            "vigente_ate": perfil.vigente_ate.isoformat() if perfil.vigente_ate else None, "tipo_receita": perfil.tipo_receita,
            "municipio": perfil.municipio, "item_lista_servico": perfil.item_lista_servico, "codigo_servico": perfil.codigo_servico,
            "versao_legal": perfil.versao_legal,
            "componentes": [_normalizar(c) for c in perfil.componentes], "metodo_calculo": perfil.metodo_calculo,
            "fonte": perfil.fonte, "observacoes": perfil.observacoes, "pendencias": pendencias(perfil)}
