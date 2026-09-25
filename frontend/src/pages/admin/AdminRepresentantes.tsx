import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Representante {
  id: number;
  nome: string;
  email: string;
  cpf: string | null;
  chave_pix: string;
  percentual_comissao: number;
  ativo: boolean;
}

function FormularioRepresentante({
  representante,
  onSalvar,
  salvando,
}: {
  representante: Representante | null;
  onSalvar: (event: FormEvent<HTMLFormElement>) => void;
  salvando: boolean;
}) {
  return (
    <form onSubmit={onSalvar} className="flex flex-col gap-3">
      <div>
        <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
        <Input name="nome" required defaultValue={representante?.nome} placeholder="Nome completo" />
      </div>
      <div>
        <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail</div>
        <Input name="email" type="email" required defaultValue={representante?.email} placeholder="representante@email.com" />
      </div>
      <div>
        <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CPF (opcional)</div>
        <Input name="cpf" defaultValue={representante?.cpf ?? ""} placeholder="000.000.000-00" />
      </div>
      <div>
        <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Chave Pix (recebe o repasse)</div>
        <Input name="chave_pix" required defaultValue={representante?.chave_pix} placeholder="e-mail, CPF/CNPJ ou aleatória" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Comissão (%)</div>
          <Input
            name="percentual_comissao_pct"
            type="number"
            min={0.01}
            max={100}
            step="0.01"
            required
            defaultValue={representante ? representante.percentual_comissao * 100 : 10}
          />
        </div>
        <label className="flex items-center gap-1.5 self-end pb-2 text-[12px] text-muted">
          <input type="checkbox" name="ativo" defaultChecked={representante?.ativo ?? true} />
          Ativo (aparece no cadastro self-service)
        </label>
      </div>

      <Button type="submit" disabled={salvando} className="mt-1 w-full justify-center">
        {salvando ? "Salvando..." : representante ? "Salvar alterações" : "Criar representante"}
      </Button>
    </form>
  );
}

export function AdminRepresentantes() {
  const { usuario } = useAuth();
  const [representantes, setRepresentantes] = useState<Representante[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [representanteEmEdicao, setRepresentanteEmEdicao] = useState<Representante | null>(null);
  const [salvando, setSalvando] = useState(false);

  const isSuperAdmin = usuario?.papel === "super_admin";

  async function carregar() {
    try {
      setRepresentantes(await api.get<Representante[]>("/representantes"));
    } catch {
      setErro("Não foi possível carregar os representantes.");
    }
  }

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin]);

  function abrirCriacao() {
    setRepresentanteEmEdicao(null);
    setModalAberto(true);
  }

  function abrirEdicao(representante: Representante) {
    setRepresentanteEmEdicao(representante);
    setModalAberto(true);
  }

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    const dados = {
      nome: String(form.get("nome")),
      email: String(form.get("email")),
      cpf: String(form.get("cpf") || "") || null,
      chave_pix: String(form.get("chave_pix")),
      percentual_comissao: Number(form.get("percentual_comissao_pct")) / 100,
      ativo: form.get("ativo") === "on",
    };
    setSalvando(true);
    setErro(null);
    try {
      if (representanteEmEdicao) {
        await api.put(`/representantes/${representanteEmEdicao.id}`, dados);
      } else {
        await api.post("/representantes", dados);
      }
      setModalAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o representante.");
    } finally {
      setSalvando(false);
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Admin — Representantes</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Vendedores externos e a % de comissão recorrente sobre os tenants que trouxerem
          </div>
        </div>
        <Button size="sm" variant="violet" onClick={abrirCriacao}>
          + Criar representante
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Representantes</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">E-mail</th>
              <th className="p-2 text-left">Chave Pix</th>
              <th className="p-2 text-left">Comissão</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Ações</th>
            </tr>
          </thead>
          <tbody>
            {representantes.map((representante) => (
              <tr key={representante.id} className="border-b border-border">
                <td className="p-2 font-semibold">{representante.nome}</td>
                <td className="p-2 text-muted">{representante.email}</td>
                <td className="p-2 text-muted">{representante.chave_pix}</td>
                <td className="p-2 text-cyan">{(representante.percentual_comissao * 100).toFixed(2)}%</td>
                <td className="p-2">
                  <Badge tone={representante.ativo ? "green" : "muted"}>
                    {representante.ativo ? "ativo" : "inativo"}
                  </Badge>
                </td>
                <td className="p-2">
                  <Button size="sm" onClick={() => abrirEdicao(representante)}>
                    Editar
                  </Button>
                </td>
              </tr>
            ))}
            {representantes.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-center text-muted">
                  Nenhum representante cadastrado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        title={representanteEmEdicao ? `Editar representante — ${representanteEmEdicao.nome}` : "Criar representante"}
        open={modalAberto}
        onClose={() => setModalAberto(false)}
      >
        <FormularioRepresentante
          key={representanteEmEdicao?.id ?? "novo"}
          representante={representanteEmEdicao}
          onSalvar={salvar}
          salvando={salvando}
        />
      </Modal>
    </div>
  );
}
