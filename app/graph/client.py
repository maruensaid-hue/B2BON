import logging
from typing import Callable

from neo4j import Driver, GraphDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)


def sincronizar_com_tolerancia(operacao_grafo: Callable[[], None], entidade: str, entidade_id: int | str) -> bool:
    """Grava no Neo4j é um espelho pra visualização de relacionamento
    (E2-H3) — nunca o registro de origem. Uma falha aqui (Neo4j fora do
    ar, AuraDB pausada, credencial errada, etc.) não pode derrubar a
    operação principal, que já está commitada no banco relacional; só
    perde a atualização do grafo até a próxima sincronização. Devolve se
    sincronizou, pra quem chama só marcar `neo4j_node_id` quando o nó
    realmente existe."""
    try:
        operacao_grafo()
        return True
    except Exception:
        logger.warning("Falha ao sincronizar %s %s com o grafo Neo4j", entidade, entidade_id, exc_info=True)
        return False


class Neo4jClient:
    """Cliente do grafo de relacionamentos (Seção 11 da especificação).

    `run_query` é o wrapper genérico do driver. Os métodos de domínio abaixo
    (upsert de conta/decisor, interação, leitura do grafo de uma conta) são o
    vocabulário usado pelo E2 — mantê-los aqui, em vez de Cypher solto nos
    serviços, é o que permite um duplo de teste simples (`FakeGraphClient`)
    sem precisar interpretar Cypher.
    """

    def __init__(self) -> None:
        self._driver: Driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    def run_query(self, query: str, parameters: dict | None = None) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def upsert_conta(self, tenant_id: str, conta_id: int, propriedades: dict) -> None:
        props = {"id": conta_id, "tenant_id": tenant_id, **propriedades}
        self.run_query(
            "MERGE (c:Conta {id: $conta_id, tenant_id: $tenant_id}) SET c += $propriedades",
            {"conta_id": conta_id, "tenant_id": tenant_id, "propriedades": props},
        )

    def upsert_decisor(self, tenant_id: str, decisor_id: int, conta_id: int, propriedades: dict) -> None:
        props = {"id": decisor_id, "tenant_id": tenant_id, **propriedades}
        self.run_query(
            "MERGE (d:Decisor {id: $decisor_id, tenant_id: $tenant_id}) SET d += $propriedades "
            "MERGE (c:Conta {id: $conta_id, tenant_id: $tenant_id}) "
            "MERGE (d)-[:DECISOR_DE]->(c)",
            {
                "decisor_id": decisor_id,
                "tenant_id": tenant_id,
                "conta_id": conta_id,
                "propriedades": props,
            },
        )

    def registrar_interacao(self, tenant_id: str, decisor_id: int, interacao_id: int, propriedades: dict) -> None:
        props = {"id": interacao_id, "tenant_id": tenant_id, **propriedades}
        self.run_query(
            "MERGE (d:Decisor {id: $decisor_id, tenant_id: $tenant_id}) "
            "MERGE (i:Interacao {id: $interacao_id, tenant_id: $tenant_id}) SET i += $propriedades "
            "MERGE (d)-[:INTERAGIU_COM]->(i)",
            {
                "decisor_id": decisor_id,
                "interacao_id": interacao_id,
                "tenant_id": tenant_id,
                "propriedades": props,
            },
        )

    def registrar_indicacao(
        self, tenant_id: str, promotor_decisor_id: int, indicado_conta_id: int, oportunidade_id: str | None = None
    ) -> None:
        """Aresta de indicação — promotor (Decisor) -> indicado (Conta),
        e indicado -> Oportunidade quando já existe negócio (E11-H3)."""
        self.run_query(
            "MERGE (p:Decisor {id: $promotor_id, tenant_id: $tenant_id}) "
            "MERGE (i:Conta {id: $indicado_id, tenant_id: $tenant_id}) "
            "MERGE (p)-[:INDICOU]->(i)",
            {"promotor_id": promotor_decisor_id, "indicado_id": indicado_conta_id, "tenant_id": tenant_id},
        )
        if oportunidade_id is None:
            return
        self.run_query(
            "MERGE (i:Conta {id: $indicado_id, tenant_id: $tenant_id}) "
            "MERGE (o:Oportunidade {id: $oportunidade_id, tenant_id: $tenant_id}) "
            "MERGE (i)-[:GEROU_OPORTUNIDADE]->(o)",
            {"indicado_id": indicado_conta_id, "oportunidade_id": oportunidade_id, "tenant_id": tenant_id},
        )

    def grafo_da_conta(self, tenant_id: str, conta_id: int) -> dict:
        registros = self.run_query(
            "MATCH (c:Conta {id: $conta_id, tenant_id: $tenant_id}) "
            "OPTIONAL MATCH (d:Decisor)-[:DECISOR_DE]->(c) "
            "OPTIONAL MATCH (d)-[:INTERAGIU_COM]->(i:Interacao) "
            "RETURN c, d, i",
            {"conta_id": conta_id, "tenant_id": tenant_id},
        )

        nos: dict[str, dict] = {}
        arestas: list[dict] = []
        for registro in registros:
            conta, decisor, interacao = registro.get("c"), registro.get("d"), registro.get("i")
            if conta:
                nos[f"conta:{conta['id']}"] = {"id": f"conta:{conta['id']}", "tipo": "Conta", "propriedades": conta}
            if decisor:
                chave_decisor = f"decisor:{decisor['id']}"
                nos[chave_decisor] = {"id": chave_decisor, "tipo": "Decisor", "propriedades": decisor}
                arestas.append({"origem": chave_decisor, "destino": f"conta:{conta_id}", "tipo": "DECISOR_DE"})
                if interacao:
                    chave_interacao = f"interacao:{interacao['id']}"
                    nos[chave_interacao] = {
                        "id": chave_interacao,
                        "tipo": "Interacao",
                        "propriedades": interacao,
                    }
                    arestas.append({"origem": chave_decisor, "destino": chave_interacao, "tipo": "INTERAGIU_COM"})

        return {"nos": list(nos.values()), "arestas": arestas}
