"""Razão de créditos de enriquecimento (append-only) e agregados derivados dele.

Saldo, reservado e disponível NUNCA são colunas editáveis: são somas de `enriquecimento_movimento`. Toda escrita de saldo acontece com a linha
da carteira do tenant travada (`SELECT … FOR UPDATE` no Postgres), e a reserva que também mexe no orçamento global trava antes a linha do
orçamento (ordem fixa orçamento → carteira, para não haver impasse entre duas pesquisas). Em SQLite (testes) a trava não existe; a unicidade de
`idempotency_key` e a atualização condicional de estado são o que segura a repetição.
"""

from datetime import datetime, timedelta

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import precos
from app.contexts.enriquecimento.config import ConfigResolvida, agora_utc, fim_do_mes, orcamento_vigente, periodo_de
from app.models.enriquecimento_creditos import EnriquecimentoCarteira, EnriquecimentoMovimento, EnriquecimentoOrcamentoGlobal
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

TIPOS = ("CONCESSAO", "RENOVACAO", "COMPRA", "ESTORNO_COMPRA", "RESERVA", "CONSUMO", "LIBERACAO", "ESTORNO", "EXPIRACAO", "AJUSTE", "RECONCILIACAO", "USO")
TIPOS_CONSUMO = ("CONSUMO", "ESTORNO")  # consumo líquido = consumos − estornos


def _soma(db: Session, coluna, *filtros) -> int:
    return int(db.query(func.coalesce(func.sum(coluna), 0)).filter(*filtros).scalar() or 0)


def _soma_decimal(db: Session, coluna, *filtros) -> Decimal:
    return precos.dec(db.query(func.coalesce(func.sum(coluna), 0)).filter(*filtros).scalar() or 0)


def travar_carteira(db: Session, tenant_id: str) -> EnriquecimentoCarteira:
    consulta = db.query(EnriquecimentoCarteira).filter_by(tenant_id=tenant_id).with_for_update()
    carteira = consulta.one_or_none()
    if carteira is None:
        try:
            with db.begin_nested():
                db.add(EnriquecimentoCarteira(tenant_id=tenant_id))
        except IntegrityError:
            pass  # outra transação criou a mesma linha agora; relê abaixo
        carteira = consulta.one()
    return carteira


def travar_orcamento(db: Session, provedor: str) -> None:
    """Trava a linha vigente do orçamento do provedor (serializa as reservas de TODOS os tenants contra o mesmo teto)."""
    vigente = orcamento_vigente(db, provedor)
    if vigente.id is not None:
        db.query(EnriquecimentoOrcamentoGlobal).filter_by(id=vigente.id).with_for_update().one_or_none()


def saldo(db: Session, tenant_id: str) -> int:
    return _soma(db, EnriquecimentoMovimento.delta_saldo, EnriquecimentoMovimento.tenant_id == tenant_id)


def reservado(db: Session, tenant_id: str) -> int:
    return _soma(db, EnriquecimentoMovimento.delta_reservado, EnriquecimentoMovimento.tenant_id == tenant_id)


def disponivel(db: Session, tenant_id: str) -> int:
    return saldo(db, tenant_id) - reservado(db, tenant_id)


def consumo_liquido(db: Session, tenant_id: str | None, periodo: str, provedor: str | None = None) -> int:
    """Créditos efetivamente consumidos no período (consumos − estornos). Sem `tenant_id`, soma todos os tenants (orçamento global)."""
    filtros = [EnriquecimentoMovimento.tipo.in_(TIPOS_CONSUMO), EnriquecimentoMovimento.periodo == periodo]
    if tenant_id is not None:
        filtros.append(EnriquecimentoMovimento.tenant_id == tenant_id)
    if provedor is not None:
        filtros.append(EnriquecimentoMovimento.provedor == provedor)
    return -_soma(db, EnriquecimentoMovimento.delta_saldo, *filtros)


def reservado_do_provedor(db: Session, provedor: str) -> int:
    """Créditos DO PROVEDOR retidos agora por pesquisas em curso de todos os tenants."""
    return _soma(db, EnriquecimentoMovimento.provedor_delta_reservado, EnriquecimentoMovimento.provedor == provedor)


