import { useEffect, useState, type FormEvent } from "react";

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
  cnpj: string | null;
  criado_em: string;
}

interface Plano {
  id: number;
  nome: string;
  franquia_contas_mes: number;
  max_usuarios: number;
  preco_mensal: number;
}

export function AdminTenants() {
  const { usuario } = useAuth();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [modalAberto, setModalAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const isSuperAdmin = usuario?.papel === "super_admin";

  async function carregar() {
    try {
      const [tenantsResp, planosResp] = await Promise.all([
        api.get<Tenant[]>("/admin/tenants"),
        api.get<Plano[]>("/planos"),
      ]);
      setTenants(tenantsResp);
      setPlanos(planosResp);
    } catch {
      setErro("Não foi possível carregar os tenants.");
    }
  }

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin]);

  async function criarTenant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/admin/tenants", {
        tenant_id: String(form.get("tenant_id")),
        razao_social: String(form.get("razao_social")),
        cnpj: String(form.get("cnpj") || "") || null,
        plano_id: Number(form.get("plano_id")),
        nome_admin: String(form.get("nome_admin")),
        email_admin: String(form.get("email_admin")),
        senha_admin: String(form.get("senha_admin")),
      });
      setModalAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o tenant.");
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Admin — Tenants</div>
          <div className="mt-0.5 text-[11px] text-muted">Assinantes da B2B ON</div>
        </div>
        <Button size="sm" variant="violet" onClick={() => setModalAberto(true)}>
          + Criar tenant
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Tenants</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">ID</th>
              <th className="p-2 text-left">Razão social</th>
              <th className="p-2 text-left">CNPJ</th>
              <th className="p-2 text-left">Criado em</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((tenant) => (
              <tr key={tenant.id} className="border-b border-border">
                <td className="p-2 font-semibold">{tenant.id}</td>
                <td className="p-2">{tenant.razao_social}</td>
                <td className="p-2 text-muted">{tenant.cnpj ?? "—"}</td>
                <td className="p-2 text-muted">{new Date(tenant.criado_em).toLocaleDateString("pt-BR")}</td>
              </tr>
            ))}
            {tenants.length === 0 && (
              <tr>
                <td colSpan={4} className="p-4 text-center text-muted">
                  Nenhum tenant cadastrado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal title="Criar tenant" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={criarTenant} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Identificador (slug)</div>
            <Input name="tenant_id" required placeholder="ex: empresa-x" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Razão social</div>
            <Input name="razao_social" required />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNPJ (opcional)</div>
            <Input name="cnpj" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Plano</div>
            <Select name="plano_id" required defaultValue="">
              <option value="" disabled>
                Selecione...
              </option>
              {planos.map((plano) => (
                <option key={plano.id} value={plano.id}>
                  {plano.nome} — R${plano.preco_mensal}/mês
                </option>
              ))}
            </Select>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do admin</div>
            <Input name="nome_admin" required />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail do admin</div>
            <Input name="email_admin" type="email" required />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Senha do admin</div>
            <Input name="senha_admin" type="password" required minLength={8} />
          </div>
          <Button type="submit" className="mt-1 w-full justify-center">
            Criar
          </Button>
        </form>
      </Modal>
    </div>
  );
}
