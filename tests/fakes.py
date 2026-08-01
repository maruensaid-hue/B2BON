from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse
from app.providers.account_data.base import (
    AccountDataProvider,
    ContaCandidata,
    DecisorCandidato,
    FiltroBusca,
)
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.email.base import ResultadoEnvio as ResultadoEnvioEmail
from app.providers.channels.whatsapp.base import ResultadoEnvio as ResultadoEnvioWhatsApp
from app.providers.channels.whatsapp.base import TemplateInfo, WhatsAppProvider


class FakeGraphClient:
    """Duplo de teste do Neo4jClient — sem Neo4j real.

    Implementa o mesmo vocabulário de domínio (`upsert_conta`,
    `upsert_decisor`, `registrar_interacao`, `grafo_da_conta`) num dicionário
    em memória, em vez de interpretar Cypher.
    """

    def __init__(self) -> None:
        self.nos: dict[str, dict] = {}
        self.arestas: list[dict] = []

    def close(self) -> None:
        pass

    def run_query(self, query: str, parameters: dict | None = None) -> list[dict]:
        return []

    def upsert_conta(self, tenant_id: str, conta_id: int, propriedades: dict) -> None:
        chave = f"conta:{conta_id}"
        self.nos[chave] = {
            "id": chave,
            "tipo": "Conta",
            "propriedades": {"id": conta_id, "tenant_id": tenant_id, **propriedades},
        }

    def upsert_decisor(self, tenant_id: str, decisor_id: int, conta_id: int, propriedades: dict) -> None:
        chave = f"decisor:{decisor_id}"
        self.nos[chave] = {
            "id": chave,
            "tipo": "Decisor",
            "propriedades": {"id": decisor_id, "tenant_id": tenant_id, **propriedades},
        }
        self.arestas.append({"origem": chave, "destino": f"conta:{conta_id}", "tipo": "DECISOR_DE"})

    def registrar_interacao(self, tenant_id: str, decisor_id: int, interacao_id: int, propriedades: dict) -> None:
        chave = f"interacao:{interacao_id}"
        self.nos[chave] = {
            "id": chave,
            "tipo": "Interacao",
            "propriedades": {"id": interacao_id, "tenant_id": tenant_id, **propriedades},
        }
        self.arestas.append({"origem": f"decisor:{decisor_id}", "destino": chave, "tipo": "INTERAGIU_COM"})

    def grafo_da_conta(self, tenant_id: str, conta_id: int) -> dict:
        chave_conta = f"conta:{conta_id}"
        nos_relevantes: dict[str, dict] = {}
        arestas_relevantes: list[dict] = []

        if chave_conta in self.nos:
            nos_relevantes[chave_conta] = self.nos[chave_conta]

        for aresta in self.arestas:
            if aresta["destino"] != chave_conta:
                continue
            nos_relevantes[aresta["origem"]] = self.nos[aresta["origem"]]
            arestas_relevantes.append(aresta)
            for aresta_interacao in self.arestas:
                if aresta_interacao["origem"] == aresta["origem"] and aresta_interacao["tipo"] == "INTERAGIU_COM":
                    nos_relevantes[aresta_interacao["destino"]] = self.nos[aresta_interacao["destino"]]
                    arestas_relevantes.append(aresta_interacao)

        return {"nos": list(nos_relevantes.values()), "arestas": arestas_relevantes}


class FakeLLMProvider(LLMProvider):
    """Retorno determinístico — permite simular texto que viola/respeita
    restrições sem chamar a API Claude de verdade."""

    def __init__(self, respostas: list[str] | None = None) -> None:
        self._fila_respostas = list(respostas) if respostas is not None else None
        self.chamadas: list[LLMRequest] = []
        self._contador = 0

    def definir_respostas(self, respostas: list[str]) -> None:
        self._fila_respostas = list(respostas)

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.chamadas.append(request)
        if self._fila_respostas is not None:
            texto = self._fila_respostas.pop(0) if self._fila_respostas else "Mensagem de prospecção padrão."
        else:
            self._contador += 1
            texto = f"Mensagem de prospecção número {self._contador}."
        return LLMResponse(content=texto, model="fake-model", input_tokens=0, output_tokens=0)


class FakeAccountDataProvider(AccountDataProvider):
    """Duplo de teste do AccountDataProvider — candidatos/decisores
    controlados pelo teste, sem depender do parser da Receita Federal."""

    def __init__(
        self,
        candidatos: list[ContaCandidata] | None = None,
        decisores: dict[str, list[DecisorCandidato]] | None = None,
    ) -> None:
        self.candidatos = candidatos or []
        self.decisores = decisores or {}

    def buscar_candidatos(self, filtro: FiltroBusca) -> list[ContaCandidata]:
        return self.candidatos[: filtro.limite]

    def buscar_decisores(self, cnpj: str) -> list[DecisorCandidato]:
        return self.decisores.get(cnpj, [])


class FakeWhatsAppProvider(WhatsAppProvider):
    """Duplo de teste — registra envios, permite simular falha e listar
    templates fixos com status controlado pelo teste."""

    def __init__(self) -> None:
        self.envios: list[dict] = []
        self.templates: list[TemplateInfo] = [
            TemplateInfo(nome="prospeccao_inicial", status="aprovado", corpo="Olá {{1}}")
        ]
        self.falhar_proximos = 0

    def _resultado(self) -> ResultadoEnvioWhatsApp:
        if self.falhar_proximos > 0:
            self.falhar_proximos -= 1
            return ResultadoEnvioWhatsApp(sucesso=False, motivo_falha="falha simulada")
        return ResultadoEnvioWhatsApp(sucesso=True, id_externo=f"fake-{len(self.envios)}")

    def enviar_template(self, telefone: str, template_id: str, variaveis: dict) -> ResultadoEnvioWhatsApp:
        self.envios.append({"tipo": "template", "telefone": telefone, "template_id": template_id})
        return self._resultado()

    def enviar_texto_livre(self, telefone: str, texto: str) -> ResultadoEnvioWhatsApp:
        self.envios.append({"tipo": "livre", "telefone": telefone, "texto": texto})
        return self._resultado()

    def listar_templates(self) -> list[TemplateInfo]:
        return self.templates


class FakeEmailProvider(EmailProvider):
    """Duplo de teste — registra envios, permite simular falha."""

    def __init__(self) -> None:
        self.envios: list[dict] = []
        self.falhar_proximos = 0

    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        remetente_nome: str,
        remetente_email: str,
    ) -> ResultadoEnvioEmail:
        self.envios.append(
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "corpo": corpo,
                "remetente_nome": remetente_nome,
                "remetente_email": remetente_email,
            }
        )
        if self.falhar_proximos > 0:
            self.falhar_proximos -= 1
            return ResultadoEnvioEmail(sucesso=False, motivo_falha="falha simulada")
        return ResultadoEnvioEmail(sucesso=True, id_externo=f"fake-{len(self.envios)}")
