import re

from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.conexao_empresa import ConexaoEmpresa
from app.models.icp import ICP
from app.models.intent import Intent
from app.models.perfil_empresa import PerfilEmpresa
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial
from app.services import llm_helpers
from app.services.errors import NaoEncontrado

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
