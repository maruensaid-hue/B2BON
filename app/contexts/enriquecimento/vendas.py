"""Venda de pacotes de créditos de enriquecimento: nota fiscal, conciliação financeira e contestação.

Mesmo modelo da compra de créditos de IA (`finops.compras`): checkout no Mercado Pago, crédito só pelo webhook assinado, idempotente. Auditoria do fluxo
existente: nem a compra de créditos de IA nem o pagamento de licença emitem nota fiscal, e a plataforma não tem emissor integrado (OI-025). Por isso a venda
NÃO fica bloqueada pela nota: o checkout funciona como o de IA, e o que existe a mais aqui é opcional e visível:

* **Nota fiscal**: uma por compra, emitida por uma porta (`FiscalProvider`) quando houver emissor configurado. Sem emissor, a nota fica `SEM_EMISSOR`
  (nunca simulada) e a venda aparece como "nota a emitir"; assim que um emissor existir, a emissão acontece no próximo aviso do pagamento ou pelo botão do
  administrador. Falha do emissor não desfaz o crédito pago: a nota fica `FALHA` e pode ser reemitida.
* **Conciliação**: duas dimensões separadas. A **financeira** cruza pedido × pagamento informado × crédito lançado no razão × contestação × estorno, e é
  DERIVADA desses fatos. A **fiscal** diz em que pé está a nota.
* **Contestação** (reembolso, chargeback, cancelamento avisados pelo provedor de pagamento): só sinaliza a compra. Estorno de créditos é sempre um fluxo manual
  com justificativa e aprovação (`estornos.py`)."""

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config, precos
from app.models.enriquecimento_creditos import EnriquecimentoCompra, EnriquecimentoEstornoCompra, EnriquecimentoMovimento, EnriquecimentoNotaFiscal
from app.models.tenant import Tenant
from app.providers.fiscal.base import DadosNota, FiscalIndisponivel, FiscalProvider, FiscalRejeitou
from app.services import auditoria_service
from app.services.errors import NaoEncontrado

logger = logging.getLogger("b2bon.enriquecimento")

TOLERANCIA_VALOR = Decimal("0.01")
ROTULO_SITUACAO = {
    "aguardando_pagamento": "aguardando pagamento", "pagamento_rejeitado": "pagamento rejeitado", "divergente": "divergente (valor ou crédito não confere)",
    "contestada": "contestada pelo provedor de pagamento", "estornada": "créditos estornados", "conciliada": "conciliada",
}
ROTULO_FISCAL = {
    "nao_aplicavel": "—", "pendente": "nota a emitir", "sem_emissor": "nota a emitir (nenhum emissor fiscal configurado)", "falha": "falha na emissão da nota",
    "emitida": "nota emitida",
}


