import re
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.atividade import Atividade
from app.models.canal_sala import CanalSala
from app.models.conexao_empresa import ConexaoEmpresa
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.icp import ICP
from app.models.intent import Intent
from app.models.mensagem_rede_social import MensagemRedeSocial
from app.models.mensagem_sala import MensagemSala
from app.models.negocio import Negocio
from app.models.oferta import Oferta
from app.models.perfil_empresa import PerfilEmpresa
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial
from app.models.sala_corporativa import SalaCorporativa
from app.models.sinal_oportunidade import SinalOportunidade
from app.models.tenant import Tenant
from app.services import auditoria_service, conta_service, llm_helpers
from app.services.errors import NaoEncontrado, RegraNegocioViolada

_STATUS_SINAL_IMUTAVEIS = {"convertido", "descartado"}

_PALAVRAS_IGNORADAS = {
    "de", "da", "do", "das", "dos", "para", "com", "sem", "por", "que", "uma", "um",
    "uns", "umas", "não", "nao", "mais", "menos", "the", "and", "for", "com", "seu", "sua",
}

_PESO_CNAE = 0.5
_PESO_UF = 0.3
_PESO_PORTE = 0.2


def calcular_fit_icp(icp: ICP, perfil_candidato: PerfilEmpresa) -> dict:
    """ICP Agent (master prompt §25, §60 ICP+Network, Fase 3B) — mesmos
    pesos de `conta_service._score_aderencia` (CNAE 0.5 + UF 0.3 +
    porte 0.2), aplicados contra o perfil de outro tenant da Rede
    Social em vez de uma `ContaCandidata` raspada. Nunca devolve um
    score isolado (§48) — sempre com `reasons`/`missing_data`."""
    pontuacao = 0.0
    reasons: list[str] = []
    missing_data: list[str] = []

    if perfil_candidato.cnae_principal:
        if perfil_candidato.cnae_principal in icp.cnae_codigos:
            pontuacao += _PESO_CNAE
            reasons.append(f"CNAE principal ({perfil_candidato.cnae_principal}) está entre os CNAEs do ICP.")
    else:
        missing_data.append("cnae_principal")

    if perfil_candidato.sede_uf:
        if perfil_candidato.sede_uf.upper() in {uf.upper() for uf in icp.ufs}:
            pontuacao += _PESO_UF
            reasons.append(f"Sede em {perfil_candidato.sede_uf} está entre as UFs do ICP.")
    else:
        missing_data.append("sede_uf")

    if perfil_candidato.porte:
        if icp.porte and perfil_candidato.porte == icp.porte:
            pontuacao += _PESO_PORTE
            reasons.append(f"Porte ({perfil_candidato.porte}) corresponde ao porte do ICP.")
    else:
        missing_data.append("porte")

    if len(missing_data) == 0:
        confidence = "alta"
    elif len(missing_data) == 1:
        confidence = "media"
    else:
        confidence = "baixa"

    return {
        "tenant_id_candidato": perfil_candidato.tenant_id,
        "empresa_nome": perfil_candidato.nome_exibicao,
        "fit_score": round(pontuacao, 2),
        "matched_icp": icp.nome,
        "reasons": reasons,
        "missing_data": missing_data,
        "confidence": confidence,
    }


def listar_fit_icp_rede(db: Session, tenant_id: str, icp_id: int) -> list[dict]:
    """Mostrar empresas da rede pertencentes a um ICP (master prompt
    §60) — compara o ICP do tenant que consulta contra o perfil
    público de todos os outros tenants da Rede Social."""
    icp = db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none()
    if icp is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")

    perfis = db.query(PerfilEmpresa).filter(PerfilEmpresa.tenant_id != tenant_id).all()
    resultados = [calcular_fit_icp(icp, perfil) for perfil in perfis]
    resultados.sort(key=lambda resultado: resultado["fit_score"], reverse=True)
    return resultados


def _tokenizar(*textos: str | None) -> set[str]:
    palavras: set[str] = set()
    for texto in textos:
        if not texto:
            continue
        for palavra in re.findall(r"[a-zà-ú0-9]+", texto.lower()):
            if len(palavra) >= 3 and palavra not in _PALAVRAS_IGNORADAS:
                palavras.add(palavra)
    return palavras


