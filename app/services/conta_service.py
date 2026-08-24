import difflib
import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fpdf import FPDF
from sqlalchemy.orm import Session

from app.graph.client import Neo4jClient, sincronizar_com_tolerancia
from app.integrations.brasilapi_client import BrasilApiClient
from app.integrations.site_fetcher import HostNaoPublico, SiteFetcher
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.alerta_detrator import AlertaDetrator
from app.models.atividade import Atividade
from app.models.cadencia import Cadencia
from app.models.campanha import CampanhaDestinatario
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conta import Conta
from app.models.conta_franquia_consumo import ContaFranquiaConsumo
from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.decisor import Decisor
from app.models.descarte_conta import DescarteConta
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.models.icp import ICP
from app.models.indicacao import Indicacao
from app.models.interacao_conta import InteracaoConta
from app.models.lista_prospeccao import ListaProspeccao
from app.models.mensagem import Mensagem
from app.models.negocio import Negocio
from app.models.pesquisa_nps import PesquisaNps
from app.models.qualificacao import QualificacaoScore
from app.models.reuniao import Reuniao
from app.models.tarefa_linkedin import TarefaLinkedin
from app.models.usuario import Usuario
from app.providers.account_data.base import AccountDataProvider, ContaCandidata, DecisorCandidato, FiltroBusca
from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos
from app.providers.web_search.base import WebSearchProvider
from app.schemas.conta import ParticipanteEventoSchema
from app.schemas.decisor import DecisorCreateSchema
from app.services import atividade_service, auditoria_service, descarte_service, llm_helpers
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

        if sincronizar_com_tolerancia(
            lambda: graph.upsert_conta(tenant_id, conta.id, {"nome": conta.nome, "cnpj": conta.cnpj}), "conta", conta.id
        ):
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


def criar_lead(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    nome: str,
    cnpj: str | None,
    dominio: str | None,
    segmento: str | None = None,
    porte: str | None = None,
    regiao: str | None = None,
) -> Conta:
    """Cadastro de cliente avulso ("lead") direto no CRM — indicação,
    evento, contato pessoal — que não se enquadra no recorte estático de
    nenhum ICP (segmento/porte/dor variam de cliente para cliente). Ao
    contrário de `criar_manual`, não exige um ICP: `icp_id` fica nulo."""
    conta = Conta(
        tenant_id=tenant_id,
        icp_id=None,
        nome=nome,
        cnpj=cnpj,
        dominio=_normalizar_dominio(dominio),
        segmento=segmento,
        porte=porte,
        regiao=regiao,
        status="prospectada",
        origem="lead",
    )
    db.add(conta)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "lead_criado", "conta", conta.id, ator_id, {"nome": nome})
    db.commit()
    db.refresh(conta)
    return conta


def criar_a_partir_de_convite_rede_social(
    db: Session, tenant_id: str, nome: str, cnpj: str | None, nome_contato: str, email_contato: str
) -> Conta:
    """Empresa convidada por um vendedor pela Rede Social e que aceitou o
    convite-vitrine (virou tenant próprio) já entra também como prospect no
    CRM de quem convidou — contato inicial vem do próprio cadastro de
    aceite do convite. CNPJ vem do que a empresa já preencheu ao aceitar
    (campo opcional do formulário); continua editável depois, igual
    qualquer outra conta.

    De propósito **não comita** — quem chama (`tenant_service.criar_tenant_vitrine`)
    precisa que isso aconteça na mesma transação da criação do tenant."""
    conta = Conta(
        tenant_id=tenant_id,
        icp_id=None,
        nome=nome,
        cnpj=cnpj,
        status="prospectada",
        origem="rede_social_convite",
    )
    db.add(conta)
    db.flush()

    decisor = Decisor(
        tenant_id=tenant_id, conta_id=conta.id, nome=nome_contato, email=email_contato,
        origem="rede_social_convite",
    )
    db.add(decisor)
    db.flush()

    atividade_service.registrar(
        db, tenant_id, conta_id=conta.id, tipo="sistema",
        descricao="Empresa cadastrada automaticamente via convite de Rede Social aceito",
    )
    auditoria_service.registrar(
        db, tenant_id, "conta_criada_via_rede_social", "conta", conta.id, None, {"nome": nome}, conta_id=conta.id
    )
    return conta


