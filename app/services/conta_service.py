import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fpdf import FPDF
from sqlalchemy.orm import Session

from app.graph.client import Neo4jClient
from app.integrations.brasilapi_client import BrasilApiClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.providers.account_data.base import AccountDataProvider, ContaCandidata, FiltroBusca
from app.schemas.conta import ParticipanteEventoSchema
from app.schemas.decisor import DecisorCreateSchema
from app.services import auditoria_service, descarte_service, llm_helpers
from app.services.errors import NaoEncontrado, RegraNegocioViolada


def _score_aderencia(db: Session, tenant_id: str, icp: ICP, candidato: ContaCandidata) -> float:
    pontuacao = 0.0
    if candidato.cnae_principal in icp.cnae_codigos:
        pontuacao += 0.5
    if candidato.uf.upper() in {uf.upper() for uf in icp.ufs}:
        pontuacao += 0.3
    if icp.porte and candidato.porte == icp.porte:
        pontuacao += 0.2

    penalidade = descarte_service.penalidade_para(
        db, tenant_id, candidato.cnae_principal, candidato.porte, candidato.uf
    )
    return round(max(pontuacao - penalidade, 0.0), 2)


def gerar_lista(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    icp_id: int,
    quantidade: int,
    account_data: AccountDataProvider,
    graph: Neo4jClient,
) -> list[Conta]:
    """Gera lista de contas-alvo aderentes ao ICP (E2-H1).

    Geração, avaliação e descarte de listas não consomem franquia — o
    consumo só acontece quando uma conta entra numa cadência ativada
    (`franquia_service.consumir_para_ativacao`, chamado pelo E3).
    """
    icp = db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none()
    if icp is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")
    if not icp.ativo:
        raise RegraNegocioViolada(
            "Sem ICP ativo, o motor não inicia prospecção. Ative um ICP antes de gerar contas."
        )

    candidatos = account_data.buscar_candidatos(
        FiltroBusca(
            cnae_codigos=icp.cnae_codigos,
            ufs=icp.ufs,
            porte=icp.porte or None,
            limite=quantidade * 3,
        )
    )

    cnpjs_existentes = {
        cnpj for (cnpj,) in db.query(Conta.cnpj).filter_by(tenant_id=tenant_id).all() if cnpj
    }

    criadas: list[Conta] = []
    for candidato in candidatos:
        if len(criadas) >= quantidade:
            break
        if candidato.cnpj in cnpjs_existentes:
            continue

        conta = Conta(
            tenant_id=tenant_id,
            icp_id=icp.id,
            cnpj=candidato.cnpj,
            nome=candidato.razao_social,
            porte=candidato.porte,
            segmento=candidato.cnae_principal,
            regiao=candidato.uf,
            score_aderencia=_score_aderencia(db, tenant_id, icp, candidato),
            status="prospectada",
            origem=candidato.fonte,
        )
        db.add(conta)
        db.flush()

        graph.upsert_conta(tenant_id, conta.id, {"nome": conta.nome, "cnpj": conta.cnpj})
        conta.neo4j_node_id = str(conta.id)

        criadas.append(conta)
        cnpjs_existentes.add(candidato.cnpj)

    auditoria_service.registrar(
        db, tenant_id, "lista_gerada", "icp", icp.id, ator_id, {"quantidade": len(criadas)}
    )
    db.commit()
    for conta in criadas:
        db.refresh(conta)
    return criadas


