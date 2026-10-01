"""Fachada do MAP Performance (D-080): permissões, painéis individual e de equipe, Daily Comercial e configuração.

Permissões: o gestor comercial da CyberFort é o `super_admin` (vê os 7 representantes, a equipe, o Daily e a
configuração). Um usuário vinculado a um representante (`Representante.usuario_id`) vê só o próprio painel; os dados de
CRM lidos são sempre os do tenant desse usuário (isolamento por tenant). Qualquer outro usuário recebe 403.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.contexts.map.performance import configuracao, inteligencia, painel, receita
from app.models.representante import Representante
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

GESTOR = "super_admin"
MAX_PIPELINE_INDIVIDUAL = 20


def representante_do_usuario(db: Session, usuario: Usuario) -> Representante | None:
    return db.query(Representante).filter_by(usuario_id=usuario.id, ativo=True).one_or_none()


def _exigir_gestor(usuario: Usuario) -> None:
    if usuario.papel != GESTOR:
        raise NaoAutorizado("Só a gestão comercial da CyberFort vê a equipe, o Daily e a configuração do MAP Performance.")


def _publico(dados: dict, pipeline_max: int = 0) -> dict:
    saida = {k: v for k, v in dados.items() if not k.startswith("_")}
    if pipeline_max:
        saida["negocios_abertos"] = [{k: n[k] for k in ("id", "nome", "conta", "valor", "probabilidade", "estagio", "familia", "velocidade",
                                                         "fechamento_previsto", "dias_sem_acao", "proximo_passo")}
                                     for n in sorted(dados["_pipeline"], key=lambda n: -n["valor_ponderado"])[:pipeline_max]]
    return saida


def acesso(db: Session, usuario: Usuario) -> dict:
    rep = representante_do_usuario(db, usuario)
    return {"gestor": usuario.papel == GESTOR, "representante_id": rep.id if rep else None,
            "pode_ver": usuario.papel == GESTOR or rep is not None}


def painel_individual(db: Session, usuario: Usuario, representante_id: int | None, competencia: str, hoje: date) -> dict:
    proprio = representante_do_usuario(db, usuario)
    if representante_id is None:
        representante_id = proprio.id if proprio else None
    if representante_id is None:
        raise NaoAutorizado("Seu usuário não está vinculado a um representante.")
    if usuario.papel != GESTOR and (proprio is None or proprio.id != representante_id):
        raise NaoAutorizado("Você só pode ver o seu próprio painel.")
    rep = db.get(Representante, representante_id)
    if rep is None:
        raise NaoEncontrado("Representante não encontrado.")
    _validar_competencia(competencia)
    dados = painel.calcular(db, [rep], competencia, hoje)
    return {**_publico(dados["paineis"][0], MAX_PIPELINE_INDIVIDUAL), "aprendizado": dados["aprendizado"]["por_representante"].get(rep.id)
            or dados["aprendizado"]["equipe"]}


def _ativos(db: Session) -> list[Representante]:
    return db.query(Representante).filter_by(ativo=True).order_by(Representante.nome).all()


def painel_equipe(db: Session, usuario: Usuario, competencia: str, hoje: date) -> dict:
    """Comparação dos representantes por attainment e indicadores operacionais (não só ranking absoluto)."""
    _exigir_gestor(usuario)
    _validar_competencia(competencia)
    dados = painel.calcular(db, _ativos(db), competencia, hoje)
    linhas = []
    for p in dados["paineis"]:
        semana = (p["atividade"] or {}).get("semana") or {}
        linhas.append({"representante": p["representante"], "quota": p["quota"], "realizado_new_mrr": p["realizado_new_mrr"],
                       "attainment": p["attainment"], "gap": p["gap"], "cobertura": p["pipeline"]["cobertura"],
                       "forecast_new_mrr": p["forecast_new_mrr"], "ticket_medio": p["ticket_medio"], "mix_quality": p["mix"]["mix_quality"],
                       "atividade_semana_pct": {k: v["pct"] for k, v in semana.items()},
                       "taxas_mes": p["taxas_mes"], "oportunidades_atualizadas_pct": p["pipeline"]["atualizadas_pct"],
                       "governo_pipeline_qualificado": p["governo"]["pipeline_qualificado"],
                       "governo_novas_semana": p["governo"]["novas_qualificadas_semana"],
                       "comissao_a_receber": p["comissao"]["a_receber"], "alertas": p["alertas"], "pendencias": p["pendencias"]})
    excecoes = [linha for linha in linhas if any(a["severidade"] in ("CRITICAL", "HIGH") for a in linha["alertas"]) or linha["pendencias"]]
    return {"competencia": competencia, "equipe": dados["equipe"], "representantes": linhas, "excecoes": excecoes,
            "aprendizado": dados["aprendizado"]["equipe"], "campanhas": dados["campanhas"]}


def daily_comercial(db: Session, usuario: Usuario, competencia: str, hoje: date) -> dict:
    _exigir_gestor(usuario)
    _validar_competencia(competencia)
    dados = painel.calcular(db, _ativos(db), competencia, hoje)
    intervencoes = inteligencia.daily(dados["paineis"], configuracao.performance(db))
    return {"data": hoje, "competencia": competencia, "equipe": dados["equipe"], "intervencoes": intervencoes,
            "sem_intervencao": len(dados["paineis"]) - len(intervencoes)}


def _validar_competencia(competencia: str) -> None:
    if not configuracao.COMPETENCIA.match(competencia or ""):
        raise ValidacaoFalhou("Competência no formato AAAA-MM.")


def vincular_usuario(db: Session, usuario: Usuario, representante_id: int, usuario_id: int | None) -> Representante:
    _exigir_gestor(usuario)
    rep = db.get(Representante, representante_id)
    if rep is None:
        raise NaoEncontrado("Representante não encontrado.")
    if usuario_id is not None:
        alvo = db.get(Usuario, usuario_id)
        if alvo is None:
            raise NaoEncontrado("Usuário não encontrado.")
        outro = db.query(Representante).filter(Representante.usuario_id == usuario_id, Representante.id != rep.id).first()
        if outro is not None:
            raise ValidacaoFalhou(f"Usuário já vinculado ao representante {outro.nome}.")
    antes = rep.usuario_id
    rep.usuario_id = usuario_id
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "representante_vinculado_crm", "representante", rep.id,
                                str(usuario.id), {"antes": antes, "depois": usuario_id})
    return rep


def configuracao_atual(db: Session, usuario: Usuario) -> dict:
    _exigir_gestor(usuario)
    performance, comissao = configuracao.politica(db, configuracao.CODIGO_POLITICA_PERFORMANCE), \
        configuracao.politica(db, configuracao.CODIGO_POLITICA_COMISSAO_PRIVADA)
    return {"performance": {"versao": performance.versao, "regras": performance.regras},
            "comissao_privada": {"versao": comissao.versao, "regras": comissao.regras},
            "campanhas": [{"codigo": c.codigo, "versao": c.versao, "regras": c.regras} for c in configuracao.campanhas(db)],
            "quotas": [configuracao.quota_dict(q) for q in configuracao.listar_quotas(db)],
            "representantes": [{"id": r.id, "nome": r.nome, "usuario_id": r.usuario_id} for r in _ativos(db)]}


def nova_politica(db: Session, usuario: Usuario, codigo: str, regras: dict, motivo: str) -> dict:
    _exigir_gestor(usuario)
    politica = configuracao.nova_politica(db, codigo, regras, motivo, str(usuario.id))
    return {"codigo": politica.codigo, "versao": politica.versao, "regras": politica.regras}


def definir_quota(db: Session, usuario: Usuario, dados: dict, motivo: str) -> dict:
    _exigir_gestor(usuario)
    if dados.get("representante_id") is not None and db.get(Representante, dados["representante_id"]) is None:
        raise NaoEncontrado("Representante não encontrado.")
    return configuracao.quota_dict(configuracao.definir_quota(db, dados, motivo, str(usuario.id)))


def tenants_com_comissao_retida(db: Session, tenant_ids: list[str], hoje: date) -> set[str]:
    """Para o repasse: clientes inadimplentes cuja comissão a pagar fica retida pela política (HOLD)."""
    return receita.tenants_inadimplentes(db, tenant_ids, hoje, configuracao.comissao_privada(db))
