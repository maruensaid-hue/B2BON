import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Convite {
  id: number;
  codigo: string;
  papel_concedido: string;
  status: string;
  validade_em: string | null;
  usado_por_usuario_id: number | null;
  criado_em: string;
}

function toneStatus(status: string): "green" | "muted" | "red" {
  if (status === "disponivel") return "green";
  if (status === "usado") return "muted";
  return "red";
}

export function AdminConvites() {
  const { usuario } = useAuth();
  const [convites, setConvites] = useState<Convite[]>([]);
  const [modalAberto, setModalAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const isSuperAdmin = usuario?.papel === "super_admin";

  async function carregar() {
    try {
      setConvites(await api.get<Convite[]>("/convites"));
    } catch {
      setErro("Não foi possível carregar os convites.");
    }
  }

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin]);

  async function gerarConvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/convites", {
        papel_concedido: String(form.get("papel_concedido")),
        validade_horas: Number(form.get("validade_horas")),
      });
      setModalAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar o convite.");
    }
  }

  async function revogar(codigo: string) {
    try {
      await api.post(`/convites/${codigo}/revogar`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível revogar o convite.");
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Admin — Convites</div>
          <div className="mt-0.5 text-[11px] text-muted">Códigos de acesso pré-autorizado do seu tenant</div>
        </div>
        <Button size="sm" variant="violet" onClick={() => setModalAberto(true)}>
          + Gerar convite
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Convites</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Código</th>
              <th className="p-2 text-left">Papel</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Validade</th>
              <th className="p-2 text-left">Ações</th>
            </tr>
          </thead>
          <tbody>
            {convites.map((convite) => (
              <tr key={convite.id} className="border-b border-border">
                <td className="p-2 font-head font-bold tracking-wide">{convite.codigo}</td>
                <td className="p-2 text-muted">{convite.papel_concedido}</td>
                <td className="p-2">
                  <Badge tone={toneStatus(convite.status)}>{convite.status}</Badge>
                </td>
                <td className="p-2 text-muted">
                  {convite.validade_em ? new Date(convite.validade_em).toLocaleString("pt-BR") : "Sem expiração"}
                </td>
                <td className="p-2">
                  {convite.status === "disponivel" && (
                    <Button size="sm" variant="danger" onClick={() => revogar(convite.codigo)}>
                      Revogar
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {convites.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-muted">
                  Nenhum convite gerado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal title="Gerar convite" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={gerarConvite} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Papel concedido</div>
            <Select name="papel_concedido" required defaultValue="user">
              <option value="user">Usuário</option>
              <option value="admin">Admin</option>
              <option value="super_admin">Super Admin</option>
            </Select>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Validade (horas)</div>
            <Input name="validade_horas" type="number" defaultValue={168} min={1} />
          </div>
          <Button type="submit" className="w-full justify-center">
            Gerar
          </Button>
        </form>
      </Modal>
    </div>
  );
}
