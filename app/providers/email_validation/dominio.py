"""Verificação de e-mail pelo DOMÍNIO, sem SMTP e sem serviço externo.

Faz de graça e sem sair da porta 443/53 o que um verificador gratuito faz antes de abrir conversa SMTP: sintaxe, domínio descartável e existência de
servidor de e-mail (registro MX, ou endereço A/AAAA como a RFC 5321 manda). Não existe checagem da CAIXA: a verificação por SMTP exige a porta 25 de
saída, que o Render não libera (e os servidores de e-mail recusam IPs de nuvem), então esta classe NUNCA diz que um e-mail está "confirmado". O melhor
estado é `dominio_valido`: o domínio recebe e-mail; se a pessoa existe, ninguém sabe.

Descarta com certeza: sintaxe inválida, domínio que não existe, domínio sem servidor de e-mail e domínio descartável. Falha de DNS (tempo esgotado,
servidor de nomes fora do ar) é `indeterminado`, nunca "inválido": um problema de rede não pode apagar um contato.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.providers.email_validation.base import EmailVerificationProvider, ResultadoVerificacao

_PADRAO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SINTAXE_INVALIDA = "sintaxe_invalida"
DOMINIO_INEXISTENTE = "dominio_inexistente"
SEM_SERVIDOR_DE_EMAIL = "sem_servidor_de_email"
DESCARTAVEL = "descartavel"
DOMINIO_VALIDO = "dominio_valido"
INDETERMINADO = "indeterminado"

ESTADOS_QUE_DESCARTAM = (SINTAXE_INVALIDA, DOMINIO_INEXISTENTE, SEM_SERVIDOR_DE_EMAIL, DESCARTAVEL)

# Respostas do consultor de DNS (`ConsultaDominio`): o que o domínio tem.
TEM_MX = "tem_mx"
TEM_ENDERECO = "tem_endereco"  # sem MX, mas com A/AAAA: a RFC 5321 trata o próprio domínio como servidor
INEXISTENTE = "inexistente"
SEM_REGISTRO = "sem_registro"  # o domínio existe, mas sem MX nem endereço (ou com "MX nulo", que recusa e-mail)
FALHA_DE_DNS = "falha_de_dns"

ConsultaDominio = Callable[[str], str]

# Lista mínima e conservadora de provedores de e-mail descartável bem conhecidos. Domínio fora da lista passa; ampliar é só acrescentar aqui.
DOMINIOS_DESCARTAVEIS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "10minutemail.com", "yopmail.com", "tempmail.com", "temp-mail.org", "trashmail.com",
    "sharklasers.com", "getnada.com", "throwawaymail.com", "maildrop.cc", "dispostable.com", "fakeinbox.com", "mailnesia.com",
})

_TEMPO_DE_VIDA_DA_RESPOSTA_S = 6 * 3600  # um domínio não muda de servidor a cada consulta; evita repetir DNS dentro de uma mesma carga


@dataclass(frozen=True)
class VerificacaoDominio:
    estado: str
    motivo: str | None = None

    @property
    def descarta(self) -> bool:
        return self.estado in ESTADOS_QUE_DESCARTAM


def consultar_dns(dominio: str) -> str:
    """Consulta real (dnspython, que já vem com o `email-validator`): MX; sem MX, A/AAAA. Tempo curto, sem tentar de novo: o chamador trata a falha."""
    import dns.exception
    import dns.resolver

    resolvedor = dns.resolver.Resolver()
    resolvedor.timeout, resolvedor.lifetime = 2.0, 3.0
    try:
        for registro in resolvedor.resolve(dominio, "MX"):
            if str(registro.exchange).rstrip(".") == "":
                return SEM_REGISTRO  # MX nulo (RFC 7505): o domínio declara que não recebe e-mail
        return TEM_MX
    except dns.resolver.NXDOMAIN:
        return INEXISTENTE
    except dns.resolver.NoAnswer:
        pass  # sem MX: tenta o endereço do próprio domínio
    except (dns.exception.Timeout, dns.resolver.NoNameservers, dns.resolver.YXDOMAIN, dns.resolver.LifetimeTimeout):
        return FALHA_DE_DNS
    except Exception:  # noqa: BLE001 — rede/DNS imprevisto nunca vira "inválido"
        return FALHA_DE_DNS
    for tipo in ("A", "AAAA"):
        try:
            resolvedor.resolve(dominio, tipo)
            return TEM_ENDERECO
        except dns.resolver.NXDOMAIN:
            return INEXISTENTE
        except dns.resolver.NoAnswer:
            continue
        except Exception:  # noqa: BLE001
            return FALHA_DE_DNS
    return SEM_REGISTRO


class DominioEmailVerificationProvider(EmailVerificationProvider):
    """`EmailVerificationProvider` sem custo: valida pelo domínio. `classificar` devolve o estado detalhado; `verificar` só reprova o que é certo."""

    def __init__(self, consulta: ConsultaDominio | None = None, relogio: Callable[[], float] = time.monotonic) -> None:
        self._consulta = consulta or consultar_dns
        self._relogio = relogio
        self._respostas: dict[str, tuple[float, str]] = {}

    def _dns(self, dominio: str) -> str:
        agora = self._relogio()
        guardada = self._respostas.get(dominio)
        if guardada is not None and agora - guardada[0] < _TEMPO_DE_VIDA_DA_RESPOSTA_S:
            return guardada[1]
        resposta = self._consulta(dominio)
        if resposta != FALHA_DE_DNS:  # falha não se guarda: a próxima tentativa pode dar certo
            self._respostas[dominio] = (agora, resposta)
        return resposta

    def classificar(self, email: str | None) -> VerificacaoDominio:
        texto = (email or "").strip()
        if not _PADRAO_EMAIL.match(texto):
            return VerificacaoDominio(SINTAXE_INVALIDA, "sintaxe de e-mail inválida")
        dominio = texto.rsplit("@", 1)[-1].lower().rstrip(".")
        if dominio in DOMINIOS_DESCARTAVEIS:
            return VerificacaoDominio(DESCARTAVEL, f"domínio de e-mail descartável: {dominio}")
        resposta = self._dns(dominio)
        if resposta == INEXISTENTE:
            return VerificacaoDominio(DOMINIO_INEXISTENTE, f"domínio inexistente: {dominio}")
        if resposta == SEM_REGISTRO:
            return VerificacaoDominio(SEM_SERVIDOR_DE_EMAIL, f"domínio sem servidor de e-mail: {dominio}")
        if resposta == FALHA_DE_DNS:
            return VerificacaoDominio(INDETERMINADO, f"não foi possível consultar o DNS de {dominio}")
        return VerificacaoDominio(DOMINIO_VALIDO)

    def verificar(self, email: str | None) -> ResultadoVerificacao:
        resultado = self.classificar(email)
        return ResultadoVerificacao(valido=not resultado.descarta, motivo=resultado.motivo if resultado.descarta else None)
