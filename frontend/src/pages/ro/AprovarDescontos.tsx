import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";

interface SolicitacaoDesconto {
  id: number;
  tenant_id: string;
  registro_oportunidade_id: number;
  solicitante_usuario_id: number;
  percentual_solicitado: number;
  justificativa: string | null;
  status: string;
  criado_em: string;
}

const TOM_STATUS: Record<string, "green" | "amber" | "red"> = {
  pendente: "amber",
  aprovado: "green",
  rejeitado: "red",
};

/** Fila de decisão sobre pedidos de desconto/vantagem — quem detém o
 * Registro de Oportunidade ativo (é PRIME) pode pedir; só o admin do
 * tenant raiz da rede (o "fabricante") decide, nunca um admin do meio
 * da subárvore. */
export function AprovarDescontos() {
  const [solicitacoes, setSolicitacoes] = useState<SolicitacaoDesconto[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [decidindoId, setDecidindoId] = useState<number | null>(null);

  async function carregar() {
    try {
      setSolicitacoes(await api.get<SolicitacaoDesconto[]>("/registro-oportunidade/solicitacoes-desconto"));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as solicitações.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function decidir(id: number, aprovar: boolean) {
    setDecidindoId(id);
    setErro(null);
    try {
      await api.put(`/registro-oportunidade/solicitacoes-desconto/${id}`, { aprovar });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível decidir a solicitação.");
    } finally {
      setDecidindoId(null);
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Aprovar Descontos</div>
        <div className="mt-0.5 text-[11px] text-muted">
          Pedidos de desconto/vantagem de revendedores PRIME da sua rede — só quem registrou a oportunidade
          primeiro pode pedir.
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Solicitações</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Tenant</th>
              <th className="p-2 text-left">Percentual</th>
              <th className="p-2 text-left">Justificativa</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left"></th>
            </tr>
          </thead>
          <tbody>
            {solicitacoes.map((solicitacao) => (
              <tr key={solicitacao.id} className="border-b border-border">
                <td className="p-2 font-semibold">{solicitacao.tenant_id}</td>
                <td className="p-2 text-muted">{solicitacao.percentual_solicitado}%</td>
                <td className="p-2 text-muted">{solicitacao.justificativa ?? "—"}</td>
                <td className="p-2">
                  <Badge tone={TOM_STATUS[solicitacao.status] ?? "muted"}>{solicitacao.status}</Badge>
                </td>
                <td className="p-2 text-right">
                  {solicitacao.status === "pendente" && (
                    <div className="flex justify-end gap-1.5">
                      <Button
                        size="sm"
                        variant="green"
                        disabled={decidindoId === solicitacao.id}
                        onClick={() => decidir(solicitacao.id, true)}
                      >
                        Aprovar
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={decidindoId === solicitacao.id}
                        onClick={() => decidir(solicitacao.id, false)}
                      >
                        Rejeitar
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {solicitacoes.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-muted">
                  Nenhuma solicitação de desconto ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
