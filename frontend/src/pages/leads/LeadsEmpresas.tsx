import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface LeadConta {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  segmento: string | null;
  porte: string | null;
  regiao: string | null;
  vendedor_usuario_id: number | null;
  criado_em: string;
}

interface UsuarioResumo {
  id: number;
  nome: string;
}

/** "Leads" (E-Leads) — clientes conquistados um a um (indicação, evento,
 * contato pessoal), fora do recorte estático de qualquer ICP. Distinta da
 * Prospecção (ICP + Receita Federal): aqui não há segmento/porte/dor único
 * esperado, cada empresa pode ser de um ramo diferente. */
export function LeadsEmpresas() {
  const navigate = useNavigate();
  const { usuario } = useAuth();
  const isGestor = usuario?.papel === "admin" || usuario?.papel === "super_admin";

  const [empresas, setEmpresas] = useState<LeadConta[]>([]);
  const [vendedores, setVendedores] = useState<UsuarioResumo[]>([]);
  const [filtroVendedorId, setFiltroVendedorId] = useState<number | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    const filtro = filtroVendedorId ? `?vendedor_usuario_id=${filtroVendedorId}` : "";
    try {
      setEmpresas(await api.get<LeadConta[]>(`/leads/contas${filtro}`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as empresas.");
    }
  }

  useEffect(() => {
    carregar();
  }, [filtroVendedorId]);

  useEffect(() => {
    if (isGestor) {
      api
        .get<UsuarioResumo[]>("/usuarios")
        .then(setVendedores)
        .catch(() => undefined);
    }
  }, [isGestor]);

  async function criarEmpresa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    setSalvando(true);
    setErro(null);
    try {
      const criada = await api.post<LeadConta>("/leads/contas", {
        nome: String(form.get("nome")),
        cnpj: String(form.get("cnpj") || "") || null,
        dominio: String(form.get("dominio") || "") || null,
        segmento: String(form.get("segmento") || "") || null,
        porte: String(form.get("porte") || "") || null,
        regiao: String(form.get("regiao") || "") || null,
      });
      setModalAberto(false);
      navigate(`/leads/contas/${criada.id}`);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível cadastrar a empresa.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Leads — Empresas</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Clientes cadastrados direto no CRM — indicação, evento, contato pessoal — sem passar por um ICP
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isGestor && (
            <Select
              value={filtroVendedorId ?? ""}
              onChange={(event) => setFiltroVendedorId(event.target.value ? Number(event.target.value) : null)}
              className="w-52"
            >
              <option value="">Todos os vendedores</option>
              {vendedores.map((vendedor) => (
                <option key={vendedor.id} value={vendedor.id}>
                  {vendedor.nome}
                </option>
              ))}
            </Select>
          )}
          <Button size="sm" onClick={() => setModalAberto(true)}>
            + Nova empresa
          </Button>
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Empresas</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Empresa</th>
              <th className="p-2 text-left">Segmento</th>
              <th className="p-2 text-left">Porte</th>
              <th className="p-2 text-left">UF</th>
            </tr>
          </thead>
          <tbody>
            {empresas.map((empresa) => (
              <tr
                key={empresa.id}
                onClick={() => navigate(`/leads/contas/${empresa.id}`)}
                className="cursor-pointer border-b border-border hover:bg-surf2"
              >
                <td className="p-2 font-semibold">{empresa.nome_fantasia || empresa.nome}</td>
                <td className="p-2 text-muted">{empresa.segmento ?? "—"}</td>
                <td className="p-2 text-muted">{empresa.porte ?? "—"}</td>
                <td className="p-2 text-muted">{empresa.regiao ?? "—"}</td>
              </tr>
            ))}
            {empresas.length === 0 && (
              <tr>
                <td colSpan={4} className="p-4 text-center text-muted">
                  Nenhuma empresa cadastrada ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal title="Nova empresa" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={criarEmpresa} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
            <Input name="nome" required placeholder="Nome da empresa" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNPJ (opcional)</div>
            <Input name="cnpj" placeholder="00.000.000/0000-00" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Domínio (opcional)</div>
            <Input name="dominio" placeholder="empresa.com.br" />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Segmento</div>
              <Input name="segmento" placeholder="Ex.: Saúde" />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Porte</div>
              <Input name="porte" placeholder="Ex.: PEQUENO" />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">UF</div>
              <Input name="regiao" placeholder="SP" />
            </div>
          </div>
          <Button type="submit" disabled={salvando} className="mt-1 w-full justify-center">
            {salvando ? "Cadastrando..." : "Cadastrar empresa"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
