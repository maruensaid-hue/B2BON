import csv
import io
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.custo_aquisicao import CustoAquisicao
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.oferta import Oferta
from app.models.usuario import Usuario
from app.schemas.crm import LinhaImportacaoNegocioSchema
from app.services import (
    atividade_service,
    auditoria_service,
    conta_service,
    llm_helpers,
    metricas_service,
    panel_service,
    saude_conta_service,
)
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

# Padrão recomendado, não decisão comercial fechada — configurável depois
# via definir_estagio (mesma regra de sempre para o que é do negócio do
# assinante, não do PREDATOR).
_ESTAGIOS_PADRAO = [
    ("Descoberta", 1, "aberto"),
    ("Proposta", 2, "aberto"),
    ("Negociação", 3, "aberto"),
    ("Ganho", 4, "ganho"),
    ("Perdido", 5, "perdido"),
]
_TIPOS_ESTAGIO_VALIDOS = {"aberto", "ganho", "perdido"}
_PERIODO_PADRAO_DIAS = 30


def garantir_estagios_padrao(db: Session, tenant_id: str) -> list[EstagioFunil]:
    """Semeia o funil padrão na primeira vez que o tenant usa o CRM (Onda B).

    Duas chamadas concorrentes (duas abas abrindo o CRM ao mesmo tempo no
    primeiro uso) podem ambas ver a tabela vazia e tentar inserir — a
    UniqueConstraint(tenant_id, ordem) do modelo garante que só uma
    vence; a outra recua e relê o que já foi gravado, em vez de duplicar.
    """
    estagios = db.query(EstagioFunil).filter_by(tenant_id=tenant_id).order_by(EstagioFunil.ordem).all()
    if estagios:
        return estagios
    for nome, ordem, tipo in _ESTAGIOS_PADRAO:
        db.add(EstagioFunil(tenant_id=tenant_id, nome=nome, ordem=ordem, tipo=tipo))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return db.query(EstagioFunil).filter_by(tenant_id=tenant_id).order_by(EstagioFunil.ordem).all()


def listar_estagios(db: Session, tenant_id: str) -> list[EstagioFunil]:
    return garantir_estagios_padrao(db, tenant_id)


def definir_estagio(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    estagio_id: int,
    nome: str | None = None,
    ordem: int | None = None,
    tipo: str | None = None,
) -> EstagioFunil:
    estagio = db.query(EstagioFunil).filter_by(id=estagio_id, tenant_id=tenant_id).one_or_none()
    if estagio is None:
        raise NaoEncontrado(f"Estágio {estagio_id} não encontrado")

    if nome is not None:
        estagio.nome = nome
    if ordem is not None:
        estagio.ordem = ordem
    if tipo is not None:
        if tipo not in _TIPOS_ESTAGIO_VALIDOS:
            raise ValidacaoFalhou(f"Tipo de estágio inválido: {tipo}")
        estagio.tipo = tipo

    auditoria_service.registrar(db, tenant_id, "estagio_funil_atualizado", "estagio_funil", estagio.id, ator_id, {})
    db.commit()
    db.refresh(estagio)
    return estagio


def obter_negocio(db: Session, tenant_id: str, negocio_id: int) -> Negocio:
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")
    return negocio


def listar_negocios(
    db: Session,
    tenant_id: str,
    estagio_id: int | None = None,
    vendedor_usuario_id: int | None = None,
    conta_id: int | None = None,
) -> list[Negocio]:
    query = db.query(Negocio).filter_by(tenant_id=tenant_id)
    if estagio_id is not None:
        query = query.filter_by(estagio_id=estagio_id)
    if vendedor_usuario_id is not None:
        query = query.filter_by(vendedor_usuario_id=vendedor_usuario_id)
    if conta_id is not None:
        query = query.filter_by(conta_id=conta_id)
    return query.order_by(Negocio.id.desc()).all()


def _validar_decisor_da_conta(db: Session, tenant_id: str, conta_id: int, decisor_id: int) -> None:
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id, conta_id=conta_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado nesta conta")


