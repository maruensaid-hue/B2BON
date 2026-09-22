import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.aprovacao import Aprovacao
from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.configuracao_comunicacao import ConfiguracaoComunicacao
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.models.oferta import Oferta
from app.models.toque_cadencia import ToqueCadencia
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.cadencia import CadenciaCreateSchema
from app.services import (
    aprovacao_service,
    auditoria_service,
    comunicacao_service,
    franquia_service,
    limite_criacao_service,
    llm_helpers,
    optout_service,
    regra_aprendida_service,
    reputacao_service,
)
from app.services.errors import NaoEncontrado, RegraNegocioViolada

logger = logging.getLogger(__name__)

MINIMO_TOQUES = 5
MINIMO_CANAIS_DISTINTOS = 2

# Cada toque gerado é uma chamada síncrona à IA (2-8s cada, dependendo do
# tamanho do prompt) dentro da mesma requisição HTTP. Um lote grande
# (ex.: 10 contas x 5 toques = 50 chamadas) estourava o timeout da conexão
# antes de terminar — bug real de produção: nem a primeira mensagem
# chegava a ser salva porque a requisição inteira caía por timeout de
# rede antes do primeiro `commit`. Cap conservador aqui; o frontend
# quebra seleções maiores em lotes automaticamente.
MAXIMO_CONTAS_POR_LOTE = 4


def obter(db: Session, tenant_id: str, cadencia_id: int) -> Cadencia:
    cadencia = db.query(Cadencia).filter_by(id=cadencia_id, tenant_id=tenant_id).one_or_none()
    if cadencia is None:
        raise NaoEncontrado(f"Cadência {cadencia_id} não encontrada")
    return cadencia


def listar(db: Session, tenant_id: str) -> list[Cadencia]:
    return db.query(Cadencia).filter_by(tenant_id=tenant_id).order_by(Cadencia.id.desc()).all()


def excluir(db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int) -> None:
    """Só permite excluir em rascunho — uma vez que `gerar_para_lote` gera
    ao menos uma mensagem com sucesso, o status já sai de rascunho, então
    isto garante que nunca há `Mensagem` presa a uma cadência excluída."""
    cadencia = obter(db, tenant_id, cadencia_id)
    if cadencia.status != "rascunho":
        raise RegraNegocioViolada("Só é possível excluir cadências em rascunho, antes da primeira geração de mensagens.")

    db.query(ToqueCadencia).filter_by(cadencia_id=cadencia.id).delete()
    auditoria_service.registrar(db, tenant_id, "cadencia_excluida", "cadencia", cadencia.id, ator_id, {"nome": cadencia.nome})
    db.delete(cadencia)
    db.commit()


def toques_da_cadencia(db: Session, cadencia_id: int) -> list[ToqueCadencia]:
    return db.query(ToqueCadencia).filter_by(cadencia_id=cadencia_id).order_by(ToqueCadencia.ordem).all()


def _recalcular_canais(db: Session, cadencia: Cadencia) -> None:
    """Mesma lista calculada em `criar()` — mantém `Cadencia.canais`
    coerente depois de adicionar/remover/trocar o canal de um toque."""
    cadencia.canais = sorted({toque.canal for toque in toques_da_cadencia(db, cadencia.id)})


def _exigir_nao_cancelada(cadencia: Cadencia) -> None:
    if cadencia.status == "cancelada":
        raise RegraNegocioViolada("Cadência cancelada — não é possível alterá-la.")


def _validar_no_maximo_um_whatsapp_com_template(toques) -> None:
    """`toques`: qualquer sequência com atributos `.canal`/`.template_whatsapp_id`
    — funciona tanto com `ToqueCadenciaCreateSchema` (na criação) quanto
    com `ToqueCadencia` do banco (nas edições). Raio-X 2026-09-15: no
    máximo 1 toque de WhatsApp por cadência, e sempre com template —
    nenhum toque agendado pra depois do primeiro contato tem garantia de
    que a janela de 24h da Meta ainda vai estar aberta quando a data
    chegar (mesmo se o próprio cliente pediu o retorno — a regra da Meta
    é só sobre horas corridas desde a última mensagem dele, sem exceção
    de contexto)."""
    toques_whatsapp = [t for t in toques if t.canal == "whatsapp"]
    if len(toques_whatsapp) > 1:
        raise RegraNegocioViolada("No máximo 1 toque de WhatsApp por cadência — os demais devem ser e-mail ou LinkedIn.")
    if toques_whatsapp and not toques_whatsapp[0].template_whatsapp_id:
        raise RegraNegocioViolada("O toque de WhatsApp precisa de um template aprovado.")


