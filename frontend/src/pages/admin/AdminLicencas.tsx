import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Tenant {
  id: string;
  razao_social: string;
}

interface Plano {
  id: number;
  nome: string;
}

interface Licenca {
  id: number;
  tenant_id: string;
  plano_id: number;
  status: string;
  data_expiracao: string | null;
}

interface LinhaLicenca {
  tenant: Tenant;
  licenca: Licenca | null;
}

export function AdminLicencas() {
  const { usuario } = useAuth();
  const [linhas, setLinhas] = useState<LinhaLicenca[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [tenantEmEdicao, setTenantEmEdicao] = useState<LinhaLicenca | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const isSuperAdmin = usuario?.papel === "super_admin";

  async function carregar() {
    try {
      const [tenants, planosResp] = await Promise.all([
        api.get<Tenant[]>("/admin/tenants"),
        api.get<Plano[]>("/planos"),
      ]);
      setPlanos(planosResp);
      const linhasCarregadas = await Promise.all(
        tenants.map(async (tenant) => {
          try {
            const licenca = await api.get<Licenca>(`/admin/tenants/${tenant.id}/licenca`);
            return { tenant, licenca };
          } catch {
            return { tenant, licenca: null };
          }
        }),
      );
      setLinhas(linhasCarregadas);
    } catch {
      setErro("Não foi possível carregar as licenças.");
    }
  }

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin]);

  async function salvarLicenca(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantEmEdicao) return;
    const form = new FormData(event.currentTarget);
    const dataExpiracao = String(form.get("data_expiracao") || "");
    try {
      await api.put(`/admin/tenants/${tenantEmEdicao.tenant.id}/licenca`, {
        plano_id: Number(form.get("plano_id")),
        status: String(form.get("status")),
        data_expiracao: dataExpiracao ? new Date(dataExpiracao).toISOString() : null,
      });
      setTenantEmEdicao(null);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a licença.");
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Admin — Licenças</div>
        <div className="mt-0.5 text-[11px] text-muted">Controle de acesso por tenant</div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Licenças</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Tenant</th>
              <th className="p-2 text-left">Plano</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Expiração</th>
              <th className="p-2 text-left">Ações</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha) => (
              <tr key={linha.tenant.id} className="border-b border-border">
                <td className="p-2 font-semibold">{linha.tenant.razao_social}</td>
                <td className="p-2">
                  {planos.find((plano) => plano.id === linha.licenca?.plano_id)?.nome ?? "—"}
                </td>
                <td className="p-2">
                  <Badge tone={linha.licenca?.status === "ativa" ? "green" : "amber"}>
                    {linha.licenca?.status ?? "sem licença"}
                  </Badge>
                </td>
                <td className="p-2 text-muted">
                  {linha.licenca?.data_expiracao
                    ? new Date(linha.licenca.data_expiracao).toLocaleDateString("pt-BR")
                    : "Sem expiração"}
                </td>
                <td className="p-2">
                  <Button
                    size="sm"
                    variant={linha.licenca ? "ghost" : "violet"}
                    onClick={() => setTenantEmEdicao(linha)}
                  >
                    {linha.licenca ? "Editar" : "Criar licença"}
                  </Button>
                </td>
              </tr>
            ))}
            {linhas.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-muted">
                  Nenhum tenant cadastrado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        title={
          tenantEmEdicao
            ? `${tenantEmEdicao.licenca ? "Editar" : "Criar"} licença — ${tenantEmEdicao.tenant.razao_social}`
            : "Licença"
        }
        open={tenantEmEdicao !== null}
        onClose={() => setTenantEmEdicao(null)}
      >
        {tenantEmEdicao && (
          <form onSubmit={salvarLicenca} className="flex flex-col gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Plano</div>
              <Select name="plano_id" required defaultValue={tenantEmEdicao.licenca?.plano_id}>
                {planos.map((plano) => (
                  <option key={plano.id} value={plano.id}>
                    {plano.nome}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Status</div>
              <Select name="status" required defaultValue={tenantEmEdicao.licenca?.status}>
                <option value="ativa">Ativa</option>
                <option value="suspensa">Suspensa</option>
                <option value="expirada">Expirada</option>
              </Select>
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Expiração (opcional)</div>
              <Input
                name="data_expiracao"
                type="date"
                defaultValue={tenantEmEdicao.licenca?.data_expiracao?.slice(0, 10) ?? ""}
              />
            </div>
            <Button type="submit" className="w-full justify-center">
              Salvar
            </Button>
          </form>
        )}
      </Modal>
    </div>
  );
}