def _validar_oferta_do_tenant(db: Session, tenant_id: str, oferta_id: int) -> None:
    if db.query(Oferta).filter_by(id=oferta_id, tenant_id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Oferta {oferta_id} não encontrada")


def criar_negocio(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    decisor_id: int | None,
    nome: str,
    valor: float = 0.0,
    probabilidade: int = 50,
    vendedor_usuario_id: int | None = None,
    estagio_id: int | None = None,
    oferta_id: int | None = None,
) -> Negocio:
    """Cadastro manual de negócio (origem="manual") — direto pelo vendedor,
    sem passar pelo PREDATOR (Onda B). O contato responsável do lado do
    cliente é obrigatório aqui — só fica nulo em negócios antigos/os que o
    PREDATOR cria sozinho (Onda J: "necessariamente deve trazer... o
    contato que está conduzindo a oportunidade")."""
    if db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    if decisor_id is None:
        raise ValidacaoFalhou("Selecione o contato responsável pela oportunidade.")
    _validar_decisor_da_conta(db, tenant_id, conta_id, decisor_id)
    if oferta_id is not None:
        _validar_oferta_do_tenant(db, tenant_id, oferta_id)

    if estagio_id is None:
        estagios = garantir_estagios_padrao(db, tenant_id)
        primeiro_aberto = next((e for e in estagios if e.tipo == "aberto"), estagios[0])
        estagio_id = primeiro_aberto.id
    elif db.query(EstagioFunil).filter_by(id=estagio_id, tenant_id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Estágio {estagio_id} não encontrado")

    negocio = Negocio(
        tenant_id=tenant_id,
        conta_id=conta_id,
        decisor_id=decisor_id,
        nome=nome,
        valor=valor,
        probabilidade=probabilidade,
        vendedor_usuario_id=vendedor_usuario_id,
        estagio_id=estagio_id,
        oferta_id=oferta_id,
        origem="manual",
    )
    db.add(negocio)
    db.flush()

    atividade_service.registrar(
        db, tenant_id, conta_id=conta_id, negocio_id=negocio.id, tipo="sistema",
        descricao=f"Negócio '{nome}' criado", ator_id=ator_id,
    )
    auditoria_service.registrar(
        db, tenant_id, "negocio_criado", "negocio", negocio.id, ator_id, {"conta_id": conta_id}, conta_id=conta_id
    )
    db.commit()
    db.refresh(negocio)
    return negocio


def atualizar_negocio(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    negocio_id: int,
    nome: str,
    valor: float,
    probabilidade: int,
    decisor_id: int | None = None,
    oferta_id: int | None = None,
) -> Negocio:
    """Edição pós-criação (nome/valor/probabilidade/contato) — não havia
    como corrigir um negócio depois de cadastrado, só mover de estágio."""
    negocio = obter_negocio(db, tenant_id, negocio_id)
    if decisor_id is None:
        raise ValidacaoFalhou("Selecione o contato responsável pela oportunidade.")
    _validar_decisor_da_conta(db, tenant_id, negocio.conta_id, decisor_id)
    if oferta_id is not None:
        _validar_oferta_do_tenant(db, tenant_id, oferta_id)

    negocio.nome = nome
    negocio.valor = valor
    negocio.probabilidade = probabilidade
    negocio.decisor_id = decisor_id
    negocio.oferta_id = oferta_id

    atividade_service.registrar(
        db, tenant_id, conta_id=negocio.conta_id, negocio_id=negocio.id, tipo="sistema",
        descricao=f"Negócio '{nome}' editado", ator_id=ator_id,
    )
    auditoria_service.registrar(
        db, tenant_id, "negocio_atualizado", "negocio", negocio.id, ator_id, {"nome": nome}, conta_id=negocio.conta_id
    )
    db.commit()
    db.refresh(negocio)
    return negocio


def mover_estagio(
    db: Session, tenant_id: str, ator_id: str | None, negocio_id: int, novo_estagio_id: int, motivo_perda: str | None = None
) -> Negocio:
    """"Arrastar no kanban" (Onda B): ao entrar num estágio tipo "ganho",
    marca a conta como cliente (só na primeira vez); ao entrar em
    "perdido", grava o motivo."""
    negocio = obter_negocio(db, tenant_id, negocio_id)
    novo_estagio = db.query(EstagioFunil).filter_by(id=novo_estagio_id, tenant_id=tenant_id).one_or_none()
    if novo_estagio is None:
        raise NaoEncontrado(f"Estágio {novo_estagio_id} não encontrado")

    negocio.estagio_id = novo_estagio.id

    if novo_estagio.tipo == "ganho":
        if negocio.ganho_em is None:
            negocio.ganho_em = datetime.now(UTC)
        conta = db.query(Conta).filter_by(id=negocio.conta_id).one()
        if conta.cliente_desde is None:
            conta.cliente_desde = datetime.now(UTC)
    elif novo_estagio.tipo == "perdido":
        if not motivo_perda or not motivo_perda.strip():
            raise ValidacaoFalhou("Informe o motivo da perda para marcar o negócio como perdido.")
        if negocio.perdido_em is None:
            negocio.perdido_em = datetime.now(UTC)
        negocio.motivo_perda = motivo_perda

    descricao = f"Negócio movido para '{novo_estagio.nome}'"
    if novo_estagio.tipo == "perdido":
        descricao += f" — motivo: {motivo_perda}"
    atividade_service.registrar(
        db, tenant_id, conta_id=negocio.conta_id, negocio_id=negocio.id, tipo="sistema",
        descricao=descricao, ator_id=ator_id,
    )
    auditoria_service.registrar(
        db,
        tenant_id,
        "negocio_estagio_alterado",
        "negocio",
        negocio.id,
        ator_id,
        {"novo_estagio": novo_estagio.nome, "tipo": novo_estagio.tipo},
        conta_id=negocio.conta_id,
    )
    db.commit()
    db.refresh(negocio)
    return negocio


def excluir_negocio(db: Session, tenant_id: str, ator_id: str | None, negocio_id: int) -> None:
    """Exclusão de negócio (Onda B) — não existia nenhuma forma de remover
    um negócio cadastrado por engano. Atividades ligadas só a este negócio
    são apagadas junto; as que também têm `conta_id` (a maioria, já que
    quase toda atividade de negócio grava os dois) só perdem o vínculo com
    o negócio e continuam na timeline da conta."""
    negocio = obter_negocio(db, tenant_id, negocio_id)
    nome = negocio.nome
    conta_id = negocio.conta_id

    atividade_service.registrar(
        db, tenant_id, conta_id=conta_id, tipo="sistema", descricao=f"Negócio '{nome}' excluído", ator_id=ator_id
    )

    atividades_do_negocio = db.query(Atividade).filter_by(tenant_id=tenant_id, negocio_id=negocio.id).all()
    for atividade in atividades_do_negocio:
        if atividade.conta_id is not None:
            atividade.negocio_id = None
        else:
            db.delete(atividade)

    auditoria_service.registrar(
        db, tenant_id, "negocio_excluido", "negocio", negocio.id, ator_id, {"nome": nome}, conta_id=conta_id
    )
    db.delete(negocio)
    db.commit()


def _normalizar_nome(nome: str) -> str:
    """Mesmo critério de dedupe por nome usado em
    `conta_service.importar_participantes` — duplicado aqui (1 linha) em
    vez de promovido a utilitário compartilhado."""
    return " ".join(nome.split()).lower()


def _normalizar_cnpj(cnpj: str) -> str:
    return "".join(caractere for caractere in cnpj if caractere.isdigit())


def importar_negocios(
    db: Session, tenant_id: str, ator_id: str | None, linhas: list[LinhaImportacaoNegocioSchema]
) -> dict:
    """Import em lote de oportunidades (raio-X 2026-09-14: cliente chegando
    de outra plataforma já com histórico de negócios). O mapeamento de
    coluna do CSV acontece no frontend — aqui só resolve/cria conta,
    decisor, estágio e vendedor por linha, mesmo raciocínio de
    `conta_service.importar_participantes` (empresa reaproveitada por
    CNPJ/nome, decisor por e-mail/nome, nunca duplicados às ciegas).

    Uma linha com `chave_importacao` que já existe neste tenant
    **atualiza** o negócio existente em vez de criar outro — permite
    reimportar o mesmo arquivo sem duplicar. Sem chave, sempre cria (
    reimportar essa linha duplica; aviso disso fica a cargo da tela)."""
    contas_por_nome: dict[str, Conta] = {}
    contas_por_cnpj: dict[str, Conta] = {}
    for conta in db.query(Conta).filter_by(tenant_id=tenant_id).all():
        contas_por_nome[_normalizar_nome(conta.nome)] = conta
        if conta.cnpj:
            chave_cnpj = _normalizar_cnpj(conta.cnpj)
            if chave_cnpj:
                contas_por_cnpj[chave_cnpj] = conta

    decisores_por_conta: dict[int, list[Decisor]] = {}
    for decisor in db.query(Decisor).filter_by(tenant_id=tenant_id).all():
        decisores_por_conta.setdefault(decisor.conta_id, []).append(decisor)

    usuarios_por_email = {
        usuario.email.strip().lower(): usuario for usuario in db.query(Usuario).filter_by(tenant_id=tenant_id).all()
    }

    estagios = garantir_estagios_padrao(db, tenant_id)
    estagios_por_nome = {_normalizar_nome(estagio.nome): estagio for estagio in estagios}
    primeiro_aberto = next((e for e in estagios if e.tipo == "aberto"), estagios[0])

    negocios_por_chave: dict[str, Negocio] = {
        negocio.chave_importacao: negocio
        for negocio in db.query(Negocio)
        .filter(Negocio.tenant_id == tenant_id, Negocio.chave_importacao.isnot(None))
        .all()
    }

    contas_criadas = 0
    contas_reaproveitadas: set[int] = set()
    decisores_criados = 0
    negocios_criados = 0
    negocios_atualizados = 0
    erros: list[dict] = []

    for indice, linha in enumerate(linhas, start=1):
        estagio = primeiro_aberto
        if linha.estagio_nome:
            estagio_encontrado = estagios_por_nome.get(_normalizar_nome(linha.estagio_nome))
            if estagio_encontrado is None:
                erros.append({"linha": indice, "motivo": f"Estágio '{linha.estagio_nome}' não encontrado"})
                continue
            estagio = estagio_encontrado

        conta = None
        if linha.empresa_cnpj:
            chave_cnpj = _normalizar_cnpj(linha.empresa_cnpj)
            if chave_cnpj:
                conta = contas_por_cnpj.get(chave_cnpj)
        if conta is None:
            conta = contas_por_nome.get(_normalizar_nome(linha.empresa_nome))
        if conta is None:
            # Raio-X 2026-09-16: guarda o CNPJ já normalizado (só
            # dígitos) — antes gravava o valor bruto da planilha
            # (`.strip()` só tira espaço, não pontuação), então a conta
            # criada aqui ficava com um CNPJ num formato diferente do
            # usado por `_normalizar_cnpj`/BrasilAPI/geração de lista por
            # ICP em qualquer lugar mais adiante.
            conta = Conta(
                tenant_id=tenant_id,
                cnpj=_normalizar_cnpj(linha.empresa_cnpj) or None if linha.empresa_cnpj else None,
                nome=linha.empresa_nome.strip(),
                status="priorizada",
                origem="crm_import",
            )
            db.add(conta)
            db.flush()
            contas_por_nome[_normalizar_nome(conta.nome)] = conta
            if conta.cnpj:
                chave_cnpj = _normalizar_cnpj(conta.cnpj)
                if chave_cnpj:
                    contas_por_cnpj[chave_cnpj] = conta
            contas_criadas += 1
        else:
            contas_reaproveitadas.add(conta.id)

        existentes = decisores_por_conta.setdefault(conta.id, [])
        email_linha = linha.decisor_email.strip().lower() if linha.decisor_email else None
        nome_linha = _normalizar_nome(linha.decisor_nome) if linha.decisor_nome else None
        decisor = None
        if email_linha or nome_linha:
            decisor = next(
                (
                    d
                    for d in existentes
                    if (email_linha and d.email and d.email.strip().lower() == email_linha)
                    or (nome_linha and _normalizar_nome(d.nome) == nome_linha)
                ),
                None,
            )
            if decisor is None:
                decisor = Decisor(
                    tenant_id=tenant_id,
                    conta_id=conta.id,
                    nome=(linha.decisor_nome or linha.decisor_email or "").strip(),
                    cargo=linha.decisor_cargo,
                    email=linha.decisor_email,
                    telefone=linha.decisor_telefone,
                    origem="crm_import",
                )
                db.add(decisor)
                db.flush()
                existentes.append(decisor)
                decisores_criados += 1

        vendedor = usuarios_por_email.get(linha.vendedor_email.strip().lower()) if linha.vendedor_email else None

        ganho_em = linha.ganho_em
        perdido_em = linha.perdido_em
        if estagio.tipo == "ganho" and ganho_em is None:
            ganho_em = linha.criado_em or datetime.now(UTC)
        if estagio.tipo == "perdido" and perdido_em is None:
            perdido_em = linha.criado_em or datetime.now(UTC)
        if estagio.tipo == "ganho" and conta.cliente_desde is None:
            conta.cliente_desde = ganho_em

        negocio_existente = negocios_por_chave.get(linha.chave_importacao) if linha.chave_importacao else None
        if negocio_existente is not None:
            negocio_existente.conta_id = conta.id
            if decisor is not None:
                negocio_existente.decisor_id = decisor.id
            negocio_existente.estagio_id = estagio.id
            negocio_existente.nome = linha.nome
            negocio_existente.valor = linha.valor
            negocio_existente.probabilidade = linha.probabilidade
            if vendedor is not None:
                negocio_existente.vendedor_usuario_id = vendedor.id
            negocio_existente.motivo_perda = linha.motivo_perda or negocio_existente.motivo_perda
            negocio_existente.ganho_em = negocio_existente.ganho_em or ganho_em
            negocio_existente.perdido_em = negocio_existente.perdido_em or perdido_em
            negocios_atualizados += 1
        else:
            novo_negocio = Negocio(
                tenant_id=tenant_id,
                conta_id=conta.id,
                decisor_id=decisor.id if decisor else None,
                vendedor_usuario_id=vendedor.id if vendedor else None,
                estagio_id=estagio.id,
                nome=linha.nome,
                valor=linha.valor,
                probabilidade=linha.probabilidade,
                origem="crm_import",
                ganho_em=ganho_em,
                perdido_em=perdido_em,
                motivo_perda=linha.motivo_perda,
                chave_importacao=linha.chave_importacao,
                criado_em=linha.criado_em or datetime.now(UTC),
            )
            db.add(novo_negocio)
            db.flush()
            if linha.chave_importacao:
                negocios_por_chave[linha.chave_importacao] = novo_negocio
            negocios_criados += 1

    auditoria_service.registrar(
        db,
        tenant_id,
        "negocios_importados",
        "negocio",
        0,
        ator_id,
        {"negocios_criados": negocios_criados, "negocios_atualizados": negocios_atualizados, "erros": len(erros)},
    )
    db.commit()

    return {
        "negocios_criados": negocios_criados,
        "negocios_atualizados": negocios_atualizados,
        "contas_criadas": contas_criadas,
        "contas_reaproveitadas": len(contas_reaproveitadas),
        "decisores_criados": decisores_criados,
        "erros": erros,
    }


_CABECALHO_EXPORTACAO_NEGOCIOS = [
    "chave_importacao",
    "empresa_nome",
    "empresa_cnpj",
    "decisor_nome",
    "decisor_email",
    "decisor_telefone",
    "decisor_cargo",
    "nome",
    "valor",
    "probabilidade",
    "estagio_nome",
    "motivo_perda",
    "vendedor_email",
    "criado_em",
    "ganho_em",
    "perdido_em",
]


def exportar_negocios_csv(db: Session, tenant_id: str) -> str:
    """Cabeçalho igual aos campos de `LinhaImportacaoNegocioSchema` — um
    export da própria B2B ON é reimportável sem mapeamento manual de
    coluna, e a `chave_importacao` ("b2bon-{id}") faz a reimportação
    atualizar em vez de duplicar (raio-X 2026-09-14: import/export CSV).

    Negócios que nunca passaram por importação (criados manualmente ou
    pelo PREDATOR) não têm `chave_importacao` gravada no banco — é
    preenchida aqui, na primeira exportação, pra que uma reimportação
    subsequente do próprio CSV encontre a linha certa em vez de criar
    outro negócio (sem isso, o round-trip export→import duplicaria)."""
    negocios = db.query(Negocio).filter_by(tenant_id=tenant_id).order_by(Negocio.id).all()
    for negocio in negocios:
        if negocio.chave_importacao is None:
            negocio.chave_importacao = f"b2bon-{negocio.id}"
    db.commit()

    conta_ids = {n.conta_id for n in negocios}
    decisor_ids = {n.decisor_id for n in negocios if n.decisor_id is not None}
    vendedor_ids = {n.vendedor_usuario_id for n in negocios if n.vendedor_usuario_id is not None}
    estagio_ids = {n.estagio_id for n in negocios}

    contas = {c.id: c for c in db.query(Conta).filter(Conta.id.in_(conta_ids)).all()} if conta_ids else {}
    decisores = {d.id: d for d in db.query(Decisor).filter(Decisor.id.in_(decisor_ids)).all()} if decisor_ids else {}
    vendedores = (
        {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_(vendedor_ids)).all()} if vendedor_ids else {}
    )
    estagios = (
        {e.id: e for e in db.query(EstagioFunil).filter(EstagioFunil.id.in_(estagio_ids)).all()} if estagio_ids else {}
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CABECALHO_EXPORTACAO_NEGOCIOS)
    for negocio in negocios:
        conta = contas.get(negocio.conta_id)
        decisor = decisores.get(negocio.decisor_id) if negocio.decisor_id else None
        vendedor = vendedores.get(negocio.vendedor_usuario_id) if negocio.vendedor_usuario_id else None
        estagio = estagios.get(negocio.estagio_id)
        writer.writerow(
            [
                negocio.chave_importacao or f"b2bon-{negocio.id}",
                conta.nome if conta else "",
                conta.cnpj if conta else "",
                decisor.nome if decisor else "",
                decisor.email if decisor else "",
                decisor.telefone if decisor else "",
                decisor.cargo if decisor else "",
                negocio.nome,
                negocio.valor,
                negocio.probabilidade,
                estagio.nome if estagio else "",
                negocio.motivo_perda or "",
                vendedor.email if vendedor else "",
                negocio.criado_em.isoformat(),
                negocio.ganho_em.isoformat() if negocio.ganho_em else "",
                negocio.perdido_em.isoformat() if negocio.perdido_em else "",
            ]
        )
    return buffer.getvalue()


def registrar_atividade(
    db: Session, tenant_id: str, ator_id: str | None, negocio_id: int, tipo: str, descricao: str
) -> Atividade:
    negocio = obter_negocio(db, tenant_id, negocio_id)
    atividade = Atividade(
        tenant_id=tenant_id,
        conta_id=negocio.conta_id,
        negocio_id=negocio.id,
        usuario_id=int(ator_id) if ator_id else None,
        tipo=tipo,
        descricao=descricao,
    )
    db.add(atividade)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "atividade_registrada", "atividade", atividade.id, ator_id, {"tipo": tipo}, conta_id=negocio.conta_id
    )
    db.commit()
    db.refresh(atividade)
    return atividade


