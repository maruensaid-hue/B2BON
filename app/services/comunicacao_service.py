from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.configuracao_comunicacao import ConfiguracaoComunicacao
from app.models.icp import ICP
from app.models.oferta import Oferta
from app.schemas.comunicacao import ConfiguracaoComunicacaoUpsertSchema
from app.services import auditoria_service
from app.services.errors import RegraNegocioViolada


def obter(db: Session, tenant_id: str) -> ConfiguracaoComunicacao | None:
    return db.query(ConfiguracaoComunicacao).filter_by(tenant_id=tenant_id).one_or_none()


def salvar(
    db: Session, tenant_id: str, ator_id: str | None, dados: ConfiguracaoComunicacaoUpsertSchema
) -> ConfiguracaoComunicacao:
    config = obter(db, tenant_id)
    if config is None:
        config = ConfiguracaoComunicacao(tenant_id=tenant_id, tom=dados.tom, restricoes=dados.restricoes)
        db.add(config)
    else:
        config.tom = dados.tom
        config.restricoes = dados.restricoes
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "comunicacao_configurada", "configuracao_comunicacao", config.id, ator_id, {"tom": config.tom}
    )
    db.commit()
    db.refresh(config)
    return config


def validar_texto(texto: str, restricoes: list[str]) -> list[str]:
    """Lista de restrições bloqueia geração que as viole (E1-H3).

    Função pura, reusável quando a geração real de mensagens existir (E3).
    """
    texto_normalizado = texto.lower()
    return [restricao for restricao in restricoes if restricao.lower() in texto_normalizado]


def gerar_amostra(
    db: Session,
    tenant_id: str,
    llm: LLMProvider,
    icp: ICP,
    oferta: Oferta,
    config: ConfiguracaoComunicacao,
    quantidade: int = 3,
    tentativas_por_mensagem: int = 3,
) -> list[str]:
    """Usuário vê `quantidade` mensagens de exemplo, sem violar restrições,
    antes de ativar o motor (E1-H3)."""
    mensagens: list[str] = []
    for indice in range(quantidade):
        texto_valido: str | None = None
        for _ in range(tentativas_por_mensagem):
            resposta = llm.generate(
                LLMRequest(
                    prompt=(
                        f"Escreva a mensagem de prospecção nº {indice + 1} para o ICP "
                        f"'{icp.nome}' (segmento {icp.segmento}), oferecendo '{oferta.nome}'. "
                        f"Tom: {config.tom}. Nunca mencione: "
                        f"{', '.join(config.restricoes) if config.restricoes else 'nenhuma restrição'}."
                    ),
                )
            )
            if not validar_texto(resposta.content, config.restricoes):
                texto_valido = resposta.content
                break
        if texto_valido is None:
            raise RegraNegocioViolada(
                "Não foi possível gerar uma amostra sem violar as restrições configuradas."
            )
        mensagens.append(texto_valido)

    auditoria_service.registrar(
        db, tenant_id, "amostra_gerada", "configuracao_comunicacao", config.id, None, {"quantidade": len(mensagens)}
    )
    db.commit()
    return mensagens
