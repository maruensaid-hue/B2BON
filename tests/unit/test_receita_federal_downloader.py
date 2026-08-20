import zipfile
from datetime import datetime, timezone

import httpx
import pytest

from app.providers.account_data import receita_federal_downloader as downloader


def test_meses_candidatos_mes_atual_primeiro_recuando():
    referencia = datetime(2026, 1, 15, tzinfo=timezone.utc)

    meses = downloader._meses_candidatos(referencia)

    assert meses == ["2026-01", "2025-12", "2025-11", "2025-10"]


def test_meses_candidatos_vira_o_ano_corretamente():
    referencia = datetime(2026, 2, 10, tzinfo=timezone.utc)

    meses = downloader._meses_candidatos(referencia)

    assert meses == ["2026-02", "2026-01", "2025-12", "2025-11"]


class _RespostaFalsa:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_resolver_mes_competencia_usa_o_mes_mais_recente_disponivel(monkeypatch: pytest.MonkeyPatch):
    chamadas = []

    def _head_falso(url: str, timeout: float, follow_redirects: bool) -> _RespostaFalsa:
        chamadas.append(url)
        return _RespostaFalsa(200)

    monkeypatch.setattr(httpx, "head", _head_falso)

    mes = downloader.resolver_mes_competencia()

    assert mes == chamadas[0].split("/")[-2]
    assert len(chamadas) == 1  # achou de primeira, não precisou recuar


def test_resolver_mes_competencia_recua_quando_mes_atual_ainda_nao_publicado(monkeypatch: pytest.MonkeyPatch):
    respostas = iter([404, 200])

    def _head_falso(url: str, timeout: float, follow_redirects: bool) -> _RespostaFalsa:
        return _RespostaFalsa(next(respostas))

    monkeypatch.setattr(httpx, "head", _head_falso)

    mes = downloader.resolver_mes_competencia()

    assert mes is not None


def test_resolver_mes_competencia_sem_nenhum_mes_disponivel_levanta_erro(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(httpx, "head", lambda url, timeout, follow_redirects: _RespostaFalsa(404))

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
