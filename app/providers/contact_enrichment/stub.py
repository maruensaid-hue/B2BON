from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos

_CONTATOS_FIXOS = [
    {"nome": "Ana Beatriz Souza", "cargo": "CEO", "email_local": "ana.souza", "telefone": "(11) 98888-0001",
     "linkedin_slug": "ana-beatriz-souza"},
    {"nome": "Carlos Eduardo Lima", "cargo": "Diretor Comercial", "email_local": "carlos.lima",
     "telefone": "(11) 98888-0002", "linkedin_slug": "carlos-eduardo-lima"},
    {"nome": "Fernanda Ribeiro", "cargo": "Head de Marketing", "email_local": "fernanda.ribeiro",
     "telefone": "(11) 98888-0003", "linkedin_slug": "fernanda-ribeiro"},
    {"nome": "Rodrigo Nascimento", "cargo": "Gerente de TI", "email_local": "rodrigo.nascimento",
     "telefone": "(11) 98888-0004", "linkedin_slug": "rodrigo-nascimento"},
]


class StubContactEnrichmentProvider(ContactEnrichmentProvider):
    """Retorna uma lista fixa e determinística de contatos fake — dev/teste,
    sem depender de fornecedor real nem gastar crédito de API."""

    def __init__(self) -> None:
        self.buscas: list[FiltroContatos] = []

    def buscar_contatos(self, filtro: FiltroContatos) -> list[ContatoCandidato]:
        self.buscas.append(filtro)
        dominio = filtro.dominio or (filtro.nome_empresa.lower().replace(" ", "") + ".com.br")
        return [
            ContatoCandidato(
                nome=contato["nome"],
                cargo=contato["cargo"],
                email=f"{contato['email_local']}@{dominio}",
                telefone=contato["telefone"],
                linkedin_url=f"https://www.linkedin.com/in/{contato['linkedin_slug']}",
            )
            for contato in _CONTATOS_FIXOS
        ]
