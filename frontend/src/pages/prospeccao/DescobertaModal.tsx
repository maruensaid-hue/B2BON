import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";

interface Estimativa {
  buscas: number;
  configurado: boolean;
  usadas_no_mes: number;
  franquia_mensal: number; // 0 = sem limite definido
}

interface Resultado {
  buscas: number;
  em_segundo_plano?: boolean;
  criadas?: number;
  atualizadas?: number;
  falhas?: string[];
}

const linhas = (texto: string) => texto.split("\n").map((l) => l.trim()).filter(Boolean);

/** Descoberta por busca de mapa: primeiro a estimativa (quantas buscas da franquia), depois a execução com as buscas confirmadas. */
export function DescobertaModal({ open, onClose, icpId, onConcluido }: { open: boolean; onClose: () => void; icpId: number | null; onConcluido: () => void }) {
  const [termos, setTermos] = useState("");
  const [cidades, setCidades] = useState("");
  const [estimativa, setEstimativa] = useState<Estimativa | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const pedido = () => ({ termos: linhas(termos), cidades: linhas(cidades), icp_id: icpId });

  async function estimar() {
    setErro(null);
    setResultado(null);
    setOcupado(true);
    try {
      setEstimativa(await api.post<Estimativa>("/descoberta/estimativa", pedido()));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível estimar.");
    } finally {
      setOcupado(false);
    }
  }

  async function executar() {
    if (!estimativa) return;
    setErro(null);
    setOcupado(true);
    try {
      setResultado(await api.post<Resultado>("/descoberta/executar", { ...pedido(), buscas_confirmadas: estimativa.buscas }));
      setEstimativa(null);
      onConcluido();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível executar a descoberta.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal title="Descobrir empresas por busca de mapa" open={open} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <div className="text-[11px] text-muted">
          Acha empresas que o recorte de CNPJ não mostra, com a posição no mapa e se têm site. Cada busca (termo × cidade) consome a
          franquia de buscas do seu plano: o consumo aparece antes e só é contado depois de você confirmar.
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">O que a empresa faz (um por linha)</div>
          <Textarea rows={3} value={termos} onChange={(e) => { setTermos(e.target.value); setEstimativa(null); }} placeholder={"escritório de contabilidade\nclínica odontológica"} />
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Cidades (uma por linha)</div>
          <Textarea rows={3} value={cidades} onChange={(e) => { setCidades(e.target.value); setEstimativa(null); }} placeholder={"Campinas SP\nRibeirão Preto SP"} />
        </div>
        {estimativa && !estimativa.configurado && (
          <div className="rounded-md bg-surf2 p-2 text-[11px] text-muted">A descoberta por busca não está disponível no momento.</div>
        )}
        {estimativa?.configurado && (
          <div className="rounded-md bg-surf2 p-2 text-[12px] text-text">
            Esta execução usa {estimativa.buscas} busca(s) da sua franquia.{" "}
            {estimativa.franquia_mensal > 0
              ? `Usadas neste mês: ${estimativa.usadas_no_mes} de ${estimativa.franquia_mensal}.`
              : `Usadas neste mês: ${estimativa.usadas_no_mes}.`}
          </div>
        )}
        {resultado?.em_segundo_plano && (
          <div className="rounded-md bg-surf2 p-2 text-[12px] text-text">
            Buscando em segundo plano ({resultado.buscas} busca{resultado.buscas === 1 ? "" : "s"}). As empresas encontradas aparecem na lista
            de contas em alguns minutos; pode fechar esta janela.
          </div>
        )}
        {resultado && !resultado.em_segundo_plano && (
          <div className="rounded-md bg-surf2 p-2 text-[12px] text-text">
            {resultado.buscas} busca(s): {resultado.criadas} conta(s) nova(s), {resultado.atualizadas} já existente(s) com sinais atualizados.
            {(resultado.falhas?.length ?? 0) > 0 && <div className="mt-1 text-[11px] text-muted">Falharam: {resultado.falhas?.join("; ")}</div>}
          </div>
        )}
        {erro && <div className="text-[11px] text-red">{erro}</div>}
        <div className="flex gap-2">
          <Button type="button" disabled={ocupado || !linhas(termos).length || !linhas(cidades).length} onClick={estimar}>
            Ver consumo
          </Button>
          {estimativa?.configurado && (
            <Button type="button" disabled={ocupado} onClick={executar}>
              {ocupado ? "Buscando..." : `Confirmar e buscar (${estimativa.buscas} busca${estimativa.buscas === 1 ? "" : "s"})`}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
