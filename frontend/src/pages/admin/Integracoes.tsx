import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface ChaveApi {
  id: number;
  nome: string;
  prefixo: string;
  criado_em: string;
  ultimo_uso_em: string | null;
  revogada_em: string | null;
}

interface Webhook {
  url_callback: string;
  ativa: boolean;
  criado_em: string;
}

export function Integracoes() {
  const { usuario } = useAuth();
  const [chaves, setChaves] = useState<ChaveApi[]>([]);
  const [webhook, setWebhook] = useState<Webhook | null>(null);
  const [modalChaveAberto, setModalChaveAberto] = useState(false);
  const [chaveGerada, setChaveGerada] = useState<string | null>(null);
  const [segredoGerado, setSegredoGerado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const podeGerenciar = usuario?.papel === "admin" && usuario.tenant_tipo === "distribuidor";

  async function carregar() {
    try {
      const chavesResp = await api.get<ChaveApi[]>("/integracoes/chaves-api");
      setChaves(chavesResp);
    } catch {
      setErro("Não foi possível carregar as chaves de API.");
    }
    try {
      setWebhook(await api.get<Webhook>("/integracoes/webhook"));
    } catch {
      setWebhook(null);
    }
  }

  useEffect(() => {
    if (podeGerenciar) carregar();
  }, [podeGerenciar]);

  async function gerarChave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const resposta = await api.post<{ chave: string }>("/integracoes/chaves-api", {
        nome: String(form.get("nome")),
      });
      setChaveGerada(resposta.chave);
      setModalChaveAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar a chave.");
    }
  }

  async function revogarChave(id: number) {
    try {
      await api.delete(`/integracoes/chaves-api/${id}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível revogar a chave.");
    }
  }

  async function salvarWebhook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const resposta = await api.put<{ segredo: string }>("/integracoes/webhook", {
        url_callback: String(form.get("url_callback")),
      });
      setSegredoGerado(resposta.segredo);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o webhook.");
    }
  }

  async function desativarWebhook() {
    try {
      await api.delete("/integracoes/webhook");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível desativar o webhook.");
    }
  }

  if (!podeGerenciar) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Integrações</div>
        <div className="mt-0.5 text-[11px] text-muted">
          API de provisionamento/billing pra chamar o B2B ON de fora do painel
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      {chaveGerada && (
        <div className="mb-4 rounded-lg border border-amber bg-amber/10 p-3 text-[12px]">
          <div className="mb-1 font-bold text-amber">Copie a chave agora — ela não aparece de novo:</div>
          <code className="block break-all rounded bg-black/30 p-2 text-[11px]">{chaveGerada}</code>
          <Button size="sm" className="mt-2" onClick={() => setChaveGerada(null)}>
            Já copiei
          </Button>
        </div>
      )}

      {segredoGerado && (
        <div className="mb-4 rounded-lg border border-amber bg-amber/10 p-3 text-[12px]">
          <div className="mb-1 font-bold text-amber">
            Copie o segredo de assinatura agora — ele não aparece de novo (usado pra verificar `X-B2BON-Signature`):
          </div>
          <code className="block break-all rounded bg-black/30 p-2 text-[11px]">{segredoGerado}</code>
          <Button size="sm" className="mt-2" onClick={() => setSegredoGerado(null)}>
            Já copiei
          </Button>
        </div>
      )}

      <Card className="mb-4">
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>Chaves de API</SectionLabel>
          <Button size="sm" variant="violet" onClick={() => setModalChaveAberto(true)}>
            + Gerar chave
          </Button>
        </div>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">Prefixo</th>
              <th className="p-2 text-left">Criada em</th>
              <th className="p-2 text-left">Último uso</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left"></th>
            </tr>
          </thead>
          <tbody>
            {chaves.map((chave) => (
              <tr key={chave.id} className="border-b border-border">
                <td className="p-2 font-semibold">{chave.nome}</td>
                <td className="p-2 text-muted">{chave.prefixo}…</td>
                <td className="p-2 text-muted">{new Date(chave.criado_em).toLocaleDateString("pt-BR")}</td>
                <td className="p-2 text-muted">
                  {chave.ultimo_uso_em ? new Date(chave.ultimo_uso_em).toLocaleDateString("pt-BR") : "nunca"}
                </td>
                <td className="p-2">
                  {chave.revogada_em ? <span className="text-red">Revogada</span> : <span className="text-green">Ativa</span>}
                </td>
                <td className="p-2 text-right">
                  {!chave.revogada_em && (
                    <Button size="sm" variant="ghost" onClick={() => revogarChave(chave.id)}>
                      Revogar
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {chaves.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-center text-muted">
                  Nenhuma chave gerada ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Card>
        <SectionLabel>Webhook</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Notifica sua URL quando: tenant provisionado, licença suspensa por inadimplência, plano/licença alterados,
          pagamento confirmado.
        </div>
        {webhook && (
          <div className="mb-3 text-[12px]">
            URL atual: <span className="font-semibold">{webhook.url_callback}</span>{" "}
            {webhook.ativa ? <span className="text-green">(ativo)</span> : <span className="text-red">(inativo)</span>}
            {webhook.ativa && (
              <Button size="sm" variant="ghost" className="ml-3" onClick={desativarWebhook}>
                Desativar
              </Button>
            )}
          </div>
        )}
        <form onSubmit={salvarWebhook} className="flex gap-2">
          <Input name="url_callback" type="url" required placeholder="https://seu-sistema.com.br/webhooks/b2bon" />
          <Button type="submit">Salvar</Button>
        </form>
      </Card>

      <Modal title="Gerar chave de API" open={modalChaveAberto} onClose={() => setModalChaveAberto(false)}>
        <form onSubmit={gerarChave} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome (identificação)</div>
            <Input name="nome" required placeholder="ex: Integração ERP" />
          </div>
          <Button type="submit" className="mt-1 w-full justify-center">
            Gerar
          </Button>
        </form>
      </Modal>
    </div>
  );
}