def _validar_minimos(toques: list[ToqueCadencia]) -> None:
    """Mesmas regras de `criar()` — reaplicadas depois de remover/trocar o
    canal de um toque, pra a cadência continuar um blueprint válido pra
    qualquer conta nova que vier a ser gerada depois."""
    if len(toques) < MINIMO_TOQUES:
        raise RegraNegocioViolada(f"Uma cadência precisa de no mínimo {MINIMO_TOQUES} toques.")
    if len({toque.canal for toque in toques}) < MINIMO_CANAIS_DISTINTOS:
        raise RegraNegocioViolada("Os toques precisam estar distribuídos entre pelo menos 2 canais.")
    _validar_no_maximo_um_whatsapp_com_template(toques)


def cancelar(db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int) -> dict:
    """Para qualquer envio futuro a partir de agora, sem apagar nada do
    histórico — raio-X 2026-09-15: "excluir mesmo já disparada" colidiria
    com a proteção que `aprovacao_service.excluir` já dá a mensagens
    `status="enviado"` (histórico real de comunicação com o cliente), e
    não existe (nem é seguro inventar agora) uma forma de devolver a
    franquia já consumida na ativação. Mesmo padrão de
    `resposta_service.marcar_resposta` (que já faz isso por decisor
    quando ele responde), generalizado pra cadência inteira: qualquer
    `Mensagem` ainda não enviada vira "cancelado" — `envio_service.
    processar_pendentes` só recolhe `status in ("aprovado","falhou")`,
    então essas linhas nunca mais são tocadas pelo cron."""
    cadencia = obter(db, tenant_id, cadencia_id)
    if cadencia.status == "cancelada":
        raise RegraNegocioViolada("Esta cadência já está cancelada.")

    mensagens_canceladas = (
        db.query(Mensagem)
        .filter(
            Mensagem.tenant_id == tenant_id,
            Mensagem.cadencia_id == cadencia.id,
            Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]),
        )
        .update({"status": "cancelado"}, synchronize_session=False)
    )
    cadencia.status = "cancelada"
    auditoria_service.registrar(
        db, tenant_id, "cadencia_cancelada", "cadencia", cadencia.id, ator_id,
        {"mensagens_canceladas": mensagens_canceladas},
    )
    db.commit()
    db.refresh(cadencia)
    return {"cadencia": cadencia, "mensagens_canceladas": mensagens_canceladas}


def renomear(db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int, novo_nome: str) -> Cadencia:
    """Só cosmético — não afeta nenhuma `Mensagem`, permitido em qualquer
    status (inclusive cancelada, pra ainda poder identificar o motivo do
    cancelamento no nome, por exemplo)."""
    cadencia = obter(db, tenant_id, cadencia_id)
    cadencia.nome = novo_nome
    auditoria_service.registrar(db, tenant_id, "cadencia_renomeada", "cadencia", cadencia.id, ator_id, {"nome": novo_nome})
    db.commit()
    db.refresh(cadencia)
    return cadencia


def definir_cancelamento_ao_responder(
    db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int, cancelar_ao_responder: bool
) -> Cadencia:
    """Liga/desliga o cancelamento automático ao responder (raio-X
    2026-09-15) — desligado por padrão desde a criação; permitido em
    qualquer status, sem retroagir sobre nenhuma `Mensagem` já cancelada
    ou não."""
    cadencia = obter(db, tenant_id, cadencia_id)
    cadencia.cancelar_ao_responder = cancelar_ao_responder
    auditoria_service.registrar(
        db, tenant_id, "cadencia_cancelamento_ao_responder_alterado", "cadencia", cadencia.id, ator_id,
        {"cancelar_ao_responder": cancelar_ao_responder},
    )
    db.commit()
    db.refresh(cadencia)
    return cadencia