def emitir_nota(db: Session, compra_id: int, fiscal: FiscalProvider, *, ator_id: str | None = None, agora: datetime | None = None) -> EnriquecimentoNotaFiscal:
    """Emite (ou reemite, se `SEM_EMISSOR`/`FALHA`) a nota da compra. Idempotente: nota `EMITIDA` é devolvida sem chamar o emissor. Nunca levanta por falha do
    emissor: registra o estado, para a confirmação do pagamento não ser desfeita por um problema fiscal. Sem emissor configurado, `SEM_EMISSOR`."""
    compra = db.get(EnriquecimentoCompra, compra_id)
    if compra is None:
        raise NaoEncontrado("Compra não encontrada.")
    nota = db.query(EnriquecimentoNotaFiscal).filter_by(compra_id=compra.id).one_or_none()
    if nota is not None and nota.status == "EMITIDA":
        return nota
    if compra.status != "APROVADA":
        raise NaoEncontrado("Só compras com pagamento aprovado têm nota fiscal.")
    if nota is None:
        nota = EnriquecimentoNotaFiscal(compra_id=compra.id, tenant_id=compra.tenant_id, status="PENDENTE", valor_brl=precos.centavos(compra.preco_total_brl))
        db.add(nota)
        db.flush()
    if not fiscal.disponivel:
        nota.status, nota.provedor_fiscal, nota.erro = "SEM_EMISSOR", None, None
        db.commit()
        return nota
    tenant = db.get(Tenant, compra.tenant_id)
    nota.provedor_fiscal, nota.tentativas = fiscal.nome, nota.tentativas + 1
    try:
        if not (tenant and (tenant.cnpj or "").strip() and (tenant.razao_social or "").strip()):
            raise FiscalRejeitou("Cadastro do cliente sem CNPJ ou razão social.")
        emitida = fiscal.emitir(DadosNota(
            chave_idempotencia=f"enriquecimento-compra-{compra.id}", compra_id=compra.id, tenant_id=compra.tenant_id,
            tomador_razao_social=tenant.razao_social, tomador_cnpj=tenant.cnpj,
            descricao=f"Créditos de enriquecimento — pacote {compra.pacote_codigo} ({compra.creditos} créditos)", valor_brl=precos.centavos(compra.preco_total_brl),
        ))
    except (FiscalIndisponivel, FiscalRejeitou) as erro:
        nota.status, nota.erro = "FALHA", str(erro)[:300]
        logger.error("ENRIQUECIMENTO_NOTA_FALHA compra=%s tentativa=%s erro=%s", compra.id, nota.tentativas, nota.erro)
        auditoria_service.registrar(db, compra.tenant_id, "enriquecimento_nota_falhou", "enriquecimento_nota_fiscal", nota.id, ator_id,
                                    {"compra_id": compra.id, "tentativa": nota.tentativas, "erro": nota.erro})
    except Exception as erro:  # noqa: BLE001 - adaptador real com defeito não pode derrubar a confirmação do pagamento
        nota.status, nota.erro = "FALHA", f"erro inesperado no emissor: {type(erro).__name__}"
        logger.exception("ENRIQUECIMENTO_NOTA_EXCECAO compra=%s", compra.id)
    else:
        nota.status, nota.erro = "EMITIDA", None
        nota.numero, nota.chave_acesso = emitida.numero, emitida.chave_acesso
        nota.referencia_externa, nota.url_documento = emitida.referencia_externa, emitida.url_documento
        nota.emitida_em = agora or config.agora_utc()
        auditoria_service.registrar(db, compra.tenant_id, "enriquecimento_nota_emitida", "enriquecimento_nota_fiscal", nota.id, ator_id,
                                    {"compra_id": compra.id, "numero": nota.numero, "provedor_fiscal": fiscal.nome})
    db.commit()
    return nota


def situacao(compra: EnriquecimentoCompra, estornada: bool = False, credito_confere: bool = True) -> str:
    """Situação de conciliação FINANCEIRA, derivada dos fatos registrados: pedido, pagamento informado pelo provedor, crédito lançado no razão, contestação e
    estorno. A nota fiscal é outra dimensão (`situacao_fiscal`)."""
    if compra.status == "PENDENTE":
        return "aguardando_pagamento"
    if compra.status == "REJEITADA":
        return "pagamento_rejeitado"
    if estornada:
        return "estornada"
    if compra.contestacao_status:
        return "contestada"
    if not credito_confere or compra.valor_pago_brl is None or abs(precos.dec(compra.valor_pago_brl) - precos.dec(compra.preco_total_brl)) > TOLERANCIA_VALOR:
        return "divergente"
    return "conciliada"


def situacao_fiscal(compra: EnriquecimentoCompra, nota: EnriquecimentoNotaFiscal | None) -> str:
    if compra.status != "APROVADA":
        return "nao_aplicavel"
    if nota is None or nota.status == "PENDENTE":
        return "pendente"
    return {"EMITIDA": "emitida", "FALHA": "falha", "SEM_EMISSOR": "sem_emissor"}.get(nota.status, "pendente")