def _leads_visiveis(db: Session, tenant_id: str, usuario: Usuario, vendedor_usuario_id: int | None):
    """Mesma regra de escopo por papel de `saude_conta_service._contas_visiveis`
    (user só vê as próprias contas; admin/super_admin veem todas e podem
    filtrar por vendedor), restrita a contas sem ICP (leads avulsos)."""
    query = db.query(Conta).filter_by(tenant_id=tenant_id).filter(Conta.icp_id.is_(None))
    if usuario.papel == "user":
        query = query.filter_by(vendedor_usuario_id=usuario.id)
    elif vendedor_usuario_id is not None:
        query = query.filter_by(vendedor_usuario_id=vendedor_usuario_id)
    return query


def listar_leads(
    db: Session, tenant_id: str, usuario: Usuario, vendedor_usuario_id: int | None = None
) -> list[Conta]:
    return _leads_visiveis(db, tenant_id, usuario, vendedor_usuario_id).order_by(Conta.id.desc()).all()


def listar_decisores_leads(
    db: Session, tenant_id: str, usuario: Usuario, vendedor_usuario_id: int | None = None
) -> list[Decisor]:
    conta_ids = [conta.id for conta in _leads_visiveis(db, tenant_id, usuario, vendedor_usuario_id).all()]
    if not conta_ids:
        return []
    return db.query(Decisor).filter(Decisor.conta_id.in_(conta_ids)).order_by(Decisor.id.desc()).all()


def _normalizar_nome(nome: str) -> str:
    return " ".join(nome.split()).lower()


def _acrescentar_observacao(conta: Conta, texto: str | None) -> None:
    """Acumula observação vinda da planilha no campo livre da conta — várias
    linhas da mesma empresa podem trazer textos diferentes; não duplica se
    o mesmo texto já estiver lá (participante repetido, ou reimportação)."""
    texto = (texto or "").strip()
    if not texto:
        return
    if conta.observacoes and texto in conta.observacoes:
        return
    conta.observacoes = f"{conta.observacoes}\n{texto}" if conta.observacoes else texto


def importar_participantes(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    lista_id: int,
    participantes: list[ParticipanteEventoSchema],
    graph: Neo4jClient,
) -> dict:
    """Cria contas a partir de uma listagem de participantes (planilha
    colada) de uma Lista de Prospecção — sem CNPJ, então a empresa é
    reconhecida pelo nome (normalizado), não por dado da Receita Federal.
    Cada linha vira um decisor dentro da conta da sua empresa; empresas
    repetidas na lista (ou já existentes no tenant) são reaproveitadas em
    vez de duplicadas. `icp_id` da conta vem da lista (opcional — pode
    ficar sem ICP, mesmo tratamento de lead avulso). Não passa pelo score
    de aderência do ICP nem consome franquia — mesmo raciocínio de
    `gerar_lista`: só consome quando a conta entra numa cadência ativada."""
    lista = db.query(ListaProspeccao).filter_by(id=lista_id, tenant_id=tenant_id).one_or_none()
    if lista is None:
        raise NaoEncontrado(f"Lista de prospecção {lista_id} não encontrada")

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
    ids_contas_novas: list[int] = []

    for participante in participantes:
        chave_empresa = _normalizar_nome(participante.empresa)
        conta = contas_por_nome.get(chave_empresa)
        if conta is None:
            conta = Conta(
                tenant_id=tenant_id,
                icp_id=lista.icp_id,
                lista_prospeccao_id=lista.id,
                nome=participante.empresa.strip(),
                status="prospectada",
                origem="lista_prospeccao",
            )
            db.add(conta)
            db.flush()
            if sincronizar_com_tolerancia(
                lambda: graph.upsert_conta(tenant_id, conta.id, {"nome": conta.nome, "cnpj": conta.cnpj}), "conta", conta.id
            ):
                conta.neo4j_node_id = str(conta.id)
            contas_por_nome[chave_empresa] = conta
            contas_criadas += 1
            ids_contas_novas.append(conta.id)
        elif conta.id not in contas_tocadas:
            contas_reaproveitadas.add(conta.id)

        contas_tocadas[conta.id] = conta
        _acrescentar_observacao(conta, participante.observacoes)

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
        "participantes_lista_importados",
        "lista_prospeccao",
        lista.id,
        ator_id,
        {"contas_criadas": contas_criadas, "decisores_criados": decisores_criados},
    )
    db.commit()
    for conta in contas_tocadas.values():
        db.refresh(conta)

    if ids_contas_novas:
        # Import local pra evitar ciclo de import entre os dois módulos
        # (enriquecimento_fila_service chama de volta funções deste
        # arquivo). Enriquecimento roda em lote pelo cron depois, nunca
        # aqui — uma planilha grande travando o request esperando LLM/
        # busca web/Lusha por empresa estouraria o timeout do proxy do
        # Render (raio-X, mesmo raciocínio do recorte de CNPJ).
        from app.services import enriquecimento_fila_service

        enriquecimento_fila_service.enfileirar(db, tenant_id, ids_contas_novas)

    return {
        "contas_criadas": contas_criadas,
        "contas_reaproveitadas": len(contas_reaproveitadas),
        "decisores_criados": decisores_criados,
        "contas": list(contas_tocadas.values()),
        "contas_enfileiradas_para_enriquecimento": len(ids_contas_novas),
    }


