import csv
import io
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.configuracao_painel import ConfiguracaoPainel
from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.qualificacao import QualificacaoScore
from app.models.reuniao import Reuniao

_PERIODO_PADRAO_DIAS = 30
ALERTA_BAIXO_USO_LIMIAR = 0.5


def _mes_anterior(mes: str) -> str:
    ano, mes_num = (int(parte) for parte in mes.split("-"))
    if mes_num == 1:
        return f"{ano - 1}-12"
    return f"{ano}-{mes_num - 1:02d}"


def obter_meta(db: Session, tenant_id: str) -> ConfiguracaoPainel | None:
    return db.query(ConfiguracaoPainel).filter_by(tenant_id=tenant_id).one_or_none()


def definir_meta(db: Session, tenant_id: str, meta_mensal_reunioes: int | None) -> ConfiguracaoPainel:
    config = obter_meta(db, tenant_id)
    if config is None:
        config = ConfiguracaoPainel(tenant_id=tenant_id, meta_mensal_reunioes=meta_mensal_reunioes)
        db.add(config)
    else:
        config.meta_mensal_reunioes = meta_mensal_reunioes
    db.commit()
    db.refresh(config)
    return config


def metrica_norte(db: Session, tenant_id: str, mes: str | None = None) -> dict:
    """Métrica-norte (reuniões qualificadas realizadas/mês), com fonte
    exclusiva nos registros automáticos do CRM (E8-H1).

    Toda `Reuniao` com status além de `horarios_propostos` só existe porque
    passou pela guarda de registro no CRM em `reuniao_service.confirmar`
    (Onda 3) — a fonte é estruturalmente exclusiva do CRM, não apenas por
    convenção. "Qualificada" exige a confirmação humana de 1 toque
    (`qualificada_confirmada`, E6-H3), não apenas o agendamento.
    """
    mes_atual = mes or date.today().strftime("%Y-%m")
    mes_ant = _mes_anterior(mes_atual)

    realizadas = (
        db.query(Reuniao)
        .filter_by(tenant_id=tenant_id, status="realizada", qualificada_confirmada=True)
        .all()
    )
    valor_mes_atual = sum(1 for r in realizadas if r.horario_confirmado and r.horario_confirmado.strftime("%Y-%m") == mes_atual)
    valor_mes_anterior = sum(1 for r in realizadas if r.horario_confirmado and r.horario_confirmado.strftime("%Y-%m") == mes_ant)

    variacao_percentual = None
    if valor_mes_anterior > 0:
        variacao_percentual = ((valor_mes_atual - valor_mes_anterior) / valor_mes_anterior) * 100

    config = obter_meta(db, tenant_id)
    meta = config.meta_mensal_reunioes if config else None

    return {
        "mes_atual": mes_atual,
        "valor_mes_atual": valor_mes_atual,
        "meta": meta,
        "valor_mes_anterior": valor_mes_anterior,
        "variacao_percentual": variacao_percentual,
    }


def ranking_assinantes(db: Session) -> list[dict]:
    """Ranking de assinantes por atingimento da métrica-norte, com alerta
    de baixo uso — visão cross-tenant do Admin B2B ON, sem `X-Tenant-Id`
    (E8-H3).

    Retorna só campos agregados (`tenant_id`, valor, meta, atingimento,
    alerta) — nenhum dado de conta/decisor/mensagem atravessa esta função,
    o que torna o isolamento entre assinantes estrutural, verificável por
    teste, não apenas convencional.
    """
    tenant_ids = {tid for (tid,) in db.query(Conta.tenant_id).distinct().all()}
    tenant_ids |= {tid for (tid,) in db.query(ConfiguracaoPainel.tenant_id).distinct().all()}

    ranking = []
    for tenant_id in sorted(tenant_ids):
        dados = metrica_norte(db, tenant_id)
        meta = dados["meta"]
        atingimento = dados["valor_mes_atual"] / meta if meta else None
        alerta_baixo_uso = meta is not None and (atingimento is None or atingimento < ALERTA_BAIXO_USO_LIMIAR)
        ranking.append(
            {
                "tenant_id": tenant_id,
                "valor_mes_atual": dados["valor_mes_atual"],
                "meta": meta,
                "atingimento": atingimento,
                "alerta_baixo_uso": alerta_baixo_uso,
            }
        )

    ranking.sort(key=lambda item: (item["atingimento"] is None, -(item["atingimento"] or 0)))
    return ranking