def criar_manual(
    db: Session, tenant_id: str, ator_id: str | None, icp_id: int, nome: str, cnpj: str | None, dominio: str | None
) -> Conta:
    """Cadastro avulso de uma conta a partir do CRM (E2-H2) — para o cliente
    que chegou por indicação/inbound, não por uma lista do PREDATOR.
    Precisa de um ICP porque `Conta.icp_id` é obrigatório no modelo (todo
    o resto do produto — score de aderência, geração de cadência —
    presume uma conta ligada a um perfil), mas não passa pelo score de
    aderência: cadastro manual não tem candidato pra pontuar contra."""
    icp = db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none()
    if icp is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")

    conta = Conta(
        tenant_id=tenant_id,
        icp_id=icp_id,
        nome=nome,
        cnpj=cnpj,
        dominio=_normalizar_dominio(dominio),
        status="prospectada",
        origem="manual",
    )
    db.add(conta)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "conta_criada_manual", "conta", conta.id, ator_id, {"nome": nome})
    db.commit()
    db.refresh(conta)
    return conta


def _normalizar_nome(nome: str) -> str:
    return " ".join(nome.split()).lower()


def importar_participantes_evento(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    icp_id: int,
    participantes: list[ParticipanteEventoSchema],
    graph: Neo4jClient,
) -> dict:
    """Cria contas a partir de uma listagem de participantes de evento —
    sem CNPJ, então a empresa é reconhecida pelo nome (normalizado), não
    por dado da Receita Federal. Cada linha vira um decisor dentro da
    conta da sua empresa; empresas repetidas na lista (ou já existentes
    no tenant) são reaproveitadas em vez de duplicadas. Não passa pelo
    score de aderência do ICP (não há CNAE/UF/porte reais para comparar)
    nem consome franquia — mesmo raciocínio de `gerar_lista`: só consome
    quando a conta entra numa cadência ativada."""
    icp = db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none()
    if icp is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")

    contas_por_nome: dict[str, Conta] = {
        _normalizar_nome(conta.nome): conta
        for conta in db.query(Conta).filter_by(tenant_id=tenant_id).all()
    }

    decisores_por_conta: dict[int, list[Decisor]] = {}
    for decisor in db.query(Decisor).filter_by(tenant_id=tenant_id).all():
        decisores_por_conta.setdefault(decisor.conta_id, []).append(decisor)

    contas_criadas = 0
    contas_reaproveitadas: set[int] = set()
    decisores_criados = 0
    contas_tocadas: dict[int, Conta] = {}

    for participante in participantes:
        chave_empresa = _normalizar_nome(participante.empresa)
        conta = contas_por_nome.get(chave_empresa)
        if conta is None:
            conta = Conta(
                tenant_id=tenant_id,
                icp_id=icp_id,
                nome=participante.empresa.strip(),
                status="prospectada",
                origem="evento",
            )
            db.add(conta)
            db.flush()
            graph.upsert_conta(tenant_id, conta.id, {"nome": conta.nome, "cnpj": conta.cnpj})
            conta.neo4j_node_id = str(conta.id)
            contas_por_nome[chave_empresa] = conta
            contas_criadas += 1
        elif conta.id not in contas_tocadas:
            contas_reaproveitadas.add(conta.id)

        contas_tocadas[conta.id] = conta

        existentes = decisores_por_conta.setdefault(conta.id, [])
        nome_participante = _normalizar_nome(participante.nome)
        email_participante = participante.email.strip().lower() if participante.email else None
        ja_cadastrado = any(
            _normalizar_nome(decisor.nome) == nome_participante
            or (email_participante and decisor.email and decisor.email.strip().lower() == email_participante)
            for decisor in existentes
        )
        if ja_cadastrado:
            continue

        novo_decisor = Decisor(
            tenant_id=tenant_id,
            conta_id=conta.id,
            nome=participante.nome.strip(),
            cargo=participante.cargo,
            email=participante.email,
            telefone=participante.telefone,
        )
        db.add(novo_decisor)
        existentes.append(novo_decisor)
        decisores_criados += 1

    auditoria_service.registrar(
        db,
        tenant_id,
        "participantes_evento_importados",
        "icp",
        icp.id,
        ator_id,
        {"contas_criadas": contas_criadas, "decisores_criados": decisores_criados},
    )
    db.commit()
    for conta in contas_tocadas.values():
        db.refresh(conta)

    return {
        "contas_criadas": contas_criadas,
        "contas_reaproveitadas": len(contas_reaproveitadas),
        "decisores_criados": decisores_criados,
        "contas": list(contas_tocadas.values()),
    }


