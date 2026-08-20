import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.reuniao import Reuniao
from app.providers.meeting_bot.base import MeetingBotProvider
from app.services import atividade_service, llm_helpers

logger = logging.getLogger(__name__)

# Links de reunião gerados pelo StubCalendarProvider/StubMeetingBotProvider
# (dev/teste) — nunca agenda bot de verdade pra eles.
_PREFIXOS_LINK_STUB = ("https://meet.stub/",)


def agendar_transcricao_pos_confirmacao(db: Session, reuniao: Reuniao, provider: MeetingBotProvider) -> None:
    """Chamado pela rota logo depois que `reuniao_service.confirmar` já
    comitou — de propósito fora do serviço de confirmação, pra não herdar
    a regra "se falhar, a reunião não confirma" (a reunião já está
    confirmada nesse ponto; o bot de transcrição é melhor-esforço)."""
    if not reuniao.link_reuniao or reuniao.link_reuniao.startswith(_PREFIXOS_LINK_STUB):
        return

    webhook_url = f"{settings.url_base_api}/webhooks/recall/eventos"
    try:
        bot_id = provider.agendar_bot(reuniao.link_reuniao, reuniao.horario_confirmado, webhook_url)
    except Exception:
        logger.exception("Falha ao agendar bot de transcrição pra reunião %s", reuniao.id)
        return

    reuniao.bot_id = bot_id
    reuniao.status_transcricao = "agendado"
    db.commit()


def _negocio_id_numerico(origem_crm_id: str | None) -> int | None:
    """Mesmo parse tolerante de `reuniao_service._confirmar_interno` —
    `StubCrmProvider` (teste) devolve id não numérico."""
    return int(origem_crm_id) if origem_crm_id and origem_crm_id.isdigit() else None


def processar_transcricao(db: Session, reuniao: Reuniao, llm: LLMProvider, texto_transcricao: str) -> None:
    """Chamado pelo webhook do bot quando a transcrição fica pronta — gera
    o resumo via LLM e alimenta a mesma `Atividade` que já aparece tanto no
    cadastro da Conta quanto no da Oportunidade (uma linha só, com
    `conta_id` e `negocio_id` preenchidos ao mesmo tempo — mesmo mecanismo
    já usado em `reuniao_service._confirmar_interno`)."""
    resposta = llm_helpers.gerar(
        llm,
        LLMRequest(
            prompt=f"Transcrição da reunião:\n\n{texto_transcricao}",
            system=(
                "Você resume reuniões de vendas B2B para o CRM, de forma objetiva e curta: "
                "principais pontos discutidos, decisões tomadas e próximos passos combinados. "
                "Sem introdução nem despedida, só o resumo."
            ),
        ),
    )

    reuniao.transcricao = texto_transcricao
    reuniao.resumo_ia = resposta.content
    reuniao.status_transcricao = "concluida"

    atividade_service.registrar(
        db,
        reuniao.tenant_id,
        conta_id=reuniao.conta_id,
        negocio_id=_negocio_id_numerico(reuniao.origem_crm_id),
        tipo="reuniao",
        descricao=f"Transcrição da reunião — resumo automático:\n\n{resposta.content}",
        ator_id=None,
    )
    db.commit()
