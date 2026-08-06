import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface LeadDecisor {
  id: number;
  conta_id: number;
  nome: string;
  cargo: string | null;
  email: string | null;
  telefone: string | null;
}

interface LeadConta {
  id: number;
  nome: string;
  nome_fantasia: string | null;
}

export function LeadsContatos() {
  const navigate = useNavigate();
  const { usuario } = useAuth();
  const isGestor = usuario?.papel === "admin" || usuario?.papel === "super_admin";

  const [contatos, setContatos] = useState<LeadDecisor[]>([]);
  const [empresas, setEmpresas] = useState<LeadConta[]>([]);
  const [modalAberto, setModalAberto] = useState(false);
  const [empresaOrigem, setEmpresaOrigem] = useState<"existente" | "nova">("existente");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      const [contatosResp, empresasResp] = await Promise.all([
        api.get<LeadDecisor[]>("/leads/decisores"),
        api.get<LeadConta[]>("/leads/contas"),
      ]);
      setContatos(contatosResp);
      setEmpresas(empresasResp);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar os contatos.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  function nomeEmpresa(contaId: number): string {
    const empresa = empresas.find((item) => item.id === contaId);
    return empresa ? empresa.nome_fantasia || empresa.nome : `Conta #${contaId}`;
  }

  async function criarContato(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    setSalvando(true);
    setErro(null);
    try {
      let contaId: number;
      if (empresaOrigem === "existente") {
        contaId = Number(form.get("conta_id"));
        if (!contaId) {
          setErro("Selecione uma empresa.");
          return;
        }
      } else {
        const nomeEmpresaNova = String(form.get("nome_empresa") || "").trim();
        if (!nomeEmpresaNova) {
          setErro("Informe o nome da empresa.");
          return;
        }
        const empresaCriada = await api.post<LeadConta>("/leads/contas", { nome: nomeEmpresaNova });
        contaId = empresaCriada.id;
      }

      await api.post(`/contas/${contaId}/decisores`, {
        nome: String(form.get("nome")),
        cargo: String(form.get("cargo") || "") || null,
        email: String(form.get("email") || "") || null,
        telefone: String(form.get("telefone") || "") || null,
      });
      setModalAberto(false);
      setEmpresaOrigem("existente");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível cadastrar o contato.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Leads — Contatos</div>
          <div className="mt-0.5 text-[11px] text-muted">
            {isGestor ? "Contatos de todos os leads do time" : "Contatos dos leads da sua carteira"}
          </div>
        </div>
        <Button size="sm" onClick={() => setModalAberto(true)}>
          + Novo contato
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Contatos</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Contato</th>
              <th className="p-2 text-left">Empresa</th>
              <th className="p-2 text-left">E-mail</th>
              <th className="p-2 text-left">Telefone</th>
            </tr>
          </thead>
          <tbody>
            {contatos.map((contato) => (
              <tr
                key={contato.id}
                onClick={() => navigate(`/leads/contas/${contato.conta_id}`)}
                className="cursor-pointer border-b border-border hover:bg-surf2"
              >
                <td className="p-2 font-semibold">
                  {contato.nome}
                  {contato.cargo && <span className="text-muted"> · {contato.cargo}</span>}
                </td>
                <td className="p-2 text-muted">{nomeEmpresa(contato.conta_id)}</td>
                <td className="p-2 text-muted">{contato.email ?? "—"}</td>
                <td className="p-2 text-muted">{contato.telefone ?? "—"}</td>
              </tr>
            ))}
            {contatos.length === 0 && (
              <tr>
                <td colSpan={4} className="p-4 text-center text-muted">
                  Nenhum contato cadastrado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal title="Novo contato" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={criarContato} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Empresa</div>
            <div className="mb-2 flex gap-2">
              <button
                type="button"
                onClick={() => setEmpresaOrigem("existente")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12px] ${
                  empresaOrigem === "existente" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                }`}
              >
                Empresa existente
              </button>
              <button
                type="button"
                onClick={() => setEmpresaOrigem("nova")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12px] ${
                  empresaOrigem === "nova" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                }`}
              >
                Cadastrar empresa nova
              </button>
            </div>
            {empresaOrigem === "existente" ? (
              <Select name="conta_id" required defaultValue="">
                <option value="" disabled>
                  Selecione a empresa
                </option>
                {empresas.map((empresa) => (
                  <option key={empresa.id} value={empresa.id}>
                    {empresa.nome_fantasia || empresa.nome}
                  </option>
                ))}
              </Select>
            ) : (
              <Input name="nome_empresa" required placeholder="Nome da empresa" />
            )}
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do contato</div>
            <Input name="nome" required placeholder="Nome completo" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Cargo</div>
            <Input name="cargo" placeholder="Ex.: Diretor Comercial" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail</div>
            <Input name="email" type="email" placeholder="contato@empresa.com.br" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Telefone</div>
            <Input name="telefone" placeholder="(11) 99999-9999" />
          </div>
          <Button type="submit" disabled={salvando} className="mt-1 w-full justify-center">
            {salvando ? "Cadastrando..." : "Cadastrar contato"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
