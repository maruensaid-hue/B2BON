import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Input } from "@/components/ui/Input";
import { SeletorArquivo } from "@/components/ui/SeletorArquivo";
import { api, ApiError, getBlob, postFile } from "@/lib/api";

interface PropostaNegocio {
  id: number;
  negocio_id: number;
  versao: number;
  numero: number | null;
  nome: string | null;
  nome_arquivo: string;
  tipo_mime: string;
  tamanho_bytes: number;
  gerada_automaticamente: boolean;
  enviada_por_usuario_id: number | null;
  criado_em: string;
}

/** Propostas de um negócio — extraído de `Kanban.tsx` (raio-X 2026-09-22)
 * pra ser reaproveitado tanto pelo modal condensado quanto pela página
 * expandida do negócio (`NegocioDetalhe.tsx`), sem duplicar a lógica de
 * upload/lista/download em dois lugares. Autocontido: só recebe o id do
 * negócio, carrega/gerencia tudo internamente. */
export function PropostasNegocio({ negocioId }: { negocioId: number }) {
  const [propostas, setPropostas] = useState<PropostaNegocio[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [nomeNovaProposta, setNomeNovaProposta] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      setPropostas(await api.get<PropostaNegocio[]>(`/crm/negocios/${negocioId}/propostas`));
    } catch {
      setPropostas([]);
    }
  }

  useEffect(() => {
    carregar();
  }, [negocioId]);

  async function enviarProposta(arquivo: File) {
    if (enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const nome = nomeNovaProposta.trim();
      await postFile(`/crm/negocios/${negocioId}/propostas`, arquivo, nome ? { nome } : undefined);
      setNomeNovaProposta("");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar a proposta.");
    } finally {
      setEnviando(false);
    }
  }

  async function baixarProposta(proposta: PropostaNegocio) {
    try {
      const blob = await getBlob(`/crm/negocios/${negocioId}/propostas/${proposta.id}/download`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = proposta.nome_arquivo;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setErro("Não foi possível baixar a proposta.");
    }
  }

  return (
    <div>
      <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Propostas</div>
      <div className="mb-3 flex flex-col gap-2 rounded-lg border border-border p-2.5">
        {erro && <div className="text-[11px] text-red">{erro}</div>}
        <Input
          value={nomeNovaProposta}
          onChange={(event) => setNomeNovaProposta(event.target.value)}
          placeholder="Nome da proposta (opcional)"
          className="text-[11px]"
        />
        <SeletorArquivo
          accept=".pdf,.docx"
          disabled={enviando}
          onSelecionar={enviarProposta}
          rotulo={enviando ? "Enviando..." : "Selecionar arquivo"}
        />
        <Link to={`/crm/propostas/nova?negocio_id=${negocioId}`} className="text-[11px] text-cyan hover:underline">
          Gerar proposta automática →
        </Link>
      </div>

      {propostas.length === 0 ? (
        <div className="text-[11px] text-muted">Nenhuma proposta anexada ainda.</div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {propostas.map((proposta) => (
            <div key={proposta.id} className="flex items-center justify-between gap-2 border-b border-border py-1 text-[11px]">
              <div>
                <div className="text-text">
                  v{proposta.versao} — {proposta.nome ?? proposta.nome_arquivo}
                  {proposta.numero && <span className="text-muted"> (#{proposta.numero})</span>}
                  {proposta.gerada_automaticamente && (
                    <span className="ml-1.5 rounded-full bg-cyan/15 px-1.5 py-px text-[10px] text-cyan">
                      gerada automaticamente
                    </span>
                  )}
                </div>
                <div className="text-muted">{new Date(proposta.criado_em).toLocaleString("pt-BR")}</div>
              </div>
              <button type="button" className="text-cyan hover:underline" onClick={() => baixarProposta(proposta)}>
                Baixar
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
