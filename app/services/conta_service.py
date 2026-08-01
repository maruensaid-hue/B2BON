from datetime import UTC, datetime

import httpx
from fpdf import FPDF
from sqlalchemy.orm import Session

from app.graph.client import Neo4jClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.providers.account_data.base import AccountDataProvider, ContaCandidata, FiltroBusca
from app.schemas.decisor import DecisorCreateSchema
from app.services import auditoria_service, descarte_service
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


def obter(db: Session, tenant_id: str, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return conta


def enriquecer(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    llm: LLMProvider,
    site_fetcher: SiteFetcher,
) -> list[CampoEnriquecido]:
    """Ficha de conta com campos enriquecidos e fonte/data de cada dado (E2-H2).

    Fetch do site institucional + extração por IA (Seção 11 da especificação).
    """
    conta = obter(db, tenant_id, conta_id)
    if not conta.dominio:
        raise RegraNegocioViolada("Conta sem domínio cadastrado — não é possível enriquecer via site.")

    try:
        texto_site = site_fetcher(conta.dominio)
    except httpx.HTTPError as erro:
        raise RegraNegocioViolada(f"Não foi possível acessar o site institucional: {erro}") from erro

    resposta = llm.generate(
        LLMRequest(
            prompt=(
                f"A partir do texto a seguir do site da empresa {conta.nome}, liste sinais "
                "públicos de porte e atuação em linhas no formato 'campo: valor'.\n\n"
                f"{texto_site}"
            )
        )
    )

    agora = datetime.now(UTC)
    campos: list[CampoEnriquecido] = []
    for linha in resposta.content.splitlines():
        if ":" not in linha:
            continue
        campo, valor = linha.split(":", 1)
        registro = CampoEnriquecido(
            conta_id=conta.id,
            campo=campo.strip(),
            valor=valor.strip(),
            fonte="site_institucional",
            coletado_em=agora,
        )
        db.add(registro)
        campos.append(registro)

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
