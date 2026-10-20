"""Histórico das coletas de site (enriquecimento): consulta, detalhe com fontes/indicadores e validação manual do domínio.

Toda consulta filtra por `tenant_id` do usuário autenticado; um id de outro tenant é "não encontrado". Nada aqui chama IA."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.coleta_site import ColetaSiteConta, IndicadorFinanceiroConta
from app.models.conta import Conta
from app.models.conteudo_pagina_site import ConteudoPaginaSite
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

_MENSAGEM_SEM_FINANCEIRO = (
    "Nenhum indicador financeiro público foi encontrado nas páginas coletadas. Isso não indica resultado negativo: a empresa "
    "pode não divulgar esses dados, ou eles podem estar em documentos (como PDFs de relações com investidores) que esta coleta não lê."
)
_MENSAGEM_DOMINIO_DIVERGENTE = "Indicadores não avaliados: o domínio exibe outro CNPJ e não foi confirmado como o da empresa."
_PREVIA_CARACTERES = 300


def obter(db: Session, tenant_id: str, coleta_id: int) -> ColetaSiteConta:
    coleta = db.query(ColetaSiteConta).filter_by(id=coleta_id, tenant_id=tenant_id).one_or_none()
    if coleta is None:
        raise NaoEncontrado(f"Coleta {coleta_id} não encontrada")
    return coleta


def _ultimas_bem_sucedidas(db: Session, tenant_id: str, conta_ids: set[int]) -> dict[int, datetime]:
    if not conta_ids:
        return {}
    linhas = (
        db.query(ColetaSiteConta.conta_id, ColetaSiteConta.concluida_em)
        .filter(ColetaSiteConta.tenant_id == tenant_id, ColetaSiteConta.conta_id.in_(conta_ids),
                ColetaSiteConta.estado.in_(("concluida", "concluida_sem_ia")), ColetaSiteConta.concluida_em.isnot(None))
        .all()
    )
    ultimas: dict[int, datetime] = {}
    for conta_id, concluida_em in linhas:
        if conta_id not in ultimas or concluida_em > ultimas[conta_id]:
            ultimas[conta_id] = concluida_em
    return ultimas


def listar(db: Session, tenant_id: str, conta_id: int | None = None, estado: str | None = None, limite: int = 50) -> list[dict]:
    consulta = db.query(ColetaSiteConta).filter_by(tenant_id=tenant_id)
    if conta_id is not None:
        consulta = consulta.filter_by(conta_id=conta_id)
    if estado:
        consulta = consulta.filter_by(estado=estado)
    coletas = consulta.order_by(ColetaSiteConta.id.desc()).limit(max(1, min(limite, 200))).all()
    contas = {c.id: c.nome for c in db.query(Conta.id, Conta.nome).filter(Conta.tenant_id == tenant_id, Conta.id.in_({c.conta_id for c in coletas})).all()} if coletas else {}
    quantidade = {}
    if coletas:
        for coleta_id, in db.query(IndicadorFinanceiroConta.coleta_id).filter(
            IndicadorFinanceiroConta.tenant_id == tenant_id, IndicadorFinanceiroConta.coleta_id.in_([c.id for c in coletas])
        ).all():
            quantidade[coleta_id] = quantidade.get(coleta_id, 0) + 1
    ultimas = _ultimas_bem_sucedidas(db, tenant_id, {c.conta_id for c in coletas})
    return [
        {
            "id": c.id, "conta_id": c.conta_id, "conta_nome": contas.get(c.conta_id), "dominio": c.dominio, "disparo": c.disparo,
            "reprocesso_de_id": c.reprocesso_de_id, "estado": c.estado, "iniciada_em": c.iniciada_em, "concluida_em": c.concluida_em,
            "paginas": c.paginas, "dominio_situacao": c.dominio_situacao, "financeiro_estado": c.financeiro_estado,
            "indicadores": quantidade.get(c.id, 0), "erro": c.erro, "avisos": len(c.avisos or []),
            "ultima_coleta_bem_sucedida_da_conta": ultimas.get(c.conta_id),
        }
        for c in coletas
    ]


def _indicador_dict(i: IndicadorFinanceiroConta) -> dict:
    return {
        "id": i.id, "nome": i.nome, "tipo": i.tipo, "valor": i.valor, "moeda": i.moeda, "escala": i.escala,
        "valor_original": i.valor_original, "periodo": i.periodo, "url_fonte": i.url_fonte, "trecho": i.trecho,
        "data_publicacao": i.data_publicacao, "coletado_em": i.coletado_em, "metodo_extracao": i.metodo_extracao,
        "confianca": i.confianca, "estado_validacao": i.estado_validacao, "formula": i.formula, "origens": i.origens or [],
    }


def detalhe(db: Session, tenant_id: str, coleta_id: int) -> dict:
    coleta = obter(db, tenant_id, coleta_id)
    conta = db.query(Conta).filter_by(id=coleta.conta_id, tenant_id=tenant_id).one_or_none()
    indicadores = (
        db.query(IndicadorFinanceiroConta).filter_by(tenant_id=tenant_id, coleta_id=coleta.id)
        .order_by(IndicadorFinanceiroConta.tipo, IndicadorFinanceiroConta.nome, IndicadorFinanceiroConta.periodo).all()
    )
    conteudos = {
        p.url: p for p in db.query(ConteudoPaginaSite).filter_by(tenant_id=tenant_id, conta_id=coleta.conta_id).all()
    }
    if coleta.financeiro_estado == "nao_encontrado":
        mensagem = _MENSAGEM_SEM_FINANCEIRO
    elif coleta.financeiro_estado == "nao_avaliado_dominio_divergente":
        mensagem = _MENSAGEM_DOMINIO_DIVERGENTE
    else:
        mensagem = None
    base = listar(db, tenant_id, conta_id=coleta.conta_id, limite=200)
    ultima = next((i["ultima_coleta_bem_sucedida_da_conta"] for i in base), None)
    return {
        "id": coleta.id, "conta_id": coleta.conta_id, "conta_nome": conta.nome if conta else None, "dominio": coleta.dominio,
        "disparo": coleta.disparo, "reprocesso_de_id": coleta.reprocesso_de_id, "estado": coleta.estado,
        "iniciada_em": coleta.iniciada_em, "concluida_em": coleta.concluida_em, "paginas": coleta.paginas,
        "fontes": coleta.fontes or [], "resumo": coleta.resumo, "erro": coleta.erro, "avisos": coleta.avisos or [],
        "ultima_coleta_bem_sucedida_da_conta": ultima,
        "dominio_verificacao": {
            "origem": coleta.dominio_origem, "situacao": coleta.dominio_situacao, "pontuacao": coleta.dominio_pontuacao,
            "evidencias": coleta.dominio_evidencias or [], "limitacoes": coleta.dominio_limitacoes or [],
            "validado_por": coleta.dominio_validado_por, "validado_em": coleta.dominio_validado_em,
            "exige_validacao_manual": coleta.dominio_situacao in ("provavel", "inconclusivo", "divergente"),
        },
        "financeiro": {"estado": coleta.financeiro_estado, "mensagem": mensagem, "indicadores": [_indicador_dict(i) for i in indicadores]},
        "paginas_coletadas": [
            {"url": url, "coletado_em": conteudos[url].coletado_em if url in conteudos else None,
             "caracteres": len(conteudos[url].conteudo) if url in conteudos else None,
             "previa": conteudos[url].conteudo[:_PREVIA_CARACTERES] if url in conteudos else None}
            for url in (coleta.fontes or [])
        ],
        "observacao_paginas": "O conteúdo mostrado é o da última coleta de cada página.",
    }


def confirmar_dominio(db: Session, tenant_id: str, ator_id: str | None, coleta_id: int) -> ColetaSiteConta:
    """Validação manual: uma pessoa confirma que o domínio é o da empresa. Vale para as próximas coletas do mesmo domínio.
    Não apaga a situação automática original: ela continua nas evidências; a nova situação fica registrada com autor e data."""
    coleta = obter(db, tenant_id, coleta_id)
    if coleta.dominio_situacao not in ("provavel", "inconclusivo", "divergente"):
        raise RegraNegocioViolada("Só domínios provável, inconclusivo ou divergente precisam de validação manual.")
    if not coleta.dominio:
        raise RegraNegocioViolada("Esta coleta não tem domínio para confirmar.")
    anterior = coleta.dominio_situacao
    coleta.dominio_situacao = "confirmado_manualmente"
    coleta.dominio_validado_por, coleta.dominio_validado_em = ator_id, datetime.now(UTC)
    coleta.avisos = [a for a in (coleta.avisos or []) if not a.startswith("Domínio não confirmado")]
    conta = db.query(Conta).filter_by(id=coleta.conta_id, tenant_id=tenant_id).one_or_none()
    if conta is not None and not conta.dominio:
        conta.dominio = coleta.dominio
    auditoria_service.registrar(
        db, tenant_id, "dominio_confirmado_manualmente", "coleta_site_conta", coleta.id, ator_id,
        {"dominio": coleta.dominio, "situacao_anterior": anterior}, conta_id=coleta.conta_id,
    )
    db.commit()
    db.refresh(coleta)
    return coleta