def listar_atividades(db: Session, tenant_id: str, negocio_id: int) -> list[Atividade]:
    obter_negocio(db, tenant_id, negocio_id)  # garante existência/isolamento por tenant
    return (
        db.query(Atividade)
        .filter_by(tenant_id=tenant_id, negocio_id=negocio_id)
        .order_by(Atividade.criado_em)
        .all()
    )


def marcar_cliente_cancelado(db: Session, tenant_id: str, ator_id: str | None, conta_id: int, motivo: str | None) -> Conta:
    """Registra o evento de churn (Onda B)."""
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    if conta.cliente_desde is None:
        raise RegraNegocioViolada("Conta ainda não é cliente (nenhum negócio ganho) — não é possível cancelar.")

    if conta.cliente_cancelado_em is None:
        conta.cliente_cancelado_em = datetime.now(UTC)

    auditoria_service.registrar(
        db, tenant_id, "cliente_cancelado", "conta", conta.id, ator_id, {"motivo": motivo}, conta_id=conta.id
    )
    db.commit()
    db.refresh(conta)
    return conta


def definir_custo_aquisicao(db: Session, tenant_id: str, ator_id: str | None, periodo: str, valor: float) -> CustoAquisicao:
    custo = db.query(CustoAquisicao).filter_by(tenant_id=tenant_id, periodo=periodo).one_or_none()
    if custo is None:
        custo = CustoAquisicao(tenant_id=tenant_id, periodo=periodo, valor=valor)
        db.add(custo)
    else:
        custo.valor = valor

    auditoria_service.registrar(
        db, tenant_id, "custo_aquisicao_definido", "custo_aquisicao", 0, ator_id, {"periodo": periodo, "valor": valor}
    )
    db.commit()
    db.refresh(custo)
    return custo