def adicionar_toque(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    cadencia_id: int,
    canal: str,
    intervalo_dias_apos_anterior: int = 0,
    template_whatsapp_id: str | None = None,
    ab_teste_habilitado: bool = False,
) -> ToqueCadencia:
    """Só afeta contas que vierem a ser geradas a partir de agora — não
    retroage sobre `Mensagem` já existentes (mesmo raciocínio de
    `definir_template_whatsapp`)."""
    cadencia = obter(db, tenant_id, cadencia_id)
    _exigir_nao_cancelada(cadencia)

    toques_atuais = toques_da_cadencia(db, cadencia.id)
    proxima_ordem = (max((t.ordem for t in toques_atuais), default=0)) + 1
    toque = ToqueCadencia(
        tenant_id=tenant_id,
        cadencia_id=cadencia.id,
        ordem=proxima_ordem,
        canal=canal,
        intervalo_dias_apos_anterior=intervalo_dias_apos_anterior,
        template_whatsapp_id=template_whatsapp_id if canal == "whatsapp" else None,
        ab_teste_habilitado=ab_teste_habilitado,
    )
    db.add(toque)
    db.flush()
    _validar_no_maximo_um_whatsapp_com_template(toques_da_cadencia(db, cadencia.id))
    _recalcular_canais(db, cadencia)
    auditoria_service.registrar(
        db, tenant_id, "toque_adicionado", "toque_cadencia", toque.id, ator_id, {"canal": canal}
    )
    db.commit()
    db.refresh(toque)
    return toque


def remover_toque(db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int, toque_id: int) -> None:
    """Desvincula em vez de bloquear — mesmo padrão de
    `crm_service.excluir_negocio` pra `Atividade`: `Mensagem.
    toque_cadencia_id` não tem `ondelete=CASCADE`, e as mensagens já
    geradas por este toque são histórico real, preservado intacto."""
    cadencia = obter(db, tenant_id, cadencia_id)
    _exigir_nao_cancelada(cadencia)
    toque = db.query(ToqueCadencia).filter_by(id=toque_id, cadencia_id=cadencia.id).one_or_none()
    if toque is None:
        raise NaoEncontrado(f"Toque {toque_id} não encontrado nesta cadência")

    restantes = [t for t in toques_da_cadencia(db, cadencia.id) if t.id != toque.id]
    _validar_minimos(restantes)

    db.query(Mensagem).filter_by(toque_cadencia_id=toque.id).update({"toque_cadencia_id": None}, synchronize_session=False)
    db.delete(toque)
    db.flush()
    _recalcular_canais(db, cadencia)
    auditoria_service.registrar(db, tenant_id, "toque_removido", "toque_cadencia", toque_id, ator_id, {})
    db.commit()


def atualizar_toque(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    cadencia_id: int,
    toque_id: int,
    canal: str | None = None,
    intervalo_dias_apos_anterior: int | None = None,
    ab_teste_habilitado: bool | None = None,
) -> ToqueCadencia:
    """Só afeta contas que vierem a ser geradas a partir de agora — mesmo
    raciocínio de `definir_template_whatsapp`/`adicionar_toque`."""
    cadencia = obter(db, tenant_id, cadencia_id)
    _exigir_nao_cancelada(cadencia)
    toque = db.query(ToqueCadencia).filter_by(id=toque_id, cadencia_id=cadencia.id).one_or_none()
    if toque is None:
        raise NaoEncontrado(f"Toque {toque_id} não encontrado nesta cadência")

    if canal is not None:
        toque.canal = canal
        if canal != "whatsapp":
            # Evita deixar um id de template órfão num toque que não é
            # mais WhatsApp.
            toque.template_whatsapp_id = None
    if intervalo_dias_apos_anterior is not None:
        toque.intervalo_dias_apos_anterior = intervalo_dias_apos_anterior
    if ab_teste_habilitado is not None:
        toque.ab_teste_habilitado = ab_teste_habilitado

    _validar_minimos(toques_da_cadencia(db, cadencia.id))
    _recalcular_canais(db, cadencia)
    auditoria_service.registrar(
        db, tenant_id, "toque_atualizado", "toque_cadencia", toque.id, ator_id,
        {"canal": canal, "intervalo_dias_apos_anterior": intervalo_dias_apos_anterior},
    )
    db.commit()
    db.refresh(toque)
    return toque


