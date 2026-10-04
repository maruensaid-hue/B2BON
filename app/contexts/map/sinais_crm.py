"""MAP → CRM do cliente (D-087): o score de risco de churn e o nível de cada
conta-cliente vão para campos PRÓPRIOS da B2B ON na conta do CRM, e conta
que fica crítica ganha uma tarefa de resgate para o dono (no máximo uma por
conta por mês).

Mesmo cálculo da tela e da API do MAP (`saude.score_risco` sobre o modelo
canônico do CRM conectado) — nada é recalculado de outro jeito aqui. Só
enfileira quando o score ou o nível mudou desde o último envio (o CRM não
recebe a mesma escrita todo dia).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.integrations import contract as integracoes
from app.contexts.map import saude
from app.contexts.map.data_source import CanonicalMapDataSource
from app.models.conexao_integracao import ConexaoIntegracao
from app.models.integracao_crm import EnvioCrm


def _ultimo_enviado(db: Session, conexao_id: int, conta_externa: str) -> dict | None:
    envio = (
        db.query(EnvioCrm)
        .filter_by(conexao_id=conexao_id, operacao="sinais_conta", id_interno=conta_externa, status="enviado")
        .order_by(EnvioCrm.id.desc())
        .first()
    )
    return envio.payload if envio else None


def publicar(db: Session, conexao: ConexaoIntegracao, adapter: integracoes.CrmAdapter | None = None, agora: datetime | None = None) -> dict:
    escrita = integracoes.obter_escrita()
    if not escrita.config(conexao).get("map"):
        return {"contas": 0, "enfileiradas": 0, "criticas": 0}
    agora = agora or datetime.now(UTC)
    adapter = adapter or integracoes.obter_registry().obter_adapter(db, conexao)
    fonte = CanonicalMapDataSource(adapter)
    contas = [c for c in fonte.contas(conexao.tenant_id) if c.cliente_desde and not c.cliente_cancelado_em]
    resultado = {"contas": len(contas), "enfileiradas": 0, "criticas": 0}
    for conta in contas:
        risco = saude.score_risco(fonte, conta)
        externo = str(conta.id).split(":", 2)[-1]
        score, nivel = round(float(risco["score"]), 1), risco["classificacao"]
        critica = nivel == "critico"
        resultado["criticas"] += critica
        anterior = _ultimo_enviado(db, conexao.id, externo)
        if anterior and anterior.get("score_risco") == score and anterior.get("nivel_risco") == nivel:
            continue
        dias = risco.get("dias_sem_contato")
        payload = {
            "score_risco": score, "nivel_risco": nivel, "criar_tarefa": critica,
            "chave_tarefa": f"risco:{externo}:{agora:%Y-%m}", "dono_externo_id": conta.vendedor_usuario_id,
            "motivo": f"{dias} dias sem contato registrado." if dias is not None else "",
        }
        resultado["enfileiradas"] += escrita.enfileirar(db, conexao.tenant_id, "sinais_conta", externo,
                                                        chave=f"sinais_conta:{externo}:{agora:%Y-%m-%dT%H}", payload=payload, conexao_id=conexao.id)
    db.commit()
    return resultado


def rotina_diaria(db: Session) -> dict:
    """Cron diário: publica os sinais de toda conexão com MAP → CRM ligado."""
    escrita = integracoes.obter_escrita()
    resultado = {"conexoes": 0, "enfileiradas": 0, "falhas": 0}
    for conexao in db.query(ConexaoIntegracao).filter(ConexaoIntegracao.status == "ativa",
                                                      ConexaoIntegracao.sistema.in_(escrita.SISTEMAS_EXTERNOS)).all():
        if not escrita.config(conexao).get("map") or not integracoes.obter_registry().conectavel(conexao.sistema):
            continue
        try:
            parcial = publicar(db, conexao)
            resultado["conexoes"] += 1
            resultado["enfileiradas"] += parcial["enfileiradas"]
        except Exception as erro:  # noqa: BLE001 — uma conexão quebrada não para as outras
            db.rollback()
            escrita.registrar_falha_leitura(db, conexao, erro)
            resultado["falhas"] += 1
    return resultado