def _relacionamento_entre(db: Session, tenant_id_a: str, tenant_id_b: str) -> RelacionamentoEmpresarial | None:
    return (
        db.query(RelacionamentoEmpresarial)
        .filter(
            (
                (RelacionamentoEmpresarial.tenant_id_origem == tenant_id_a)
                & (RelacionamentoEmpresarial.tenant_id_destino == tenant_id_b)
            )
            | (
                (RelacionamentoEmpresarial.tenant_id_origem == tenant_id_b)
                & (RelacionamentoEmpresarial.tenant_id_destino == tenant_id_a)
            )
        )
        .first()
    )


def _conexao_aceita_entre(db: Session, tenant_id_a: str, tenant_id_b: str) -> bool:
    conexao = (
        db.query(ConexaoEmpresa)
        .filter(
            (
                (ConexaoEmpresa.tenant_id_origem == tenant_id_a)
                & (ConexaoEmpresa.tenant_id_destino == tenant_id_b)
            )
            | (
                (ConexaoEmpresa.tenant_id_origem == tenant_id_b)
                & (ConexaoEmpresa.tenant_id_destino == tenant_id_a)
            )
        )
        .one_or_none()
    )
    return conexao is not None and conexao.status == "aceita"


def _calcular_match_intent(db: Session, intent: Intent, perfil_candidato: PerfilEmpresa) -> dict | None:
    """Intent Agent + Match Engine (master prompt §26, §48-49, Fase 3C)
    — comparação determinística de palavras-chave (sem embeddings/
    vector search, fora de escopo desta fase) entre o que a Intent
    descreve e o que o perfil candidato oferece, com boost explícito
    quando já existe conexão aceita ou relacionamento comercial
    declarado entre os dois tenants. Nunca um score opaco (§48) — quem
    não bate nenhum critério e não tem nenhum sinal de relação nem
    entra na lista."""
    termos_intent = _tokenizar(intent.categoria, intent.titulo, intent.descricao, *intent.requisitos)
    termos_perfil = _tokenizar(
        perfil_candidato.descricao,
        perfil_candidato.setor,
        *perfil_candidato.produtos_servicos,
        *perfil_candidato.mercados,
        *perfil_candidato.tecnologias,
    )
    termos_em_comum = sorted(termos_intent & termos_perfil)

    match_score = min(1.0, len(termos_em_comum) * 0.2)
    reasons = [f"Palavra-chave em comum: \"{termo}\"." for termo in termos_em_comum[:5]]
    signals: list[str] = []

    if _conexao_aceita_entre(db, intent.tenant_id, perfil_candidato.tenant_id):
        signals.append("Já existe conexão aceita entre as duas empresas na rede.")
        match_score = min(1.0, match_score + 0.2)

    relacionamento = _relacionamento_entre(db, intent.tenant_id, perfil_candidato.tenant_id)
    if relacionamento is not None:
        signals.append(f"Relacionamento comercial declarado na rede: {relacionamento.tipo}.")
        match_score = min(1.0, match_score + 0.2)

    if match_score == 0.0 and not signals:
        return None  # sem nenhum critério nem sinal — não é um match plausível

    if match_score >= 0.6:
        confidence = "alta"
    elif match_score >= 0.3:
        confidence = "media"
    else:
        confidence = "baixa"

    return {
        "tenant_id_candidato": perfil_candidato.tenant_id,
        "empresa_nome": perfil_candidato.nome_exibicao,
        "match_score": round(match_score, 2),
        "match_reasons": reasons,
        "confidence": confidence,
        "signals": signals,
    }


def sugerir_fornecedores_para_intent(db: Session, tenant_id: str, intent_id: int) -> list[dict]:
    """Só quem pode ver a Intent (visibilidade + próprio autor) pode ver
    os matches sugeridos — mesma regra de `intent_service.obter_visivel`,
    verificada pelo endpoint antes de chamar esta função."""
    intent = db.query(Intent).filter_by(id=intent_id).one_or_none()
    if intent is None:
        raise NaoEncontrado(f"Intent {intent_id} não encontrada")

    perfis = db.query(PerfilEmpresa).filter(PerfilEmpresa.tenant_id != intent.tenant_id).all()
    resultados = [_calcular_match_intent(db, intent, perfil) for perfil in perfis]
    matches = [resultado for resultado in resultados if resultado is not None]
    matches.sort(key=lambda resultado: resultado["match_score"], reverse=True)
    return matches