def definir_template_whatsapp(
    db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int, toque_id: int, template_whatsapp_id: str
) -> ToqueCadencia:
    """Define/troca o template aprovado de um toque de WhatsApp já
    existente — raio-X 2026-09-15: o template só pode ser escolhido na
    criação da cadência, então quem criasse a cadência antes da Meta
    aprovar o template ficava sem nenhuma forma de configurá-lo depois.

    Só afeta mensagens geradas A PARTIR de agora — `Mensagem.template_id`
    é copiado do toque no momento da geração (`aprovacao_service.criar_proposta`),
    então mensagens já geradas antes desta troca continuam com o valor
    antigo (nulo ou outro template), sem retroatividade."""
    cadencia = obter(db, tenant_id, cadencia_id)
    toque = db.query(ToqueCadencia).filter_by(id=toque_id, cadencia_id=cadencia.id).one_or_none()
    if toque is None:
        raise NaoEncontrado(f"Toque {toque_id} não encontrado nesta cadência")
    if toque.canal != "whatsapp":
        raise RegraNegocioViolada("Só toques de WhatsApp têm template.")

    toque.template_whatsapp_id = template_whatsapp_id
    auditoria_service.registrar(
        db, tenant_id, "toque_template_whatsapp_definido", "toque_cadencia", toque.id, ator_id,
        {"template_whatsapp_id": template_whatsapp_id},
    )
    db.commit()
    db.refresh(toque)
    return toque


def criar(
    db: Session, tenant_id: str, ator_id: str | None, dados: CadenciaCreateSchema, plan_limits: PlanLimitsProvider
) -> Cadencia:
    """Cadência com no mínimo 5 toques distribuídos entre canais disponíveis (E3-H1)."""
    limite_criacao_service.verificar_limite_cadencias(db, tenant_id, plan_limits)

    if len(dados.toques) < MINIMO_TOQUES:
        raise RegraNegocioViolada(f"Uma cadência precisa de no mínimo {MINIMO_TOQUES} toques.")

    if any(toque.ab_teste_habilitado for toque in dados.toques) and not plan_limits.permite_ab_teste_cadencia(
        tenant_id
    ):
        raise RegraNegocioViolada("Teste A/B é exclusivo do plano Professional ou superior. Faça upgrade pra usar.")

    canais = {toque.canal for toque in dados.toques}
    if len(canais) < MINIMO_CANAIS_DISTINTOS:
        raise RegraNegocioViolada("Os toques precisam estar distribuídos entre pelo menos 2 canais.")

    _validar_no_maximo_um_whatsapp_com_template(dados.toques)

    # Capturado AGORA, na criação — não re-avaliado a cada geração (raio-X:
    # bug real de produção, ver docstring de `Cadencia.icp_id`/`oferta_id`
    # e de `_contexto_de_geracao`). `dados.icp_id` explícito serve pra quem
    # tem mais de um ICP ativo simultâneo (comparação de campanhas); a
    # Oferta nunca tem essa ambiguidade — só uma fica ativa por vez
    # (`oferta_service.ativar`).
    if dados.icp_id is not None:
        icp = db.query(ICP).filter_by(id=dados.icp_id, tenant_id=tenant_id).one_or_none()
        if icp is None:
            raise NaoEncontrado(f"ICP {dados.icp_id} não encontrado")
        icp_id = icp.id
    else:
        icp_ativo = db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).first()
        icp_id = icp_ativo.id if icp_ativo else None
    oferta_ativa = db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).first()
    oferta_id = oferta_ativa.id if oferta_ativa else None

    cadencia = Cadencia(
        tenant_id=tenant_id, nome=dados.nome, canais=sorted(canais), status="rascunho", tipo=dados.tipo,
        icp_id=icp_id, oferta_id=oferta_id, cancelar_ao_responder=dados.cancelar_ao_responder,
    )
    db.add(cadencia)
    db.flush()

    for toque in dados.toques:
        db.add(
            ToqueCadencia(
                tenant_id=tenant_id,
                cadencia_id=cadencia.id,
                ordem=toque.ordem,
                canal=toque.canal,
                intervalo_dias_apos_anterior=toque.intervalo_dias_apos_anterior,
                template_whatsapp_id=toque.template_whatsapp_id,
                ab_teste_habilitado=toque.ab_teste_habilitado,
            )
        )

    auditoria_service.registrar(
        db, tenant_id, "cadencia_criada", "cadencia", cadencia.id, ator_id, {"toques": len(dados.toques)}
    )
    db.commit()
    db.refresh(cadencia)
    return cadencia


