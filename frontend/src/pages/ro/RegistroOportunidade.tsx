import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";

interface RegistroOportunidadeItem {
  id: number;
  tenant_id: string;
  vendedor_usuario_id: number;
  cnpj: string;
  nome_empresa: string;
  conta_id: number | null;
  status: string;
  criado_em: string;
  expira_em: string;
}

const TOM_STATUS: Record<string, "green" | "amber" | "red" | "muted" | "cyan"> = {
  ativo: "green",
  ganho: "cyan",
  perdido: "red",
  cancelado: "muted",
  expirado: "amber",
};

function formatarCnpj(cnpj: string): string {
  if (cnpj.length !== 14) return cnpj;
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`;
}

/** RO (Registro de Oportunidade) — deal registration: garante que o
 * primeiro revendedor a registrar uma empresa (por CNPJ) fica PRIME
 * dela dentro da própria rede de tenants; um segundo registro pro mesmo
 * CNPJ é bloqueado pela API (409) enquanto o primeiro estiver ativo. */
export function RegistroOportunidade() {
  const [registros, setRegistros] = useState<RegistroOportunidadeItem[]>([]);
  const [modalAberto, setModalAberto] = useState(false);
  const [modalDescontoId, setModalDescontoId] = useState<number | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function carregar() {
    try {
      setRegistros(await api.get<RegistroOportunidadeItem[]>("/registro-oportunidade"));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar os registros.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function registrarOportunidade(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    setSalvando(true);
    setErro(null);
    try {
      await api.post("/registro-oportunidade", {
        cnpj: String(form.get("cnpj")),
        nome_empresa: String(form.get("nome_empresa")),
      });
      setModalAberto(false);
      setMensagem("Oportunidade registrada — você é PRIME desta conta.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível registrar a oportunidade.");
    } finally {
      setSalvando(false);
    }
  }

  async function solicitarDesconto(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando || modalDescontoId === null) return;
    const form = new FormData(event.currentTarget);
    setSalvando(true);
    setErro(null);
    try {
      await api.post(`/registro-oportunidade/${modalDescontoId}/solicitar-desconto`, {
        percentual_solicitado: Number(form.get("percentual_solicitado")),
        justificativa: String(form.get("justificativa") || "") || null,
      });
      setModalDescontoId(null);
      setMensagem("Solicitação de desconto enviada para aprovação.");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível solicitar o desconto.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">RO — Registro de Oportunidade</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Registre uma empresa que você prospectou e fique PRIME dela na sua rede — nenhum outro revendedor
            consegue registrar a mesma empresa enquanto o seu registro estiver ativo.
          </div>
        </div>
        <Button size="sm" onClick={() => setModalAberto(true)}>
          + Registrar oportunidade
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card>
        <SectionLabel>Minhas oportunidades</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Empresa</th>
              <th className="p-2 text-left">CNPJ</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Registrado em</th>
              <th className="p-2 text-left">Válido até</th>
              <th className="p-2 text-left">Conta vinculada</th>
              <th className="p-2 text-left"></th>
            </tr>
          </thead>
          <tbody>
            {registros.map((registro) => (
              <tr key={registro.id} className="border-b border-border">
                <td className="p-2 font-semibold">{registro.nome_empresa}</td>
                <td className="p-2 text-muted">{formatarCnpj(registro.cnpj)}</td>
                <td className="p-2">
                  <Badge tone={TOM_STATUS[registro.status] ?? "muted"}>{registro.status}</Badge>
                </td>
                <td className="p-2 text-muted">{new Date(registro.criado_em).toLocaleDateString("pt-BR")}</td>
                <td className="p-2 text-muted">{new Date(registro.expira_em).toLocaleDateString("pt-BR")}</td>
                <td className="p-2 text-muted">{registro.conta_id ?? "—"}</td>
                <td className="p-2 text-right">
                  {registro.status === "ativo" && (
                    <Button size="sm" variant="ghost" onClick={() => setModalDescontoId(registro.id)}>
                      Solicitar desconto
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {registros.length === 0 && (
              <tr>
                <td colSpan={7} className="p-4 text-center text-muted">
                  Nenhuma oportunidade registrada ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal title="Registrar oportunidade" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={registrarOportunidade} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome da empresa</div>
            <Input name="nome_empresa" required placeholder="Nome da empresa" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNPJ</div>
            <Input name="cnpj" required placeholder="00.000.000/0000-00" />
          </div>
          <Button type="submit" disabled={salvando} className="mt-1 w-full justify-center">
            {salvando ? "Registrando..." : "Registrar oportunidade"}
          </Button>
        </form>
      </Modal>

      <Modal title="Solicitar desconto" open={modalDescontoId !== null} onClose={() => setModalDescontoId(null)}>
        <form onSubmit={solicitarDesconto} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Percentual solicitado</div>
            <Input name="percentual_solicitado" type="number" step="0.1" min="0" max="100" required />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Justificativa (opcional)</div>
            <Input name="justificativa" placeholder="Ex.: negociação avançada, concorrência no preço" />
          </div>
          <Button type="submit" disabled={salvando} className="mt-1 w-full justify-center">
            {salvando ? "Enviando..." : "Enviar solicitação"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
