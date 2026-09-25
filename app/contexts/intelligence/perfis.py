"""Company Intelligence e User Intelligence (Fase 4, §16, §59).

Consolidação de memória DETERMINÍSTICA (classe C0, sem LLM): transforma
histórico volumoso em um perfil estruturado, com a proveniência e o
tamanho de amostra de cada campo. Nenhum campo é preenchido sem dado;
abaixo da amostra mínima o valor é `None` (mesma regra de
`calcular_padroes_observados`).
"""

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.aprovacao import Aprovacao
from app.models.configuracao_comunicacao import ConfiguracaoComunicacao
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.models.oferta import Oferta
from app.models.perfil_inteligencia import PerfilInteligencia
from app.models.regra_aprendida import RegraAprendida
from app.services import metricas_service

AMOSTRA_MINIMA = 5


def _taxa(parte: int, total: int) -> float | None:
    return round(parte / total, 3) if total >= AMOSTRA_MINIMA else None


def _salvar(db: Session, tenant_id: str, escopo: str, usuario_id: int | None, dados: dict, fontes: dict) -> PerfilInteligencia:
    perfil = db.query(PerfilInteligencia).filter_by(tenant_id=tenant_id, escopo=escopo, usuario_id=usuario_id).one_or_none()
    if perfil is None:
        perfil = PerfilInteligencia(tenant_id=tenant_id, escopo=escopo, usuario_id=usuario_id, versao=0)
        db.add(perfil)
    perfil.dados = dados
    perfil.fontes = fontes
    perfil.versao = (perfil.versao or 0) + 1
    perfil.atualizado_em = datetime.now(UTC)
    db.commit()
    db.refresh(perfil)
    return perfil


def _decisoes(db: Session, tenant_id: str, aprovador_id: str | None = None) -> Counter:
    query = db.query(Aprovacao.status).filter(Aprovacao.tenant_id == tenant_id, Aprovacao.status != "pendente")
    if aprovador_id is not None:
        query = query.filter(Aprovacao.aprovador_id == aprovador_id)
    return Counter(status for (status,) in query.all())


def consolidar_empresa(db: Session, tenant_id: str) -> PerfilInteligencia:
    decisoes = _decisoes(db, tenant_id)
    total = sum(decisoes.values())
    config = db.query(ConfiguracaoComunicacao).filter_by(tenant_id=tenant_id).one_or_none()
    ofertas = db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).all()
    icps = db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).all()
    regras = db.query(RegraAprendida).filter_by(tenant_id=tenant_id).all()
    canais = Counter(canal for (canal,) in db.query(Mensagem.canal).filter(Mensagem.tenant_id == tenant_id, Mensagem.status == "enviado").all())
    padroes = metricas_service.calcular_padroes_observados(db, tenant_id)

    dados = {
        "tom_comunicacao": config.tom if config else None,
        "restricoes_comunicacao": list(config.restricoes or []) if config else [],
        "ofertas_ativas": [o.nome for o in ofertas],
        "icps_ativos": [i.nome for i in icps],
        "regras_aprendidas": len(regras),
        "taxa_aprovacao_sem_edicao_ia": _taxa(decisoes.get("aprovado", 0), total),
        "taxa_rejeicao_ia": _taxa(decisoes.get("rejeitado", 0), total),
        "canais_mais_usados": [canal for canal, _ in canais.most_common(3)] if sum(canais.values()) >= AMOSTRA_MINIMA else None,
        "padroes_observados": padroes,
    }
    fontes = {
        "tom_comunicacao": "configuracao_comunicacao",
        "ofertas_ativas": f"oferta (n={len(ofertas)})",
        "icps_ativos": f"icp (n={len(icps)})",
        "taxa_aprovacao_sem_edicao_ia": f"aprovacao decidida (n={total}, mínimo {AMOSTRA_MINIMA})",
        "canais_mais_usados": f"mensagem enviada (n={sum(canais.values())})",
        "padroes_observados": "metricas_service.calcular_padroes_observados (correlação observada, não causal)",
    }
    return _salvar(db, tenant_id, "empresa", None, dados, fontes)


def consolidar_usuario(db: Session, tenant_id: str, usuario_id: int) -> PerfilInteligencia:
    decisoes = _decisoes(db, tenant_id, aprovador_id=str(usuario_id))
    total = sum(decisoes.values())
    dados = {
        "decisoes_de_aprovacao": total,
        "taxa_edita_antes_de_aprovar": _taxa(decisoes.get("editado", 0), total),
        "taxa_rejeita": _taxa(decisoes.get("rejeitado", 0), total),
    }
    fontes = {"decisoes_de_aprovacao": f"aprovacao com aprovador_id={usuario_id} (n={total}, mínimo {AMOSTRA_MINIMA})"}
    return _salvar(db, tenant_id, "usuario", usuario_id, dados, fontes)


def obter(db: Session, tenant_id: str, escopo: str, usuario_id: int | None = None) -> PerfilInteligencia | None:
    return db.query(PerfilInteligencia).filter_by(tenant_id=tenant_id, escopo=escopo, usuario_id=usuario_id).one_or_none()
