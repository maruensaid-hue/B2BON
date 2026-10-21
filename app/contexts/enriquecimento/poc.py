"""POC de enriquecimento: sem franquia fixa, com autorização e orçamento definidos por operação.

A POC não tem quantidade de créditos inventada. O teto de uma operação é CALCULADO com a política do provedor aprovada (tarifas confirmadas):
empresas × (busca + decisores × revelação) em créditos do provedor, convertidos em créditos do cliente pelo fator da política. Esse teto vira uma
configuração do TENANT (`periodicidade=unica`, uma concessão na vida do tenant) que nasce pendente e só vale depois de aprovada por um administrador
(mesmo caminho de qualquer configuração). O limite é de 1 decisor por empresa, o da linha POC da matriz. Sem política aprovada (ou incompleta) não há
teto: nada é estimado "no chute".

Uma nova operação de POC para o mesmo tenant não ganha franquia nova automaticamente (a concessão `unica` é idempotente): é crédito extra por ajuste
administrativo, com motivo e auditoria."""

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config, precos
from app.services.errors import ValidacaoFalhou


def calcular_teto(db: Session, provedor: str, empresas: int, decisores_por_empresa: int = 1) -> dict:
    """Teto de créditos de uma operação de POC, só com a política APROVADA e completa do provedor."""
    if isinstance(empresas, bool) or not isinstance(empresas, int) or empresas <= 0:
        raise ValidacaoFalhou("Informe o número de empresas da operação (inteiro positivo).")
    if isinstance(decisores_por_empresa, bool) or not isinstance(decisores_por_empresa, int) or decisores_por_empresa <= 0:
        raise ValidacaoFalhou("Informe os decisores por empresa (inteiro positivo).")
    politica, motivo = config.politica_vigente(db, provedor)
    if politica is None:
        raise ValidacaoFalhou(f"Não há teto calculável: {config.mensagem(motivo)}")
    if not politica.utilizavel:
        raise ValidacaoFalhou(f"Não há teto calculável: a política do provedor está incompleta (faltando: {', '.join(politica.faltando)}).")
    por_empresa = politica.creditos_maximos_por_empresa(decisores_por_empresa)
    creditos_provedor = empresas * por_empresa
    creditos_cliente = creditos_provedor * politica.creditos_cliente_por_credito_provedor
    return {
        "provedor": provedor, "politica_id": politica.id, "politica_versao": politica.versao, "empresas": empresas,
        "decisores_por_empresa": decisores_por_empresa, "creditos_provedor_por_empresa": por_empresa, "creditos_provedor_teto": creditos_provedor,
        "creditos_cliente_teto": creditos_cliente,
        "custo_maximo_brl": str(precos.exibir(precos.valor(creditos_provedor, politica.custo_unitario_brl), politica.casas_exibicao)),
        "valor_venda_maximo_brl": str(precos.exibir(precos.valor(creditos_provedor, politica.preco_unitario_brl), politica.casas_exibicao)),
        "aviso": "Teto por operação com as tarifas aprovadas; o consumo real é o medido pelo provedor e costuma ser menor.",
    }


def autorizar(db: Session, tenant_id: str, *, provedor: str, empresas: int, decisores_por_empresa: int = 1, ator_id: str | None,
              tenant_auditoria: str, motivo: str | None) -> dict:
    """Cria (PENDENTE de aprovação) a configuração do tenant que autoriza a operação de POC com o teto calculado. Exige que o plano do tenant seja
    o da POC (`modo=poc_autorizada`) e respeita o limite de decisores da linha POC."""
    plano_id = config.plano_ativo_do_tenant(db, tenant_id)
    plano_cfg = config.config_aprovada_do_plano(db, plano_id) if plano_id is not None else None
    if plano_cfg is None or (plano_cfg.modo or "franquia_fixa") != "poc_autorizada":
        raise ValidacaoFalhou("O plano do tenant não é uma POC com configuração aprovada: autorização de POC só vale para o plano POC.")
    if decisores_por_empresa > plano_cfg.decisores_por_empresa_max:
        raise ValidacaoFalhou(f"A POC permite até {plano_cfg.decisores_por_empresa_max} decisor(es) por empresa.")
    teto = calcular_teto(db, provedor, empresas, decisores_por_empresa)
    creditos = teto["creditos_cliente_teto"]
    nova = config.definir_config(
        db, plano_id=None, tenant_id=tenant_id, ator_id=ator_id, tenant_auditoria=tenant_auditoria,
        motivo=motivo or f"Autorização de POC: {empresas} empresa(s) × {decisores_por_empresa} decisor(es)",
        campos={"modo": "franquia_fixa", "franquia_creditos": creditos, "periodicidade": "unica", "limite_creditos_pesquisa": creditos,
                "decisores_por_empresa_padrao": decisores_por_empresa, "decisores_por_empresa_max": decisores_por_empresa,
                "itens_por_lote_max": empresas},
    )
    return {"config_id": nova.id, "versao": nova.versao, "pendente_aprovacao": True, "teto": teto}
