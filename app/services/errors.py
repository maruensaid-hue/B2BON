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


class IAIndisponivel(RegraNegocioViolada):
    """A camada de IA não pode atender agora (provedor fora do ar, circuito aberto, orçamento ou teto automático).

    Subclasse de `RegraNegocioViolada` (mesma resposta 409 com mensagem clara), mas distinguível: quem tem um núcleo
    determinístico a preservar (ex.: a coleta do site) captura só esta exceção, grava o que já coletou e deixa a análise
    para depois. `falha_de_provedor` é verdadeiro só quando o provedor falhou de fato (conta para o disjuntor)."""

    def __init__(self, mensagem: str, falha_de_provedor: bool = False) -> None:
        super().__init__(mensagem)
        self.falha_de_provedor = falha_de_provedor


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


class PesquisaBloqueada(RegraNegocioViolada):
    """Mapeado para 409 com `codigo` estável e `bloqueios` — a pesquisa de decisores não pode seguir (configuração ausente, saldo, limite,
    orçamento global…). O front mostra a mensagem e trata o código; nunca chega ao provedor."""

    def __init__(self, mensagem: str, codigo: str, bloqueios: list[dict] | None = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.bloqueios = bloqueios or []