def _contexto_de_geracao(
    db: Session, tenant_id: str, icp_id: int | None = None, oferta_id: int | None = None
) -> tuple[ICP, Oferta, ConfiguracaoComunicacao]:
    """`icp_id`/`oferta_id` vêm de `Cadencia.icp_id`/`Cadencia.oferta_id`
    (capturados na criação) — busca por id, não mais "o que estiver ativo
    agora" (raio-X: bug real de produção, ver docstring de
    `Cadencia.icp_id`). `None` só acontece pra cadência criada antes desta
    coluna existir; cai no fallback antigo, único caso em que "ativo
    agora" ainda é usado."""
    if icp_id is not None:
        icp = db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none()
    else:
        icp = db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).first()
    if icp is None:
        raise RegraNegocioViolada("Sem ICP ativo, o motor não inicia prospecção.")
    if oferta_id is not None:
        oferta = db.query(Oferta).filter_by(id=oferta_id, tenant_id=tenant_id).one_or_none()
    else:
        oferta = db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).first()
    if oferta is None:
        raise RegraNegocioViolada("Cadastre ao menos uma oferta antes de gerar uma cadência.")
    config = db.query(ConfiguracaoComunicacao).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        raise RegraNegocioViolada("Configure tom e restrições de comunicação antes de gerar uma cadência.")
    return icp, oferta, config


_ENQUADRAMENTO_VARIANTE = {
    "A": "Use um tom direto e objetivo, indo reto ao ponto.",
    "B": "Use um tom consultivo, abrindo com uma pergunta sobre o contexto do decisor.",
}


def variante_ab_para_decisor(decisor_id: int) -> str:
    """Distribuição controlada e reproduzível (não aleatória) entre as duas
    variantes do teste A/B (E3-H5)."""
    return "A" if decisor_id % 2 == 0 else "B"


_TENTATIVAS_POR_TOQUE = 3