def obter_custo_aquisicao(db: Session, tenant_id: str, periodo: str) -> CustoAquisicao | None:
    return db.query(CustoAquisicao).filter_by(tenant_id=tenant_id, periodo=periodo).one_or_none()


def _periodo_padrao(data_inicio: date | None, data_fim: date | None) -> tuple[date, date]:
    fim = data_fim or date.today()
    inicio = data_inicio or (fim - timedelta(days=_PERIODO_PADRAO_DIAS))
    return inicio, fim


def _no_periodo(momento: datetime | None, inicio: date, fim: date) -> bool:
    if momento is None:
        return False
    return inicio <= momento.date() <= fim


def dashboard_funil(db: Session, tenant_id: str, data_inicio: date | None = None, data_fim: date | None = None) -> dict:
    """Contagem/valor por estágio e taxa de conversão do período (Onda B)."""
    inicio, fim = _periodo_padrao(data_inicio, data_fim)
    estagios = garantir_estagios_padrao(db, tenant_id)
    negocios = db.query(Negocio).filter_by(tenant_id=tenant_id).all()
    negocios_periodo = [n for n in negocios if _no_periodo(n.criado_em, inicio, fim)]

    resumo = []
    for estagio in estagios:
        do_estagio = [n for n in negocios_periodo if n.estagio_id == estagio.id]
        resumo.append(
            {
                "estagio_id": estagio.id,
                "nome": estagio.nome,
                "tipo": estagio.tipo,
                "quantidade": len(do_estagio),
                "valor_total": sum(n.valor for n in do_estagio),
            }
        )

    ids_ganho = {e.id for e in estagios if e.tipo == "ganho"}
    total = len(negocios_periodo)
    ganhos = sum(1 for n in negocios_periodo if n.estagio_id in ids_ganho)
    taxa_conversao = ganhos / total if total else None

    return {
        "periodo_inicio": inicio.isoformat(),
        "periodo_fim": fim.isoformat(),
        "estagios": resumo,
        "taxa_conversao": taxa_conversao,
    }


