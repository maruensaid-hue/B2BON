import zipfile

import httpx
import pytest

from app.providers.account_data import receita_federal_downloader as downloader


class _RespostaIndiceFalsa:
    def __init__(self, texto: str) -> None:
        self.text = texto

    def raise_for_status(self) -> None:
        return None


def test_resolver_mes_competencia_usa_a_pasta_mais_recente_do_indice(monkeypatch: pytest.MonkeyPatch):
    html_indice = """
    <a href="2026-06-15/">2026-06-15/</a>
    <a href="2026-08-09/">2026-08-09/</a>
    <a href="2026-07-12/">2026-07-12/</a>
    """
    monkeypatch.setattr(httpx, "get", lambda url, timeout, follow_redirects: _RespostaIndiceFalsa(html_indice))

    mes = downloader.resolver_mes_competencia()

    assert mes == "2026-08-09"  # a mais recente, não a última do HTML nem a primeira


def test_resolver_mes_competencia_sem_nenhuma_pasta_levanta_erro(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout, follow_redirects: _RespostaIndiceFalsa("<html></html>"))

    with pytest.raises(downloader.MesCompetenciaIndisponivel):
        downloader.resolver_mes_competencia()


class _StreamFalso:
    def __init__(self, status_code: int, conteudo: bytes = b"") -> None:
        self.status_code = status_code
        self._conteudo = conteudo

    def __enter__(self) -> "_StreamFalso":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)

    def iter_bytes(self):
        yield self._conteudo


def _zip_bytes(nome_membro: str, conteudo: str) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as arquivo_zip:
        arquivo_zip.writestr(nome_membro, conteudo)
    return buffer.getvalue()


def test_baixar_shards_extrai_todos_os_indices_disponiveis(monkeypatch: pytest.MonkeyPatch, tmp_path):
    conteudos_por_indice = {
        0: _zip_bytes("ESTABELE0", "linha-shard-0"),
        1: _zip_bytes("ESTABELE1", "linha-shard-1"),
    }

    def _stream_falso(metodo: str, url: str, timeout: float, follow_redirects: bool) -> _StreamFalso:
        indice = int(url.rsplit("Estabelecimentos", 1)[1].split(".zip")[0])
        if indice in conteudos_por_indice:
            return _StreamFalso(200, conteudos_por_indice[indice])
        return _StreamFalso(404)

    monkeypatch.setattr(httpx, "stream", _stream_falso)

    caminhos = downloader.baixar_shards("2026-01", "Estabelecimentos", tmp_path)

    assert len(caminhos) == 2
    conteudo_lido = {open(c, encoding="utf-8").read() for c in caminhos}
    assert conteudo_lido == {"linha-shard-0", "linha-shard-1"}


def test_baixar_shards_pula_indices_ausentes_sem_abortar(monkeypatch: pytest.MonkeyPatch, tmp_path):
    def _stream_falso(metodo: str, url: str, timeout: float, follow_redirects: bool) -> _StreamFalso:
        if url.endswith("Estabelecimentos3.zip"):
            return _StreamFalso(200, _zip_bytes("ESTABELE3", "unico-shard"))
        return _StreamFalso(404)

    monkeypatch.setattr(httpx, "stream", _stream_falso)

    caminhos = downloader.baixar_shards("2026-01", "Estabelecimentos", tmp_path)

    assert len(caminhos) == 1