def explicar_match_com_ia(db: Session, intent_id: int, tenant_id_candidato: str, llm: LLMProvider) -> str:
    """UMA chamada real de IA (mesmo padrão de
    `regra_aprendida_service.sugerir_regra_com_ia`, Peça 3) — só
    escreve uma frase explicando, em linguagem natural, os motivos
    estruturados já calculados. Nunca decide o match por conta própria
    e o prompt instrui explicitamente a não inventar nenhum fato além
    dos motivos fornecidos (master prompt §21)."""
    intent = db.query(Intent).filter_by(id=intent_id).one_or_none()
    if intent is None:
        raise NaoEncontrado(f"Intent {intent_id} não encontrada")

    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id_candidato).one_or_none()
    if perfil is None:
        raise NaoEncontrado(f"Empresa {tenant_id_candidato} não encontrada")

    match = _calcular_match_intent(db, intent, perfil)
    if match is None:
        raise NaoEncontrado("Esta empresa não tem nenhum critério ou sinal em comum com a necessidade.")

    motivos = "; ".join(match["match_reasons"] + match["signals"]) or "nenhum motivo estruturado disponível"
    prompt = (
        f"Uma empresa declarou a seguinte necessidade na rede: \"{intent.titulo}\" — {intent.descricao}\n"
        f"Outra empresa, \"{perfil.nome_exibicao}\", foi sugerida como possível fornecedora com base nestes "
        f"motivos JÁ CALCULADOS (não invente nenhum motivo além destes): {motivos}.\n"
        "Em uma frase curta, escreva por que essa empresa pode atender a necessidade, usando só os motivos "
        "acima. Responda só com a frase, sem explicações nem aspas."
    )
    resposta = llm_helpers.gerar(llm, LLMRequest(prompt=prompt, max_tokens=200))
    return resposta.content.strip()


def nome_empresa(db: Session, tenant_id: str) -> str:
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    return perfil.nome_exibicao if perfil is not None else tenant_id


def _confianca_por_score(score: float) -> str:
    if score >= 0.6:
        return "alta"
    if score >= 0.3:
        return "media"
    return "baixa"


def gerar_sinais(db: Session, tenant_id: str) -> list[dict]:
    """Opportunity Agent (master prompt §28, §50, Fase 3D) — combina fit
    ICP (3B) + matches de Intent (3C) + Business Graph declarado
    (`RelacionamentoEmpresarial`, Fase 1D) num sinal por
    (tenant_alvo, tipo). On-demand (sem cron novo, §84 fora de escopo):
    idempotente — regenerar atualiza score/motivo de sinais "novo"/
    "visto" existentes, nunca duplica, e nunca sobrescreve um sinal já
    "convertido"/"descartado" (decisão humana anterior é respeitada)."""
    dados_por_par: dict[tuple[str, str], dict] = {}

    for icp in db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).all():
        for fit in listar_fit_icp_rede(db, tenant_id, icp.id):
            if fit["fit_score"] <= 0:
                continue
            chave = (fit["tenant_id_candidato"], "fit_icp")
            candidato = {
                "score": fit["fit_score"],
                "motivo": f"Fit com o ICP \"{fit['matched_icp']}\": " + "; ".join(fit["reasons"]),
                "evidencias": fit["reasons"],
            }
            if chave not in dados_por_par or candidato["score"] > dados_por_par[chave]["score"]:
                dados_por_par[chave] = candidato

    for intent in db.query(Intent).filter_by(tenant_id=tenant_id, status="aberta").all():
        for match in sugerir_fornecedores_para_intent(db, tenant_id, intent.id):
            chave = (match["tenant_id_candidato"], "match_intent")
            motivos = match["match_reasons"] + match["signals"]
            candidato = {
                "score": match["match_score"],
                "motivo": f"Pode atender a necessidade \"{intent.titulo}\": " + "; ".join(motivos),
                "evidencias": motivos,
            }
            if chave not in dados_por_par or candidato["score"] > dados_por_par[chave]["score"]:
                dados_por_par[chave] = candidato

    relacionamentos = (
        db.query(RelacionamentoEmpresarial)
        .filter(
            RelacionamentoEmpresarial.tenant_id_destino == tenant_id,
            RelacionamentoEmpresarial.tipo.in_(["LOOKING_FOR", "INTERESTED_IN"]),
        )
        .all()
    )
    for relacionamento in relacionamentos:
        chave = (relacionamento.tenant_id_origem, "relacionamento_declarado")
        dados_por_par[chave] = {
            "score": 0.5,
            "motivo": (
                f"{nome_empresa(db, relacionamento.tenant_id_origem)} declarou \"{relacionamento.tipo}\" "
                "em relação à sua empresa no Business Graph da rede."
            ),
            "evidencias": [relacionamento.tipo],
        }

    # Lote (Fase 7B, hardening) — antes buscava um `SinalOportunidade`
    # existente por par dentro do loop de get-or-create.
    sinais_existentes = {
        (sinal_existente.tenant_id_alvo, sinal_existente.tipo_sinal): sinal_existente
        for sinal_existente in db.query(SinalOportunidade).filter_by(tenant_id=tenant_id).all()
    }

    sinais: list[SinalOportunidade] = []
    for (tenant_id_alvo, tipo_sinal), dados in dados_por_par.items():
        sinal = sinais_existentes.get((tenant_id_alvo, tipo_sinal))
        if sinal is None:
            sinal = SinalOportunidade(
                tenant_id=tenant_id, tenant_id_alvo=tenant_id_alvo, tipo_sinal=tipo_sinal, status="novo"
            )
            db.add(sinal)
        if sinal.status not in _STATUS_SINAL_IMUTAVEIS:
            sinal.score = dados["score"]
            sinal.motivo = dados["motivo"]
            sinal.evidencias = dados["evidencias"]
            sinal.confianca = _confianca_por_score(dados["score"])
        sinais.append(sinal)

    db.commit()
    return listar(db, tenant_id)