def listar_por_icp(db: Session, tenant_id: str, icp_id: int) -> list[Conta]:
    """Contas já geradas para um ICP — para a tela de Prospecção
    sobreviver a um refresh sem depender só da resposta pontual de
    `gerar_lista` (Onda F2)."""
    return db.query(Conta).filter_by(tenant_id=tenant_id, icp_id=icp_id).order_by(Conta.criado_em.desc()).all()


def listar_por_lista(db: Session, tenant_id: str, lista_prospeccao_id: int) -> list[Conta]:
    """Contas de uma Lista de Prospecção específica — mesmo raciocínio de
    `listar_por_icp`, mas pro agrupamento por lote de importação."""
    return (
        db.query(Conta)
        .filter_by(tenant_id=tenant_id, lista_prospeccao_id=lista_prospeccao_id)
        .order_by(Conta.criado_em.desc())
        .all()
    )


def listar_todas(db: Session, tenant_id: str) -> list[Conta]:
    """Toda conta do tenant, com ou sem ICP — usado pelo seletor "conta
    existente" do Kanban (E2), que antes só listava contas de um ICP e
    deixava um lead (conta sem ICP) impossível de escolher pra criar um
    negócio nele."""
    return db.query(Conta).filter_by(tenant_id=tenant_id).order_by(Conta.criado_em.desc()).all()