def consumo_provedor(db: Session, provedor: str, periodo: str) -> int:
    """Créditos DO PROVEDOR consumidos (medidos pelas respostas dele, menos o que ele devolveu) no mês, todos os tenants somados."""
    return _soma(db, EnriquecimentoMovimento.provedor_delta_consumido, EnriquecimentoMovimento.provedor == provedor,
                 EnriquecimentoMovimento.periodo == periodo)


def resultado_financeiro(db: Session, provedor: str, periodo: str | None = None) -> dict:
    """Custo de aquisição × valor de venda dos consumos do provedor (somente administrativo). Valores na precisão interna, sem arredondar."""
    filtros = [EnriquecimentoMovimento.provedor == provedor, EnriquecimentoMovimento.custo_total_brl.isnot(None)]
    if periodo:
        filtros.append(EnriquecimentoMovimento.periodo == periodo)
    custo = _soma_decimal(db, EnriquecimentoMovimento.custo_total_brl, *filtros)
    venda = _soma_decimal(db, EnriquecimentoMovimento.valor_venda_brl, *filtros)
    return {"custo_brl": custo, "venda_brl": venda, "margem_brl": venda - custo,
            "margem_percentual": (precos.margem_sobre_venda(venda, custo)) if venda else None}


def lancar(db: Session, tenant_id: str, tipo: str, *, delta_saldo: int = 0, delta_reservado: int = 0, provedor: str | None = None,
           pesquisa_id: str | None = None, item_id: int | None = None, origem: str | None = None, motivo: str | None = None,
           ator_id: str | None = None, expira_em: datetime | None = None, idempotency_key: str | None = None,
           agora: datetime | None = None, provedor_delta_reservado: int = 0, provedor_delta_consumido: int = 0,
           custo_unitario_brl=None, preco_unitario_brl=None, custo_total_brl=None, valor_venda_brl=None, politica_id: int | None = None,
           fonte: str | None = None) -> EnriquecimentoMovimento:
    """Acrescenta uma linha ao razão. Idempotente por (tenant, idempotency_key): repetir devolve a linha original sem lançar de novo.
    Quem chama já deve ter travado a carteira do tenant."""
    if tipo not in TIPOS:
        raise ValidacaoFalhou(f"Tipo de movimento desconhecido: {tipo}")
    if idempotency_key:
        existente = db.query(EnriquecimentoMovimento).filter_by(tenant_id=tenant_id, idempotency_key=idempotency_key).one_or_none()
        if existente is not None:
            return existente
    agora = agora or agora_utc()
    db.flush()
    antes = disponivel(db, tenant_id)
    movimento = EnriquecimentoMovimento(
        tenant_id=tenant_id, tipo=tipo, delta_saldo=delta_saldo, delta_reservado=delta_reservado,
        disponivel_apos=antes + delta_saldo - delta_reservado, provedor=provedor, periodo=periodo_de(agora), pesquisa_id=pesquisa_id,
        item_id=item_id, origem=origem, motivo=motivo, ator_id=ator_id, expira_em=expira_em, idempotency_key=idempotency_key, criado_em=agora,
        provedor_delta_reservado=provedor_delta_reservado, provedor_delta_consumido=provedor_delta_consumido, custo_unitario_brl=custo_unitario_brl,
        preco_unitario_brl=preco_unitario_brl, custo_total_brl=custo_total_brl, valor_venda_brl=valor_venda_brl, politica_id=politica_id, fonte=fonte,
    )
    db.add(movimento)
    db.flush()
    return movimento