def _gerar_conteudo_toque(
    llm: LLMProvider,
    icp: ICP,
    oferta: Oferta,
    config: ConfiguracaoComunicacao,
    conta: Conta,
    decisor: Decisor,
    toque: ToqueCadencia,
    variante: str | None = None,
    regras_aprendidas: str = "",
) -> tuple[str | None, bool]:
    """Mensagem personalizada por conta/decisor — não mala direta (E3-H1).

    Tenta até `_TENTATIVAS_POR_TOQUE` vezes (mesmo padrão de
    `comunicacao_service.gerar_amostra`) antes de desistir — raio-X: sem
    retentativa, uma única resposta da IA que mencionasse por acaso uma
    restrição configurada (ex.: o nome da própria empresa/oferta) já
    descartava o toque silenciosamente, podendo zerar o lote inteiro sem
    nenhum aviso.

    Retorna `(conteudo, falhou_por_erro_ia)`. `conteudo` vem `None` por
    dois motivos bem diferentes, por isso o segundo valor: (a) toda
    tentativa violou as restrições configuradas — problema de
    configuração, quem chama deveria revisá-las; ou (b)
    `llm_helpers.gerar` levantou `RegraNegocioViolada` em toda tentativa
    (raio-X mais grave: a IA não respondeu com texto, limite de taxa,
    etc. — instabilidade, não tem nada a ver com o prompt). **Precisa
    capturar essa exceção aqui dentro** — sem o `try/except`, ela
    escapava direto pra fora de `gerar_para_lote` na primeira falha,
    sem nem chegar a tentar de novo, e derrubava a requisição INTEIRA
    (todo o lote, todas as contas) com 409, mesmo com só 1 conta
    selecionada — o "melhor esforço" de pular só o toque problemático
    nunca chegava a valer pra esse caso.

    `regras_aprendidas` (raio-X 2026-09-17, loop de aprendizado do master
    prompt) já vem formatado como trecho de prompt pronto (ou string
    vazia) por `regra_aprendida_service.regras_aplicaveis_texto` — texto
    escrito por um humano depois de observar edição/rejeição repetida
    neste tenant/ICP/oferta/canal."""
    enquadramento_variante = f" {_ENQUADRAMENTO_VARIANTE[variante]}" if variante else ""
    dores_e_gatilhos = (
        f" Dores prováveis desse perfil de cliente: {', '.join(icp.dores)}." if icp.dores else ""
    ) + (f" Gatilhos de abordagem: {', '.join(icp.gatilhos)}." if icp.gatilhos else "")
    diferenciais = f" Diferenciais: {', '.join(oferta.diferenciais)}." if oferta.diferenciais else ""
    provas_sociais = f" Provas sociais: {', '.join(oferta.provas_sociais)}." if oferta.provas_sociais else ""
    prompt = (
        f"Escreva o toque {toque.ordem} (canal {toque.canal}) de uma cadência de prospecção "
        f"para {decisor.nome} ({decisor.cargo or 'decisor'}) na empresa {conta.nome}, "
        f"aderente ao ICP '{icp.nome}' (segmento {icp.segmento}).{dores_e_gatilhos} "
        f"Oferta: '{oferta.nome}' — {oferta.descricao}.{diferenciais}{provas_sociais}{regras_aprendidas} "
        f"Tom: {config.tom}.{enquadramento_variante} Nunca mencione: "
        f"{', '.join(config.restricoes) if config.restricoes else 'nenhuma restrição'}."
    )
    falhou_por_erro_ia = False
    for _ in range(_TENTATIVAS_POR_TOQUE):
        try:
            # max_tokens acima do default (1024) — mensagens de prospecção
            # em português, com contexto de ICP/oferta, às vezes batiam no
            # teto padrão e voltavam cortadas ao meio (ver claude_provider.py).
            resposta = llm_helpers.gerar(llm, LLMRequest(prompt=prompt, max_tokens=2048))
        except RegraNegocioViolada as erro:
            # Raio-X: a retentativa engolia esse erro sem logar nada — o
            # Render só mostrava "POST .../messages 400 Bad Request" (do
            # httpx, sem o corpo do erro), impossível de diagnosticar sem
            # isto. `str(erro)` já inclui a mensagem original da Anthropic
            # (embutida por `llm_helpers.gerar`).
            logger.warning("Falha ao gerar toque via IA (tentativa será refeita): %s", erro)
            falhou_por_erro_ia = True
            continue
        falhou_por_erro_ia = False
        if not comunicacao_service.validar_texto(resposta.content, config.restricoes):
            return resposta.content, False
    return None, falhou_por_erro_ia


def _rodape_por_canal(db: Session, tenant_id: str, decisor: Decisor, canal: str, conteudo: str) -> str:
    if canal == "email":
        token = optout_service.gerar_token(tenant_id, decisor.id)
        link = f"{settings.url_base_api}/opt-out/email/{token}"
        return f"{conteudo}\n\nPara não receber mais e-mails: {link}"
    if canal == "whatsapp":
        return f"{conteudo}\n\nResponda SAIR para parar de receber mensagens."
    return conteudo