def distribuicao_nps(db: Session, tenant_id: str) -> dict:
    """Distribuição promotor/neutro/detrator, visível no painel (E11-H1)."""
    contas = (
        db.query(Conta).filter(Conta.tenant_id == tenant_id, Conta.nps_classificacao.isnot(None)).all()
    )
    resultado = {"promotor": 0, "neutro": 0, "detrator": 0}
    for conta in contas:
        resultado[conta.nps_classificacao] += 1
    return resultado


def periodo_padrao(data_inicio: date | None, data_fim: date | None) -> tuple[date, date]:
    fim = data_fim or date.today()
    inicio = data_inicio or (fim - timedelta(days=_PERIODO_PADRAO_DIAS))
    return inicio, fim


def _no_periodo(momento, inicio: date, fim: date) -> bool:
    if momento is None:
        return False
    return inicio <= momento.date() <= fim


def indicadores_energia(db: Session, tenant_id: str, data_inicio: date | None, data_fim: date | None) -> dict:
    """Indicadores de energia por canal (E8-H2): resposta, qualificação,
    tempo até a 1ª reunião e origem da oportunidade."""
    inicio, fim = periodo_padrao(data_inicio, data_fim)

    mensagens_enviadas = (
        db.query(Mensagem)
        .filter(Mensagem.tenant_id == tenant_id, Mensagem.status == "enviado")
        .all()
    )
    decisores_por_canal: dict[str, set[int]] = {}
    for mensagem in mensagens_enviadas:
        if not _no_periodo(mensagem.enviado_em, inicio, fim):
            continue
        decisores_por_canal.setdefault(mensagem.canal, set()).add(mensagem.decisor_id)

    taxa_resposta_por_canal: dict[str, float] = {}
    for canal, decisor_ids in decisores_por_canal.items():
        respondentes = (
            db.query(Decisor).filter(Decisor.id.in_(decisor_ids), Decisor.ultima_interacao_em.isnot(None)).count()
        )
        taxa_resposta_por_canal[canal] = respondentes / len(decisor_ids)

    conversas = (
        db.query(ConversaQualificacao)
        .filter(ConversaQualificacao.tenant_id == tenant_id)
        .all()
    )
    conversas_no_periodo = [c for c in conversas if _no_periodo(c.criado_em, inicio, fim)]
    conversa_ids_no_periodo = {c.id for c in conversas_no_periodo}
    scores_qualificados = (
        db.query(QualificacaoScore)
        .filter(
            QualificacaoScore.tenant_id == tenant_id,
            QualificacaoScore.conversa_id.in_(conversa_ids_no_periodo),
            QualificacaoScore.score_total >= QualificacaoScore.limiar_configurado,
        )
        .all()
        if conversa_ids_no_periodo
        else []
    )
    conversas_qualificadas = {s.conversa_id for s in scores_qualificados}
    taxa_qualificacao = len(conversas_qualificadas) / len(conversas_no_periodo) if conversas_no_periodo else 0.0

    reunioes = db.query(Reuniao).filter_by(tenant_id=tenant_id).all()
    primeira_reuniao_por_conta: dict[int, Reuniao] = {}
    for reuniao in reunioes:
        if not _no_periodo(reuniao.criado_em, inicio, fim):
            continue
        atual = primeira_reuniao_por_conta.get(reuniao.conta_id)
        if atual is None or reuniao.criado_em < atual.criado_em:
            primeira_reuniao_por_conta[reuniao.conta_id] = reuniao

    tempos_horas = []
    for conta_id, reuniao in primeira_reuniao_por_conta.items():
        conta = db.query(Conta).filter_by(id=conta_id).one_or_none()
        if conta is None:
            continue
        delta = reuniao.criado_em - conta.criado_em
        tempos_horas.append(delta.total_seconds() / 3600)
    tempo_medio_ate_primeira_reuniao_horas = sum(tempos_horas) / len(tempos_horas) if tempos_horas else None

    return {
        "taxa_resposta_por_canal": taxa_resposta_por_canal,
        "taxa_qualificacao": taxa_qualificacao,
        "tempo_medio_ate_primeira_reuniao_horas": tempo_medio_ate_primeira_reuniao_horas,
        "origem_oportunidade": origem_oportunidade(db, tenant_id),
    }