def garantir_franquia(db: Session, tenant_id: str, config: ConfigResolvida, agora: datetime | None = None) -> EnriquecimentoMovimento | None:
    """Concede a franquia do período corrente, uma única vez (idempotente). `mensal` renova todo mês e vence no fim dele (sem rollover);
    `unica` (POC / Free Trial) é concedida uma vez na vida do tenant. Config sem franquia ou sem periodicidade não concede nada."""
    if config.franquia_creditos is None or config.franquia_creditos <= 0 or config.periodicidade is None:
        return None
    agora = agora or agora_utc()
    if config.periodicidade == "mensal":
        chave, expira = f"franquia:{periodo_de(agora)}", fim_do_mes(agora)
    else:
        chave, expira = "franquia:unica", None
    travar_carteira(db, tenant_id)
    ja_teve = db.query(EnriquecimentoMovimento.id).filter(
        EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.origem == "franquia").first() is not None
    return lancar(db, tenant_id, "RENOVACAO" if ja_teve else "CONCESSAO", delta_saldo=config.franquia_creditos, origem="franquia",
                  motivo=f"Franquia {config.periodicidade} (config v{config.versao}, {config.origem})", expira_em=expira,
                  idempotency_key=chave, agora=agora)


ORIGENS_COM_VALIDADE = ("franquia", "compra")
VALIDADE_PACOTE_DIAS = 30  # o pacote adicional vale 30 dias a partir da confirmação do pagamento (não o fim do mês)
JANELA_DE_CONSUMO_DIAS = 70  # franquia vive no máximo 31 dias e pacote 30: tudo que ainda vale hoje nasceu dentro desta janela
_SEM_VALIDADE = datetime.max


def baldes(db: Session, tenant_id: str, agora: datetime | None = None, *, janela_dias: int = JANELA_DE_CONSUMO_DIAS,
           coletor: list[dict] | None = None) -> list[dict]:
    """Reconstrói, a partir do razão, de QUAL concessão cada crédito ainda disponível veio (franquia do mês, pacotes comprados, créditos sem validade).

    Reprodução cronológica: cada concessão vira um balde com validade; cada consumo sai primeiro do balde que vence antes (a franquia do mês, depois os
    pacotes, depois o que não vence), o que é o mais favorável ao cliente; o que sobra num balde na hora em que ele vence é o que expira. Estorno de
    pacote reduz o balde do pacote; estorno de consumo devolve ao balde de onde saiu. É uma distribuição derivada do razão, não um segundo saldo. `coletor` recebe cada consumo com a
    origem do balde (franquia, compra, ...), para os relatórios; `janela_dias` alarga a reprodução para períodos antigos."""
    agora = agora or agora_utc()
    desde = agora - timedelta(days=janela_dias)
    chaves_expiradas = {chave for (chave,) in db.query(EnriquecimentoMovimento.idempotency_key).filter(
        EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.tipo == "EXPIRACAO").all() if chave}
    # Concessão com validade que ainda não teve a sua expiração lançada pode ser mais antiga que a janela (tenant parado): entra mesmo assim.
    pendente = db.query(EnriquecimentoMovimento).filter(
        EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.origem.in_(ORIGENS_COM_VALIDADE),
        EnriquecimentoMovimento.tipo.in_(("CONCESSAO", "RENOVACAO", "COMPRA")), EnriquecimentoMovimento.expira_em.isnot(None),
        EnriquecimentoMovimento.criado_em < desde).order_by(EnriquecimentoMovimento.criado_em).all()
    for c in pendente:
        if f"expiracao:{c.id}" not in chaves_expiradas:
            desde = min(desde, c.criado_em)
            break
    movimentos = db.query(EnriquecimentoMovimento).filter(
        EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.criado_em >= desde,
        EnriquecimentoMovimento.tipo.in_(("CONCESSAO", "RENOVACAO", "COMPRA", "AJUSTE", "ESTORNO_COMPRA", "CONSUMO", "ESTORNO")),
    ).order_by(EnriquecimentoMovimento.criado_em, EnriquecimentoMovimento.id).all()

    lista: list[dict] = []
    pilha: list[tuple[dict, int]] = []  # consumos feitos, para devolver um estorno de consumo ao balde certo

    def vencer(ate: datetime) -> None:
        for b in lista:
            if not b["vencido"] and b["expira_em"] is not None and b["expira_em"] <= ate:
                b["vencido"], b["restante_ao_vencer"], b["restante"] = True, b["restante"], 0

    def consumir(quantidade: int, registrar: bool, quando: datetime | None = None) -> None:
        candidatos = sorted((b for b in lista if not b["vencido"] and b["restante"] > 0),
                            key=lambda b: (b["expira_em"] or _SEM_VALIDADE, b["origem"] != "franquia", b["id"]))
        for b in candidatos:
            if quantidade <= 0:
                break
            tirar = min(quantidade, b["restante"])
            b["restante"] -= tirar
            quantidade -= tirar
            if registrar:
                pilha.append((b, tirar))
            if coletor is not None and quando is not None:
                coletor.append({"em": quando, "origem": b["origem"], "creditos": tirar})
        if coletor is not None and quando is not None and quantidade > 0:
            coletor.append({"em": quando, "origem": "sem_origem_identificada", "creditos": quantidade})

    for m in movimentos:
        vencer(m.criado_em)
        if m.tipo in ("CONCESSAO", "RENOVACAO", "COMPRA") or (m.tipo == "AJUSTE" and m.delta_saldo > 0):
            lista.append({"id": m.id, "origem": m.origem or "ajuste", "quantidade": m.delta_saldo, "restante": m.delta_saldo, "criado_em": m.criado_em,
                          "expira_em": m.expira_em, "vencido": False, "restante_ao_vencer": 0, "chave": m.idempotency_key})
        elif m.tipo == "ESTORNO_COMPRA":
            alvo = next((b for b in lista if b["origem"] == "compra" and b["expira_em"] == m.expira_em and b["quantidade"] > 0), None)
            if alvo is not None:
                tirar = min(-m.delta_saldo, alvo["quantidade"])
                alvo["quantidade"] -= tirar
                alvo["restante"] = max(0, alvo["restante"] - tirar) if not alvo["vencido"] else 0
        elif m.tipo == "CONSUMO" or (m.tipo == "AJUSTE" and m.delta_saldo < 0):
            consumir(-m.delta_saldo, registrar=m.tipo == "CONSUMO", quando=m.criado_em if m.tipo == "CONSUMO" else None)
        elif m.tipo == "ESTORNO" and m.delta_saldo > 0:
            devolver = m.delta_saldo
            while devolver > 0 and pilha:
                balde, qtd = pilha.pop()
                volta = min(devolver, qtd)
                devolver -= volta
                if not balde["vencido"]:
                    balde["restante"] += volta
    vencer(agora)
    return lista