def dashboard_atividade(db: Session, tenant_id: str, data_inicio: date | None = None, data_fim: date | None = None) -> dict:
    """Atividade por vendedor e por equipe (Onda B)."""
    inicio, fim = _periodo_padrao(data_inicio, data_fim)
    # Filtro de período NA QUERY (Fase 7B, hardening) — antes carregava
    # TODA a `Atividade` do tenant pra filtrar em Python; um tenant
    # antigo com histórico grande pagava esse custo em toda consulta.
    inicio_dt = datetime.combine(inicio, time.min)
    fim_dt = datetime.combine(fim + timedelta(days=1), time.min)
    atividades_periodo = (
        db.query(Atividade)
        .filter(
            Atividade.tenant_id == tenant_id,
            Atividade.usuario_id.isnot(None),
            Atividade.criado_em >= inicio_dt,
            Atividade.criado_em < fim_dt,
        )
        .all()
    )

    contagem: dict[int, int] = {}
    for atividade in atividades_periodo:
        contagem[atividade.usuario_id] = contagem.get(atividade.usuario_id, 0) + 1

    # Lote (Fase 7B, hardening) — antes buscava um `Usuario` por
    # vendedor dentro do loop.
    usuarios_por_id = {
        usuario.id: usuario for usuario in db.query(Usuario).filter(Usuario.id.in_(contagem.keys())).all()
    } if contagem else {}
    por_vendedor = []
    for usuario_id, quantidade in contagem.items():
        usuario = usuarios_por_id.get(usuario_id)
        por_vendedor.append(
            {"usuario_id": usuario_id, "nome": usuario.nome if usuario else "Desconhecido", "quantidade": quantidade}
        )
    por_vendedor.sort(key=lambda item: item["quantidade"], reverse=True)

    return {
        "periodo_inicio": inicio.isoformat(),
        "periodo_fim": fim.isoformat(),
        "por_vendedor": por_vendedor,
        "total_equipe": len(atividades_periodo),
    }


