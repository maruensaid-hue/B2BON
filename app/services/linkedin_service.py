import re
from urllib.parse import quote, unquote

from sqlalchemy.orm import Session

from app.models.conexao_linkedin import ConexaoLinkedin
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.tarefa_linkedin import TarefaLinkedin
from app.services import aprovacao_service, atividade_service, auditoria_service, linkedin_importacao_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada


_URL_PERFIL_NO_TEXTO = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[^\s,;|<>\"')]+", re.IGNORECASE)


def _tokens_nome(nome: str | None) -> list[str]:
    return linkedin_importacao_service._normalizar_pessoa(nome).split()


def _url_nas_observacoes(conta: Conta | None, decisor: Decisor, decisores_da_conta: int) -> str | None:
    """A importação de planilha mandava a coluna de URL do LinkedIn para as Observações da empresa (visto em produção em 16/11/2026:
    13 mil empresas do cyberfort assim). Usa a URL de lá quando dá para saber de quem é: a única URL de uma empresa com um só
    contato, ou a URL cujo endereço traz o nome do contato."""
    if conta is None or not conta.observacoes:
        return None
    urls = list(dict.fromkeys(m.group(0).rstrip(".") for m in _URL_PERFIL_NO_TEXTO.finditer(conta.observacoes)))
    if not urls:
        return None
    if len(urls) == 1 and decisores_da_conta == 1:
        return urls[0]
    tokens = [t for t in _tokens_nome(decisor.nome) if len(t) > 2]
    com_nome = [u for u in urls if tokens and all(t in linkedin_importacao_service._normalizar_pessoa(unquote(u)) for t in tokens)]
    return com_nome[0] if len(com_nome) == 1 else None


def _url_nas_conexoes(db: Session, tenant_id: str, decisor: Decisor) -> str | None:
    """Conexão do LinkedIn importada no tenant com exatamente o mesmo nome completo (duas palavras ou mais) e um só perfil."""
    tokens = _tokens_nome(decisor.nome)
    if len(tokens) < 2:
        return None
    candidatas = (
        db.query(ConexaoLinkedin.nome_completo, ConexaoLinkedin.url_perfil)
        .filter(ConexaoLinkedin.tenant_id == tenant_id, ConexaoLinkedin.url_perfil.isnot(None), ConexaoLinkedin.nome_completo.ilike(f"%{tokens[-1]}%"))
        .all()
    )
    urls = {url for nome, url in candidatas if _tokens_nome(nome) == tokens}
    return next(iter(urls)) if len(urls) == 1 else None


def link_de_busca(decisor: Decisor, conta: Conta | None) -> str:
    """Busca de pessoas do LinkedIn pelo nome e empresa: quando o perfil não é conhecido, a pessoa acha o contato com um clique."""
    termos = " ".join(p for p in (decisor.nome, (conta.nome_fantasia or conta.nome) if conta is not None else None) if p)
    return f"https://www.linkedin.com/search/results/people/?keywords={quote(termos)}"


def resolver_perfil(db: Session, tenant_id: str, decisor: Decisor, conta: Conta | None) -> str | None:
    """Perfil do contato no LinkedIn: o cadastrado ou, se faltar, o que der para recuperar com segurança dos dados já importados
    (observações da empresa ou conexões do LinkedIn). O que for achado fica gravado no contato."""
    if decisor.linkedin_url and decisor.linkedin_url.strip():
        return decisor.linkedin_url.strip()
    decisores_da_conta = db.query(Decisor).filter_by(tenant_id=tenant_id, conta_id=decisor.conta_id).count()
    url = _url_nas_observacoes(conta, decisor, decisores_da_conta) or _url_nas_conexoes(db, tenant_id, decisor)
    if url:
        decisor.linkedin_url = linkedin_importacao_service._url_completa(linkedin_importacao_service._normalizar_url(url))
    return decisor.linkedin_url


