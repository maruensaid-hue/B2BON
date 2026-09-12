import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Plano {
  id: number;
  nome: string;
  franquia_contas_mes: number;
  max_usuarios: number;
  preco_mensal: number;
  visivel_self_service: boolean;
  limite_enriquecimento_site_semanal: number | null;
  limite_enriquecimento_contatos_semanal: number | null;
  permite_ab_teste_cadencia: boolean;
  permite_auto_aprovacao: boolean;
  permite_webhook_relatorio: boolean;
  permite_api_parceiros: boolean;
  permite_subtenants: boolean;
  permite_registro_oportunidade: boolean;
  retencao_dias_relatorio: number | null;
  retencao_dias_auditoria: number | null;
}

const RECURSOS_PLANO: { campo: keyof Plano; rotulo: string }[] = [
  { campo: "permite_ab_teste_cadencia", rotulo: "Teste A/B de cadência" },
  { campo: "permite_auto_aprovacao", rotulo: "Auto-aprovação de mensagens" },
  { campo: "permite_webhook_relatorio", rotulo: "Webhook de relatório" },
  { campo: "permite_api_parceiros", rotulo: "API de parceiros" },
  { campo: "permite_subtenants", rotulo: "Criar sub-tenants (revenda)" },
  { campo: "permite_registro_oportunidade", rotulo: "Registro de Oportunidade (RO)" },
];

function campoNumeroOuVazio(valor: FormDataEntryValue | null): number | null {
  const texto = String(valor ?? "").trim();
  return texto ? Number(texto) : null;
}

