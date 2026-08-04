"""Carrega no staging local o recorte de CNPJ da Receita Federal exigido
pelos ICPs ativos de um tenant (Onda E).

Uso: python scripts/carregar_recorte_receita_federal.py

Os arquivos públicos de dados abertos de CNPJ da Receita Federal
(https://dadosabertos.rfb.gov.br/CNPJ/) são grandes demais (vários GB,
atualizados mensalmente) para baixar e processar automaticamente — este
script espera que o operador já tenha baixado e descompactado localmente
os 3 arquivos (empresas, estabelecimentos, sócios) do layout público.

Só existe como script, não como rota HTTP: carregar um CSV a partir de um
caminho arbitrário do disco do servidor seria uma rota de risco
(path traversal/DoS) para uma tarefa pesada e pouco frequente — mesmo
raciocínio de `bootstrap_tenant.py`.
"""

import sys

import app.models  # noqa: F401 — registra as tabelas em Base.metadata
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.icp import ICP
from app.providers.account_data.receita_federal_loader import carregar_recorte


def _ler_caminho(mensagem: str) -> str:
    """Remove aspas coladas por "Copiar como caminho" do Windows Explorer
    (que envolve o texto em `"..."`, inclusive quando há espaço no caminho)
    — sem isso, `open()` recebe as aspas como parte literal do nome do
    arquivo e falha com OSError Errno 22."""
    return input(mensagem).strip().strip('"').strip("'")


def _unir_filtros_icps_ativos(db, tenant_id: str) -> tuple[list[str], list[str]]:
    """União (sem duplicatas) de CNAEs e UFs de todos os ICPs ativos do
    tenant — o recorte carregado deve cobrir todos os ICPs em uso, não só
    um de cada vez."""
    icps_ativos = db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).all()

    cnae_codigos: set[str] = set()
    ufs: set[str] = set()
    for icp in icps_ativos:
        cnae_codigos.update(icp.cnae_codigos)
        ufs.update(icp.ufs)

    return sorted(cnae_codigos), sorted(ufs)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        tenant_id = input("Identificador do tenant (slug, ex.: cyberfort): ").strip()
        cnae_codigos, ufs = _unir_filtros_icps_ativos(db, tenant_id)
        if not cnae_codigos or not ufs:
            print(
                f"\nNenhum ICP ativo com CNAEs/UFs configurados para o tenant '{tenant_id}'. "
                "Cadastre ao menos um ICP antes de carregar o recorte.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"\nCNAEs no recorte: {', '.join(cnae_codigos)}")
        print(f"UFs no recorte: {', '.join(ufs)}")

        caminho_empresas = _ler_caminho("\nCaminho local do arquivo de empresas (ex.: ./dados/EMPRECSV): ")
        caminho_estabelecimentos = _ler_caminho(
            "Caminho local do arquivo de estabelecimentos (ex.: ./dados/ESTABELE): "
        )
        caminho_socios = _ler_caminho("Caminho local do arquivo de sócios (ex.: ./dados/SOCIOCSV): ")

        carregados = carregar_recorte(
            db, cnae_codigos, ufs, caminho_empresas, caminho_estabelecimentos, caminho_socios
        )
        print(f"\n✓ {carregados} estabelecimento(s) carregado(s) no recorte de '{tenant_id}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