def _enriquecer(db: Session, tenant_id: str, tarefas: list[TarefaLinkedin]) -> list[dict]:
    """Acrescenta contato, cargo e empresa a cada tarefa (consultas em lote, não uma por linha). Tarefa pendente sem perfil
    tenta recuperar o perfil dos dados importados; sem perfil, oferece a busca do LinkedIn pelo nome e empresa."""
    ids_decisores = {t.decisor_id for t in tarefas}
    decisores = (
        {d.id: d for d in db.query(Decisor).filter(Decisor.tenant_id == tenant_id, Decisor.id.in_(ids_decisores)).all()} if ids_decisores else {}
    )
    ids_contas = {d.conta_id for d in decisores.values()}
    contas = {c.id: c for c in db.query(Conta).filter(Conta.tenant_id == tenant_id, Conta.id.in_(ids_contas)).all()} if ids_contas else {}
    resultado = []
    recuperou = False
    for tarefa in tarefas:
        decisor = decisores.get(tarefa.decisor_id)
        conta = contas.get(decisor.conta_id) if decisor is not None else None
        if decisor is not None and tarefa.status == "pendente" and not (tarefa.link_perfil or "").strip():
            perfil = resolver_perfil(db, tenant_id, decisor, conta)
            if perfil:
                tarefa.link_perfil = perfil
                recuperou = True
        link_busca = link_de_busca(decisor, conta) if decisor is not None and not (tarefa.link_perfil or "").strip() else None
        resultado.append(
            {
                "id": tarefa.id,
                "tenant_id": tarefa.tenant_id,
                "mensagem_id": tarefa.mensagem_id,
                "decisor_id": tarefa.decisor_id,
                "texto": tarefa.texto,
                "link_perfil": tarefa.link_perfil,
                "link_busca": link_busca,
                "status": tarefa.status,
                "criado_em": tarefa.criado_em,
                "atualizado_em": tarefa.atualizado_em,
                "decisor_nome": decisor.nome if decisor is not None else None,
                "decisor_cargo": decisor.cargo if decisor is not None else None,
                "conta_id": conta.id if conta is not None else None,
                "conta_nome": (conta.nome_fantasia or conta.nome) if conta is not None else None,
            }
        )
    if recuperou:
        db.commit()
    return resultado


def listar_tarefas(db: Session, tenant_id: str, status: str | None = None) -> list[dict]:
    """Fila de trabalho: as mais antigas primeiro (a que está esperando há mais tempo é a que deve sair antes)."""
    query = db.query(TarefaLinkedin).filter_by(tenant_id=tenant_id)
    if status:
        query = query.filter_by(status=status)
    return _enriquecer(db, tenant_id, query.order_by(TarefaLinkedin.criado_em, TarefaLinkedin.id).all())


def contar_pendentes(db: Session, tenant_id: str) -> int:
    """Quantas tarefas pendentes o tenant tem (o número do menu)."""
    return db.query(TarefaLinkedin).filter_by(tenant_id=tenant_id, status="pendente").count()


def marcar(db: Session, tenant_id: str, ator_id: str | None, tarefa_id: int, executada: bool) -> dict:
    """Marcação de executado/ignorado realimenta a cadência (E3-H4): fecha
    o único caminho que leva um toque de LinkedIn a um estado terminal,
    já que o envio nunca é automatizado. "Enviada" também entra na linha do
    tempo da conta, como os demais canais; repetir a mesma marcação (duplo
    clique) não repete o registro."""
    tarefa = db.query(TarefaLinkedin).filter_by(id=tarefa_id, tenant_id=tenant_id).one_or_none()
    if tarefa is None:
        raise NaoEncontrado(f"Tarefa de LinkedIn {tarefa_id} não encontrada")

    pedido = "executada" if executada else "ignorada"
    if tarefa.status != "pendente":
        if tarefa.status == pedido:
            return _enriquecer(db, tenant_id, [tarefa])[0]
        raise RegraNegocioViolada(f"Esta tarefa já foi marcada como {tarefa.status}.")

    if executada:
        aprovacao_service.marcar_enviada(db, tenant_id, tarefa.mensagem_id)
        tarefa.status = "executada"
        decisor = db.query(Decisor).filter_by(id=tarefa.decisor_id, tenant_id=tenant_id).one_or_none()
        if decisor is not None:
            atividade_service.registrar(
                db,
                tenant_id,
                conta_id=decisor.conta_id,
                tipo="linkedin",
                descricao=f"Mensagem de LinkedIn enviada (manual) para {decisor.nome}",
                ator_id=ator_id,
            )
    else:
        mensagem = db.query(Mensagem).filter_by(id=tarefa.mensagem_id).one()
        mensagem.status = "cancelado"
        tarefa.status = "ignorada"

    auditoria_service.registrar(
        db,
        tenant_id,
        "tarefa_linkedin_marcada",
        "tarefa_linkedin",
        tarefa.id,
        ator_id,
        {"executada": executada},
        canal="linkedin",
    )
    db.commit()
    db.refresh(tarefa)
    return _enriquecer(db, tenant_id, [tarefa])[0]