def expirar_vencidos(db: Session, tenant_id: str, agora: datetime | None = None) -> int:
    """Franquia mensal (fim do mês) e pacotes adicionais (30 dias) vencem e não acumulam. O que sobrou no balde na hora em que ele venceu, e não está
    retido por pesquisa, vira EXPIRACAO. Ajustes administrativos e a autorização de POC (`unica`) não têm validade e não expiram aqui."""
    agora = agora or agora_utc()
    total = 0
    for balde in baldes(db, tenant_id, agora):
        if not balde["vencido"] or balde["origem"] not in ORIGENS_COM_VALIDADE or balde["restante_ao_vencer"] <= 0:
            continue
        chave = f"expiracao:{balde['id']}"
        if db.query(EnriquecimentoMovimento.id).filter_by(tenant_id=tenant_id, idempotency_key=chave).first() is not None:
            continue
        a_expirar = max(0, min(balde["restante_ao_vencer"], disponivel(db, tenant_id)))
        if a_expirar > 0:
            travar_carteira(db, tenant_id)
            lancar(db, tenant_id, "EXPIRACAO", delta_saldo=-a_expirar, origem=balde["origem"], idempotency_key=chave, agora=agora,
                   motivo=f"{'Franquia' if balde['origem'] == 'franquia' else 'Pacote adicional'} {periodo_de(balde['criado_em'])} vencido(a) sem uso")
            total += a_expirar
    return total


