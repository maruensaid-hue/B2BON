"""Need Extraction / Meeting Intelligence (Fase 6, §20-§21).

A IA lê uma transcrição (ou resumo) de reunião ou uma nota do negócio e
propõe necessidades, cada uma com a citação literal que a sustenta. O
que não tiver citação encontrada no texto é descartado antes de gravar
(grounding). Tudo nasce `sugerida`; só um humano confirma ou descarta.
Os motores determinísticos distinguem as duas coisas nas evidências.
"""

import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.intelligence.contract import ContextoIA, aprendizado, gerar, prompt_seguro
from app.contexts.opportunity import texto
from app.core.observability import correlation_id_atual
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.atividade import Atividade
from app.models.necessidade_oportunidade import CATEGORIAS, NecessidadeOportunidade
from app.models.negocio import Negocio
from app.models.reuniao import Reuniao
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

FEATURE = "opportunity.extracao_necessidades"
LIMITE_CARACTERES_FONTE = 30_000
MAXIMO_POR_EXTRACAO = 15
_TIPOS_ATIVIDADE_COM_CONTEUDO = frozenset({"reuniao", "nota", "ligacao", "email", "whatsapp"})

_SISTEMA = (
    "Você extrai necessidades de clientes B2B a partir de conversas comerciais. "
    "Responda SOMENTE com um array JSON. Cada item: "
    '{"categoria": uma de ' + ", ".join(CATEGORIAS) + ', "descricao": frase curta em português, '
    '"citacao": trecho COPIADO LITERALMENTE do texto que comprova a necessidade}. '
    "Não invente: se não houver trecho literal que comprove, não inclua o item. "
    "Categorias: dor (problema), requisito (exigência técnica/funcional), orcamento (verba, faixa, aprovação), "
    "autoridade (quem decide/aprova), prazo (quando precisa), concorrencia (alternativas avaliadas), "
    "objecao (resistência), outro. Se não houver nenhuma necessidade, responda []."
)


def _negocio(db: Session, tenant_id: str, negocio_id: int) -> Negocio:
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")
    return negocio


def _fonte(
    db: Session, tenant_id: str, negocio: Negocio, reuniao_id: int | None, atividade_id: int | None
) -> tuple[str, int, str]:
    if reuniao_id is not None and atividade_id is not None:
        raise RegraNegocioViolada("Informe a reunião ou a atividade, não as duas.")
    if atividade_id is not None:
        atividade = (
            db.query(Atividade)
            .filter(Atividade.id == atividade_id, Atividade.tenant_id == tenant_id)
            .filter((Atividade.negocio_id == negocio.id) | (Atividade.conta_id == negocio.conta_id))
            .one_or_none()
        )
        if atividade is None:
            raise NaoEncontrado(f"Atividade {atividade_id} não encontrada neste negócio")
        if atividade.tipo not in _TIPOS_ATIVIDADE_COM_CONTEUDO:
            raise RegraNegocioViolada("Esta atividade não tem conteúdo de conversa para analisar.")
        return "atividade", atividade.id, atividade.descricao

    consulta = db.query(Reuniao).filter(Reuniao.tenant_id == tenant_id, Reuniao.conta_id == negocio.conta_id)
    if reuniao_id is not None:
        reuniao = consulta.filter(Reuniao.id == reuniao_id).one_or_none()
        if reuniao is None:
            raise NaoEncontrado(f"Reunião {reuniao_id} não encontrada nesta conta")
    else:
        reuniao = (
            consulta.filter((Reuniao.transcricao.isnot(None)) | (Reuniao.resumo_ia.isnot(None)))
            .order_by(Reuniao.data_hora.desc())
            .first()
        )
        if reuniao is None:
            raise RegraNegocioViolada(
                "Nenhuma reunião desta conta tem transcrição ou resumo. Registre uma nota ou escolha uma atividade."
            )
    conteudo = reuniao.transcricao or reuniao.resumo_ia
    if not conteudo:
        raise RegraNegocioViolada("Esta reunião ainda não tem transcrição nem resumo.")
    return "reuniao", reuniao.id, conteudo