def _serializar_sinal(db: Session, sinal: SinalOportunidade) -> dict:
    return {
        "id": sinal.id,
        "tenant_id_alvo": sinal.tenant_id_alvo,
        "empresa_nome": nome_empresa(db, sinal.tenant_id_alvo),
        "tipo_sinal": sinal.tipo_sinal,
        "score": sinal.score,
        "confianca": sinal.confianca,
        "motivo": sinal.motivo,
        "evidencias": sinal.evidencias,
        "status": sinal.status,
        "conta_id_gerada": sinal.conta_id_gerada,
        "criado_em": sinal.criado_em,
    }


def listar(db: Session, tenant_id: str) -> list[dict]:
    sinais = (
        db.query(SinalOportunidade)
        .filter_by(tenant_id=tenant_id)
        .order_by(SinalOportunidade.score.desc(), SinalOportunidade.id.desc())
        .all()
    )
    return [_serializar_sinal(db, sinal) for sinal in sinais]


def _obter_sinal(db: Session, tenant_id: str, sinal_id: int) -> SinalOportunidade:
    sinal = db.query(SinalOportunidade).filter_by(id=sinal_id, tenant_id=tenant_id).one_or_none()
    if sinal is None:
        raise NaoEncontrado(f"Sinal de oportunidade {sinal_id} não encontrado")
    return sinal


def marcar_visto(db: Session, tenant_id: str, sinal_id: int) -> dict:
    sinal = _obter_sinal(db, tenant_id, sinal_id)
    if sinal.status == "novo":
        sinal.status = "visto"
        db.commit()
    return _serializar_sinal(db, sinal)


def descartar(db: Session, tenant_id: str, ator_id: str | None, sinal_id: int) -> dict:
    sinal = _obter_sinal(db, tenant_id, sinal_id)
    if sinal.status == "convertido":
        raise RegraNegocioViolada("Este sinal já foi convertido em uma conta do CRM.")
    sinal.status = "descartado"
    auditoria_service.registrar(db, tenant_id, "sinal_oportunidade_descartado", "sinal_oportunidade", sinal.id, ator_id, {})
    db.commit()
    return _serializar_sinal(db, sinal)