def indicadores_atrito(db: Session, tenant_id: str, data_inicio: date | None, data_fim: date | None) -> dict:
    """Indicadores de atrito (E8-H2): no-show e tempo parado entre estágios."""
    inicio, fim = periodo_padrao(data_inicio, data_fim)

    reunioes = (
        db.query(Reuniao)
        .filter(Reuniao.tenant_id == tenant_id, Reuniao.status.in_(["realizada", "no_show"]))
        .all()
    )
    reunioes_no_periodo = [r for r in reunioes if _no_periodo(r.criado_em, inicio, fim)]
    no_show = sum(1 for r in reunioes_no_periodo if r.status == "no_show")
    taxa_no_show = no_show / len(reunioes_no_periodo) if reunioes_no_periodo else None

    conversas_em_andamento = (
        db.query(ConversaQualificacao)
        .filter_by(tenant_id=tenant_id, status="em_andamento")
        .all()
    )
    conversas_no_periodo = [c for c in conversas_em_andamento if _no_periodo(c.criado_em, inicio, fim)]
    tempos_horas = [(c.atualizado_em - c.criado_em).total_seconds() / 3600 for c in conversas_no_periodo]
    tempo_medio_parado_entre_estagios_horas = sum(tempos_horas) / len(tempos_horas) if tempos_horas else None

    return {
        "taxa_no_show": taxa_no_show,
        "tempo_medio_parado_entre_estagios_horas": tempo_medio_parado_entre_estagios_horas,
    }


def origem_oportunidade(db: Session, tenant_id: str) -> dict:
    """Prospecção ativa vs. indicação (E8-H2).

    Contas nascidas de prospecção ativa (`conta_service.gerar_lista`) nunca
    setam `origem`; `indicacao_service.converter` (E11-H3) grava
    `Conta.origem = "indicacao"` quando a indicação vira negócio — esta
    função já foi desenhada para ler isso sem alteração de código.
    """
    contas = db.query(Conta).filter_by(tenant_id=tenant_id).all()
    resultado = {"prospeccao_ativa": 0, "indicacao": 0}
    for conta in contas:
        chave = "indicacao" if conta.origem == "indicacao" else "prospeccao_ativa"
        resultado[chave] += 1
    return resultado


def exportar_csv(db: Session, tenant_id: str, data_inicio: date | None, data_fim: date | None) -> str:
    energia = indicadores_energia(db, tenant_id, data_inicio, data_fim)
    atrito = indicadores_atrito(db, tenant_id, data_inicio, data_fim)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["indicador", "valor"])
    for canal, taxa in energia["taxa_resposta_por_canal"].items():
        writer.writerow([f"taxa_resposta_{canal}", taxa])
    writer.writerow(["taxa_qualificacao", energia["taxa_qualificacao"]])
    writer.writerow(["tempo_medio_ate_primeira_reuniao_horas", energia["tempo_medio_ate_primeira_reuniao_horas"]])
    for origem, quantidade in energia["origem_oportunidade"].items():
        writer.writerow([f"origem_{origem}", quantidade])
    writer.writerow(["taxa_no_show", atrito["taxa_no_show"]])
    writer.writerow(
        ["tempo_medio_parado_entre_estagios_horas", atrito["tempo_medio_parado_entre_estagios_horas"]]
    )
    return buffer.getvalue()
