from app.providers.fiscal.base import DadosNota, FiscalIndisponivel, FiscalProvider, NotaEmitida


class FiscalDesativado(FiscalProvider):
    """Sem emissor fiscal configurado: não emite e não finge que emitiu. Mantém o checkout de pacotes bloqueado."""

    nome = "desativado"
    disponivel = False

    def emitir(self, dados: DadosNota) -> NotaEmitida:
        raise FiscalIndisponivel("Nenhum emissor de nota fiscal está configurado neste ambiente.")
