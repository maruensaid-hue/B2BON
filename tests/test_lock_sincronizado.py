"""O lock não pode ficar para trás do pyproject: a imagem Docker e o CI instalam SÓ o que está nele (`pip install --no-deps .`),
então uma dependência nova (ou uma faixa de versão alterada) que não foi para o lock só apareceria como ImportError em produção.

Como atualizar: ver README, seção "Dependências do backend"."""

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

RAIZ = Path(__file__).resolve().parents[1]
_ENTRADA = re.compile(r"^([A-Za-z0-9_.\-]+)==(\S+?)(?:\s*;.*)?\s*\\?$", re.MULTILINE)


def _texto(arquivo: str) -> str:
    return (RAIZ / arquivo).read_text(encoding="utf-8")


def _travadas(arquivo: str) -> dict[str, str]:
    return {canonicalize_name(m.group(1)): m.group(2) for m in _ENTRADA.finditer(_texto(arquivo))}


def _declaradas(extra: str | None) -> list[Requirement]:
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lista = projeto["dependencies"] if extra is None else projeto["optional-dependencies"][extra]
    return [Requirement(item) for item in lista]


@pytest.mark.parametrize(("arquivo", "extras"), [("requirements.lock", [None]), ("requirements-dev.lock", [None, "dev"])])
def test_toda_dependencia_declarada_esta_travada_numa_versao_que_o_pyproject_aceita(arquivo, extras):
    travadas = _travadas(arquivo)
    assert travadas, f"nenhuma dependência lida de {arquivo}"
    faltando, fora_da_faixa = [], []
    for extra in extras:
        for requisito in _declaradas(extra):
            nome = canonicalize_name(requisito.name)
            if nome not in travadas:
                faltando.append(requisito.name)
            elif not requisito.specifier.contains(travadas[nome], prereleases=True):
                fora_da_faixa.append(f"{requisito.name}=={travadas[nome]} fora de {requisito.specifier}")
    assert not faltando, f"Dependência declarada e ausente de {arquivo}: {faltando}. Regerar o lock (README)."
    assert not fora_da_faixa, f"{arquivo} desatualizado em relação ao pyproject.toml: {fora_da_faixa}"


def test_todo_pacote_do_lock_tem_hash():
    """`pip install --require-hashes` recusa qualquer entrada sem hash: a falha apareceria só no build da imagem."""
    for arquivo in ("requirements.lock", "requirements-dev.lock"):
        blocos = re.split(r"^(?=[A-Za-z0-9_.\-]+==)", _texto(arquivo), flags=re.MULTILINE)[1:]
        assert blocos, f"{arquivo} vazio"
        sem_hash = [b.split("==")[0] for b in blocos if "--hash=sha256:" not in b]
        assert not sem_hash, f"{arquivo}: sem hash {sem_hash}"


def test_o_lock_de_runtime_nao_traz_ferramentas_de_desenvolvimento():
    assert not {"pytest", "ruff"} & set(_travadas("requirements.lock"))


def test_o_lock_de_desenvolvimento_traz_as_ferramentas_do_ci():
    assert {"pytest", "ruff"} <= set(_travadas("requirements-dev.lock"))