def gerar_para_lote(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    cadencia_id: int,
    conta_ids: list[int],
    llm: LLMProvider,
    plan_limits: PlanLimitsProvider,
) -> dict:
    """Gera os toques personalizados para um lote de contas e os submete à
    fila de aprovações — cadência inteira antes de ativar (E3-H1)."""
    if len(conta_ids) > MAXIMO_CONTAS_POR_LOTE:
        raise RegraNegocioViolada(
            f"Selecione no máximo {MAXIMO_CONTAS_POR_LOTE} contas por vez — cada toque gerado é uma "
            "chamada à IA dentro da mesma requisição, e um lote maior arrisca estourar o tempo de "
            "conexão antes de terminar. Gere em lotes menores."
        )
    cadencia = obter(db, tenant_id, cadencia_id)
    _exigir_nao_cancelada(cadencia)
    toques = toques_da_cadencia(db, cadencia.id)
    icp, oferta, config = _contexto_de_geracao(db, tenant_id, cadencia.icp_id, cadencia.oferta_id)
    # Loop de aprendizado (raio-X 2026-09-17) — uma consulta por canal
    # distinto dos toques, não por (conta x toque): o escopo (tenant/ICP/
    # oferta/canal) é o mesmo pra todas as contas deste lote.
    regras_por_canal = {
        canal: regra_aprendida_service.regras_aplicaveis_texto(db, tenant_id, cadencia.icp_id, cadencia.oferta_id, canal)
        for canal in {toque.canal for toque in toques}
    }

    contas_processadas: list[int] = []
    contas_sem_decisor: list[int] = []
    mensagens_geradas = 0
    toques_bloqueados_restricao = 0
    toques_falha_ia = 0

    # Lote (Fase 7B, hardening) — antes buscava `Conta`/primeiro
    # `Decisor` um a um dentro do loop; aqui o custo é ofuscado pela
    # chamada de IA por toque ao lado, mas o lote é trivial e sem risco.
    contas_por_id = {
        conta.id: conta for conta in db.query(Conta).filter(Conta.id.in_(conta_ids), Conta.tenant_id == tenant_id).all()
    }
    primeiro_decisor_por_conta: dict[int, Decisor] = {}
    for decisor_candidato in (
        db.query(Decisor).filter(Decisor.conta_id.in_(conta_ids)).order_by(Decisor.conta_id, Decisor.id).all()
    ):
        primeiro_decisor_por_conta.setdefault(decisor_candidato.conta_id, decisor_candidato)

    for conta_id in conta_ids:
        conta = contas_por_id.get(conta_id)
        if conta is None:
            raise NaoEncontrado(f"Conta {conta_id} não encontrada")

        decisor = primeiro_decisor_por_conta.get(conta.id)
        if decisor is None:
            contas_sem_decisor.append(conta_id)
            continue

        contas_processadas.append(conta_id)
        for toque in toques:
            variante = variante_ab_para_decisor(decisor.id) if toque.ab_teste_habilitado else None
            conteudo, falhou_por_erro_ia = _gerar_conteudo_toque(
                llm, icp, oferta, config, conta, decisor, toque, variante, regras_por_canal[toque.canal]
            )
            if conteudo is None:
                if falhou_por_erro_ia:
                    toques_falha_ia += 1
                else:
                    toques_bloqueados_restricao += 1
                continue
            conteudo = _rodape_por_canal(db, tenant_id, decisor, toque.canal, conteudo)
            aprovacao_service.criar_proposta(
                db,
                tenant_id,
                cadencia.id,
                decisor.id,
                toque.canal,
                toque.template_whatsapp_id,
                conteudo,
                plan_limits,
                toque_cadencia_id=toque.id,
                variante_ab=variante,
            )
            mensagens_geradas += 1

    if mensagens_geradas > 0:
        cadencia.status = "aguardando_aprovacao"

    auditoria_service.registrar(
        db,
        tenant_id,
        "cadencia_gerada_para_lote",
        "cadencia",
        cadencia.id,
        ator_id,
        {"contas_processadas": contas_processadas, "mensagens_geradas": mensagens_geradas},
    )
    db.commit()

    return {
        "contas_processadas": contas_processadas,
        "contas_sem_decisor": contas_sem_decisor,
        "mensagens_geradas": mensagens_geradas,
        "toques_bloqueados_restricao": toques_bloqueados_restricao,
        "toques_falha_ia": toques_falha_ia,
    }