def composicao(db: Session, tenant_id: str, agora: datetime | None = None) -> dict:
    """Saldo por origem, para o painel: franquia do mês, pacotes adicionais ainda válidos e outros (ajuste, autorização de POC). Distribuição derivada
    do razão (ver `baldes`), não um segundo saldo."""
    agora = agora or agora_utc()
    ativos = [b for b in baldes(db, tenant_id, agora) if not b["vencido"]]
    franquia_restante = sum(b["restante"] for b in ativos if b["origem"] == "franquia")
    pacotes_ativos = sorted((b for b in ativos if b["origem"] == "compra"), key=lambda b: (b["expira_em"] or _SEM_VALIDADE, b["id"]))
    adicional_restante = sum(b["restante"] for b in pacotes_ativos)
    total = saldo(db, tenant_id)
    return {"franquia_restante": franquia_restante, "adicional_restante": adicional_restante,
            "outros": total - franquia_restante - adicional_restante, "saldo": total,
            "adicional_expira_em": pacotes_ativos[0]["expira_em"].isoformat() if pacotes_ativos and pacotes_ativos[0]["restante"] > 0 else None,
            "pacotes_ativos": [{"creditos": b["quantidade"], "restante": b["restante"], "expira_em": b["expira_em"].isoformat() if b["expira_em"] else None}
                               for b in pacotes_ativos if b["restante"] > 0]}


def limite_por_pacotes(db: Session, tenant_id: str, agora: datetime | None = None) -> tuple[int | None, list[dict]]:
    """Limite de créditos por pesquisa concedido por pacotes adicionais: enquanto houver crédito de pacote válido (não consumido e dentro dos 30 dias), o
    limite do tenant passa a ser o tamanho do pacote comprado (a soma, se houver mais de um ativo). Acabou o crédito ou venceu: volta ao do plano."""
    pacotes = composicao(db, tenant_id, agora)["pacotes_ativos"]
    return (sum(p["creditos"] for p in pacotes) or None), pacotes


def conceder_compra(db: Session, tenant_id: str, compra_id: int, quantidade: int, expira_em: datetime, pacote_codigo: str, agora: datetime | None = None
                    ) -> EnriquecimentoMovimento:
    """Crédito de pacote adicional pago (idempotente por `compra:<id>`), com validade de 30 dias. Separado da franquia (`origem=compra`)."""
    travar_carteira(db, tenant_id)
    return lancar(db, tenant_id, "COMPRA", delta_saldo=quantidade, origem="compra", expira_em=expira_em, idempotency_key=f"compra:{compra_id}",
                  motivo=f"Pacote {pacote_codigo}", agora=agora)


def preparar(db: Session, tenant_id: str, config: ConfigResolvida | None, agora: datetime | None = None) -> None:
    """Expira o vencido e garante a franquia do período, com a carteira travada. Não faz commit."""
    travar_carteira(db, tenant_id)
    expirar_vencidos(db, tenant_id, agora)
    if config is not None and config.utilizavel:
        garantir_franquia(db, tenant_id, config, agora)


def ajustar(db: Session, tenant_id: str, quantidade: int, motivo: str, ator_id: str | None, tenant_auditoria: str, *,
            idempotency_key: str | None = None) -> EnriquecimentoMovimento:
    """Ajuste administrativo (positivo concede, negativo debita), sempre com motivo e auditado. Débito maior que o disponível é recusado."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo do ajuste.")
    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade == 0:
        raise ValidacaoFalhou("A quantidade do ajuste deve ser um inteiro diferente de zero.")
    travar_carteira(db, tenant_id)
    if quantidade < 0 and -quantidade > disponivel(db, tenant_id):
        raise ValidacaoFalhou("Débito maior que o saldo disponível.")
    movimento = lancar(db, tenant_id, "AJUSTE", delta_saldo=quantidade, origem="ajuste_admin", motivo=motivo.strip(), ator_id=ator_id,
                       idempotency_key=idempotency_key)
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_creditos_ajustados", "enriquecimento_movimento", movimento.id, ator_id,
                                {"tenant_alvo": tenant_id, "quantidade": quantidade, "motivo": motivo.strip()})
    db.commit()
    return movimento


def estornar(db: Session, tenant_id: str, quantidade: int, motivo: str, ator_id: str | None, tenant_auditoria: str, *,
             pesquisa_id: str | None = None, provedor: str | None = None, idempotency_key: str | None = None,
             provedor_devolvidos: int = 0) -> EnriquecimentoMovimento:
    """Devolve créditos DO CLIENTE já consumidos. Se o provedor também devolveu créditos a CyberFort, informe `provedor_devolvidos` (em créditos
    do provedor): o consumo do provedor e o orçamento global são reduzidos nessa quantidade. Não estorna mais do que o consumo líquido da pesquisa."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo do estorno.")
    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade <= 0:
        raise ValidacaoFalhou("A quantidade do estorno deve ser um inteiro positivo.")
    travar_carteira(db, tenant_id)
    if pesquisa_id is not None:
        liquido = -_soma(db, EnriquecimentoMovimento.delta_saldo, EnriquecimentoMovimento.tenant_id == tenant_id,
                         EnriquecimentoMovimento.pesquisa_id == pesquisa_id, EnriquecimentoMovimento.tipo.in_(TIPOS_CONSUMO))
        if quantidade > liquido:
            raise ValidacaoFalhou("Estorno maior que o consumo líquido da pesquisa.")
    if isinstance(provedor_devolvidos, bool) or not isinstance(provedor_devolvidos, int) or provedor_devolvidos < 0:
        raise ValidacaoFalhou("provedor_devolvidos deve ser um inteiro maior ou igual a zero.")
    movimento = lancar(db, tenant_id, "ESTORNO", delta_saldo=quantidade, provedor=provedor, pesquisa_id=pesquisa_id, origem="estorno",
                       motivo=motivo.strip(), ator_id=ator_id, idempotency_key=idempotency_key, provedor_delta_consumido=-provedor_devolvidos)
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_creditos_estornados", "enriquecimento_movimento", movimento.id, ator_id,
                                {"tenant_alvo": tenant_id, "quantidade": quantidade, "pesquisa_id": pesquisa_id, "motivo": motivo.strip()})
    db.commit()
    return movimento


