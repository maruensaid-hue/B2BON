import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";

interface EstagioFunil {
  id: number;
  nome: string;
  ordem: number;
  tipo: "aberto" | "ganho" | "perdido";
}

interface Negocio {
  id: number;
  conta_id: number;
  estagio_id: number;
  nome: string;
  valor: number;
  probabilidade: number;
}

export function Kanban() {
  const [estagios, setEstagios] = useState<EstagioFunil[]>([]);
  const [negocios, setNegocios] = useState<Negocio[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);

  async function carregar() {
    try {
      const [estagiosResp, negociosResp] = await Promise.all([
        api.get<EstagioFunil[]>("/crm/estagios"),
        api.get<Negocio[]>("/crm/negocios"),
      ]);
      setEstagios([...estagiosResp].sort((a, b) => a.ordem - b.ordem));
      setNegocios(negociosResp);
    } catch {
      setErro("Não foi possível carregar o kanban.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function moverEstagio(negocioId: number, estagioId: number) {
    try {
      await api.put(`/crm/negocios/${negocioId}/estagio`, { estagio_id: estagioId });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível mover o negócio.");
    }
  }

  async function criarNegocio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/crm/negocios", {
        conta_id: Number(form.get("conta_id")),
        nome: String(form.get("nome")),
        valor: Number(form.get("valor") || 0),
      });
      setModalAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o negócio.");
    }
  }

  const valorTotal = negocios.reduce((soma, negocio) => soma + negocio.valor, 0);

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">CRM — Pipeline</div>
          <div className="mt-0.5 text-[11px] text-muted">
            {negocios.length} negócio(s) · R${Math.round(valorTotal / 1000)}k em pipeline
          </div>
        </div>
        <Button size="sm" onClick={() => setModalAberto(true)}>
          + Novo negócio
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="grid grid-cols-1 gap-2.5 overflow-x-auto sm:grid-cols-2 lg:grid-cols-4">
        {estagios.map((estagio) => {
          const negociosDoEstagio = negocios.filter((negocio) => negocio.estagio_id === estagio.id);
          return (
            <div key={estagio.id} className="min-w-0">
              <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold tracking-wide text-muted uppercase">
                {estagio.nome}
                <span className="rounded-full bg-cyan/15 px-1.5 py-px text-cyan">{negociosDoEstagio.length}</span>
              </div>
              {negociosDoEstagio.map((negocio) => (
                <Card key={negocio.id} className="mb-2 p-3">
                  <div className="mb-1 text-[12px] font-bold">{negocio.nome}</div>
                  <div className="font-head mb-2 text-base font-bold text-cyan">
                    R${Math.round(negocio.valor / 1000)}k
                  </div>
                  <Select
                    value={negocio.estagio_id}
                    onChange={(event) => moverEstagio(negocio.id, Number(event.target.value))}
                  >
                    {estagios.map((opcao) => (
                      <option key={opcao.id} value={opcao.id}>
                        {opcao.nome}
                      </option>
                    ))}
                  </Select>
                </Card>
              ))}
              {negociosDoEstagio.length === 0 && (
                <div className="rounded-xl border border-dashed border-border p-4 text-center text-[11px] text-muted">
                  Vazio
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Modal title="Novo negócio" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={criarNegocio} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">ID da conta</div>
            <Input name="conta_id" type="number" required placeholder="Ex: 1" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do negócio</div>
            <Input name="nome" required placeholder="Ex: Licença Professional — 12 meses" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Valor (R$)</div>
            <Input name="valor" type="number" step="0.01" placeholder="0,00" />
          </div>
          <Button type="submit" className="mt-1 w-full justify-center">
            Criar negócio
          </Button>
        </form>
      </Modal>
    </div>
  );
}