def dashboard_economia(db: Session, tenant_id: str, periodo: str) -> dict:
    """LTV médio, CAC e taxa de churn do período "YYYY-MM" (Onda B)."""
    ano, mes = (int(parte) for parte in periodo.split("-"))
    inicio_periodo = date(ano, mes, 1)
    proximo_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    fim_periodo = proximo_mes - timedelta(days=1)

    contas = db.query(Conta).filter_by(tenant_id=tenant_id).all()
    contas_clientes = [conta for conta in contas if conta.cliente_desde is not None]

    estagios = {estagio.id: estagio for estagio in garantir_estagios_padrao(db, tenant_id)}
    negocios = db.query(Negocio).filter_by(tenant_id=tenant_id).all()
    valor_ganho_por_conta: dict[int, float] = {}
    for negocio in negocios:
        estagio = estagios.get(negocio.estagio_id)
        if estagio and estagio.tipo == "ganho":
            valor_ganho_por_conta[negocio.conta_id] = valor_ganho_por_conta.get(negocio.conta_id, 0.0) + negocio.valor
    ltv_medio = (sum(valor_ganho_por_conta.values()) / len(contas_clientes)) if contas_clientes else None

    novos_clientes = [
        conta for conta in contas_clientes if inicio_periodo <= conta.cliente_desde.date() <= fim_periodo
    ]

    custo = obter_custo_aquisicao(db, tenant_id, periodo)
    cac = (custo.valor / len(novos_clientes)) if custo and novos_clientes else None

    ativos_inicio = [
        conta
        for conta in contas_clientes
        if conta.cliente_desde.date() < inicio_periodo
        and (conta.cliente_cancelado_em is None or conta.cliente_cancelado_em.date() >= inicio_periodo)
    ]
    cancelados_periodo = [
        conta
        for conta in contas_clientes
        if conta.cliente_cancelado_em and inicio_periodo <= conta.cliente_cancelado_em.date() <= fim_periodo
    ]
    taxa_churn = (len(cancelados_periodo) / len(ativos_inicio)) if ativos_inicio else None

    roi = metricas_service.calcular_roi(ltv_medio, cac)
    scores_risco = [saude_conta_service.calcular_score_risco_da_conta(db, conta)["score"] for conta in contas]
    cs = metricas_service.calcular_cs_score(
        db, tenant_id, conta_ids=[conta.id for conta in contas], scores_risco=scores_risco
    )

    return {
        "periodo": periodo,
        "ltv_medio": ltv_medio,
        "cac": cac,
        "taxa_churn": taxa_churn,
        "novos_clientes": len(novos_clientes),
        "clientes_ativos_inicio_periodo": len(ativos_inicio),
        "clientes_cancelados_periodo": len(cancelados_periodo),
        "roi": roi,
        "cs_score": cs["cs_score"],
        "nps_medio": cs["nps_medio"],
    }


