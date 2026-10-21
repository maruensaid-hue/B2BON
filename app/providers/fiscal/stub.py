from app.providers.fiscal.base import DadosNota, FiscalIndisponivel, FiscalProvider, FiscalRejeitou, NotaEmitida


class StubFiscalProvider(FiscalProvider):
    """Dublê de teste: nunca chama rede. Idempotente por `chave_idempotencia` (como um emissor real deve ser) e pode ser instruído a falhar."""

    nome = "stub"

    def __init__(self, *, indisponivel: bool = False, rejeitar: str | None = None, fora_do_ar_vezes: int = 0) -> None:
        self.indisponivel = indisponivel
        self.rejeitar = rejeitar
        self.fora_do_ar_vezes = fora_do_ar_vezes
        self.chamadas: list[DadosNota] = []
        self._emitidas: dict[str, NotaEmitida] = {}

    @property
    def disponivel(self) -> bool:  # type: ignore[override]
        return not self.indisponivel

    def emitir(self, dados: DadosNota) -> NotaEmitida:
        self.chamadas.append(dados)
        if self.indisponivel or self.fora_do_ar_vezes > 0:
            self.fora_do_ar_vezes = max(0, self.fora_do_ar_vezes - 1)
            raise FiscalIndisponivel("emissor fora do ar (stub)")
        if self.rejeitar:
            raise FiscalRejeitou(self.rejeitar)
        if dados.chave_idempotencia not in self._emitidas:
            numero = str(len(self._emitidas) + 1)
            self._emitidas[dados.chave_idempotencia] = NotaEmitida(numero=numero, referencia_externa=f"stub-nf-{numero}", chave_acesso=f"stub-chave-{numero}")
        return self._emitidas[dados.chave_idempotencia]
