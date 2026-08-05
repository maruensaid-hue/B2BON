import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError, getBlob } from "@/lib/api";

interface ContaCompleta {
  id: number;
  cnpj: string | null;
  nome: string;
  dominio: string | null;
  porte: string | null;
  segmento: string | null;
  regiao: string | null;
  score_aderencia: number | null;
  status: string;
  motivo_descarte: string | null;
}

interface CampoEnriquecido {
  campo: string;
  valor: string;
  fonte: string;
  coletado_em: string;
}

interface Decisor {
  id: number;
  nome: string;
  cargo: string | null;
  canal_provavel: string | null;
  email: string | null;
  telefone: string | null;
}

interface Props {
  contaId: number;
  onClose: () => void;
  onAtualizado: () => void;
}

export function ContaDetalheModal({ contaId, onClose, onAtualizado }: Props) {
  const [conta, setConta] = useState<ContaCompleta | null>(null);
  const [campos, setCampos] = useState<CampoEnriquecido[]>([]);
  const [decisores, setDecisores] = useState<Decisor[]>([]);
  const [mostrarDescarte, setMostrarDescarte] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState<string | null>(null);

  async function carregar() {
    try {
      setConta(await api.get<ContaCompleta>(`/contas/${contaId}`));
    } catch {
      setErro("Não foi possível carregar a conta.");
    }
  }

  useEffect(() => {
    carregar();
  }, [contaId]);

  async function executar(nomeAcao: string, acao: () => Promise<void>) {
    setErro(null);
    setCarregando(nomeAcao);
    try {
      await acao();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
    } finally {
      setCarregando(null);
    }
  }

  async function priorizar() {
    await executar("priorizar", async () => {
      await api.post(`/contas/${contaId}/priorizar`);
      await carregar();
      onAtualizado();
    });
  }

  async function descartar(motivo: string) {
    await executar("descartar", async () => {
      await api.post(`/contas/${contaId}/descartar`, { motivo });
      setMostrarDescarte(false);
      await carregar();
      onAtualizado();
    });
  }

  async function enriquecerSite() {
    await executar("enriquecer-site", async () => {
      const resposta = await api.post<{ campos: CampoEnriquecido[] }>(`/contas/${contaId}/enriquecer`);
      setCampos(resposta.campos);
    });
  }

  async function enriquecerBrasilApi() {
    await executar("enriquecer-brasilapi", async () => {
      const resposta = await api.post<{ campos: CampoEnriquecido[] }>(`/contas/${contaId}/enriquecer-brasilapi`);
      setCampos(resposta.campos);
    });
  }

  async function mapearDecisores() {
    await executar("mapear-decisores", async () => {
      setDecisores(await api.post<Decisor[]>(`/contas/${contaId}/decisores/mapear`));
    });
  }

  async function exportarPdf() {
    await executar("exportar-pdf", async () => {
      const blob = await getBlob(`/contas/${contaId}/export/pdf`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `conta-${contaId}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  return (
    <Modal title={conta?.nome ?? "Conta"} open onClose={onClose}>
      {erro && <div className="mb-3 text-[12px] text-red">{erro}</div>}

      {conta && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-2 text-[11px] text-muted">
            <div>CNPJ: {conta.cnpj ?? "—"}</div>
            <div>Domínio: {conta.dominio ?? "—"}</div>
            <div>Porte: {conta.porte ?? "—"}</div>
            <div>Segmento: {conta.segmento ?? "—"}</div>
            <div>
              Status: <Badge tone={conta.status === "priorizada" ? "green" : "cyan"}>{conta.status}</Badge>
            </div>
            <div>Score: {conta.score_aderencia ?? "—"}</div>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <Button size="sm" variant="green" disabled={carregando !== null} onClick={priorizar}>
              Priorizar
            </Button>
            <Button size="sm" variant="danger" disabled={carregando !== null} onClick={() => setMostrarDescarte(true)}>
              Descartar
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={enriquecerSite}>
              Pesquisar empresa (site)
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={enriquecerBrasilApi}>
              Enriquecer (BrasilAPI)
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={mapearDecisores}>
              Mapear decisores
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={exportarPdf}>
              Exportar PDF
            </Button>
          </div>
          <div className="mb-4 text-[11px] text-muted">
            "Pesquisar empresa (site)" varre a home e páginas internas (sobre,
            investidores, notícias, privacidade) do domínio cadastrado e pede à
            IA um resumo de porte, crescimento, marcos, novos projetos e se há
            política de privacidade/LGPD publicada — serve de insumo para
            qualquer oferta, não só para prospecção de LGPD.
          </div>

          {mostrarDescarte && (
            <form
              className="mb-4 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                const motivo = new FormData(event.currentTarget).get("motivo");
                descartar(String(motivo ?? ""));
              }}
            >
              <Input name="motivo" required placeholder="Motivo do descarte" className="flex-1" />
              <Button size="sm" variant="danger" type="submit">
                Confirmar
              </Button>
            </form>
          )}

          {campos.length > 0 && (
            <div className="mb-4">
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Campos enriquecidos</div>
              <div className="flex flex-col gap-1 text-[11px]">
                {campos.map((campo, indice) => (
                  <div key={indice} className="flex justify-between border-b border-border py-1">
                    <span className="text-text">{campo.campo}</span>
                    <span className="text-muted">{campo.valor}</span>
                    <Badge tone="muted">{campo.fonte}</Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

          {decisores.length > 0 && (
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Decisores mapeados</div>
              <div className="flex flex-col gap-1 text-[11px]">
                {decisores.map((decisor) => (
                  <div key={decisor.id} className="border-b border-border py-1">
                    <span className="font-semibold text-text">{decisor.nome}</span>
                    {decisor.cargo && <span className="text-muted"> · {decisor.cargo}</span>}
                    {decisor.canal_provavel && <span className="text-muted"> · canal: {decisor.canal_provavel}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