def dashboard_flywheel(db: Session, tenant_id: str) -> dict:
    """Ponto de encontro CRM (novo) + PREDATOR (já existente) num único
    payload (Onda B) — a "retroalimentação" pedida."""
    return {
        "metrica_norte": panel_service.metrica_norte(db, tenant_id),
        "indicadores_energia": panel_service.indicadores_energia(db, tenant_id, None, None),
        "indicadores_atrito": panel_service.indicadores_atrito(db, tenant_id, None, None),
        "funil": dashboard_funil(db, tenant_id),
    }


def gerar_meeting_brief(db: Session, tenant_id: str, ator_id: str | None, negocio_id: int, llm: LLMProvider) -> dict:
    """Meeting Agent (master prompt §32, Fase 6B) — junta negócio, conta,
    decisores com papel (Stakeholder Map, Fase 5B) e as últimas
    atividades reais em UMA chamada de IA; nunca altera o CRM (é
    preparação, distinto do `resumo_ia` que `Reuniao` já grava DEPOIS da
    reunião via transcrição)."""
    negocio = obter_negocio(db, tenant_id, negocio_id)
    conta = db.query(Conta).filter_by(id=negocio.conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {negocio.conta_id} não encontrada")

    linhas_decisores = conta_service.contexto_decisores_texto(db, tenant_id, conta.id)
    linhas_atividades = atividade_service.contexto_recentes_texto(db, tenant_id, negocio_id=negocio.id)

    oferta = db.query(Oferta).filter_by(id=negocio.oferta_id).one_or_none() if negocio.oferta_id else None
    linha_oferta = f"Oferta vinculada: {oferta.nome} — {oferta.descricao}" if oferta is not None else "Sem oferta vinculada."

    resposta = llm_helpers.gerar_e_registrar(
        db,
        tenant_id,
        "meeting_agent",
        llm,
        LLMRequest(
            prompt=(
                f"Negócio: \"{negocio.nome}\" (R$ {negocio.valor:.2f}), conta \"{conta.nome}\" "
                f"({conta.segmento or 'segmento desconhecido'}, porte {conta.porte or 'desconhecido'}).\n"
                f"{linha_oferta}\n\n"
                f"Decisores mapeados:\n{linhas_decisores}\n\n"
                f"Últimas atividades registradas:\n{linhas_atividades}\n\n"
                "Com base SÓ nas informações acima (não invente nenhum dado além delas), escreva um briefing "
                "curto para o vendedor se preparar para a próxima reunião com esta conta, cobrindo: objetivos da "
                "reunião, perguntas a fazer, riscos a observar, resumo dos stakeholders envolvidos e próximos "
                "passos recomendados."
            ),
            system="Você prepara vendedores B2B para reuniões, só com base nos dados fornecidos.",
        ),
        entidade_tipo="negocio",
        entidade_id=negocio.id,
    )

    auditoria_service.registrar(
        db, tenant_id, "meeting_brief_gerado", "negocio", negocio.id, ator_id, {}, conta_id=conta.id
    )
    db.commit()
    return {"brief": resposta.content.strip()}