def obter(db: Session, tenant_id: str, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return conta


def _sinais_de_trabalho_real(db: Session, tenant_id: str, conta: Conta, decisor_ids: list[int]) -> list[str]:
    """Levanta o que já aconteceu de verdade nesta conta — usado por
    `excluir` pra recusar apagar quando há qualquer sinal de trabalho
    (mesmo que pequeno). Não é uma exclusão genérica de conta com
    qualquer histórico: é especificamente pra desfazer uma importação de
    planilha malfeita antes de mexer nela (pedido do usuário), então erra
    pro lado de bloquear, não de apagar em cascata dado real."""
    sinais = []
    if db.query(Negocio).filter_by(tenant_id=tenant_id, conta_id=conta.id).first() is not None:
        sinais.append("negócio no CRM")
    if db.query(Atividade).filter_by(tenant_id=tenant_id, conta_id=conta.id).first() is not None:
        sinais.append("atividade registrada")
    if db.query(Cadencia).filter_by(tenant_id=tenant_id, conta_id=conta.id).first() is not None:
        sinais.append("cadência de prospecção")
    if decisor_ids:
        if db.query(Mensagem).filter(Mensagem.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("mensagem enviada")
        if db.query(Reuniao).filter(Reuniao.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("reunião agendada")
        if db.query(ConversaQualificacao).filter(ConversaQualificacao.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("conversa de qualificação")
        if db.query(PesquisaNps).filter(PesquisaNps.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("pesquisa de NPS")
        if db.query(TarefaLinkedin).filter(TarefaLinkedin.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("tarefa de LinkedIn")
        if db.query(Indicacao).filter(Indicacao.promotor_decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("indicação")
        if db.query(CampanhaDestinatario).filter(CampanhaDestinatario.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("campanha de e-mail/WhatsApp")
        if db.query(AlertaDetrator).filter(AlertaDetrator.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("alerta de detrator")
        if db.query(QualificacaoScore).filter(QualificacaoScore.decisor_id.in_(decisor_ids)).first() is not None:
            sinais.append("score de qualificação")
    return sinais


def excluir(db: Session, tenant_id: str, ator_id: str | None, conta_id: int) -> None:
    """Apaga uma conta de verdade — diferente de `icp_service.excluir`,
    que só desvincula (`icp_id = None`) em vez de apagar: aqui o objetivo
    é corrigir uma importação de planilha malfeita e poder reimportar do
    zero com as funcionalidades novas (cargo-alvo, fila de
    enriquecimento, mapeamento de coluna) — reimportar só funciona se a
    conta antiga sumir de verdade, senão o dedupe por nome reaproveita a
    conta velha em vez de criar uma nova.

    Recusa apagar (`RegraNegocioViolada`) se houver qualquer sinal de
    trabalho real já feito na conta — negócio, mensagem, reunião etc.
    (ver `_sinais_de_trabalho_real`). Só contas recém-importadas e nunca
    trabalhadas podem ser removidas por aqui."""
    conta = obter(db, tenant_id, conta_id)
    decisor_ids = [
        decisor_id for (decisor_id,) in db.query(Decisor.id).filter_by(tenant_id=tenant_id, conta_id=conta.id).all()
    ]

    sinais = _sinais_de_trabalho_real(db, tenant_id, conta, decisor_ids)
    if sinais:
        raise RegraNegocioViolada(
            f'"{conta.nome}" já tem {", ".join(sinais)} — só contas recém-importadas, sem histórico de '
            f"trabalho, podem ser apagadas pra reimportar."
        )

    db.query(CampoEnriquecido).filter_by(conta_id=conta.id).delete(synchronize_session=False)
    db.query(FilaEnriquecimentoConta).filter_by(tenant_id=tenant_id, conta_id=conta.id).delete(synchronize_session=False)
    db.query(InteracaoConta).filter_by(tenant_id=tenant_id, conta_id=conta.id).delete(synchronize_session=False)
    db.query(ContaFranquiaConsumo).filter_by(tenant_id=tenant_id, conta_id=conta.id).delete(synchronize_session=False)
    db.query(DescarteConta).filter_by(tenant_id=tenant_id, conta_id=conta.id).delete(synchronize_session=False)
    if decisor_ids:
        db.query(Decisor).filter(Decisor.id.in_(decisor_ids)).delete(synchronize_session=False)

    auditoria_service.registrar(db, tenant_id, "conta_excluida", "conta", conta.id, ator_id, {"nome": conta.nome})
    db.delete(conta)
    db.commit()


def excluir_lote_por_lista(db: Session, tenant_id: str, ator_id: str | None, lista_prospeccao_id: int) -> dict:
    """Apaga em lote todas as contas de uma Lista de Prospecção — cada
    conta passa pelo mesmo crivo de `excluir` (recusa individual não
    aborta o lote inteiro, só aquela conta continua existindo)."""
    contas = listar_por_lista(db, tenant_id, lista_prospeccao_id)
    apagadas = 0
    bloqueadas: list[dict] = []
    for conta in contas:
        try:
            excluir(db, tenant_id, ator_id, conta.id)
            apagadas += 1
        except RegraNegocioViolada as erro:
            bloqueadas.append({"conta_id": conta.id, "nome": conta.nome, "motivo": str(erro)})
    return {"apagadas": apagadas, "bloqueadas": len(bloqueadas), "detalhes_bloqueadas": bloqueadas}


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


# Domínios que aparecem com frequência nos primeiros resultados de busca
# mas nunca são o site institucional da empresa — descartados ao tentar
# descobrir o domínio automaticamente (evita salvar o perfil do LinkedIn
# da empresa, ou um portal de agendamento/marketplace/diretório terceiro,
# como se fosse o site dela). Complementa (não substitui) a checagem de
# similaridade em `_descobrir_dominio` — ver comentário lá.
_DOMINIOS_IGNORADOS_BUSCA = {
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "wikipedia.org", "indeed.com", "glassdoor.com",
    "econodata.com.br", "cnpj.biz",
    # Portais/marketplaces/diretórios que listam empresas de terceiros —
    # aparecem bem rankeados pra razão social completa mas nunca são o
    # site da própria empresa (raio-X de produção: pegaram
    # "guia.agendarconsulta.com" e "dnb.com" no lugar do site real).
    "agendarconsulta.com", "doctoralia.com.br", "boaconsulta.com",
    "reclameaqui.com.br", "mercadolivre.com.br", "empresascnpj.com",
    "dnb.com", "bloomberg.com", "crunchbase.com", "zoominfo.com", "manta.com",
}

# Sufixos de natureza jurídica (com variações comuns de grafia) — a razão
# social crua ("Empresa X Ltda ME") quase nunca aparece assim no próprio
# site da empresa, então mandar isso pra busca faz mecanismos de busca
# priorizarem diretórios/agregadores de terceiros (que listam pela razão
# social completa) acima do site oficial (que usa o nome de marca).
_SUFIXOS_NATUREZA_JURIDICA = re.compile(
    r"\b(LTDA\.?|EIRELI|EPP|MEI|SCP|S\.?\s*/?\s*A\.?|SOCIEDADE\s+AN[ÔO]NIMA|"
    r"SOCIEDADE\s+SIMPLES|ME)\b\.?",
    re.IGNORECASE,
)

# Abaixo desta similaridade (0-1, `difflib.SequenceMatcher.ratio`) entre o
# nome da empresa e o domínio candidato, prefere não achar nada a arriscar
# um diretório/agregador desconhecido — a lista acima nunca vai cobrir
# todos eles (raio-X: "dnb.com" apareceu sem estar na lista até então).
_SIMILARIDADE_MINIMA_DOMINIO = 0.3


def _nome_para_busca(nome_empresa: str) -> str:
    """Remove sufixos de natureza jurídica antes de montar a query de
    busca — ver `_SUFIXOS_NATUREZA_JURIDICA`."""
    limpo = _SUFIXOS_NATUREZA_JURIDICA.sub("", nome_empresa)
    return re.sub(r"\s+", " ", limpo).strip() or nome_empresa


def _slug(texto: str) -> str:
    """Só letras/números em minúsculo, sem acento — forma comparável entre
    nome de empresa e núcleo de domínio (ambos tendem a virar isto na
    prática: "Total Life" e "totallife.com.br" viram "totallife")."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _nucleo_dominio(dominio: str) -> str:
    """Primeiro rótulo do domínio, sem "www." — "www.totallife.com.br"
    vira "totallife", o pedaço que de fato costuma remeter à marca."""
    sem_www = re.sub(r"^www\.", "", dominio, flags=re.IGNORECASE)
    return sem_www.split(".")[0]


def _descobrir_dominio(nome_empresa: str, web_search: WebSearchProvider) -> str | None:
    """Descoberta best-effort do site oficial via busca na web, usada
    quando a conta ainda não tem domínio cadastrado (E2-H2). Entre os
    resultados que não são um domínio conhecido por nunca ser o site
    institucional (`_DOMINIOS_IGNORADOS_BUSCA`), fica com o mais parecido
    com o nome da empresa — não simplesmente o primeiro da lista.

    A lista de bloqueio sozinha nunca cobre todo diretório/agregador que
    existe (raio-X de produção: "dnb.com" veio antes de entrar na lista);
    comparar o nome ajuda a rejeitar esse tipo de resultado mesmo sem
    conhecê-lo de antemão — se nada bater o suficiente, prefere não achar
    nada a arriscar um domínio errado (cai no aviso de cadastro manual)."""
    nome_limpo = _nome_para_busca(nome_empresa)
    nome_alvo = _slug(nome_limpo)
    melhor_dominio: str | None = None
    melhor_similaridade = 0.0
    for resultado in web_search.buscar(f"{nome_limpo} site oficial"):
        dominio = _normalizar_dominio(resultado.url)
        if not dominio or any(dominio == d or dominio.endswith(f".{d}") for d in _DOMINIOS_IGNORADOS_BUSCA):
            continue
        similaridade = difflib.SequenceMatcher(None, nome_alvo, _slug(_nucleo_dominio(dominio))).ratio()
        if similaridade > melhor_similaridade:
            melhor_dominio, melhor_similaridade = dominio, similaridade
    if melhor_dominio is None or melhor_similaridade < _SIMILARIDADE_MINIMA_DOMINIO:
        return None
    return melhor_dominio


def atualizar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    nome: str,
    cnpj: str | None,
    nome_fantasia: str | None,
    dominio: str | None,
    segmento: str | None,
    porte: str | None,
    regiao: str | None,
    resumo_site: str | None = None,
    observacoes: str | None = None,
) -> Conta:
    """Edição manual da conta (E2-H2) — dados vindos de enriquecimento
    automático (Receita Federal, PREDATOR) nem sempre batem com a
    realidade (segmento errado, CNPJ digitado errado na importação,
    razão social desatualizada), e não havia como corrigir depois que a
    conta já existe."""
    conta = obter(db, tenant_id, conta_id)
    conta.nome = nome
    conta.cnpj = cnpj
    conta.nome_fantasia = nome_fantasia
    conta.dominio = _normalizar_dominio(dominio)
    conta.segmento = segmento
    conta.porte = porte
    conta.regiao = regiao
    conta.resumo_site = resumo_site
    conta.observacoes = observacoes

    auditoria_service.registrar(db, tenant_id, "conta_atualizada", "conta", conta.id, ator_id, {}, conta_id=conta.id)
    db.commit()
    db.refresh(conta)
    return conta


def definir_proximo_passo(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    proximo_passo: str | None,
    proximo_passo_em: datetime | None,
) -> Conta:
    """Próxima ação prevista na conta (E-Leads) — em endpoint próprio, e não
    dentro de `atualizar()`, para que salvar nome/domínio nunca apague sem
    querer um próximo passo já anotado (o form de edição de conta não
    manda esses dois campos)."""
    conta = obter(db, tenant_id, conta_id)
    conta.proximo_passo = proximo_passo
    conta.proximo_passo_em = proximo_passo_em

    auditoria_service.registrar(
        db, tenant_id, "proximo_passo_definido", "conta", conta.id, ator_id, {}, conta_id=conta.id
    )
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
    nova_conta_id: int | None = None,
) -> Decisor:
    """`nova_conta_id`, quando presente e diferente da conta atual, move o
    contato pra outra empresa do mesmo tenant (E2-H2) — contato cadastrado
    na empresa errada por engano, ou que mudou de emprego, sem precisar
    excluir e recriar do zero."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, conta_id=conta_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado nesta conta")
    decisor.nome = nome
    decisor.cargo = cargo
    decisor.email = email
    decisor.telefone = telefone
    decisor.linkedin_url = linkedin_url

    conta_destino_id = conta_id
    if nova_conta_id is not None and nova_conta_id != conta_id:
        obter(db, tenant_id, nova_conta_id)  # 404 se não existir/não for do tenant
        decisor.conta_id = nova_conta_id
        conta_destino_id = nova_conta_id

    auditoria_service.registrar(
        db, tenant_id, "decisor_atualizado", "decisor", decisor.id, ator_id, {}, conta_id=conta_destino_id
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
    web_search: WebSearchProvider,
) -> list[CampoEnriquecido]:
    """Pesquisa ampla dentro do site institucional da conta, com ficha de
    campos enriquecidos e fonte/data de cada dado (E2-H2).

    Não fica só na home: `site_fetcher` já tenta páginas de sobre,
    investidores, notícias, vagas abertas e privacidade quando existem
    (best-effort). O prompt pede sinais de porte/atuação, crescimento,
    marcos históricos, novos projetos, vagas abertas e presença de
    política de privacidade/LGPD — cobre prospecção para qualquer
    oferta, não só compliance. Cada página efetivamente pesquisada
    também vira um campo `pagina_pesquisada`, que funciona como o
    histórico da pesquisa feita.

    Se a conta ainda não tem domínio cadastrado, tenta descobrir o site
    oficial sozinha via `web_search` e já salva o domínio encontrado na
    ficha da empresa — não busca de novo nas próximas pesquisas.
    """
    conta = obter(db, tenant_id, conta_id)
    dominio_descoberto: str | None = None
    if not conta.dominio:
        dominio_descoberto = _descobrir_dominio(conta.nome_fantasia or conta.nome, web_search)
        if not dominio_descoberto:
            raise RegraNegocioViolada(
                "Não foi possível descobrir automaticamente o site da empresa — "
                "cadastre o domínio manualmente e tente de novo."
            )
        conta.dominio = dominio_descoberto
        db.flush()

    try:
        texto_site = site_fetcher(conta.dominio)
    except HostNaoPublico as erro:
        raise RegraNegocioViolada(
            f'Não conseguimos acessar "{conta.dominio}" — o domínio não existe ou não resolve. '
            'Confirme o endereço em "Editar dados da conta".'
        ) from erro
    except httpx.HTTPStatusError as erro:
        raise RegraNegocioViolada(
            f'O site "{conta.dominio}" recusou o acesso (erro {erro.response.status_code}) — pode ser '
            'proteção antibot do próprio site, ou o domínio pode não ser o correto. Confirme em '
            '"Editar dados da conta" ou tente novamente mais tarde.'
        ) from erro
    except httpx.HTTPError as erro:
        raise RegraNegocioViolada(
            f'Não conseguimos acessar "{conta.dominio}" agora (site fora do ar ou muito lento). '
            "Tente novamente mais tarde."
        ) from erro

    resposta = llm_helpers.gerar(
        llm,
        LLMRequest(
            prompt=(
                f"A seguir está o conteúdo de várias páginas do site institucional da empresa "
                f"{conta.nome} (cada uma marcada por '=== url ==='). A partir só do que estiver "
                "de fato presente no texto (nunca invente), liste em linhas no formato "
                "'campo: valor' sinais públicos relevantes para uma prospecção comercial e para a "
                "abordagem de decisores: porte e área de atuação, crescimento ou expansão, marcos "
                "ou linha do tempo da empresa, lançamento de novos produtos/projetos, resultados "
                "financeiros ou informações voltadas a investidores, vagas abertas ou áreas em "
                "contratação (sinal de crescimento e ponto de entrada pra abordagem), e se há (ou "
                "não) política de privacidade/menção a LGPD/DPO publicada. Se um desses pontos não "
                "aparecer no texto, não invente — simplesmente não escreva uma linha para ele. "
                "Termine com uma linha 'possivel_dor: ' resumindo, em uma frase, qual dor ou "
                "necessidade de negócio os sinais encontrados sugerem.\n\n"
                f"{texto_site}"
            )
        )
    )

    agora = datetime.now(UTC)
    campos: list[CampoEnriquecido] = []
    if dominio_descoberto:
        campos.append(
            CampoEnriquecido(
                conta_id=conta.id, campo="dominio_descoberto_automaticamente", valor=dominio_descoberto,
                fonte="busca_web", coletado_em=agora,
            )
        )
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

    if not conta.resumo_site or not conta.resumo_site.strip():
        conta.resumo_site = resposta.content

    atividade_service.registrar(
        db, tenant_id, conta_id=conta.id, tipo="sistema", descricao="IA pesquisou o site institucional",
        ator_id=ator_id,
    )
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

    atividade_service.registrar(
        db, tenant_id, conta_id=conta.id, tipo="sistema", descricao="IA enriqueceu via BrasilAPI", ator_id=ator_id
    )
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


def _normalizar_nome_decisor(nome: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acentos.lower().split())


def _dados_candidato(candidato: DecisorCandidato | ContatoCandidato) -> dict:
    return {
        "nome": candidato.nome,
        "cargo": getattr(candidato, "qualificacao", None) or getattr(candidato, "cargo", None),
        "email": getattr(candidato, "email", None),
        "telefone": getattr(candidato, "telefone", None),
        "linkedin_url": getattr(candidato, "linkedin_url", None),
        "fonte": candidato.fonte,
    }


def mapear_decisores(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_id: int,
    account_data: AccountDataProvider,
    contact_enrichment: ContactEnrichmentProvider,
    graph: Neo4jClient,
) -> list[Decisor]:
    """Decisores mapeados combinando o QSA da Receita Federal (sócios/
    administradores formais, quando a conta tem CNPJ) com uma base de
    enriquecimento de contatos (C-Levels, Diretores, Gerentes e Heads que
    não aparecem no QSA por não terem participação societária),
    persistidos no grafo (E2-H2).

    Se a conta pertence a uma Lista de Prospecção com `cargos_alvo`
    definido (ex.: só "CISO"/"Diretor de Segurança" pra um projeto de
    cibersegurança), a busca no provedor de enriquecimento já sai
    restrita a esses cargos — filtra na requisição, não depois de já ter
    revelado o contato, economizando consulta de verdade. Sem lista (ou
    lista sem cargos definidos), cai no default genérico do provider."""
    conta = obter(db, tenant_id, conta_id)

    kwargs_filtro: dict = {"nome_empresa": conta.nome_fantasia or conta.nome, "dominio": conta.dominio, "cnpj": conta.cnpj}
    if conta.lista_prospeccao_id:
        lista = db.query(ListaProspeccao).filter_by(id=conta.lista_prospeccao_id).one_or_none()
        if lista is not None and lista.cargos_alvo:
            kwargs_filtro["cargos_alvo"] = lista.cargos_alvo

    candidatos: list[DecisorCandidato | ContatoCandidato] = []
    if conta.cnpj:
        candidatos.extend(account_data.buscar_decisores(conta.cnpj))
    candidatos.extend(contact_enrichment.buscar_contatos(FiltroContatos(**kwargs_filtro)))

    existentes = {_normalizar_nome_decisor(d.nome): d for d in decisores_da_conta(db, conta.id)}
    novos = 0
    for candidato in candidatos:
        dados = _dados_candidato(candidato)
        chave = _normalizar_nome_decisor(dados["nome"])

        decisor_existente = existentes.get(chave)
        if decisor_existente is not None:
            # Já mapeado antes (reclique ou mesma pessoa nas duas fontes) —
            # só completa o que estava vazio, não duplica a linha.
            decisor_existente.email = decisor_existente.email or dados["email"]
            decisor_existente.telefone = decisor_existente.telefone or dados["telefone"]
            decisor_existente.linkedin_url = decisor_existente.linkedin_url or dados["linkedin_url"]
            decisor_existente.origem = decisor_existente.origem or dados["fonte"]
            continue

        decisor = Decisor(
            tenant_id=tenant_id,
            conta_id=conta.id,
            nome=dados["nome"],
            cargo=dados["cargo"],
            canal_provavel="email",
            email=dados["email"],
            telefone=dados["telefone"],
            linkedin_url=dados["linkedin_url"],
            origem=dados["fonte"],
        )
        db.add(decisor)
        db.flush()

        if sincronizar_com_tolerancia(
            lambda: graph.upsert_decisor(tenant_id, decisor.id, conta.id, {"nome": decisor.nome, "cargo": decisor.cargo}),
            "decisor",
            decisor.id,
        ):
            decisor.neo4j_node_id = str(decisor.id)
        existentes[chave] = decisor
        novos += 1

    atividade_service.registrar(
        db, tenant_id, conta_id=conta.id, tipo="sistema", descricao=f"IA mapeou {novos} decisor(es)",
        ator_id=ator_id,
    )
    auditoria_service.registrar(
        db,
        tenant_id,
        "decisores_mapeados",
        "conta",
        conta.id,
        ator_id,
        {"quantidade": novos},
        conta_id=conta.id,
    )
    db.commit()
    return decisores_da_conta(db, conta.id)


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

    if sincronizar_com_tolerancia(
        lambda: graph.upsert_decisor(tenant_id, decisor.id, conta.id, {"nome": decisor.nome, "cargo": decisor.cargo or ""}),
        "decisor",
        decisor.id,
    ):
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


def _texto_seguro_pdf(texto: str) -> str:
    """A fonte core "Helvetica" do fpdf2 só suporta Latin-1/cp1252 — nome de
    empresa/decisor com aspas curvas, travessão longo etc. (comum em texto
    colado do Word) derruba a exportação com `FPDFUnicodeEncodingException`.
    Troca o que não é suportado por "?" em vez de deixar a exceção estourar.

    Normaliza pra NFC antes: nome vindo de fornecedor externo (Lusha) pode
    chegar com acento em forma decomposta (\"e\" + acento agudo combinante,
    em vez de \"é\" pré-composto) — o acento combinante sozinho fica fora
    do Latin-1 e virava \"?\" (ex.: \"César\" -> \"Ce?sar\"), mesmo o
    caractere final sendo perfeitamente representável em Latin-1."""
    texto = unicodedata.normalize("NFC", texto)
    return texto.encode("latin-1", errors="replace").decode("latin-1")


def exportar_pdf(db: Session, tenant_id: str, conta_id: int) -> bytes:
    """Exportação da ficha da conta em PDF (E2-H3)."""
    conta = obter(db, tenant_id, conta_id)
    decisores = decisores_da_conta(db, conta.id)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, text=_texto_seguro_pdf(conta.nome), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, text=_texto_seguro_pdf(f"CNPJ: {conta.cnpj or '-'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, text=_texto_seguro_pdf(f"Porte: {conta.porte or '-'} | UF: {conta.regiao or '-'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, text=f"Score de aderência: {conta.score_aderencia}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, text="Decisores", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    for decisor in decisores:
        contato = " · ".join(valor for valor in (decisor.email, decisor.telefone) if valor)
        linha = f"- {decisor.nome} ({decisor.cargo or '-'})" + (f" — {contato}" if contato else "")
        pdf.cell(0, 8, text=_texto_seguro_pdf(linha), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
