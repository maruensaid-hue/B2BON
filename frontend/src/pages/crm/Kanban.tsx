import { useEffect, useMemo, useState, type FormEvent } from "react";

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

interface ICP {
  id: number;
  nome: string;
  ativo: boolean;
}

interface Conta {
  id: number;
  nome: string;
  nome_fantasia: string | null;
}

export function Kanban() {
  const [estagios, setEstagios] = useState<EstagioFunil[]>([]);
  const [negocios, setNegocios] = useState<Negocio[]>([]);
  const [icps, setIcps] = useState<ICP[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [contaOrigem, setContaOrigem] = useState<"existente" | "nova">("existente");
  const [icpSelecionadoId, setIcpSelecionadoId] = useState<number | null>(null);
  const [contasDoIcp, setContasDoIcp] = useState<Conta[]>([]);
  const [negocioArrastadoId, setNegocioArrastadoId] = useState<number | null>(null);
  const [salvandoNegocio, setSalvandoNegocio] = useState(false);

  // Defesa contra a duplicidade de estágios já corrigida no backend
  // (UniqueConstraint tenant_id+ordem) — se ainda houver dado antigo
  // duplicado, a tela não volta a mostrar a mesma fila duas vezes.
  const estagiosUnicos = useMemo(() => {
    const vistos = new Set<string>();
    return estagios
      .filter((estagio) => {
        const chave = `${estagio.nome}::${estagio.tipo}`;
        if (vistos.has(chave)) return false;
        vistos.add(chave);
        return true;
      })
      .sort((a, b) => a.ordem - b.ordem);
  }, [estagios]);

  async function carregar() {
    try {
      const [estagiosResp, negociosResp] = await Promise.all([
        api.get<EstagioFunil[]>("/crm/estagios"),
        api.get<Negocio[]>("/crm/negocios"),
      ]);
      setEstagios(estagiosResp);
      setNegocios(negociosResp);
    } catch {
      setErro("Não foi possível carregar o kanban.");
    }
  }

  useEffect(() => {
    carregar();
    api
      .get<ICP[]>("/icp")
      .then(setIcps)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (icpSelecionadoId === null) {
      setContasDoIcp([]);
      return;
    }
    api
      .get<Conta[]>(`/icp/${icpSelecionadoId}/contas`)
      .then(setContasDoIcp)
      .catch(() => setErro("Não foi possível carregar as contas do ICP."));
  }, [icpSelecionadoId]);

  async function moverEstagio(negocioId: number, estagioId: number) {
    try {
      await api.put(`/crm/negocios/${negocioId}/estagio`, { estagio_id: estagioId });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível mover o negócio.");
    }
  }

  function aoSoltarNoEstagio(estagioId: number) {
    if (negocioArrastadoId === null) return;
    const negocio = negocios.find((n) => n.id === negocioArrastadoId);
    setNegocioArrastadoId(null);
    if (!negocio || negocio.estagio_id === estagioId) return;
    moverEstagio(negocio.id, estagioId);
  }

  async function criarNegocio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvandoNegocio) return;
    const form = new FormData(event.currentTarget);
    const nomeNegocio = String(form.get("nome"));
    const valor = Number(form.get("valor") || 0);

    setSalvandoNegocio(true);
    setErro(null);
    try {
      let contaId: number;
      if (contaOrigem === "existente") {
        contaId = Number(form.get("conta_id"));
        if (!contaId) {
          setErro("Selecione uma conta.");
          return;
        }
      } else {
        if (icpSelecionadoId === null) {
          setErro("Selecione um ICP para cadastrar a conta nova.");
          return;
        }
        const nomeConta = String(form.get("nome_conta") || "").trim();
        if (!nomeConta) {
          setErro("Informe o nome do cliente.");
          return;
        }
        const contaCriada = await api.post<Conta>(`/icp/${icpSelecionadoId}/contas`, {
          nome: nomeConta,
          dominio: String(form.get("dominio_conta") || "") || null,
        });
        contaId = contaCriada.id;
      }

      await api.post("/crm/negocios", { conta_id: contaId, nome: nomeNegocio, valor });
      setModalAberto(false);
      setContaOrigem("existente");
      setIcpSelecionadoId(null);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o negócio.");
    } finally {
      setSalvandoNegocio(false);
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
        {estagiosUnicos.map((estagio) => {
          const negociosDoEstagio = negocios.filter((negocio) => negocio.estagio_id === estagio.id);
          return (
            <div
              key={estagio.id}
              className="min-w-0"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                aoSoltarNoEstagio(estagio.id);
              }}
            >
              <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold tracking-wide text-muted uppercase">
                {estagio.nome}
                <span className="rounded-full bg-cyan/15 px-1.5 py-px text-cyan">{negociosDoEstagio.length}</span>
              </div>
              {negociosDoEstagio.map((negocio) => (
                <Card
                  key={negocio.id}
                  className="mb-2 cursor-grab p-3 active:cursor-grabbing"
                  draggable
                  onDragStart={() => setNegocioArrastadoId(negocio.id)}
                  onDragEnd={() => setNegocioArrastadoId(null)}
                >
                  <div className="mb-1 text-[12px] font-bold">{negocio.nome}</div>
                  <div className="font-head mb-2 text-base font-bold text-cyan">
                    R${Math.round(negocio.valor / 1000)}k
                  </div>
                  <Select
                    value={negocio.estagio_id}
                    onChange={(event) => moverEstagio(negocio.id, Number(event.target.value))}
                  >
                    {estagiosUnicos.map((opcao) => (
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
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Cliente</div>
            <div className="mb-2 flex gap-2">
              <button
                type="button"
                onClick={() => setContaOrigem("existente")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12px] ${
                  contaOrigem === "existente" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                }`}
              >
                Conta existente
              </button>
              <button
                type="button"
                onClick={() => setContaOrigem("nova")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12px] ${
                  contaOrigem === "nova" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                }`}
              >
                Cadastrar cliente novo
              </button>
            </div>

            <Select
              value={icpSelecionadoId ?? ""}
              onChange={(event) => setIcpSelecionadoId(event.target.value ? Number(event.target.value) : null)}
              className="mb-2"
            >
              <option value="">{contaOrigem === "existente" ? "Filtrar por ICP" : "Selecione o ICP da conta"}</option>
              {icps.map((icp) => (
                <option key={icp.id} value={icp.id}>
                  {icp.nome}
                </option>
              ))}
            </Select>

            {contaOrigem === "existente" ? (
              <Select name="conta_id" required defaultValue="">
                <option value="" disabled>
                  {icpSelecionadoId === null ? "Selecione um ICP primeiro" : "Selecione a conta"}
                </option>
                {contasDoIcp.map((conta) => (
                  <option key={conta.id} value={conta.id}>
                    {conta.nome_fantasia || conta.nome}
                  </option>
                ))}
              </Select>
            ) : (
              <div className="flex flex-col gap-2">
                <Input name="nome_conta" required placeholder="Nome do cliente" />
                <Input name="dominio_conta" placeholder="Domínio (opcional)" />
              </div>
            )}
          </div>

          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do negócio</div>
            <Input name="nome" required placeholder="Ex: Licença Professional — 12 meses" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Valor (R$)</div>
            <Input name="valor" type="number" step="0.01" placeholder="0,00" />
          </div>
          <Button type="submit" disabled={salvandoNegocio} className="mt-1 w-full justify-center">
            {salvandoNegocio ? "Criando..." : "Criar negócio"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
