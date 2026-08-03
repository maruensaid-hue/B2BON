import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { Modal } from "@/components/ui/Modal";
import { ContaDetalheModal } from "@/pages/prospeccao/ContaDetalheModal";
import { api, ApiError } from "@/lib/api";

export interface ICP {
  id: number;
  grupo_id: string;
  nome: string;
  versao: number;
  ativo: boolean;
  segmento: string;
  porte: string;
  regiao: string;
  dores: string[];
  gatilhos: string[];
  cnae_codigos: string[];
  ufs: string[];
}

export interface Conta {
  id: number;
  icp_id: number;
  cnpj: string | null;
  nome: string;
  dominio: string | null;
  score_aderencia: number | null;
  status: string;
  motivo_descarte: string | null;
}

interface Franquia {
  limite: number;
  usado: number;
  restante: number;
}

function paraLista(texto: string): string[] {
  return texto
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function statusTone(status: string): "cyan" | "green" | "muted" {
  if (status === "priorizada") return "green";
  if (status === "descartada") return "muted";
  return "cyan";
}

export function Prospeccao() {
  const [icps, setIcps] = useState<ICP[]>([]);
  const [icpSelecionadoId, setIcpSelecionadoId] = useState<number | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);
  const [franquia, setFranquia] = useState<Franquia | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [modalIcpAberto, setModalIcpAberto] = useState(false);
  const [icpEmEdicao, setIcpEmEdicao] = useState<ICP | null>(null);
  const [modalGerarAberto, setModalGerarAberto] = useState(false);
  const [contaSelecionadaId, setContaSelecionadaId] = useState<number | null>(null);

  const icpSelecionado = icps.find((icp) => icp.id === icpSelecionadoId) ?? null;

  async function carregarIcps() {
    try {
      const resposta = await api.get<ICP[]>("/icp");
      setIcps(resposta);
      if (resposta.length > 0 && icpSelecionadoId === null) {
        setIcpSelecionadoId(resposta.find((icp) => icp.ativo)?.id ?? resposta[0].id);
      }
    } catch {
      setErro("Não foi possível carregar os ICPs.");
    }
  }

  async function carregarContas(icpId: number) {
    try {
      setContas(await api.get<Conta[]>(`/icp/${icpId}/contas`));
    } catch {
      setErro("Não foi possível carregar as contas do ICP.");
    }
  }

  async function carregarFranquia() {
    try {
      setFranquia(await api.get<Franquia>("/contas/franquia"));
    } catch {
      // franquia é informativa — falha aqui não bloqueia o resto da tela
    }
  }

  useEffect(() => {
    carregarIcps();
    carregarFranquia();
  }, []);

  useEffect(() => {
    if (icpSelecionadoId !== null) carregarContas(icpSelecionadoId);
  }, [icpSelecionadoId]);

  async function salvarIcp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      nome: String(form.get("nome")),
      segmento: String(form.get("segmento")),
      porte: String(form.get("porte")),
      regiao: String(form.get("regiao")),
      dores: paraLista(String(form.get("dores") ?? "")),
      gatilhos: paraLista(String(form.get("gatilhos") ?? "")),
      cnae_codigos: paraLista(String(form.get("cnae_codigos") ?? "")),
      ufs: paraLista(String(form.get("ufs") ?? "")),
    };

    try {
      const salvo = icpEmEdicao
        ? await api.put<ICP>(`/icp/${icpEmEdicao.id}`, body)
        : await api.post<ICP>("/icp", body);
      setModalIcpAberto(false);
      setIcpEmEdicao(null);
      await carregarIcps();
      setIcpSelecionadoId(salvo.id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o ICP.");
    }
  }

  async function clonarIcp(icp: ICP) {
    try {
      const clonado = await api.post<ICP>(`/icp/${icp.id}/clonar`);
      await carregarIcps();
      setIcpSelecionadoId(clonado.id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível clonar o ICP.");
    }
  }

  async function gerarLista(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (icpSelecionadoId === null) return;
    const form = new FormData(event.currentTarget);
    try {
      await api.post(`/icp/${icpSelecionadoId}/contas/gerar`, { quantidade: Number(form.get("quantidade")) });
      setModalGerarAberto(false);
      await carregarContas(icpSelecionadoId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar a lista de contas.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Prospecção</div>
          <div className="mt-0.5 text-[11px] text-muted">ICPs e contas geradas pelo PREDATOR</div>
        </div>
        <Button
          size="sm"
          variant="violet"
          onClick={() => {
            setIcpEmEdicao(null);
            setModalIcpAberto(true);
          }}
        >
          + Criar ICP
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="mb-4 grid grid-cols-3 gap-2.5">
        <KpiCard label="Franquia — limite" value={franquia?.limite ?? "—"} colorClassName="text-cyan" />
        <KpiCard label="Usado no mês" value={franquia?.usado ?? "—"} colorClassName="text-amber" />
        <KpiCard label="Restante" value={franquia?.restante ?? "—"} colorClassName="text-green" />
      </div>

      <Card className="mb-4">
        <SectionLabel>ICPs</SectionLabel>
        <div className="flex flex-wrap gap-2">
          {icps.map((icp) => (
            <button
              key={icp.id}
              onClick={() => setIcpSelecionadoId(icp.id)}
              className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                icp.id === icpSelecionadoId
                  ? "border-cyan bg-cyan/15 text-cyan"
                  : "border-border text-muted hover:text-text"
              }`}
            >
              {icp.nome} <span className="opacity-60">v{icp.versao}</span>
              {!icp.ativo && <span className="ml-1 opacity-50">(inativo)</span>}
            </button>
          ))}
          {icps.length === 0 && <div className="text-[12px] text-muted">Nenhum ICP cadastrado ainda.</div>}
        </div>

        {icpSelecionado && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <div className="text-[11px] text-muted">
              {icpSelecionado.segmento} · {icpSelecionado.porte} · {icpSelecionado.regiao} · CNAEs:{" "}
              {icpSelecionado.cnae_codigos.join(", ") || "—"} · UFs: {icpSelecionado.ufs.join(", ") || "—"}
            </div>
            <div className="ml-auto flex gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setIcpEmEdicao(icpSelecionado);
                  setModalIcpAberto(true);
                }}
              >
                Nova versão
              </Button>
              <Button size="sm" variant="ghost" onClick={() => clonarIcp(icpSelecionado)}>
                Clonar
              </Button>
              <Button size="sm" onClick={() => setModalGerarAberto(true)}>
                Gerar lista
              </Button>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <SectionLabel>Contas {icpSelecionado ? `— ${icpSelecionado.nome}` : ""}</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">CNPJ</th>
              <th className="p-2 text-left">Score</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Ações</th>
            </tr>
          </thead>
          <tbody>
            {contas.map((conta) => (
              <tr key={conta.id} className="border-b border-border">
                <td className="p-2 font-semibold">{conta.nome}</td>
                <td className="p-2 text-muted">{conta.cnpj ?? "—"}</td>
                <td className="p-2 text-cyan">{conta.score_aderencia ?? "—"}</td>
                <td className="p-2">
                  <Badge tone={statusTone(conta.status)}>{conta.status}</Badge>
                </td>
                <td className="p-2">
                  <Button size="sm" variant="ghost" onClick={() => setContaSelecionadaId(conta.id)}>
                    Ver detalhes
                  </Button>
                </td>
              </tr>
            ))}
            {contas.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-muted">
                  Nenhuma conta gerada para este ICP ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        title={icpEmEdicao ? `Nova versão — ${icpEmEdicao.nome}` : "Criar ICP"}
        open={modalIcpAberto}
        onClose={() => setModalIcpAberto(false)}
      >
        <form onSubmit={salvarIcp} className="flex flex-col gap-3">
          {(
            [
              ["nome", "Nome"],
              ["segmento", "Segmento"],
              ["porte", "Porte"],
              ["regiao", "Região"],
            ] as const
          ).map(([campo, rotulo]) => (
            <div key={campo}>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{rotulo}</div>
              <Input name={campo} required defaultValue={icpEmEdicao?.[campo as keyof ICP] as string} />
            </div>
          ))}
          {(
            [
              ["cnae_codigos", "CNAEs (separados por vírgula)"],
              ["ufs", "UFs (separadas por vírgula)"],
              ["dores", "Dores (separadas por vírgula)"],
              ["gatilhos", "Gatilhos (separados por vírgula)"],
            ] as const
          ).map(([campo, rotulo]) => (
            <div key={campo}>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{rotulo}</div>
              <Input name={campo} defaultValue={(icpEmEdicao?.[campo as keyof ICP] as string[])?.join(", ")} />
            </div>
          ))}
          <Button type="submit" className="mt-1 w-full justify-center">
            Salvar
          </Button>
        </form>
      </Modal>

      <Modal title="Gerar lista de contas" open={modalGerarAberto} onClose={() => setModalGerarAberto(false)}>
        <form onSubmit={gerarLista} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Quantidade</div>
            <Input name="quantidade" type="number" required defaultValue={10} min={1} />
          </div>
          <Button type="submit" className="w-full justify-center">
            Gerar
          </Button>
        </form>
      </Modal>

      {contaSelecionadaId !== null && (
        <ContaDetalheModal
          contaId={contaSelecionadaId}
          onClose={() => setContaSelecionadaId(null)}
          onAtualizado={() => icpSelecionadoId !== null && carregarContas(icpSelecionadoId)}
        />
      )}
    </div>
  );
}