def _linha(compra: EnriquecimentoCompra, nota: EnriquecimentoNotaFiscal | None, estornada: bool, credito_lancado: int | None) -> dict:
    confere = compra.status != "APROVADA" or credito_lancado == compra.creditos
    sit, fiscal = situacao(compra, estornada, confere), situacao_fiscal(compra, nota)
    return {
        "compra_id": compra.id, "tenant_id": compra.tenant_id, "pacote": compra.pacote_codigo, "creditos": compra.creditos,
        "preco_total_brl": str(precos.centavos(compra.preco_total_brl)), "status": compra.status,
        "valor_pago_brl": str(compra.valor_pago_brl) if compra.valor_pago_brl is not None else None,
        "taxa_pagamento_brl": str(compra.taxa_pagamento_brl) if compra.taxa_pagamento_brl is not None else None,
        "valor_liquido_brl": str(compra.valor_liquido_brl) if compra.valor_liquido_brl is not None else None,
        "pagamento_id_externo": compra.pagamento_id_externo, "contestacao_status": compra.contestacao_status,
        "credito_lancado": credito_lancado, "credito_confere": confere,
        "nota": None if nota is None else {"status": nota.status, "numero": nota.numero, "emitida_em": nota.emitida_em, "tentativas": nota.tentativas,
                                          "erro": nota.erro, "url_documento": nota.url_documento},
        "situacao": sit, "situacao_rotulo": ROTULO_SITUACAO[sit], "situacao_fiscal": fiscal, "situacao_fiscal_rotulo": ROTULO_FISCAL[fiscal],
        "confirmado_em": compra.confirmado_em, "criado_em": compra.criado_em,
    }


def listar_vendas(db: Session, tenant_id: str | None = None, limite: int = 100) -> list[dict]:
    """Vendas com nota e conciliação. `tenant_id=None` (visão do super admin) cruza tenants."""
    consulta = db.query(EnriquecimentoCompra)
    if tenant_id is not None:
        consulta = consulta.filter(EnriquecimentoCompra.tenant_id == tenant_id)
    compras = consulta.order_by(EnriquecimentoCompra.id.desc()).limit(max(1, min(limite, 500))).all()
    ids = [c.id for c in compras]
    notas = {n.compra_id: n for n in db.query(EnriquecimentoNotaFiscal).filter(EnriquecimentoNotaFiscal.compra_id.in_(ids or [0])).all()}
    estornadas = {e for (e,) in db.query(EnriquecimentoEstornoCompra.compra_id).filter(EnriquecimentoEstornoCompra.compra_id.in_(ids or [0]),
                                                                                       EnriquecimentoEstornoCompra.status == "EXECUTADO").all()}
    chaves = {f"compra:{i}": i for i in ids}
    creditos_no_razao = {chaves[chave]: delta for chave, delta in db.query(EnriquecimentoMovimento.idempotency_key, EnriquecimentoMovimento.delta_saldo).filter(
        EnriquecimentoMovimento.tipo == "COMPRA", EnriquecimentoMovimento.idempotency_key.in_(list(chaves) or [""])).all()}
    return [_linha(c, notas.get(c.id), c.id in estornadas, creditos_no_razao.get(c.id)) for c in compras]


def resumo_conciliacao(db: Session) -> dict:
    """Totais para o painel do super admin: por situação financeira e fiscal, valor bruto vendido (aprovadas), tarifas e líquido informados pelo provedor de
    pagamento, e as vendas cujo crédito no razão não confere com o pedido (a conciliação crédito × pagamento, como a do saldo de IA)."""
    linhas = listar_vendas(db, None, 500)
    por_situacao: dict[str, int] = {}
    por_fiscal: dict[str, int] = {}
    for linha in linhas:
        por_situacao[linha["situacao"]] = por_situacao.get(linha["situacao"], 0) + 1
        if linha["situacao_fiscal"] != "nao_aplicavel":
            por_fiscal[linha["situacao_fiscal"]] = por_fiscal.get(linha["situacao_fiscal"], 0) + 1
    aprovadas = db.query(
        func.coalesce(func.sum(EnriquecimentoCompra.preco_total_brl), 0), func.coalesce(func.sum(EnriquecimentoCompra.taxa_pagamento_brl), 0),
        func.coalesce(func.sum(EnriquecimentoCompra.valor_liquido_brl), 0), func.count(EnriquecimentoCompra.id),
    ).filter(EnriquecimentoCompra.status == "APROVADA").one()
    return {"por_situacao": por_situacao, "por_situacao_fiscal": por_fiscal, "vendas_aprovadas": int(aprovadas[3]), "bruto_brl": str(precos.centavos(aprovadas[0])),
            "taxas_informadas_brl": str(precos.centavos(aprovadas[1])), "liquido_informado_brl": str(precos.centavos(aprovadas[2])),
            "creditos_que_nao_conferem": [linha["compra_id"] for linha in linhas if not linha["credito_confere"]],
            "observacao": "Taxas e líquido só entram quando o provedor de pagamento os informa; nada é estimado."}
