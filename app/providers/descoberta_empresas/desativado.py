from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider, DescobertaIndisponivel, EmpresaDescoberta


class DescobertaDesativadaProvider(DescobertaEmpresasProvider):
    """Sem chave configurada: a descoberta por busca simplesmente não existe (nada é inventado, nada é cobrado)."""

    configurado = False

    def buscar(self, termo: str, cidade: str, limite: int = 20) -> list[EmpresaDescoberta]:
        raise DescobertaIndisponivel("A descoberta por busca não está configurada nesta instalação.")