def _itens_da_resposta(conteudo: str) -> list[dict]:
    achado = re.search(r"\[.*\]", conteudo, re.DOTALL)
    if achado is None:
        raise RegraNegocioViolada("A IA respondeu fora do formato esperado. Tente novamente.")
    try:
        itens = json.loads(achado.group(0))
    except json.JSONDecodeError as erro:
        raise RegraNegocioViolada("A IA respondeu fora do formato esperado. Tente novamente.") from erro
    return [item for item in itens if isinstance(item, dict)] if isinstance(itens, list) else []


def extrair(
    db: Session,
    llm: LLMProvider,
    tenant_id: str,
    usuario_id: int | None,
    negocio_id: int,
    reuniao_id: int | None = None,
    atividade_id: int | None = None,
) -> dict:
    negocio = _negocio(db, tenant_id, negocio_id)
    fonte_tipo, fonte_id, conteudo = _fonte(db, tenant_id, negocio, reuniao_id, atividade_id)
    conteudo = conteudo[:LIMITE_CARACTERES_FONTE]

    resposta = gerar(
        db,
        llm,
        ContextoIA(
            tenant_id=tenant_id, feature=FEATURE, usuario_id=usuario_id,
            entidade_tipo="negocio", entidade_id=negocio.id,
        ),
        LLMRequest(
            system=_SISTEMA,
            prompt=prompt_seguro.bloco_dados_externos(f"{fonte_tipo} {fonte_id}", conteudo),
            max_tokens=2000,
        ),
    )

    existentes = {
        texto.normalizar(n.descricao)
        for n in db.query(NecessidadeOportunidade).filter_by(tenant_id=tenant_id, negocio_id=negocio.id).all()
    }
    criadas: list[NecessidadeOportunidade] = []
    sem_evidencia = 0
    for item in _itens_da_resposta(resposta.content)[:MAXIMO_POR_EXTRACAO]:
        descricao = str(item.get("descricao") or "").strip()[:300]
        citacao = str(item.get("citacao") or "").strip()[:1000]
        categoria = str(item.get("categoria") or "outro").strip().lower()
        if not descricao:
            continue
        if not citacao or not texto.contem_literal(conteudo, citacao):
            sem_evidencia += 1
            continue
        chave = texto.normalizar(descricao)
        if chave in existentes:
            continue
        existentes.add(chave)
        necessidade = NecessidadeOportunidade(
            tenant_id=tenant_id, negocio_id=negocio.id, conta_id=negocio.conta_id,
            categoria=categoria if categoria in CATEGORIAS else "outro",
            descricao=descricao, citacao=citacao, fonte_tipo=fonte_tipo, fonte_id=fonte_id,
            origem="ia", status="sugerida", registro_uso_ia_correlation_id=correlation_id_atual(),
            criado_por_usuario_id=usuario_id,
        )
        db.add(necessidade)
        criadas.append(necessidade)
    db.flush()

    if criadas:
        aprendizado.registrar(
            db, tenant_id, FEATURE, "GERADO", entidade_tipo="negocio", entidade_id=negocio.id,
            usuario_id=usuario_id, dados={"sugeridas": len(criadas), "sem_evidencia": sem_evidencia},
        )
    auditoria_service.registrar(
        db, tenant_id, "necessidades_extraidas", "negocio", negocio.id,
        str(usuario_id) if usuario_id is not None else None,
        {"fonte_tipo": fonte_tipo, "fonte_id": fonte_id, "sugeridas": len(criadas), "sem_evidencia": sem_evidencia},
    )
    db.commit()
    return {
        "fonte_tipo": fonte_tipo,
        "fonte_id": fonte_id,
        "sugeridas": [como_dict(n) for n in criadas],
        "descartadas_sem_evidencia": sem_evidencia,
    }