def listar_por_icp(db: Session, tenant_id: str, icp_id: int) -> list[Conta]:
    """Contas já geradas para um ICP — para a tela de Prospecção
    sobreviver a um refresh sem depender só da resposta pontual de
    `gerar_lista` (Onda F2)."""
    return db.query(Conta).filter_by(tenant_id=tenant_id, icp_id=icp_id).order_by(Conta.criado_em.desc()).all()


def obter(db: Session, tenant_id: str, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return conta


def _normalizar_dominio(dominio: str | None) -> str | None:
    """Aceita o que a pessoa colar (com ou sem `https://`, com ou sem
    caminho/barra final) e guarda só o host — `site_fetcher` monta a URL
    como `https://{dominio}`, então um valor como `https://empresa.com`
    salvo ao pé da letra virava `https://https://empresa.com` e quebrava
    a busca com erro de DNS (bug real reportado em produção)."""
    if not dominio:
        return None
    texto = dominio.strip()
    if not texto:
        return None
    if "://" not in texto:
        texto = f"//{texto}"
    netloc = urlparse(texto).netloc
    return (netloc or texto.lstrip("/")).rstrip("/") or None


def atualizar(
    db: Session, tenant_id: str, ator_id: str | None, conta_id: int, nome_fantasia: str | None, dominio: str | None
) -> Conta:
    """Edição manual da conta (E2-H2) — a Receita Federal não traz site, e
    a razão social nem sempre é a marca comercial conhecida; sem isto não
    havia como corrigir esses dois campos depois que a conta já existe."""
    conta = obter(db, tenant_id, conta_id)
    conta.nome_fantasia = nome_fantasia
    conta.dominio = _normalizar_dominio(dominio)

    auditoria_service.registrar(db, tenant_id, "conta_atualizada", "conta", conta.id, ator_id, {}, conta_id=conta.id)
    db.commit()
    db.refresh(conta)
    return conta


def atualizar_decisor(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    decisor_id: int,
    nome: str,
    cargo: str | None,
    email: str | None,
    telefone: str | None,
    linkedin_url: str | None,
) -> Decisor:
    decisor = db.query(Decisor).filter_by(id=decisor_id, conta_id=conta_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado nesta conta")
    decisor.nome = nome
    decisor.cargo = cargo
    decisor.email = email
    decisor.telefone = telefone
    decisor.linkedin_url = linkedin_url

    auditoria_service.registrar(
        db, tenant_id, "decisor_atualizado", "decisor", decisor.id, ator_id, {}, conta_id=conta_id
    )
    db.commit()
    db.refresh(decisor)
    return decisor


def enriquecer(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    llm: LLMProvider,
    site_fetcher: SiteFetcher,
) -> list[CampoEnriquecido]:
    """Pesquisa ampla dentro do site institucional da conta, com ficha de
    campos enriquecidos e fonte/data de cada dado (E2-H2).

    Não fica só na home: `site_fetcher` já tenta páginas de sobre,
    investidores, notícias e privacidade quando existem (best-effort). O
    prompt pede sinais de porte/atuação, crescimento, marcos históricos,
    novos projetos e presença de política de privacidade/LGPD — cobre
    prospecção para qualquer oferta, não só compliance. Cada página
    efetivamente pesquisada também vira um campo `pagina_pesquisada`, que
    funciona como o histórico da pesquisa feita.
    """
    conta = obter(db, tenant_id, conta_id)
    if not conta.dominio:
        raise RegraNegocioViolada("Conta sem domínio cadastrado — não é possível enriquecer via site.")

    try:
        texto_site = site_fetcher(conta.dominio)
    except httpx.HTTPError as erro:
        raise RegraNegocioViolada(f"Não foi possível acessar o site institucional: {erro}") from erro

    resposta = llm_helpers.gerar(
        llm,
        LLMRequest(
            prompt=(
                f"A seguir está o conteúdo de várias páginas do site institucional da empresa "
                f"{conta.nome} (cada uma marcada por '=== url ==='). A partir só do que estiver "
                "de fato presente no texto (nunca invente), liste em linhas no formato "
                "'campo: valor' sinais públicos relevantes para uma prospecção comercial: porte e "
                "área de atuação, crescimento ou expansão, marcos ou linha do tempo da empresa, "
                "lançamento de novos produtos/projetos, resultados financeiros ou informações "
                "voltadas a investidores, e se há (ou não) política de privacidade/menção a "
                "LGPD/DPO publicada. Se um desses pontos não aparecer no texto, não invente — "
                "simplesmente não escreva uma linha para ele. Termine com uma linha "
                "'possivel_dor: ' resumindo, em uma frase, qual dor ou necessidade de negócio os "
                "sinais encontrados sugerem.\n\n"
                f"{texto_site}"
            )
        )
    )

    agora = datetime.now(UTC)
    campos: list[CampoEnriquecido] = []
    for url_pagina in re.findall(r"=== (.*?) ===", texto_site):
        campos.append(
            CampoEnriquecido(
                conta_id=conta.id, campo="pagina_pesquisada", valor=url_pagina,
                fonte="pesquisa_no_site", coletado_em=agora,
            )
        )
    for linha in resposta.content.splitlines():
        if ":" not in linha:
            continue
        campo, valor = linha.split(":", 1)
        if not valor.strip():
            continue
        campos.append(
            CampoEnriquecido(
                conta_id=conta.id, campo=campo.strip(), valor=valor.strip(),
                fonte="pesquisa_no_site", coletado_em=agora,
            )
        )
    db.add_all(campos)

    auditoria_service.registrar(
        db,
        tenant_id,
        "conta_enriquecida",
        "conta",
        conta.id,
        ator_id,
        {"campos": len(campos)},
        conta_id=conta.id,
    )
    db.commit()
    for campo_registro in campos:
        db.refresh(campo_registro)
    return campos


def enriquecer_via_brasilapi(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    brasilapi_client: BrasilApiClient,
) -> list[CampoEnriquecido]:
    """Enriquecimento pontual de uma conta via BrasilAPI (Onda E) — dados
    já estruturados, complementares ao snapshot em lote da Receita
    Federal (mais recentes: telefone, e-mail, situação cadastral, CNAEs
    secundários). Sem LLM, ao contrário de `enriquecer()` (site
    institucional), pois a resposta já vem em JSON."""
    conta = obter(db, tenant_id, conta_id)
    if not conta.cnpj:
        raise RegraNegocioViolada("Conta sem CNPJ cadastrado — não é possível enriquecer via BrasilAPI.")

    try:
        resposta = brasilapi_client(conta.cnpj)
    except httpx.HTTPError as erro:
        raise RegraNegocioViolada(f"Não foi possível consultar a BrasilAPI: {erro}") from erro

    cnaes_secundarios = resposta.get("cnaes_secundarios") or []
    valores_por_campo = {
        "telefone": resposta.get("ddd_telefone_1"),
        "email": resposta.get("email"),
        "situacao_cadastral": resposta.get("descricao_situacao_cadastral"),
        "data_situacao_cadastral": resposta.get("data_situacao_cadastral"),
        "porte": resposta.get("descricao_porte"),
        "capital_social": resposta.get("capital_social"),
        "cnaes_secundarios": ", ".join(
            f"{item.get('codigo')} - {item.get('descricao')}" for item in cnaes_secundarios
        )
        if cnaes_secundarios
        else None,
    }

    agora = datetime.now(UTC)
    campos: list[CampoEnriquecido] = []
    for campo, valor in valores_por_campo.items():
        if valor in (None, ""):
            continue
        registro = CampoEnriquecido(
            conta_id=conta.id,
            campo=campo,
            valor=str(valor),
            fonte="brasilapi_cnpj",
            coletado_em=agora,
        )
        db.add(registro)
        campos.append(registro)

    auditoria_service.registrar(
        db,
        tenant_id,
        "conta_enriquecida_brasilapi",
        "conta",
        conta.id,
        ator_id,
        {"campos": len(campos)},
        conta_id=conta.id,
    )
    db.commit()
    for campo_registro in campos:
        db.refresh(campo_registro)
    return campos


def campos_enriquecidos(db: Session, conta_id: int) -> list[CampoEnriquecido]:
    return db.query(CampoEnriquecido).filter_by(conta_id=conta_id).all()


def mapear_decisores(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    account_data: AccountDataProvider,
    graph: Neo4jClient,
) -> list[Decisor]:
    """Decisores mapeados com cargo e canal provável, persistidos no grafo (E2-H2)."""
    conta = obter(db, tenant_id, conta_id)
    if not conta.cnpj:
        raise RegraNegocioViolada("Conta sem CNPJ — não é possível mapear decisores via QSA.")

    candidatos = account_data.buscar_decisores(conta.cnpj)

    decisores: list[Decisor] = []
    for candidato in candidatos:
        decisor = Decisor(
            tenant_id=tenant_id,
            conta_id=conta.id,
            nome=candidato.nome,
            cargo=candidato.qualificacao,
            canal_provavel="email",
        )
        db.add(decisor)
        db.flush()

        graph.upsert_decisor(tenant_id, decisor.id, conta.id, {"nome": decisor.nome, "cargo": decisor.cargo})
        decisor.neo4j_node_id = str(decisor.id)
        decisores.append(decisor)

    auditoria_service.registrar(
        db,
        tenant_id,
        "decisores_mapeados",
        "conta",
        conta.id,
        ator_id,
        {"quantidade": len(decisores)},
        conta_id=conta.id,
    )
    db.commit()
    for decisor in decisores:
        db.refresh(decisor)
    return decisores


def criar_decisor_manual(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    dados: DecisorCreateSchema,
    graph: Neo4jClient,
) -> Decisor:
    conta = obter(db, tenant_id, conta_id)

    decisor = Decisor(tenant_id=tenant_id, conta_id=conta.id, **dados.model_dump())
    db.add(decisor)
    db.flush()

    graph.upsert_decisor(tenant_id, decisor.id, conta.id, {"nome": decisor.nome, "cargo": decisor.cargo or ""})
    decisor.neo4j_node_id = str(decisor.id)

    auditoria_service.registrar(
        db, tenant_id, "decisor_criado_manual", "decisor", decisor.id, ator_id, {}, conta_id=conta.id
    )
    db.commit()
    db.refresh(decisor)
    return decisor


def decisores_da_conta(db: Session, conta_id: int) -> list[Decisor]:
    return db.query(Decisor).filter_by(conta_id=conta_id).all()


def grafo(db: Session, tenant_id: str, conta_id: int, graph: Neo4jClient) -> dict:
    """Visualização navegável do grafo por conta, com interações ligadas ao decisor (E2-H3)."""
    obter(db, tenant_id, conta_id)  # garante existência/isolamento por tenant
    return graph.grafo_da_conta(tenant_id, conta_id)


def exportar_pdf(db: Session, tenant_id: str, conta_id: int) -> bytes:
    """Exportação da ficha da conta em PDF (E2-H3)."""
    conta = obter(db, tenant_id, conta_id)
    decisores = decisores_da_conta(db, conta.id)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, text=conta.nome, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, text=f"CNPJ: {conta.cnpj or '-'}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, text=f"Porte: {conta.porte or '-'} | UF: {conta.regiao or '-'}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, text=f"Score de aderência: {conta.score_aderencia}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, text="Decisores", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    for decisor in decisores:
        pdf.cell(0, 8, text=f"- {decisor.nome} ({decisor.cargo or '-'})", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