function FormularioPlano({
  plano,
  onSalvar,
  salvando,
}: {
  plano: Plano | null;
  onSalvar: (event: FormEvent<HTMLFormElement>) => void;
  salvando: boolean;
}) {
  return (
    <form onSubmit={onSalvar} className="flex flex-col gap-3">
      <div>
        <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
        <Input name="nome" required defaultValue={plano?.nome} placeholder="Ex.: Professional" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Franquia (contas/mês)</div>
          <Input name="franquia_contas_mes" type="number" min={0} required defaultValue={plano?.franquia_contas_mes} />
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Máx. usuários</div>
          <Input name="max_usuarios" type="number" min={0} required defaultValue={plano?.max_usuarios} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Preço mensal (R$)</div>
          <Input name="preco_mensal" type="number" min={0} step="0.01" required defaultValue={plano?.preco_mensal} />
        </div>
        <label className="flex items-center gap-1.5 self-end pb-2 text-[12px] text-muted">
          <input type="checkbox" name="visivel_self_service" defaultChecked={plano?.visivel_self_service ?? true} />
          Visível no cadastro self-service
        </label>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
            Enriq. site/semana (vazio = sem limite)
          </div>
          <Input name="limite_enriquecimento_site_semanal" type="number" min={0} defaultValue={plano?.limite_enriquecimento_site_semanal ?? ""} />
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
            Enriq. contatos/semana (vazio = sem limite)
          </div>
          <Input
            name="limite_enriquecimento_contatos_semanal"
            type="number"
            min={0}
            defaultValue={plano?.limite_enriquecimento_contatos_semanal ?? ""}
          />
        </div>
      </div>

      <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
        Recursos exclusivos (gancho de upgrade além de volume)
      </div>
      <div className="grid grid-cols-2 gap-2">
        {RECURSOS_PLANO.map(({ campo, rotulo }) => (
          <label key={campo} className="flex items-center gap-1.5 text-[12px] text-muted">
            <input type="checkbox" name={campo} defaultChecked={Boolean(plano?.[campo])} />
            {rotulo}
          </label>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
            Retenção de relatórios em dias (vazio = sem limite)
          </div>
          <Input name="retencao_dias_relatorio" type="number" min={0} defaultValue={plano?.retencao_dias_relatorio ?? ""} />
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
            Retenção de auditoria em dias (vazio = sem limite)
          </div>
          <Input name="retencao_dias_auditoria" type="number" min={0} defaultValue={plano?.retencao_dias_auditoria ?? ""} />
        </div>
      </div>

      <Button type="submit" disabled={salvando} className="mt-1 w-full justify-center">
        {salvando ? "Salvando..." : plano ? "Salvar alterações" : "Criar plano"}
      </Button>
    </form>
  );
}

export function AdminPlanos() {
  const { usuario } = useAuth();
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [planoEmEdicao, setPlanoEmEdicao] = useState<Plano | null>(null);
  const [salvando, setSalvando] = useState(false);

  const isSuperAdmin = usuario?.papel === "super_admin";

  async function carregar() {
    try {
      setPlanos(await api.get<Plano[]>("/planos"));
    } catch {
      setErro("Não foi possível carregar os planos.");
    }
  }

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin]);

  function abrirCriacao() {
    setPlanoEmEdicao(null);
    setModalAberto(true);
  }

  function abrirEdicao(plano: Plano) {
    setPlanoEmEdicao(plano);
    setModalAberto(true);
  }

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    const dados = {
      nome: String(form.get("nome")),
      franquia_contas_mes: Number(form.get("franquia_contas_mes")),
      max_usuarios: Number(form.get("max_usuarios")),
      preco_mensal: Number(form.get("preco_mensal")),
      visivel_self_service: form.get("visivel_self_service") === "on",
      limite_enriquecimento_site_semanal: campoNumeroOuVazio(form.get("limite_enriquecimento_site_semanal")),
      limite_enriquecimento_contatos_semanal: campoNumeroOuVazio(form.get("limite_enriquecimento_contatos_semanal")),
      permite_ab_teste_cadencia: form.get("permite_ab_teste_cadencia") === "on",
      permite_auto_aprovacao: form.get("permite_auto_aprovacao") === "on",
      permite_webhook_relatorio: form.get("permite_webhook_relatorio") === "on",
      permite_api_parceiros: form.get("permite_api_parceiros") === "on",
      permite_subtenants: form.get("permite_subtenants") === "on",
      permite_registro_oportunidade: form.get("permite_registro_oportunidade") === "on",
      retencao_dias_relatorio: campoNumeroOuVazio(form.get("retencao_dias_relatorio")),
      retencao_dias_auditoria: campoNumeroOuVazio(form.get("retencao_dias_auditoria")),
    };
    setSalvando(true);
    setErro(null);
    try {
      if (planoEmEdicao) {
        await api.put(`/planos/${planoEmEdicao.id}`, dados);
      } else {
        await api.post("/planos", dados);
      }
      setModalAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o plano.");
    } finally {
      setSalvando(false);
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Admin — Planos</div>
          <div className="mt-0.5 text-[11px] text-muted">Planos comerciais e recursos exclusivos por plano</div>
        </div>
        <Button size="sm" variant="violet" onClick={abrirCriacao}>
          + Criar plano
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Planos</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">Franquia</th>
              <th className="p-2 text-left">Usuários</th>
              <th className="p-2 text-left">Preço</th>
              <th className="p-2 text-left">Recursos exclusivos</th>
              <th className="p-2 text-left">Ações</th>
            </tr>
          </thead>
          <tbody>
            {planos.map((plano) => (
              <tr key={plano.id} className="border-b border-border">
                <td className="p-2 font-semibold">{plano.nome}</td>
                <td className="p-2 text-muted">{plano.franquia_contas_mes}</td>
                <td className="p-2 text-muted">{plano.max_usuarios}</td>
                <td className="p-2 text-cyan">R${plano.preco_mensal.toFixed(2)}</td>
                <td className="p-2">
                  <div className="flex flex-wrap gap-1">
                    {RECURSOS_PLANO.filter(({ campo }) => plano[campo]).map(({ campo, rotulo }) => (
                      <Badge key={campo} tone="violet">
                        {rotulo}
                      </Badge>
                    ))}
                    {RECURSOS_PLANO.every(({ campo }) => !plano[campo]) && (
                      <span className="text-muted">nenhum</span>
                    )}
                  </div>
                </td>
                <td className="p-2">
                  <Button size="sm" variant="ghost" onClick={() => abrirEdicao(plano)}>
                    Editar
                  </Button>
                </td>
              </tr>
            ))}
            {planos.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-center text-muted">
                  Nenhum plano cadastrado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal title={planoEmEdicao ? `Editar plano — ${planoEmEdicao.nome}` : "Criar plano"} open={modalAberto} onClose={() => setModalAberto(false)}>
        <FormularioPlano key={planoEmEdicao?.id ?? "novo"} plano={planoEmEdicao} onSalvar={salvar} salvando={salvando} />
      </Modal>
    </div>
  );
}
