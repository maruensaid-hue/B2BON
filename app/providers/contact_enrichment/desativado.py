from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos


class ContactEnrichmentDesativadoProvider(ContactEnrichmentProvider):
    """No-op para produção sem `CONTACT_ENRICHMENT_API_KEY` configurada —
    `mapear_decisores` chama `buscar_contatos` sem nenhuma trava, então
    usar o `StubContactEnrichmentProvider` (dados fictícios fixos) fora
    de dev/teste criaria decisores fantasma de verdade no CRM de
    qualquer tenant. Sem fornecedor contratado, o mapeamento simplesmente
    cai pro QSA da Receita Federal, como já era a intenção documentada."""

    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        return []
