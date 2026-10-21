"""Dados da matriz comercial de enriquecimento informada pelo PO em 2026-10-21 (franquias por plano e pacotes adicionais).

Módulo SÓ de dados (nenhuma dependência do app): a migração e o serviço `matriz.aplicar` leem os mesmos números, então não há duas cópias que
possam divergir. Estes valores são o ponto de partida aprovado; depois de aplicados viram linhas versionadas e auditadas no banco, e qualquer
mudança futura passa por nova versão aprovada (nunca por edição deste arquivo em produção).

Nada aqui define preço de mensalidade nem outra condição comercial além do que o PO informou."""

APROVADOR_MATRIZ = "po:matriz-2026-10-21"
MOTIVO_MATRIZ = "Matriz de franquias de enriquecimento aprovada pelo PO em 2026-10-21"
MOTIVO_PACOTES = "Pacotes adicionais de enriquecimento aprovados pelo PO em 2026-10-21"

# Franquia mensal incluída = limite máximo de créditos por pesquisa (a matriz usa o mesmo número). Créditos não usados expiram no fim do mês e não
# acumulam. `decisores_por_empresa_max` é por empresa, por pesquisa. Não há valor padrão de decisores nem limite de empresas por pesquisa na matriz:
# ficam nulos (o usuário escolhe o número de decisores; o limite de créditos por pesquisa já limita o tamanho do lote).
#
# `aliases`: nomes com que o plano pode existir no banco (o plano gratuito chama-se "Teste"). Plano que não existe no banco NÃO é criado aqui (criar plano
# exigiria preço): a matriz é aplicada quando ele existir (rodar `aplicar` de novo).
PLANOS: dict[str, dict] = {
    "POC": {
        "aliases": ("POC",),
        # Sem franquia fixa: cada operação exige autorização aprovada por tenant, com teto calculado pelas tarifas confirmadas. Limite: 1 decisor.
        "config": {"modo": "poc_autorizada", "decisores_por_empresa_max": 1},
    },
    "Teste gratuito": {
        "aliases": ("Teste gratuito", "Teste", "Free Trial"),
        "config": {"modo": "franquia_fixa", "franquia_creditos": 30, "periodicidade": "mensal", "limite_creditos_pesquisa": 30, "decisores_por_empresa_max": 3},
    },
    "Starter": {
        "aliases": ("Starter",),
        "config": {"modo": "franquia_fixa", "franquia_creditos": 30, "periodicidade": "mensal", "limite_creditos_pesquisa": 30, "decisores_por_empresa_max": 5},
    },
    "Professional": {
        "aliases": ("Professional",),
        "config": {"modo": "franquia_fixa", "franquia_creditos": 60, "periodicidade": "mensal", "limite_creditos_pesquisa": 60, "decisores_por_empresa_max": 10},
    },
    "Business": {
        "aliases": ("Business",),
        "config": {"modo": "franquia_fixa", "franquia_creditos": 120, "periodicidade": "mensal", "limite_creditos_pesquisa": 120, "decisores_por_empresa_max": 20},
    },
    "Corporate": {
        "aliases": ("Corporate",),
        "config": {"modo": "franquia_fixa", "franquia_creditos": 180, "periodicidade": "mensal", "limite_creditos_pesquisa": 180, "decisores_por_empresa_max": 30},
    },
    # Enterprise: configurável por administrador, por tenant (contatos, créditos, empresas e operações por período). Sem linha no plano.
    "Enterprise": {"aliases": ("Enterprise",), "config": None},
}

# Pacotes adicionais: (código, nome, créditos, preço unitário R$, preço total R$, status, ordem). Preço total = créditos × unitário, exato em centavos.
PACOTES: tuple[tuple, ...] = (
    ("ENRIQ_400", "400 créditos", 400, "1.35", "540.00", "ATIVO", 1),
    ("ENRIQ_660", "660 créditos", 660, "1.28", "844.80", "ATIVO", 2),
    ("ENRIQ_1200", "1.200 créditos", 1200, "1.21", "1452.00", "ATIVO", 3),
    ("ENRIQ_3000", "3.000 créditos", 3000, "1.08", "3240.00", "ATIVO", 4),
    ("ENRIQ_ACIMA_3000", "Acima de 3.000 créditos", None, None, None, "CONTACT_SALES", 5),  # sob negociação: sem preço, sem checkout automático
)

# Base econômica do provedor (Lusha), informada pelo PO em 2026-10-21. A compra pontual de 400 créditos por R$ 269,94 foi DESCONSIDERADA por ele e não
# participa de custo, preço, margem nem configuração. O câmbio é de PLANEJAMENTO (precificação); o contábil é o efetivamente pago (`custo.registrar_pagamento`).
APROVADOR_CUSTO = "po:custo-lusha-2026-10-21"
MOTIVO_CUSTO = "Base econômica Lusha informada pelo PO em 2026-10-21: USD 600/mês, 81.600 créditos/ano, câmbio de planejamento R$ 6,00"
CUSTO_LUSHA = {"provedor": "lusha", "custo_mensal_usd": "600", "creditos_anuais": 81600, "cambio_planejamento_brl": "6.00"}
# Orçamento global = a capacidade mensal equivalente ao teto de USD 600 (81.600 ÷ 12 créditos do provedor por mês).
ORCAMENTO_LUSHA_CREDITOS_MES = CUSTO_LUSHA["creditos_anuais"] // 12
ALERTA_ORCAMENTO_PERCENTUAL = 80
LOTE_DESCONSIDERADO = "APORTE-LUSHA-2026-10-21"