def converter_em_oportunidade(db: Session, tenant_id: str, ator_id: str | None, sinal_id: int) -> dict:
    """Signal → CRM (master prompt §51, Fase 3D), até onde os dados
    permitem sem inventar um decisor de outro tenant (ver decisão de
    escopo 5 do plano): cria/reaproveita a `Conta` a partir do perfil
    público do tenant-alvo (mesmo padrão de `conta_service.criar_lead`,
    `origem="rede_social_signal"`) e devolve o `conta_id` — o humano
    escolhe/cadastra o decisor real e fecha o `Negocio` pelo fluxo
    manual já existente no CRM."""
    sinal = _obter_sinal(db, tenant_id, sinal_id)
    if sinal.status == "convertido":
        raise RegraNegocioViolada("Este sinal já foi convertido em uma conta do CRM.")

    tenant_alvo = db.query(Tenant).filter_by(id=sinal.tenant_id_alvo).one_or_none()
    perfil_alvo = db.query(PerfilEmpresa).filter_by(tenant_id=sinal.tenant_id_alvo).one_or_none()

    conta = conta_service.criar_lead(
        db,
        tenant_id,
        ator_id,
        nome=perfil_alvo.nome_exibicao if perfil_alvo is not None else sinal.tenant_id_alvo,
        cnpj=tenant_alvo.cnpj if tenant_alvo is not None else None,
        dominio=perfil_alvo.site if perfil_alvo is not None else None,
        segmento=perfil_alvo.setor if perfil_alvo is not None else None,
        porte=perfil_alvo.porte if perfil_alvo is not None else None,
        regiao=perfil_alvo.sede_uf if perfil_alvo is not None else None,
        origem="rede_social_signal",
    )

    sinal.status = "convertido"
    sinal.conta_id_gerada = conta.id
    auditoria_service.registrar(
        db, tenant_id, "sinal_oportunidade_convertido", "sinal_oportunidade", sinal.id, ator_id, {"conta_id": conta.id}
    )
    db.commit()
    return {"conta_id": conta.id}


_LIMITE_DIAS_ESFRIANDO = 30
_LIMITE_DIAS_NEUTRO = 14


def _ultima_interacao_entre(db: Session, tenant_a: str, tenant_b: str) -> datetime | None:
    ultima_dm = (
        db.query(func.max(MensagemRedeSocial.criado_em))
        .filter(
            (
                (MensagemRedeSocial.tenant_id_remetente == tenant_a)
                & (MensagemRedeSocial.tenant_id_destinatario == tenant_b)
            )
            | (
                (MensagemRedeSocial.tenant_id_remetente == tenant_b)
                & (MensagemRedeSocial.tenant_id_destinatario == tenant_a)
            )
        )
        .scalar()
    )
    tenant_sala_a, tenant_sala_b = sorted((tenant_a, tenant_b))
    ultima_sala = (
        db.query(func.max(MensagemSala.criado_em))
        .join(CanalSala, CanalSala.id == MensagemSala.canal_id)
        .join(SalaCorporativa, SalaCorporativa.id == CanalSala.sala_id)
        .filter(SalaCorporativa.tenant_id_a == tenant_sala_a, SalaCorporativa.tenant_id_b == tenant_sala_b)
        .scalar()
    )
    datas = [data for data in (ultima_dm, ultima_sala) if data is not None]
    return max(datas) if datas else None


_LIMITE_DIAS_PIPELINE_PARADO = 14