def registrar_manual(
    db: Session, tenant_id: str, usuario_id: int | None, negocio_id: int, categoria: str, descricao: str, citacao: str | None
) -> dict:
    negocio = _negocio(db, tenant_id, negocio_id)
    if categoria not in CATEGORIAS:
        raise RegraNegocioViolada(f"Categoria inválida: {categoria}")
    necessidade = NecessidadeOportunidade(
        tenant_id=tenant_id, negocio_id=negocio.id, conta_id=negocio.conta_id, categoria=categoria,
        descricao=descricao.strip()[:300], citacao=(citacao or None), fonte_tipo="manual", fonte_id=None,
        origem="manual", status="confirmada", criado_por_usuario_id=usuario_id,
        revisado_por_usuario_id=usuario_id, revisado_em=datetime.now(UTC),
    )
    db.add(necessidade)
    db.flush()
    auditoria_service.registrar(
        db, tenant_id, "necessidade_registrada", "negocio", negocio.id,
        str(usuario_id) if usuario_id is not None else None, {"necessidade_id": necessidade.id, "categoria": categoria},
    )
    db.commit()
    return como_dict(necessidade)


def revisar(
    db: Session,
    tenant_id: str,
    usuario_id: int | None,
    necessidade_id: int,
    status: str,
    descricao: str | None = None,
    categoria: str | None = None,
) -> dict:
    """Human-in-the-loop: confirmar (com ou sem edição) ou descartar."""
    if status not in ("confirmada", "descartada"):
        raise RegraNegocioViolada("Status deve ser 'confirmada' ou 'descartada'.")
    necessidade = db.query(NecessidadeOportunidade).filter_by(id=necessidade_id, tenant_id=tenant_id).one_or_none()
    if necessidade is None:
        raise NaoEncontrado(f"Necessidade {necessidade_id} não encontrada")
    if categoria is not None and categoria not in CATEGORIAS:
        raise RegraNegocioViolada(f"Categoria inválida: {categoria}")

    editou = (descricao is not None and descricao.strip() != necessidade.descricao) or (
        categoria is not None and categoria != necessidade.categoria
    )
    if descricao is not None and descricao.strip():
        necessidade.descricao = descricao.strip()[:300]
    if categoria is not None:
        necessidade.categoria = categoria
    necessidade.status = status
    necessidade.revisado_por_usuario_id = usuario_id
    necessidade.revisado_em = datetime.now(UTC)

    if necessidade.origem == "ia":
        tipo = "REJEITADO" if status == "descartada" else ("EDITADO" if editou else "APROVADO")
        aprendizado.registrar(
            db, tenant_id, FEATURE, tipo, entidade_tipo="necessidade_oportunidade", entidade_id=necessidade.id,
            usuario_id=usuario_id, dados={"categoria": necessidade.categoria},
        )
    auditoria_service.registrar(
        db, tenant_id, f"necessidade_{status}", "necessidade_oportunidade", necessidade.id,
        str(usuario_id) if usuario_id is not None else None, {"negocio_id": necessidade.negocio_id},
    )
    db.commit()
    return como_dict(necessidade)


def listar(db: Session, tenant_id: str, negocio_id: int, incluir_descartadas: bool = False) -> list[NecessidadeOportunidade]:
    consulta = db.query(NecessidadeOportunidade).filter_by(tenant_id=tenant_id, negocio_id=negocio_id)
    if not incluir_descartadas:
        consulta = consulta.filter(NecessidadeOportunidade.status != "descartada")
    return consulta.order_by(NecessidadeOportunidade.id).all()


def listar_da_conta(db: Session, tenant_id: str, conta_id: int) -> list[NecessidadeOportunidade]:
    return (
        db.query(NecessidadeOportunidade)
        .filter(
            NecessidadeOportunidade.tenant_id == tenant_id,
            NecessidadeOportunidade.conta_id == conta_id,
            NecessidadeOportunidade.status != "descartada",
        )
        .order_by(NecessidadeOportunidade.id)
        .all()
    )


def como_dict(n: NecessidadeOportunidade) -> dict:
    return {
        "id": n.id,
        "negocio_id": n.negocio_id,
        "categoria": n.categoria,
        "descricao": n.descricao,
        "citacao": n.citacao,
        "fonte_tipo": n.fonte_tipo,
        "fonte_id": n.fonte_id,
        "origem": n.origem,
        "status": n.status,
        "criado_em": n.criado_em,
        "revisado_em": n.revisado_em,
    }
