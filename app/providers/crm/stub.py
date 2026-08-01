from app.providers.crm.base import CrmProvider


class StubCrmProvider(CrmProvider):
    """Grava oportunidades em memória — dev/teste enquanto o núcleo não
    está disponível para integração. O id externo é determinístico
    (tenant+conta), então o upsert é idempotente mesmo entre instâncias."""

    def __init__(self) -> None:
        self.oportunidades: dict[str, dict] = {}
        self.notas: list[dict] = []
        self.falhar_proximos = 0

    def criar_ou_atualizar_oportunidade(self, tenant_id: str, conta_id: int, dados: dict) -> str:
        if self.falhar_proximos > 0:
            self.falhar_proximos -= 1
            raise RuntimeError("Falha simulada de integração com o CRM.")

        id_externo = f"stub-oportunidade-{tenant_id}-{conta_id}"
        registro = self.oportunidades.setdefault(id_externo, {"tenant_id": tenant_id, "conta_id": conta_id})
        registro.update(dados)
        return id_externo

    def anexar_nota(self, tenant_id: str, oportunidade_id: str, texto: str) -> None:
        self.notas.append({"tenant_id": tenant_id, "oportunidade_id": oportunidade_id, "texto": texto})
