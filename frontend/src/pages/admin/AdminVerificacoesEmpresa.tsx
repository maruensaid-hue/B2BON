import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface VerificacaoEmpresa {
  id: number;
  tenant_id: string;
  status: string;
  email_verificacao: string;
  dominio_confere: boolean;
  cnpj_encontrado_receita: boolean;
  solicitado_em: string;
}

export function AdminVerificacoesEmpresa() {
  const { usuario } = useAuth();
  const [pendentes, setPendentes] = useState<VerificacaoEmpresa[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [processandoId, setProcessandoId] = useState<number | null>(null);
  const [motivoRejeicaoId, setMotivoRejeicaoId] = useState<number | null>(null);
  const [motivoTexto, setMotivoTexto] = useState("");

  const isSuperAdmin = usuario?.papel === "super_admin";

  async function carregar() {
    try {
      setPendentes(await api.get<VerificacaoEmpresa[]>("/verificacao-empresa/pendentes"));
    } catch {
      setErro("Não foi possível carregar as solicitações de verificação.");
    }
  }

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin]);

  async function revisar(verificacaoId: number, aprovar: boolean, motivoRejeicao?: string) {
    setProcessandoId(verificacaoId);
    setErro(null);
    try {
      await api.post(`/verificacao-empresa/${verificacaoId}/revisar`, { aprovar, motivo_rejeicao: motivoRejeicao ?? null });
      setMotivoRejeicaoId(null);
      setMotivoTexto("");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível revisar a solicitação.");
    } finally {
      setProcessandoId(null);
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Verificações de Empresa</div>
        <div className="mt-0.5 text-[11px] text-muted">
          Company Claim/Trust Layer do Shoal — sinais automáticos orientam, a decisão final é sempre manual.
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Pendentes</SectionLabel>
        <div className="flex flex-col gap-2">
          {pendentes.map((verificacao) => (
            <div key={verificacao.id} className="rounded-lg border border-border p-3 text-[12px]">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-semibold text-text">{verificacao.tenant_id}</span>
                <span className="text-muted">{new Date(verificacao.solicitado_em).toLocaleString("pt-BR")}</span>
              </div>
              <div className="mb-2 text-muted">{verificacao.email_verificacao}</div>
              <div className="mb-2 flex gap-1.5">
                <Badge tone={verificacao.dominio_confere ? "green" : "muted"}>
                  {verificacao.dominio_confere ? "Domínio confere" : "Domínio não confere"}
                </Badge>
                <Badge tone={verificacao.cnpj_encontrado_receita ? "green" : "muted"}>
                  {verificacao.cnpj_encontrado_receita ? "CNPJ visto na Receita" : "CNPJ não visto no recorte"}
                </Badge>
              </div>
              {motivoRejeicaoId === verificacao.id ? (
                <div className="flex flex-col gap-2">
                  <input
                    className="w-full rounded-lg border border-border bg-surf2 px-3 py-2 text-[12px] text-text outline-none"
                    placeholder="Motivo da recusa (opcional)"
                    value={motivoTexto}
                    onChange={(event) => setMotivoTexto(event.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={processandoId === verificacao.id}
                      onClick={() => revisar(verificacao.id, false, motivoTexto || undefined)}
                    >
                      Confirmar recusa
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setMotivoRejeicaoId(null)}>
                      Cancelar
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="green"
                    disabled={processandoId === verificacao.id}
                    onClick={() => revisar(verificacao.id, true)}
                  >
                    Aprovar
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => setMotivoRejeicaoId(verificacao.id)}>
                    Recusar
                  </Button>
                </div>
              )}
            </div>
          ))}
          {pendentes.length === 0 && <div className="text-[12px] text-muted">Nenhuma solicitação pendente.</div>}
        </div>
      </Card>
    </div>
  );
}