def ativar(
    db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int, plan_limits: PlanLimitsProvider
) -> dict:
    """Ativa a cadência: exige todos os toques aprovados, calcula o
    agendamento e consome a franquia das contas envolvidas (E3-H1, gancho
    da Onda 1 em `franquia_service.consumir_para_ativacao`).

    Raio-X 2026-09-15 ("adicionar mais contas a uma cadência já ativa"):
    escopado só às mensagens com `agendado_para IS NULL` — ou seja, as
    que nenhuma chamada anterior a `ativar` ainda processou. Numa
    cadência nova isso é exatamente todas as mensagens (nenhuma foi
    agendada ainda, então o resultado é idêntico ao de sempre); numa
    cadência já `"ativa"` que recebeu contas novas (`gerar_para_lote`
    não tem guard de status, já funciona em qualquer status), chamar
    `ativar` de novo processa só as mensagens novas, sem re-agendar (ou
    piorar) as que já foram enviadas ou já estavam corretamente
    agendadas antes."""
    cadencia = obter(db, tenant_id, cadencia_id)
    if cadencia.status == "cancelada":
        raise RegraNegocioViolada("Cadência cancelada não pode ser ativada.")
    if any(toque.canal == "email" for toque in toques_da_cadencia(db, cadencia.id)):
        reputacao_service.exigir_canal_nao_pausado(db, tenant_id, "email")

    mensagens = (
        db.query(Mensagem)
        .filter_by(tenant_id=tenant_id, cadencia_id=cadencia.id, agendado_para=None)
        .all()
    )
    if not mensagens:
        raise RegraNegocioViolada("Cadência não tem mensagens novas pendentes de agendamento.")

    for mensagem in mensagens:
        aprovacao = (
            db.query(Aprovacao)
            .filter_by(mensagem_id=mensagem.id)
            .order_by(Aprovacao.id.desc())
            .first()
        )
        if aprovacao is None or aprovacao.status != "aprovado":
            raise RegraNegocioViolada(
                "Cadência tem toques pendentes de aprovação — não pode ser ativada."
            )

    agora = datetime.now(UTC)
    mensagens_por_decisor: dict[int, list[Mensagem]] = {}
    for mensagem in mensagens:
        mensagens_por_decisor.setdefault(mensagem.decisor_id, []).append(mensagem)

    toques_por_id = {toque.id: toque for toque in toques_da_cadencia(db, cadencia.id)}
    conta_ids: set[int] = set()

    for decisor_id, mensagens_do_decisor in mensagens_por_decisor.items():
        decisor = db.query(Decisor).filter_by(id=decisor_id).one()
        conta_ids.add(decisor.conta_id)

        mensagens_ordenadas = sorted(
            mensagens_do_decisor, key=lambda m: toques_por_id[m.toque_cadencia_id].ordem if m.toque_cadencia_id else 0
        )
        data_acumulada = agora
        for mensagem in mensagens_ordenadas:
            toque = toques_por_id.get(mensagem.toque_cadencia_id)
            if toque and toque.ordem > 1:
                data_acumulada = data_acumulada + timedelta(days=toque.intervalo_dias_apos_anterior)
            mensagem.agendado_para = data_acumulada

    franquia = franquia_service.consumir_para_ativacao(db, tenant_id, ator_id, sorted(conta_ids), plan_limits)

    cadencia.status = "ativa"
    if cadencia.data_inicio is None:
        cadencia.data_inicio = agora
    auditoria_service.registrar(
        db, tenant_id, "cadencia_ativada", "cadencia", cadencia.id, ator_id, {"contas": sorted(conta_ids)}
    )
    db.commit()
    db.refresh(cadencia)

    return {"cadencia": cadencia, "franquia": franquia}