def analisar_pipeline(db: Session, tenant_id: str, negocio: Negocio) -> dict:
    """Pipeline Agent (master prompt §33, Fase 5C) — só sinais reais, sem
    NLP: dias sem atividade registrada (`Atividade`, mesmo raciocínio de
    "dias sem contato" de `motor_service.calcular_score_risco`), ausência
    de decision maker confirmado na Conta (Stakeholder Map, Fase 5B) e o
    campo estruturado `Conta.proximo_passo` que já existe (dado real
    declarado pelo vendedor, não inferência — nunca inventa "próximo
    passo" por texto livre)."""
    agora = datetime.now(UTC)

    ultima_atividade_em = (
        db.query(func.max(Atividade.criado_em)).filter(Atividade.negocio_id == negocio.id).scalar()
    )
    referencia = ultima_atividade_em or negocio.criado_em
    dias_sem_atividade = (agora - referencia.replace(tzinfo=UTC)).days

    tem_decision_maker = (
        db.query(Decisor)
        .filter(Decisor.tenant_id == tenant_id, Decisor.conta_id == negocio.conta_id, Decisor.papel_confirmado == "DECISION_MAKER")
        .first()
        is not None
    )

    conta = db.query(Conta).filter_by(id=negocio.conta_id, tenant_id=tenant_id).one_or_none()

    riscos: list[str] = []
    if dias_sem_atividade > _LIMITE_DIAS_PIPELINE_PARADO:
        motivo = "sem nenhuma atividade registrada ainda" if ultima_atividade_em is None else f"há {dias_sem_atividade} dias sem atividade registrada"
        riscos.append(f"Negócio parado — {motivo}.")
    if not tem_decision_maker:
        riscos.append("Nenhum decisor com papel DECISION_MAKER confirmado nesta conta.")
    if conta is not None:
        if not conta.proximo_passo:
            riscos.append("Sem próximo passo definido para esta conta.")
        elif conta.proximo_passo_em and conta.proximo_passo_em.replace(tzinfo=UTC) < agora:
            riscos.append(f"Próximo passo atrasado: \"{conta.proximo_passo}\" estava previsto para {conta.proximo_passo_em:%d/%m/%Y}.")

    return {
        "negocio_id": negocio.id,
        "negocio_nome": negocio.nome,
        "conta_id": negocio.conta_id,
        "conta_nome": conta.nome if conta is not None else None,
        "dias_sem_atividade": dias_sem_atividade,
        "tem_decision_maker": tem_decision_maker,
        "riscos": riscos,
    }


def listar_riscos_pipeline(db: Session, tenant_id: str) -> list[dict]:
    negocios_abertos = (
        db.query(Negocio)
        .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(Negocio.tenant_id == tenant_id, EstagioFunil.tipo == "aberto")
        .all()
    )
    resultados = [analisar_pipeline(db, tenant_id, negocio) for negocio in negocios_abertos]
    resultados = [resultado for resultado in resultados if resultado["riscos"]]
    resultados.sort(key=lambda resultado: len(resultado["riscos"]), reverse=True)
    return resultados


def calcular_atribuicao_receita(db: Session, tenant_id: str) -> dict:
    """Revenue Agent — Attribution (master prompt §34, §76, Fase 5D). Já é
    100% computável sem nenhuma inferência: toda `Conta` nascida de um
    sinal da rede tem `origem="rede_social_signal"` (Fase 3D,
    `converter_em_oportunidade`) — basta somar o valor dos negócios dessas
    contas, por estágio, e cruzar com a taxa de conversão real de
    `SinalOportunidade`."""
    contas_geradas_ids = [
        conta.id for conta in db.query(Conta.id).filter_by(tenant_id=tenant_id, origem="rede_social_signal").all()
    ]

    valor_aberto = 0.0
    valor_ganho = 0.0
    if contas_geradas_ids:
        linhas = (
            db.query(Negocio.valor, EstagioFunil.tipo)
            .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
            .filter(Negocio.tenant_id == tenant_id, Negocio.conta_id.in_(contas_geradas_ids))
            .all()
        )
        valor_aberto = sum(valor for valor, tipo in linhas if tipo == "aberto")
        valor_ganho = sum(valor for valor, tipo in linhas if tipo == "ganho")

    sinais_gerados = db.query(SinalOportunidade).filter_by(tenant_id=tenant_id).count()
    sinais_convertidos = db.query(SinalOportunidade).filter_by(tenant_id=tenant_id, status="convertido").count()

    return {
        "contas_geradas_pela_rede": len(contas_geradas_ids),
        "negocios_em_aberto_valor": valor_aberto,
        "negocios_ganhos_valor": valor_ganho,
        "sinais_gerados": sinais_gerados,
        "sinais_convertidos": sinais_convertidos,
        "taxa_conversao_sinais": (sinais_convertidos / sinais_gerados) if sinais_gerados else 0.0,
    }


