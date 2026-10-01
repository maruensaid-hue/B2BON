"""Fachada do MAP Performance (D-080): permissões, painéis individual e de equipe, Daily Comercial e configuração.

Permissões: o gestor comercial da CyberFort é o `super_admin` (vê todos os representantes ativos — o número
não é fixo —, a equipe, o Daily e a configuração). Um usuário vinculado a um representante (`Representante.usuario_id`) vê só o próprio painel; os dados de
CRM lidos são sempre os do tenant desse usuário (isolamento por tenant). Qualquer outro usuário recebe 403.
"""

from copy import deepcopy
from datetime import date

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.contexts.map.performance import configuracao, inteligencia, painel, receita
from app.contexts.map.performance.tipos import TIPOS_ATIVIDADE_HUMANA, Familia
from app.models.oferta import Oferta
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
            "configuracao_pendente": prontidao(db)["pendencias"],
            "aprendizado": dados["aprendizado"]["equipe"], "campanhas": dados["campanhas"]}


def daily_comercial(db: Session, usuario: Usuario, competencia: str, hoje: date) -> dict:
    _exigir_gestor(usuario)
    _validar_competencia(competencia)
    dados = painel.calcular(db, _ativos(db), competencia, hoje)
    intervencoes = inteligencia.daily(dados["paineis"], configuracao.performance(db))
    return {"data": hoje, "competencia": competencia, "equipe": dados["equipe"], "intervencoes": intervencoes,
            "sem_intervencao": len(dados["paineis"]) - len(intervencoes), "configuracao_pendente": prontidao(db)["pendencias"]}


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
            "representantes": [{"id": r.id, "nome": r.nome, "usuario_id": r.usuario_id} for r in _ativos(db)],
            "prontidao": prontidao(db),
            "familias": [f.value for f in Familia if f != Familia.NAO_CLASSIFICADA],
            "tipos_atividade": list(TIPOS_ATIVIDADE_HUMANA)}


def _tenants_operadores(db: Session) -> list[str]:
    """Tenants dos usuários vinculados aos representantes ativos (o CRM de onde o MAP lê)."""
    ids = [r.usuario_id for r in _ativos(db) if r.usuario_id]
    return sorted({t for (t,) in db.query(Usuario.tenant_id).filter(Usuario.id.in_(ids)).all()}) if ids else []


def _ofertas(db: Session) -> list[Oferta]:
    tenants = _tenants_operadores(db)
    return (db.query(Oferta).filter(Oferta.tenant_id.in_(tenants), Oferta.ativo.is_(True)).order_by(Oferta.nome).all()) if tenants else []


def prontidao(db: Session) -> dict:
    """O que ainda falta configurar (OI-029). O time pode ter qualquer tamanho: tudo é por representante ativo."""
    regras = configuracao.performance(db)
    ativos = _ativos(db)
    usuarios = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_([r.usuario_id for r in ativos if r.usuario_id] or [-1])).all()}
    mapa = regras["familia_por_oferta"]
    ofertas = _ofertas(db)
    definicoes = regras["definicoes"]
    pendencias = []
    sem_vinculo = [{"id": r.id, "nome": r.nome} for r in ativos if r.usuario_id not in usuarios]
    if not ativos:
        pendencias.append("Cadastrar os representantes (Admin → Representantes)")
    if sem_vinculo:
        pendencias.append(f"Vincular {len(sem_vinculo)} representante(s) ao usuário do CRM")
    sem_familia = [{"id": o.id, "nome": o.nome, "tenant_id": o.tenant_id} for o in ofertas if str(o.id) not in mapa]
    if sem_familia:
        pendencias.append(f"Classificar {len(sem_familia)} oferta(s) do CRM por produto")
    if not definicoes.get("contato_efetivo_confirmado"):
        pendencias.append("Confirmar o critério de contato efetivo")
    return {"representantes_ativos": len(ativos), "vinculados": len(ativos) - len(sem_vinculo), "sem_vinculo": sem_vinculo,
            "tenants_crm": _tenants_operadores(db),
            "ofertas": [{"id": o.id, "nome": o.nome, "tenant_id": o.tenant_id, "familia": mapa.get(str(o.id))} for o in ofertas],
            "ofertas_sem_familia": sem_familia, "tipos_contato_efetivo": definicoes["tipos_contato_efetivo"],
            "contato_efetivo_confirmado": bool(definicoes.get("contato_efetivo_confirmado")), "pendencias": pendencias,
            "pronto": not pendencias}


def buscar_usuarios(db: Session, usuario: Usuario, busca: str) -> list[dict]:
    """Candidatos ao vínculo (nome ou e-mail); no máximo 20, sempre com o tenant para o gestor conferir o CRM certo."""
    _exigir_gestor(usuario)
    termo = (busca or "").strip()
    if len(termo) < 2:
        return []
    vinculados = {r.usuario_id: r.nome for r in db.query(Representante).filter(Representante.usuario_id.isnot(None)).all()}
    filtro = f"%{termo.lower()}%"
    candidatos = (db.query(Usuario).filter(Usuario.ativo.is_(True), or_(func.lower(Usuario.nome).like(filtro), func.lower(Usuario.email).like(filtro)))
                  .order_by(Usuario.nome).limit(20).all())
    return [{"id": u.id, "nome": u.nome, "email": u.email, "tenant_id": u.tenant_id, "vinculado_a": vinculados.get(u.id)} for u in candidatos]


def _nova_versao_performance(db: Session, usuario: Usuario, alterar, motivo: str) -> dict:
    regras = deepcopy(configuracao.performance(db))
    alterar(regras)
    configuracao.nova_politica(db, configuracao.CODIGO_POLITICA_PERFORMANCE, regras, motivo, str(usuario.id))
    return prontidao(db)


def classificar_ofertas(db: Session, usuario: Usuario, familias: dict[str, str | None], motivo: str) -> dict:
    """Oferta do CRM → família de produto (velocidade, mix e forecast). `None` remove a classificação."""
    _exigir_gestor(usuario)
    validas = {f.value for f in Familia if f != Familia.NAO_CLASSIFICADA}
    conhecidas = {str(o.id) for o in _ofertas(db)}
    for oferta_id, familia in familias.items():
        if str(oferta_id) not in conhecidas:
            raise ValidacaoFalhou(f"Oferta {oferta_id} não pertence ao CRM dos representantes.")
        if familia is not None and familia not in validas:
            raise ValidacaoFalhou(f"Família inválida: {familia}. Use {', '.join(sorted(validas))}.")

    def alterar(regras: dict) -> None:
        mapa = dict(regras["familia_por_oferta"])
        for oferta_id, familia in familias.items():
            if familia is None:
                mapa.pop(str(oferta_id), None)
            else:
                mapa[str(oferta_id)] = familia
        regras["familia_por_oferta"] = mapa

    return _nova_versao_performance(db, usuario, alterar, motivo)


def confirmar_contato_efetivo(db: Session, usuario: Usuario, tipos: list[str], motivo: str) -> dict:
    """Confirma (ou muda) quais ações registradas contam como contato efetivo; deixa de ser pendência."""
    _exigir_gestor(usuario)
    if not tipos or set(tipos) - set(TIPOS_ATIVIDADE_HUMANA):
        raise ValidacaoFalhou(f"Escolha ao menos um tipo entre {', '.join(TIPOS_ATIVIDADE_HUMANA)}.")

    def alterar(regras: dict) -> None:
        regras["definicoes"] = {**regras["definicoes"], "tipos_contato_efetivo": sorted(set(tipos)), "contato_efetivo_confirmado": True}

    return _nova_versao_performance(db, usuario, alterar, motivo)


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
