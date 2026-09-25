class ErroServico(Exception):
    """Base para erros de domínio mapeados a respostas HTTP em app/main.py."""


class NaoEncontrado(ErroServico):
    """Mapeado para 404."""


class RegraNegocioViolada(ErroServico):
    """Mapeado para 409 — pré-condição de negócio não satisfeita."""


class ValidacaoFalhou(ErroServico):
    """Mapeado para 422 — entrada estruturalmente válida, mas semanticamente inválida."""


class NaoAutenticado(ErroServico):
    """Mapeado para 401 — token ausente/inválido ou credenciais incorretas (Onda A)."""


class NaoAutorizado(ErroServico):
    """Mapeado para 403 — usuário autenticado, mas sem papel suficiente (Onda A)."""


class LimiteDeTaxaExcedido(ErroServico):
    """Mapeado para 429 — proteção contra força bruta em rotas públicas de autenticação."""


class CreditosInsuficientes(RegraNegocioViolada):
    """Mapeado para 402 — sem AI Credits disponíveis para a operação (Fase 15)."""

    def __init__(self, mensagem: str, detalhe: dict | None = None) -> None:
        super().__init__(mensagem)
        self.detalhe = detalhe or {}


class ConfirmacaoNecessaria(RegraNegocioViolada):
    """Mapeado para 409 com a estimativa — operação cara precisa de "continuar"."""

    def __init__(self, mensagem: str, detalhe: dict | None = None) -> None:
        super().__init__(mensagem)
        self.detalhe = detalhe or {}


class OrcamentoIaExcedido(RegraNegocioViolada):
    """Mapeado para 409 — budget guard do tenant (hard stop) atingido."""
