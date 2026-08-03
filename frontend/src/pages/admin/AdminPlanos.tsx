import { useEffect, useState } from "react";

import { Card, SectionLabel } from "@/components/ui/Card";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Plano {
  id: number;
  nome: string;
  franquia_contas_mes: number;
  max_usuarios: number;
  preco_mensal: number;
}

export function AdminPlanos() {
  const { usuario } = useAuth();
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const isSuperAdmin = usuario?.papel === "super_admin";

  useEffect(() => {
    if (!isSuperAdmin) return;
    api
      .get<Plano[]>("/planos")
      .then(setPlanos)
      .catch(() => setErro("Não foi possível carregar os planos."));
  }, [isSuperAdmin]);

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Admin — Planos</div>
        <div className="mt-0.5 text-[11px] text-muted">Planos comerciais disponíveis (somente leitura)</div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Planos</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">Franquia (contas/mês)</th>
              <th className="p-2 text-left">Máx. usuários</th>
              <th className="p-2 text-left">Preço mensal</th>
            </tr>
          </thead>
          <tbody>
            {planos.map((plano) => (
              <tr key={plano.id} className="border-b border-border">
                <td className="p-2 font-semibold">{plano.nome}</td>
                <td className="p-2 text-muted">{plano.franquia_contas_mes}</td>
                <td className="p-2 text-muted">{plano.max_usuarios}</td>
                <td className="p-2 text-cyan">R${plano.preco_mensal.toFixed(2)}</td>
              </tr>
            ))}
            {planos.length === 0 && (
              <tr>
                <td colSpan={4} className="p-4 text-center text-muted">
                  Nenhum plano cadastrado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
