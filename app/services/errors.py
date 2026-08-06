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
