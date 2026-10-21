"""Conciliação do razão com o uso informado pelo próprio provedor (`GET /v3/account/usage` na Lusha).

Também sincroniza a política do provedor com as TARIFAS que ele próprio informa (`pricing` da mesma consulta), sem aprovação manual adicional: as decisões
comerciais (custo, créditos, câmbio de planejamento, preços dos pacotes) já são do PO; as tarifas por ação são fato do provedor.

Cada leitura guarda os créditos usados segundo o provedor e compara a variação desde a leitura anterior com os créditos do provedor lançados
como consumo no razão no mesmo intervalo. Diferença ≠ 0 é divergência: vira alerta (log de erro, destaque no painel administrativo) e exige
investigação — pode ser pesquisa ambígua ainda não reconciliada, uso da conta fora do B2B ON ou virada de ciclo do provedor. Nada é ajustado
automaticamente."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config, custo, pacotes, precos
from app.contexts.enriquecimento.config import agora_utc
from app.models.enriquecimento_creditos import EnriquecimentoMovimento, EnriquecimentoUsoProvedor
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.services import auditoria_service
from app.services.errors import PesquisaBloqueada, ValidacaoFalhou

logger = logging.getLogger("b2bon.enriquecimento")

ATOR_SISTEMA = "sistema:politica-do-provedor"
# Nomes das ações em `pricing` de `GET /v3/account/usage` (docs.lusha.com): busca de contatos, revelação de e-mail e de telefone.
ACAO_BUSCA, ACAO_EMAIL, ACAO_TELEFONE = "api_search", "revealEmail", "revealPhone"
# Dados revelados pela pesquisa: só e-mail. A matriz de franquias (ex.: 30 créditos para até 5 decisores por empresa) só fecha com ~1 crédito por contato,
# e o telefone custa 5. O administrador pode publicar uma política que também revele telefones.
REVELAR_EMAILS, REVELAR_TELEFONES = True, False


def _leitura(provider: ContactEnrichmentProvider):
    try:
        return provider.consultar_uso()
    except NotImplementedError:
        raise PesquisaBloqueada("Este provedor não informa o próprio uso, então não há como conciliar automaticamente.",
                                "provedor_sem_consulta_de_uso") from None
    except Exception:  # noqa: BLE001 — a mensagem do provedor/da rede pode conter detalhes; o log guarda o rastro
        logger.exception("ENRIQUECIMENTO_FALHA_CONSULTA_USO provedor=%s", provider.nome_provedor)
        raise PesquisaBloqueada("Não foi possível consultar o uso no provedor agora. Tente novamente em instantes.",
                                "falha_consulta_uso_provedor") from None


def tarifas_do_provedor(provider: ContactEnrichmentProvider) -> dict:
    """Tarifas por ação, como o PRÓPRIO provedor publica, para o administrador conferir antes de aprovar a política. Só leitura: nada é gravado."""
    uso = _leitura(provider)
    return {"provedor": provider.nome_provedor, "tarifas": uso.tarifas}


def conciliar(db: Session, provider: ContactEnrichmentProvider, ator_id: str | None, tenant_auditoria: str, agora: datetime | None = None) -> dict:
    agora = agora or agora_utc()
    uso = _leitura(provider)
    anterior = (
        db.query(EnriquecimentoUsoProvedor).filter_by(provedor=provider.nome_provedor).order_by(EnriquecimentoUsoProvedor.id.desc()).first()
    )
    delta_provedor = delta_razao = divergencia = None
    if anterior is not None and anterior.creditos_usados is not None and uso.creditos_usados is not None:
        delta_provedor = uso.creditos_usados - anterior.creditos_usados
        delta_razao = int(db.query(func.coalesce(func.sum(EnriquecimentoMovimento.provedor_delta_consumido), 0)).filter(
            EnriquecimentoMovimento.provedor == provider.nome_provedor, EnriquecimentoMovimento.criado_em > anterior.lido_em,
            EnriquecimentoMovimento.criado_em <= agora).scalar() or 0)
        divergencia = delta_provedor - delta_razao
    leitura = EnriquecimentoUsoProvedor(
        provedor=provider.nome_provedor, lido_em=agora, lido_por=ator_id, creditos_total=uso.creditos_total, creditos_usados=uso.creditos_usados,
        creditos_restantes=uso.creditos_restantes, anterior_id=anterior.id if anterior else None, delta_provedor=delta_provedor, delta_razao=delta_razao,
        divergencia=divergencia,
    )
    db.add(leitura)
    db.flush()
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_conciliacao_provedor", "enriquecimento_uso_provedor", leitura.id, ator_id,
                                {"provedor": provider.nome_provedor, "usados": uso.creditos_usados, "delta_provedor": delta_provedor,
                                 "delta_razao": delta_razao, "divergencia": divergencia})
    db.commit()
    if divergencia:
        logger.error("ENRIQUECIMENTO_DIVERGENCIA_PROVEDOR provedor=%s delta_provedor=%s delta_razao=%s divergencia=%s", provider.nome_provedor,
                     delta_provedor, delta_razao, divergencia)
    return {**serializar(leitura), "capacidade": conferir_capacidade(db, provider, uso)}


def serializar(leitura: EnriquecimentoUsoProvedor) -> dict:
    explicacao = None
    if leitura.divergencia is None:
        explicacao = "Primeira leitura (ou sem leitura anterior comparável): sem base de comparação ainda."
    elif leitura.divergencia == 0:
        explicacao = "O uso informado pelo provedor bate com o razão desde a leitura anterior."
    elif leitura.delta_provedor is not None and leitura.delta_provedor < 0:
        explicacao = "O uso do provedor diminuiu: provável virada de ciclo da conta. Confira antes de concluir que há divergência."
    else:
        explicacao = ("Divergência: investigue pesquisas ambíguas ainda não reconciliadas, uso da conta fora do B2B ON ou consumo não lançado "
                      "no razão. Nada foi ajustado automaticamente.")
    return {
        "id": leitura.id, "provedor": leitura.provedor, "lido_em": leitura.lido_em, "creditos_total": leitura.creditos_total,
        "creditos_usados": leitura.creditos_usados, "creditos_restantes": leitura.creditos_restantes, "delta_provedor": leitura.delta_provedor,
        "delta_razao": leitura.delta_razao, "divergencia": leitura.divergencia, "explicacao": explicacao,
    }


def listar(db: Session, provedor: str, limite: int = 20) -> list[dict]:
    leituras = (
        db.query(EnriquecimentoUsoProvedor).filter_by(provedor=provedor).order_by(EnriquecimentoUsoProvedor.id.desc()).limit(min(max(limite, 1), 100)).all()
    )
    return [serializar(leitura) for leitura in leituras]


def _creditos_por_unidade(tarifas: dict, acao: str) -> int | None:
    """Créditos por unidade de uma ação, a partir de `{"credits": n, "perQuantity": m}` como o provedor publica. Ausente = None. Fração (ex.: 1 crédito por
    25 resultados) não cabe no modelo de créditos inteiros por unidade e vira bloqueio técnico explícito, nunca arredondamento silencioso."""
    entrada = tarifas.get(acao)
    if not isinstance(entrada, dict):
        return None
    try:
        creditos, por = Decimal(str(entrada.get("credits"))), Decimal(str(entrada.get("perQuantity", 1)))
    except Exception:  # noqa: BLE001 - valor ilegível do provedor
        raise ValidacaoFalhou(f"A tarifa '{acao}' informada pelo provedor está ilegível: {entrada!r}.") from None
    if creditos < 0 or por <= 0 or not creditos.is_finite() or not por.is_finite():
        raise ValidacaoFalhou(f"A tarifa '{acao}' informada pelo provedor é inválida: {entrada!r}.")
    unidade = creditos / por
    if unidade != unidade.to_integral_value():
        raise ValidacaoFalhou(f"Bloqueio técnico: a tarifa '{acao}' do provedor ({creditos} crédito(s) por {por}) não é um número inteiro de créditos por unidade, "
                              "e o modelo de reserva trabalha com créditos inteiros por unidade.")
    return int(unidade)


def _igual(vigente, alvo: dict) -> bool:
    return (vigente.creditos_busca_por_resultado == alvo["busca"] and vigente.creditos_email == alvo["email"] and vigente.creditos_telefone == alvo["telefone"]
            and vigente.revelar_emails == REVELAR_EMAILS and vigente.revelar_telefones == REVELAR_TELEFONES
            and vigente.tamanho_pagina_busca == alvo["pagina"] and vigente.creditos_cliente_por_credito_provedor == 1
            and vigente.markup_percentual == alvo["markup"] and vigente.custo_unitario_brl == alvo["custo"])


def sincronizar_politica(db: Session, provider: ContactEnrichmentProvider, *, ator_id: str = ATOR_SISTEMA,
                         tenant_auditoria: str = auditoria_service.TENANT_PLATAFORMA) -> dict:
    """Publica (e já aprova, em nome do sistema) a política do provedor derivada de dados que já existem: tarifas por ação informadas pelo PRÓPRIO provedor,
    custo contratual aprovado pelo PO, preço de referência = menor pacote ativo do catálogo aprovado, página mínima aceita pela integração, 1 crédito do
    cliente por crédito do provedor. Idempotente: se a política vigente já é igual, não cria versão.

    Limitação técnica (nunca preenchida no chute): se o provedor não informar a tarifa da busca ou do e-mail, ou informar uma fração, levanta
    `ValidacaoFalhou` descrevendo exatamente o que faltou, e a pesquisa permanece bloqueada."""
    nome = provider.nome_provedor
    contrato = custo.custo_vigente(db, nome)
    if contrato is None:
        raise ValidacaoFalhou("Bloqueio técnico: não há custo contratual cadastrado para este provedor.")
    referencia = min((p for p in pacotes.pacotes_vigentes(db) if p.status == "ATIVO" and p.quantidade_creditos), key=lambda p: p.quantidade_creditos, default=None)
    if referencia is None:
        raise ValidacaoFalhou("Bloqueio técnico: não há pacote ativo aprovado para servir de preço de referência.")
    if not provider.tamanho_pagina_minimo:
        raise ValidacaoFalhou("Bloqueio técnico: a integração não declara o tamanho mínimo de página da busca.")
    uso = _leitura(provider)
    busca, email, telefone = (_creditos_por_unidade(uso.tarifas, a) for a in (ACAO_BUSCA, ACAO_EMAIL, ACAO_TELEFONE))
    faltam = [rotulo for rotulo, valor in ((ACAO_BUSCA, busca), (ACAO_EMAIL, email)) if valor is None]
    if faltam:
        raise ValidacaoFalhou("Bloqueio técnico: a Lusha não informou, em GET /v3/account/usage (pricing), a tarifa de " + ", ".join(faltam)
                              + f". Chaves recebidas: {sorted(uso.tarifas) or 'nenhuma'}. Sem a tarifa não há teto de reserva confiável.")
    alvo = {"busca": busca, "email": email, "telefone": telefone, "pagina": provider.tamanho_pagina_minimo,
            "markup": precos.markup_percentual(referencia.preco_unitario_brl, contrato.custo_unitario_brl).quantize(Decimal("0.0001")),
            "custo": contrato.custo_unitario_brl}
    vigente, _ = config.politica_vigente(db, nome)
    if vigente is not None and vigente.utilizavel and _igual(vigente, alvo):
        return {"alterada": False, "politica_id": vigente.id, "versao": vigente.versao, "tarifas": {"busca": busca, "email": email, "telefone": telefone}}
    nova = config.definir_politica(
        db, provedor=nome, creditos_busca_por_resultado=busca, creditos_email=email, creditos_telefone=telefone, revelar_emails=REVELAR_EMAILS,
        revelar_telefones=REVELAR_TELEFONES, tamanho_pagina_busca=alvo["pagina"], creditos_cliente_por_credito_provedor=1, markup_percentual=alvo["markup"],
        metodo_custo="contrato_mensal", lote_compra_id=None, casas_exibicao=2, fonte_tarifas="provedor_usage", ator_id=ator_id, tenant_auditoria=tenant_auditoria,
        motivo=f"Sincronização com as tarifas informadas pelo provedor; preço de referência: pacote {referencia.codigo}",
        tamanho_pagina_minimo=provider.tamanho_pagina_minimo, tamanho_pagina_maximo=provider.max_contatos_por_consulta, aprovar=True)
    logger.info("ENRIQUECIMENTO_POLITICA_SINCRONIZADA provedor=%s versao=%s busca=%s email=%s telefone=%s", nome, nova.versao, busca, email, telefone)
    return {"alterada": True, "politica_id": nova.id, "versao": nova.versao, "tarifas": {"busca": busca, "email": email, "telefone": telefone}}


def conferir_capacidade(db: Session, provider: ContactEnrichmentProvider, uso=None) -> dict:
    """Compara os créditos totais do ciclo informados pela Lusha com os créditos anuais do contrato cadastrado (81.600). Divergência não bloqueia nada: vira aviso."""
    contrato = custo.custo_vigente(db, provider.nome_provedor)
    uso = uso or _leitura(provider)
    if contrato is None or uso.creditos_total is None:
        return {"confere": None, "esperado_anual": contrato.creditos_anuais if contrato else None, "informado_pelo_provedor": uso.creditos_total}
    confere = uso.creditos_total == contrato.creditos_anuais
    if not confere:
        logger.warning("ENRIQUECIMENTO_CAPACIDADE_DIVERGENTE provedor=%s contrato=%s provedor_informa=%s", provider.nome_provedor, contrato.creditos_anuais, uso.creditos_total)
    return {"confere": confere, "esperado_anual": contrato.creditos_anuais, "informado_pelo_provedor": uso.creditos_total,
            "explicacao": "Os créditos totais informados pela Lusha batem com o contrato." if confere else
            "Os créditos totais informados pela Lusha diferem dos créditos anuais cadastrados: confira o contrato ou o cadastro de custo."}


def conciliar_se_devido(db: Session, provider: ContactEnrichmentProvider, ator_id: str | None, tenant_auditoria: str, intervalo_horas: int = 6,
                        agora: datetime | None = None) -> dict | None:
    """Rotina agendada: concilia com o uso do provedor no máximo uma vez por intervalo (o uso da Lusha tem limite de 5 consultas/min)."""
    agora = agora or agora_utc()
    ultima = db.query(EnriquecimentoUsoProvedor).filter_by(provedor=provider.nome_provedor).order_by(EnriquecimentoUsoProvedor.id.desc()).first()
    if ultima is not None and agora - ultima.lido_em < timedelta(hours=intervalo_horas):
        return None
    return conciliar(db, provider, ator_id, tenant_auditoria, agora)


def rotina(db: Session, provider: ContactEnrichmentProvider, agora: datetime | None = None) -> dict:
    """Tarefa agendada (cron de créditos): mantém a política alinhada às tarifas do provedor e concilia o uso. Só roda para provedor pago e configurado
    (com credencial). Cada etapa falha isolada: o motivo fica no resultado e no log, sem derrubar o cron nem pedir aprovação a ninguém."""
    if not provider.pago or not provider.disponivel:
        return {"ativa": False}
    resultado: dict = {"ativa": True}
    for etapa, funcao in (("politica", lambda: sincronizar_politica(db, provider)),
                          ("conciliacao", lambda: conciliar_se_devido(db, provider, ATOR_SISTEMA, auditoria_service.TENANT_PLATAFORMA, agora=agora))):
        try:
            resultado[etapa] = funcao()
        except (PesquisaBloqueada, ValidacaoFalhou) as erro:
            db.rollback()
            resultado[etapa] = {"erro": str(erro)}
            logger.warning("ENRIQUECIMENTO_ROTINA_%s_FALHOU provedor=%s motivo=%s", etapa.upper(), provider.nome_provedor, erro)
        except Exception:  # noqa: BLE001 - uma etapa com defeito não derruba o cron
            db.rollback()
            resultado[etapa] = {"erro": "falha inesperada (ver log)"}
            logger.exception("ENRIQUECIMENTO_ROTINA_%s_EXCECAO provedor=%s", etapa.upper(), provider.nome_provedor)
    return resultado
