class ErroServico(Exception):
    """Base para erros de domínio mapeados a respostas HTTP em app/main.py."""


class NaoEncontrado(ErroServico):
    """Mapeado para 404."""


class RegraNegocioViolada(ErroServico):
    """Mapeado para 409 — pré-condição de negócio não satisfeita."""


class ValidacaoFalhou(ErroServico):
    """Mapeado para 422 — entrada estruturalmente válida, mas semanticamente inválida."""