def situacao_global(db: Session, provedor: str, agora: datetime | None = None) -> dict:
    """Uso do orçamento global do provedor no mês, em créditos DO PROVEDOR: medido + reservado contra o limite aprovado.
    `nivel`: nao_configurado | ok | alerta | esgotado."""
    agora = agora or agora_utc()
    orcamento = orcamento_vigente(db, provedor)
    consumido = consumo_provedor(db, provedor, periodo_de(agora))
    retido = reservado_do_provedor(db, provedor)
    if not orcamento.configurado:
        return {"provedor": provedor, "nivel": "nao_configurado", "limite": None, "consumido": consumido, "reservado": retido,
                "restante": None, "percentual": None, "versao": orcamento.versao, "alerta_percentual": orcamento.alerta_percentual}
    usado = consumido + retido
    limite = orcamento.limite_creditos
    percentual = round(100 * usado / limite, 1) if limite else 100.0
    nivel = "esgotado" if usado >= limite else ("alerta" if percentual >= orcamento.alerta_percentual else "ok")
    return {"provedor": provedor, "nivel": nivel, "limite": limite, "consumido": consumido, "reservado": retido,
            "restante": max(0, limite - usado), "percentual": percentual, "versao": orcamento.versao,
            "alerta_percentual": orcamento.alerta_percentual}


def registrar_uso_fonte(db: Session, tenant_id: str, fonte: str, operacao: str, quantidade: int = 1, *, ator_id: str | None = None,
                        referencia: str | None = None) -> EnriquecimentoMovimento:
    """Contabiliza o USO de uma fonte de enriquecimento (QSA da Receita, Brasil API…) sem custo de crédito: lançamento `USO` de deltas zero, com
    a fonte e a operação, para o painel mostrar quanto cada fonte foi usada. Cobrança por fonte só existirá com regra comercial aprovada."""
    return lancar(db, tenant_id, "USO", origem=operacao, fonte=fonte, motivo=f"{operacao} x{quantidade}" + (f" ({referencia})" if referencia else ""),
                  ator_id=ator_id)


def uso_por_fonte(db: Session, tenant_id: str, periodo: str) -> dict[str, int]:
    """Quantidade de operações registradas por fonte no mês (QSA, Brasil API, provedor de contatos…)."""
    linhas = (
        db.query(EnriquecimentoMovimento.fonte, func.count(EnriquecimentoMovimento.id))
        .filter(EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.tipo == "USO", EnriquecimentoMovimento.periodo == periodo)
        .group_by(EnriquecimentoMovimento.fonte).all()
    )
    return {fonte: total for fonte, total in linhas}
