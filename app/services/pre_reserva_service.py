"""Formulário público de pré-reserva de data (palestra, workshop…): quem preenche cai direto no CRM do tenant como conta + contato + negócio, e a data sai da agenda.

A escassez que a página mostra é a agenda real: só aparecem as datas configuradas que ainda não têm pré-reserva ativa e que respeitam a antecedência mínima. Duas pessoas
enviando a mesma data ao mesmo tempo não conseguem as duas: o índice único parcial em `pre_reserva` recusa a segunda, e ela recebe a mensagem de que a data acabou de sair.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.shared import events as eventos
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.negocio import Negocio
from app.models.pre_reserva import ConfiguracaoPreReserva, PreReserva
from app.services import atividade_service, auditoria_service, conta_service, crm_service, link_captura_lead_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

ORIGEM = "pre_reserva_publica"
NOMES_PAGAMENTO = {"pix": "Pix", "boleto": "Boleto", "cartao_credito": "Cartão de crédito", "cartao_debito": "Cartão de débito"}
_FUSO_BRASIL = timedelta(hours=-3)  # Brasília, sem horário de verão desde 2019: a data "de hoje" é a do cliente, não a de UTC


def hoje_no_brasil(agora: datetime | None = None) -> date:
    return ((agora or datetime.now(UTC)) + _FUSO_BRASIL).date()


def obter_config(db: Session, tenant_id: str) -> ConfiguracaoPreReserva | None:
    return db.get(ConfiguracaoPreReserva, tenant_id)


def salvar_config(db: Session, tenant_id: str, ator_id: str | None, dados: dict) -> ConfiguracaoPreReserva:
    dados = dict(dados)
    dados["datas_disponiveis"] = sorted({d.isoformat() if isinstance(d, date) else str(d) for d in dados.get("datas_disponiveis", [])})
    config = obter_config(db, tenant_id)
    if config is None:
        config = ConfiguracaoPreReserva(tenant_id=tenant_id, **dados)
        db.add(config)
    else:
        for campo, valor in dados.items():
            setattr(config, campo, valor)
    auditoria_service.registrar(db, tenant_id, "pre_reserva_config_salva", "configuracao_pre_reserva", 0, ator_id, {"titulo": dados.get("titulo")})
    db.commit()
    db.refresh(config)
    return config


def _datas_ocupadas(db: Session, tenant_id: str) -> set[date]:
    linhas = db.query(PreReserva.data_evento).filter(PreReserva.tenant_id == tenant_id, PreReserva.status != "cancelada").all()
    return {linha[0] for linha in linhas}


def datas_livres(db: Session, config: ConfiguracaoPreReserva, hoje: date | None = None) -> list[date]:
    primeira_possivel = (hoje or hoje_no_brasil()) + timedelta(days=config.antecedencia_minima_dias)
    ocupadas = _datas_ocupadas(db, config.tenant_id)
    datas = sorted({date.fromisoformat(str(d)) for d in (config.datas_disponiveis or [])})
    return [d for d in datas if d >= primeira_possivel and d not in ocupadas]


def _config_publica(db: Session, codigo: str) -> ConfiguracaoPreReserva:
    tenant_id = link_captura_lead_service.resolver_tenant_por_codigo(db, codigo)  # também troca o RLS para o tenant dono do link
    config = obter_config(db, tenant_id)
    if config is None or not config.ativo:
        raise NaoEncontrado("Formulário de pré-reserva não encontrado.")
    return config


def info_publica(db: Session, codigo: str, hoje: date | None = None) -> dict:
    config = _config_publica(db, codigo)
    return {
        "marca": config.marca,
        "titulo": config.titulo,
        "descricao": config.descricao,
        "site": config.site,
        "datas_livres": datas_livres(db, config, hoje),
        "antecedencia_minima_dias": config.antecedencia_minima_dias,
        "horas_pre_reserva": config.horas_pre_reserva,
        "valor_presencial": config.valor_presencial,
        "valor_online": config.valor_online,
        "percentual_sinal": config.percentual_sinal,
        "formas_pagamento": list(config.formas_pagamento or []),
        "condicao_especial": config.condicao_especial,
    }


def _moeda(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def criar_pre_reserva_publica(db: Session, codigo: str, dados, agora: datetime | None = None) -> PreReserva:
    agora = agora or datetime.now(UTC)
    config = _config_publica(db, codigo)
    tenant_id = config.tenant_id

    if not dados.aceite_contato:
        raise ValidacaoFalhou("Para reservar, autorize o contato sobre esta pré-reserva.")
    if dados.data_evento not in datas_livres(db, config, hoje_no_brasil(agora)):
        raise RegraNegocioViolada("Essa data não está mais disponível. Escolha outra data da lista.")
    valor = config.valor_presencial if dados.formato == "presencial" else config.valor_online
    if valor is None:
        raise ValidacaoFalhou(f"O formato {dados.formato} não está disponível.")
    if dados.formato == "presencial" and not (dados.cidade or "").strip():
        raise ValidacaoFalhou("Informe a cidade do evento.")
    if config.formas_pagamento and dados.forma_pagamento not in config.formas_pagamento:
        raise ValidacaoFalhou("Escolha uma das formas de pagamento disponíveis.")

    conta = conta_service.criar_a_partir_de_convite_rede_social(
        db, tenant_id, dados.nome_empresa.strip(), dados.cnpj, dados.nome_contato.strip(), dados.email_contato.strip(),
        telefone_contato=dados.telefone_contato.strip(), cargo_contato=(dados.cargo_contato or "").strip() or None,
        origem=ORIGEM, descricao_atividade=f"Empresa cadastrada pelo formulário público de pré-reserva ({config.titulo})",
    )
    decisor = db.query(Decisor).filter_by(tenant_id=tenant_id, conta_id=conta.id).order_by(Decisor.id).first()

    data_br = dados.data_evento.strftime("%d/%m/%Y")
    estagios = crm_service.garantir_estagios_padrao(db, tenant_id)
    primeiro_aberto = next((e for e in estagios if e.tipo == "aberto"), estagios[0])
    negocio = Negocio(
        tenant_id=tenant_id, conta_id=conta.id, decisor_id=decisor.id, estagio_id=primeiro_aberto.id,
        nome=f"{config.titulo} – {conta.nome} – {data_br} ({dados.formato})", valor=float(valor), probabilidade=50, origem=ORIGEM,
    )
    db.add(negocio)
    db.flush()

    expira_em = (agora + timedelta(hours=config.horas_pre_reserva)).replace(tzinfo=None)
    pre_reserva = PreReserva(
        tenant_id=tenant_id, conta_id=conta.id, decisor_id=decisor.id, negocio_id=negocio.id, data_evento=dados.data_evento,
        formato=dados.formato, cidade=(dados.cidade or "").strip() or None, participantes=dados.participantes,
        forma_pagamento=dados.forma_pagamento, observacoes=(dados.observacoes or "").strip() or None, valor=float(valor),
        status="pre_reservada", expira_em=expira_em,
    )
    db.add(pre_reserva)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise RegraNegocioViolada("Essa data acabou de ser reservada por outra empresa. Escolha outra data da lista.") from None

    sinal = float(valor) * config.percentual_sinal / 100
    detalhes = [
        f"Pré-reserva de {data_br} ({dados.formato}{', ' + pre_reserva.cidade if pre_reserva.cidade else ''})",
        f"valor {_moeda(float(valor))}, sinal {_moeda(sinal)}",
        f"pagamento preferido: {NOMES_PAGAMENTO.get(dados.forma_pagamento, dados.forma_pagamento)}",
        f"prazo sem custo até {(expira_em + _FUSO_BRASIL).strftime('%d/%m/%Y %H:%M')} (Brasília)",
    ]
    if dados.participantes:
        detalhes.append(f"{dados.participantes} participantes")
    if pre_reserva.observacoes:
        detalhes.append(f"observações: {pre_reserva.observacoes}")
    atividade_service.registrar(db, tenant_id, conta_id=conta.id, negocio_id=negocio.id, tipo="sistema", descricao="; ".join(detalhes) + ".")
    auditoria_service.registrar(
        db, tenant_id, "negocio_criado", "negocio", negocio.id, None, {"conta_id": conta.id, "origem": ORIGEM}, conta_id=conta.id
    )
    eventos.publicar(
        db, eventos.TipoEvento.OPPORTUNITY_CREATED, tenant_id, "negocio", negocio.id,
        {"conta_id": conta.id, "valor": negocio.valor, "estagio_id": negocio.estagio_id, "origem": ORIGEM},
    )
    db.commit()
    db.refresh(pre_reserva)
    return pre_reserva


def listar(db: Session, tenant_id: str) -> list[dict]:
    linhas = (
        db.query(PreReserva, Conta.nome, Decisor.nome)
        .join(Conta, Conta.id == PreReserva.conta_id)
        .join(Decisor, Decisor.id == PreReserva.decisor_id)
        .filter(PreReserva.tenant_id == tenant_id)
        .order_by(PreReserva.data_evento)
        .all()
    )
    return [
        {**{c: getattr(p, c) for c in (
            "id", "conta_id", "negocio_id", "data_evento", "formato", "cidade", "participantes", "forma_pagamento",
            "observacoes", "valor", "status", "expira_em", "criado_em",
        )}, "nome_empresa": nome_conta, "nome_contato": nome_contato}
        for p, nome_conta, nome_contato in linhas
    ]


def alterar_status(db: Session, tenant_id: str, ator_id: str | None, pre_reserva_id: int, status: str) -> PreReserva:
    pre_reserva = db.query(PreReserva).filter_by(id=pre_reserva_id, tenant_id=tenant_id).one_or_none()
    if pre_reserva is None:
        raise NaoEncontrado("Pré-reserva não encontrada.")
    if pre_reserva.status == "cancelada":
        raise RegraNegocioViolada("Pré-reserva cancelada não volta: a data já foi devolvida para a agenda. Peça uma nova pré-reserva.")
    if pre_reserva.status == status:
        return pre_reserva
    pre_reserva.status = status
    data_br = pre_reserva.data_evento.strftime("%d/%m/%Y")
    descricao = (
        f"Sinal pago: data de {data_br} confirmada." if status == "confirmada"
        else f"Pré-reserva de {data_br} cancelada: a data voltou para a agenda."
    )
    atividade_service.registrar(
        db, tenant_id, conta_id=pre_reserva.conta_id, negocio_id=pre_reserva.negocio_id, tipo="sistema", descricao=descricao, ator_id=ator_id
    )
    auditoria_service.registrar(db, tenant_id, f"pre_reserva_{status}", "pre_reserva", pre_reserva.id, ator_id, {"data": data_br}, conta_id=pre_reserva.conta_id)
    db.commit()
    db.refresh(pre_reserva)
    return pre_reserva
