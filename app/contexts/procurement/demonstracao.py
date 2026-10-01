"""Dados fictícios do lado comprador para o ambiente de demonstração (D-082): Public Procurement e Strategic Sourcing.

Fica dentro do contexto (barreira Buy/Sell): registra-se em `shared.demonstracao` e é chamado por quem monta a
demonstração sem que ninguém de fora importe procurement. Usa as mesmas funções da API, então nasce em estados válidos.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.procurement import cadastros, estrategico
from app.contexts.shared import demonstracao


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _compras_publicas(db: Session, tenant_id: str, usuario_id: int) -> None:
    """Public Procurement (lado comprador): órgão, PCA, demandas, processo em pesquisa de preços, fornecedores e contratos."""
    C = cadastros
    hoje = date.today()
    orgao = C.criar(db, tenant_id, usuario_id, "orgao_publico", {"nome": "Prefeitura Municipal de Vale do Sol (demonstração)",
                                                                 "esfera": "MUNICIPAL", "regime_juridico": "LEI_14133"})
    unidade = C.criar(db, tenant_id, usuario_id, "unidade_compras", {"orgao_id": orgao.id, "nome": "Secretaria de Infraestrutura", "codigo": "SINFRA"})
    pca = C.criar(db, tenant_id, usuario_id, "plano_contratacao", {"orgao_id": orgao.id, "ano": hoje.year + 1, "nome": f"PCA {hoje.year + 1}"})
    itens = [C.criar(db, tenant_id, usuario_id, "item_pca", {"plano_id": pca.id, "descricao": descricao, "categoria": categoria,
                                                             "valor_estimado": valor, "data_prevista": hoje + timedelta(days=dias)})
             for descricao, categoria, valor, dias in (("Manutenção de bombas e motores", "SERVICOS", 480000.0, 60),
                                                       ("Notebooks para as escolas municipais", "TI", 350000.0, 120),
                                                       ("Limpeza predial do Paço", "SERVICOS", 220000.0, 200))]
    for necessidade, valor, prioridade in (("Manutenção preventiva das 12 estações elevatórias", 480000.0, "ALTA"),
                                           ("Reposição de 300 notebooks da rede de ensino", 350000.0, "MEDIA")):
        C.criar(db, tenant_id, usuario_id, "demanda_compra", {"unidade_id": unidade.id, "necessidade": necessidade, "valor_estimado": valor,
                                                              "prioridade": prioridade, "categoria": "SERVICOS",
                                                              "justificativa": "Previsto no PCA e no orçamento do próximo exercício",
                                                              "data_necessaria": hoje + timedelta(days=90), "solicitante_usuario_id": usuario_id})
    processo = C.criar(db, tenant_id, usuario_id, "processo_contratacao", {
        "orgao_id": orgao.id, "unidade_id": unidade.id, "item_pca_id": itens[0].id, "numero": f"PE {hoje.year}/0042",
        "objeto": "Manutenção preventiva e preditiva de bombas e motores das estações elevatórias", "modalidade": "PREGAO_ELETRONICO",
        "categoria": "SERVICOS", "valor_estimado": 480000.0, "prazo_previsto": hoje + timedelta(days=75), "responsavel_usuario_id": usuario_id})
    for status in ("ESTUDOS_TECNICOS", "TERMO_REFERENCIA", "PESQUISA_PRECOS"):
        C.atualizar(db, tenant_id, usuario_id, "processo_contratacao", processo.id, {"status": status})
    for tipo, fonte, preco in (("PAINEL_PRECOS", "Painel de Preços — contratação similar", 3850.0),
                               ("COTACAO_FORNECEDOR", "Cotação — fornecedor A", 4120.0), ("COTACAO_FORNECEDOR", "Cotação — fornecedor B", 3990.0)):
        C.criar(db, tenant_id, usuario_id, "pesquisa_preco", {"processo_id": processo.id, "item_descricao": "Conjunto motobomba monitorado/mês",
                                                              "unidade": "unidade/mês", "preco_unitario": preco, "fonte_tipo": tipo,
                                                              "fonte_descricao": fonte, "data_coleta": hoje - timedelta(days=4)})
    fornecedores = [C.criar(db, tenant_id, usuario_id, "fornecedor_compras", {"razao_social": nome, "categorias": categorias,
                                                                              "dados_internos": {"avaliacao": nota}})
                    for nome, categorias, nota in (("Hidrotec Serviços Ltda. (fictícia)", ["SERVICOS"], 4.1),
                                                   ("Limpa Bem Facilities Ltda. (fictícia)", ["SERVICOS"], 3.6),
                                                   ("InfoEscola Tecnologia S.A. (fictícia)", ["TI"], 4.5))]
    C.criar(db, tenant_id, usuario_id, "contrato_compra", {
        "orgao_id": orgao.id, "fornecedor_id": fornecedores[1].id, "numero": f"CT {hoje.year - 1}/0118", "objeto": "Limpeza predial do Paço Municipal",
        "categoria": "SERVICOS", "valor_inicial": 198000.0, "vigencia_inicio": hoje - timedelta(days=330), "vigencia_fim": hoje + timedelta(days=35),
        "necessidade_continuada": True, "sla": "Equipe de 12 pessoas, 2 turnos"})
    C.criar(db, tenant_id, usuario_id, "contrato_compra", {
        "orgao_id": orgao.id, "fornecedor_id": fornecedores[0].id, "numero": f"CT {hoje.year}/0007", "objeto": "Manutenção corretiva de bombas",
        "categoria": "SERVICOS", "valor_inicial": 145000.0, "vigencia_inicio": hoje - timedelta(days=120), "vigencia_fim": hoje + timedelta(days=245)})


def _sourcing(db: Session, tenant_id: str, usuario_id: int) -> None:
    """Strategic Sourcing (comprador privado): RFP de notebooks com propostas avaliadas e RFQ de manutenção predial em rascunho."""
    E = estrategico
    rfp = E.criar_processo(db, tenant_id, usuario_id, {"tipo_processo": "RFP", "titulo": "Notebooks corporativos para 200 colaboradores",
                                                        "descricao": "Renovação do parque de notebooks com garantia on-site de 36 meses",
                                                        "prazo": _agora() + timedelta(days=10), "valor_estimado": 1100000.0, "moeda": "BRL"})
    requisitos = [E.adicionar_requisito(db, tenant_id, usuario_id, rfp.id, {"categoria": categoria, "texto": texto, "obrigatorio": obrigatorio, "peso": peso})
                  for categoria, texto, obrigatorio, peso in (("REQUISITO_TECNICO", "16 GB de RAM e SSD de 512 GB", True, 3),
                                                              ("GARANTIA", "Garantia on-site de 36 meses", True, 2),
                                                              ("SLA", "Substituição em até 2 dias úteis", False, 2),
                                                              ("REQUISITO_COMERCIAL", "Pagamento em 60 dias", False, 1))]
    participantes = [E.convidar(db, tenant_id, usuario_id, rfp.id, {"nome": nome}) for nome in
                     ("TecnoDistribuidora Ltda. (fictícia)", "Grupo Byte Corporativo S.A. (fictício)", "Nuvem Hardware Ltda. (fictícia)")]
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        E.mudar_status(db, tenant_id, usuario_id, rfp.id, status)
    notas = ((1050000.0, 8, ("COMPLIANT", "COMPLIANT", "COMPLIANT", "PARTIALLY_COMPLIANT")),
             (980000.0, 15, ("COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "COMPLIANT")),
             (1120000.0, 5, ("COMPLIANT", "COMPLIANT", "COMPLIANT", "COMPLIANT")))
    for participante, (valor, prazo, avaliacoes) in zip(participantes, notas, strict=True):
        proposta = E.registrar_proposta(db, tenant_id, usuario_id, rfp.id, {"participante_id": participante.id, "valor_total": valor,
                                                                            "prazo_entrega_dias": prazo})
        for requisito, status in zip(requisitos, avaliacoes, strict=True):
            E.avaliar(db, tenant_id, usuario_id, proposta.id, requisito.id, status, 9 if status == "COMPLIANT" else 6, "Avaliação da área de TI")
    rfq = E.criar_processo(db, tenant_id, usuario_id, {"tipo_processo": "RFQ", "titulo": "Manutenção predial das unidades de São Paulo",
                                                        "descricao": "Cotação para contrato anual de manutenção predial",
                                                        "valor_estimado": 240000.0, "moeda": "BRL"})
    E.adicionar_requisito(db, tenant_id, usuario_id, rfq.id, {"categoria": "REQUISITO_TECNICO", "texto": "Equipe técnica com NR-10",
                                                               "obrigatorio": True, "peso": 2})


def semear(db: Session, tenant_id: str, usuario_id: int) -> None:
    _compras_publicas(db, tenant_id, usuario_id)
    _sourcing(db, tenant_id, usuario_id)


demonstracao.registrar("procurement", semear)
