import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface IcpResumo {
  id: number;
  nome: string;
}

interface FitIcpRede {
  tenant_id_candidato: string;
  empresa_nome: string;
  fit_score: number;
  matched_icp: string;
  reasons: string[];
  missing_data: string[];
  confidence: "alta" | "media" | "baixa";
}

const ROTULO_CONFIANCA: Record<string, { texto: string; tone: "green" | "amber" | "muted" }> = {
  alta: { texto: "Confiança alta", tone: "green" },
  media: { texto: "Confiança média", tone: "amber" },
  baixa: { texto: "Confiança baixa", tone: "muted" },
};

export function InteligenciaRede() {
  const [icps, setIcps] = useState<IcpResumo[]>([]);
  const [icpSelecionado, setIcpSelecionado] = useState<string>("");
  const [fits, setFits] = useState<FitIcpRede[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<IcpResumo[]>("/icp")
      .then((resposta) => {
        setIcps(resposta);
        if (resposta.length > 0) setIcpSelecionado(String(resposta[0].id));
      })
      .catch(() => setErro("Não foi possível carregar os ICPs."));
  }, []);

  useEffect(() => {
    if (!icpSelecionado) {
      setFits([]);
      return;
    }
    setCarregando(true);
    setErro(null);
    api
      .get<FitIcpRede[]>(`/inteligencia-rede/fit-icp?icp_id=${icpSelecionado}`)
      .then(setFits)
      .catch((error) => setErro(error instanceof ApiError ? error.message : "Não foi possível calcular o fit."))
      .finally(() => setCarregando(false));
  }, [icpSelecionado]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-head text-[22px] font-extrabold text-text">Sinais de Oportunidade</h1>
        <p className="text-[13px] text-muted">Inteligência comercial cruzando ICP, Intents e o Business Graph da rede</p>
      </div>

      {erro && <div className="rounded-lg border border-red/30 bg-red/10 p-3 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Fit por ICP na Rede</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Compara seu ICP contra o perfil público de todas as outras empresas da Rede Social — quanto mais critérios
          baterem (CNAE, UF, porte), maior o fit. Sempre com os motivos explicados, nunca um score isolado.
        </p>
        {icps.length === 0 ? (
          <div className="text-[12px] text-muted">Cadastre um ICP em Prospecção antes de calcular fit com a rede.</div>
        ) : (
          <div className="mb-3 w-[280px]">
            <Select value={icpSelecionado} onChange={(event) => setIcpSelecionado(event.target.value)}>
              {icps.map((icp) => (
                <option key={icp.id} value={icp.id}>
                  {icp.nome}
                </option>
              ))}
            </Select>
          </div>
        )}
        <div className="flex flex-col gap-2">
          {carregando && <div className="text-[12px] text-muted">Calculando...</div>}
          {!carregando &&
            fits.map((fit) => {
              const confianca = ROTULO_CONFIANCA[fit.confidence] ?? ROTULO_CONFIANCA.baixa;
              return (
                <div key={fit.tenant_id_candidato} className="rounded-lg border border-border p-3 text-[12px]">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-semibold text-text">{fit.empresa_nome}</span>
                    <div className="flex items-center gap-2">
                      <Badge tone={confianca.tone}>{confianca.texto}</Badge>
                      <span className="font-semibold text-cyan">{Math.round(fit.fit_score * 100)}% fit</span>
                    </div>
                  </div>
                  {fit.reasons.length > 0 && (
                    <ul className="list-disc pl-4 text-text">
                      {fit.reasons.map((motivo) => (
                        <li key={motivo}>{motivo}</li>
                      ))}
                    </ul>
                  )}
                  {fit.missing_data.length > 0 && (
                    <div className="mt-1 text-muted">
                      Dados que a empresa não preencheu: {fit.missing_data.join(", ")}
                    </div>
                  )}
                </div>
              );
            })}
          {!carregando && icpSelecionado && fits.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma outra empresa da rede ainda.</div>
          )}
        </div>
      </Card>
    </div>
  );
}