def sugerir_expansao(db: Session, tenant_id: str) -> list[dict]:
    """Revenue Agent — cross-sell/upsell (master prompt §34, Fase 5D):
    Conta com pelo menos um negócio "ganho" + Oferta ativa que essa Conta
    nunca teve em nenhum negócio (aberto, ganho ou perdido) — sinal real
    a partir de `Negocio.oferta_id`, nunca inferido por texto."""
    contas_com_negocio_ganho = (
        db.query(Conta)
        .join(Negocio, Negocio.conta_id == Conta.id)
        .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(Conta.tenant_id == tenant_id, EstagioFunil.tipo == "ganho")
        .distinct()
        .all()
    )
    ofertas_ativas = db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).all()
    if not ofertas_ativas:
        return []

    sugestoes: list[dict] = []
    for conta in contas_com_negocio_ganho:
        ofertas_ja_vinculadas = {
            oferta_id
            for (oferta_id,) in db.query(Negocio.oferta_id)
            .filter(Negocio.conta_id == conta.id, Negocio.oferta_id.isnot(None))
            .all()
        }
        for oferta in ofertas_ativas:
            if oferta.id in ofertas_ja_vinculadas:
                continue
            sugestoes.append(
                {
                    "conta_id": conta.id,
                    "conta_nome": conta.nome_fantasia or conta.nome,
                    "oferta_id": oferta.id,
                    "oferta_nome": oferta.nome,
                    "motivo": f"Conta com negócio ganho, ainda sem nenhum negócio vinculado à oferta \"{oferta.nome}\".",
                }
            )
    return sugestoes


def analisar_saude_relacionamento(db: Session, tenant_id: str, tenant_id_alvo: str) -> dict:
    """Relationship Agent (master prompt §31, Fase 4B) — mesmo
    raciocínio de "dias sem contato" já usado em
    `motor_service.calcular_score_risco`, aplicado à relação entre DUAS
    EMPRESAS (não tenant×Conta): combina a última interação real (DM ou
    Sala Corporativa) com a existência de um `RelacionamentoEmpresarial`
    declarado. Não infere "stakeholder importante não envolvido" (isso
    exigiria um conceito de contato cross-tenant que não existe ainda —
    fica pra Fase 5/Stakeholder Map)."""
    ultima_interacao = _ultima_interacao_entre(db, tenant_id, tenant_id_alvo)
    agora = datetime.now(UTC)
    dias_sem_interacao = (agora - ultima_interacao.replace(tzinfo=UTC)).days if ultima_interacao is not None else None

    tem_relacionamento = _relacionamento_entre(db, tenant_id, tenant_id_alvo) is not None

    sugestoes: list[str] = []
    if dias_sem_interacao is None:
        classificacao = "sem_interacao"
        sugestoes.append("Nenhuma mensagem trocada ainda — considere iniciar uma conversa ou abrir uma sala corporativa.")
    elif dias_sem_interacao > _LIMITE_DIAS_ESFRIANDO:
        classificacao = "esfriando"
        sugestoes.append(f"Nenhuma mensagem trocada nos últimos {dias_sem_interacao} dias.")
    elif dias_sem_interacao > _LIMITE_DIAS_NEUTRO:
        classificacao = "neutro"
        sugestoes.append(f"Última interação há {dias_sem_interacao} dias — pode ser hora de retomar contato.")
    else:
        classificacao = "aquecido"

    if not tem_relacionamento:
        sugestoes.append(
            "Nenhum relacionamento comercial declarado ainda — considere declarar um (fornecedor, cliente, parceiro...)."
        )

    return {
        "tenant_id_alvo": tenant_id_alvo,
        "empresa_nome": nome_empresa(db, tenant_id_alvo),
        "dias_sem_interacao": dias_sem_interacao,
        "tem_relacionamento_declarado": tem_relacionamento,
        "classificacao": classificacao,
        "sugestoes": sugestoes,
    }


def listar_saude_relacionamentos(db: Session, tenant_id: str) -> list[dict]:
    conexoes = (
        db.query(ConexaoEmpresa)
        .filter(
            ConexaoEmpresa.status == "aceita",
            (ConexaoEmpresa.tenant_id_origem == tenant_id) | (ConexaoEmpresa.tenant_id_destino == tenant_id),
        )
        .all()
    )
    tenants_alvo = {
        conexao.tenant_id_destino if conexao.tenant_id_origem == tenant_id else conexao.tenant_id_origem
        for conexao in conexoes
    }
    resultados = [analisar_saude_relacionamento(db, tenant_id, tenant_id_alvo) for tenant_id_alvo in tenants_alvo]
    ordem_classificacao = {"esfriando": 0, "sem_interacao": 1, "neutro": 2, "aquecido": 3}
    resultados.sort(key=lambda resultado: ordem_classificacao.get(resultado["classificacao"], 99))
    return resultados
