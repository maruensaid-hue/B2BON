import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** API de produto, webhooks de saída e Integration Hub (Fase 3 do
 * Master Prompt v4). Diferente de `Integracoes.tsx` (API de
 * provisionamento do Distribuidor): aqui o tenant integra o MAP e o
 * PREDATOR com os sistemas dele. */

interface ChaveApi {
  id: number;
  nome: string;
  prefixo: string;
  escopos: string[];
  criado_em: string | null;
  ultimo_uso_em: string | null;
  revogada_em: string | null;
}

interface WebhookSaida {
  id: number;
  url: string;
  eventos: string[];
  ativa: boolean;
}

interface Conector {
  sistema: string;
  nome: string;
  status: "AVAILABLE" | "BETA" | "COMING_SOON";
  descricao: string;
}

const ROTULO_STATUS: Record<Conector["status"], string> = {
  AVAILABLE: "Disponível",
  BETA: "Beta",
  COMING_SOON: "Em breve",
};

function data(valor: string | null) {
  return valor ? new Date(valor).toLocaleDateString("pt-BR") : "—";
}

export function ApiPlataforma() {
  const { usuario } = useAuth();
  const [chaves, setChaves] = useState<ChaveApi[]>([]);
  const [escopos, setEscopos] = useState<string[]>([]);
  const [escoposEscolhidos, setEscoposEscolhidos] = useState<string[]>([]);
  const [webhooks, setWebhooks] = useState<WebhookSaida[]>([]);
  const [eventos, setEventos] = useState<string[]>([]);
  const [eventosEscolhidos, setEventosEscolhidos] = useState<string[]>([]);
  const [conectores, setConectores] = useState<Conector[]>([]);
  const [segredo, setSegredo] = useState<{ titulo: string; valor: string } | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const podeGerenciar = usuario?.papel === "admin" || usuario?.papel === "super_admin";

  async function carregar() {
    try {
      const [chavesResp, escoposResp, webhooksResp, eventosResp, conectoresResp] = await Promise.all([
        api.get<ChaveApi[]>("/chaves-api"),
        api.get<string[]>("/chaves-api/escopos"),
        api.get<WebhookSaida[]>("/webhooks-saida"),
        api.get<string[]>("/webhooks-saida/eventos"),
        api.get<Conector[]>("/hub-integracoes/conectores"),
      ]);
      setChaves(chavesResp);
      setEscopos(escoposResp);
      setWebhooks(webhooksResp);
      setEventos(eventosResp);
      setConectores(conectoresResp);
    } catch {
      setErro("Não foi possível carregar as configurações de API.");
    }
  }

  useEffect(() => {
    if (podeGerenciar) carregar();
  }, [podeGerenciar]);

  function alternar(lista: string[], item: string, definir: (valor: string[]) => void) {
    definir(lista.includes(item) ? lista.filter((x) => x !== item) : [...lista, item]);
  }

  async function criarChave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const resposta = await api.post<{ segredo: string }>("/chaves-api", {
        nome: String(form.get("nome")),
        escopos: escoposEscolhidos,
      });
      setSegredo({ titulo: "Copie a chave de API agora — ela não aparece de novo:", valor: resposta.segredo });
      setEscoposEscolhidos([]);
      event.currentTarget.reset();
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar a chave.");
    }
  }

  async function revogar(id: number) {
    try {
      await api.delete(`/chaves-api/${id}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível revogar a chave.");
    }
  }

  async function criarWebhook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const resposta = await api.post<{ segredo: string }>("/webhooks-saida", {
        url: String(form.get("url")),
        eventos: eventosEscolhidos,
      });
      setSegredo({
        titulo: "Copie o segredo de assinatura agora (verifica o header X-B2BON-Signature) — ele não aparece de novo:",
        valor: resposta.segredo,
      });
      setEventosEscolhidos([]);
      event.currentTarget.reset();
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o webhook.");
    }
  }

  async function desativarWebhook(id: number) {
    try {
      await api.delete(`/webhooks-saida/${id}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível desativar o webhook.");
    }
  }

  if (!podeGerenciar) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">API &amp; Webhooks</div>
        <div className="mt-0.5 text-[11px] text-muted">
          Integre o MAP e o PREDATOR com seus sistemas: chaves de API, eventos em tempo real e conectores de CRM.
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      {segredo && (
        <div className="mb-4 rounded-lg border border-amber bg-amber/10 p-3 text-[12px]">
          <div className="mb-1 font-bold text-amber">{segredo.titulo}</div>
          <code className="block break-all rounded bg-black/30 p-2 text-[11px]">{segredo.valor}</code>
          <Button size="sm" className="mt-2" onClick={() => setSegredo(null)}>
            Já copiei
          </Button>
        </div>
      )}

      <Card className="mb-4">
        <SectionLabel>Chaves de API</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Envie no header <code>X-API-Key</code>. Endpoints em <code>/api/v1/map/*</code> e{" "}
          <code>/api/v1/predator/*</code> — cada chave só acessa os escopos marcados e os módulos do seu plano.
        </div>
        <table className="mb-3 w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">Prefixo</th>
              <th className="p-2 text-left">Escopos</th>
              <th className="p-2 text-left">Último uso</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2" />
            </tr>
          </thead>
          <tbody>
            {chaves.map((chave) => (
              <tr key={chave.id} className="border-b border-border">
                <td className="p-2 font-semibold">{chave.nome}</td>
                <td className="p-2 text-muted">{chave.prefixo}…</td>
                <td className="p-2 text-muted">{chave.escopos.join(", ")}</td>
                <td className="p-2 text-muted">{chave.ultimo_uso_em ? data(chave.ultimo_uso_em) : "nunca"}</td>
                <td className="p-2">
                  {chave.revogada_em ? <span className="text-red">Revogada</span> : <span className="text-green">Ativa</span>}
                </td>
                <td className="p-2 text-right">
                  {!chave.revogada_em && (
                    <Button size="sm" variant="ghost" onClick={() => revogar(chave.id)}>
                      Revogar
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {chaves.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-center text-muted">
                  Nenhuma chave criada.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <form onSubmit={criarChave} className="flex flex-col gap-2">
          <Input name="nome" required placeholder="Nome da chave (ex.: Integração HubSpot)" />
          <div className="flex flex-wrap gap-3 text-[12px]">
            {escopos.map((escopo) => (
              <label key={escopo} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={escoposEscolhidos.includes(escopo)}
                  onChange={() => alternar(escoposEscolhidos, escopo, setEscoposEscolhidos)}
                />
                {escopo}
              </label>
            ))}
          </div>
          <Button type="submit" disabled={escoposEscolhidos.length === 0} className="self-start">
            Criar chave
          </Button>
        </form>
      </Card>

      <Card className="mb-4">
        <SectionLabel>Webhooks de eventos</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Enviamos um POST assinado (HMAC-SHA256) para sua URL quando os eventos escolhidos acontecem.
        </div>
        {webhooks.map((webhook) => (
          <div key={webhook.id} className="mb-2 flex items-center justify-between border-b border-border pb-2 text-[12px]">
            <div>
              <div className="font-semibold">{webhook.url}</div>
              <div className="text-muted">{webhook.eventos.join(", ")}</div>
            </div>
            {webhook.ativa ? (
              <Button size="sm" variant="ghost" onClick={() => desativarWebhook(webhook.id)}>
                Desativar
              </Button>
            ) : (
              <span className="text-red">Inativo</span>
            )}
          </div>
        ))}
        <form onSubmit={criarWebhook} className="mt-2 flex flex-col gap-2">
          <Input name="url" type="url" required placeholder="https://seu-sistema.com.br/webhooks/b2bon" />
          <div className="flex flex-wrap gap-3 text-[12px]">
            {eventos.map((evento) => (
              <label key={evento} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={eventosEscolhidos.includes(evento)}
                  onChange={() => alternar(eventosEscolhidos, evento, setEventosEscolhidos)}
                />
                {evento}
              </label>
            ))}
          </div>
          <Button type="submit" disabled={eventosEscolhidos.length === 0} className="self-start">
            Criar webhook
          </Button>
        </form>
      </Card>

      <Card>
        <SectionLabel>Conectores de CRM</SectionLabel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {conectores.map((conector) => (
            <div key={conector.sistema} className="rounded-lg border border-border p-3 text-[12px]">
              <div className="flex items-center justify-between">
                <span className="font-semibold">{conector.nome}</span>
                <span className={conector.status === "COMING_SOON" ? "text-muted" : "text-green"}>
                  {ROTULO_STATUS[conector.status]}
                </span>
              </div>
              <div className="mt-1 text-muted">{conector.descricao}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
