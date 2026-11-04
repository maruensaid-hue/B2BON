import { useEffect, useRef, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

export interface ConfiguracaoWhatsApp {
  id: number;
  phone_number_id: string;
  business_account_id: string;
  access_token_mascarado: string;
  origem_conexao: string | null;
  numero_exibicao: string | null;
  nome_verificado: string | null;
  qualidade: string | null;
  token_expira_em: string | null;
  direct_send_habilitado: boolean;
  direct_send_motivo_desligado: string | null;
}

interface ParametrosMeta {
  disponivel: boolean;
  app_id: string | null;
  config_id: string | null;
  graph_versao: string;
}

interface ResultadoConexao {
  numero_exibicao: string | null;
  nome_verificado: string | null;
  qualidade: string | null;
  token_expira_em?: string | null;
  avisos?: string[];
  erro?: string | null;
}

const DIAS_PARA_AVISAR = 15;

/** Dias até o token vencer (negativo = vencido). A API devolve a data em UTC sem fuso. */
function diasAteVencer(expiraEm: string | null | undefined): number | null {
  if (!expiraEm) return null;
  const vence = new Date(expiraEm.endsWith("Z") ? expiraEm : `${expiraEm}Z`).getTime();
  return Math.floor((vence - Date.now()) / 86_400_000);
}

interface FacebookSdk {
  init: (opcoes: Record<string, unknown>) => void;
  login: (callback: (resposta: { authResponse?: { code?: string } }) => void, opcoes: Record<string, unknown>) => void;
}

declare global {
  interface Window {
    FB?: FacebookSdk;
    fbAsyncInit?: () => void;
  }
}

const TOM_QUALIDADE: Record<string, "green" | "amber" | "red" | "muted"> = { GREEN: "green", YELLOW: "amber", RED: "red" };
const ROTULO_QUALIDADE: Record<string, string> = { GREEN: "qualidade alta", YELLOW: "qualidade média", RED: "qualidade baixa" };

function carregarSdk(parametros: ParametrosMeta): Promise<FacebookSdk> {
  return new Promise((resolver, rejeitar) => {
    if (window.FB) {
      resolver(window.FB);
      return;
    }
    window.fbAsyncInit = () => {
      window.FB?.init({ appId: parametros.app_id, autoLogAppEvents: true, xfbml: false, version: parametros.graph_versao });
      if (window.FB) resolver(window.FB);
    };
    const script = document.createElement("script");
    script.src = "https://connect.facebook.net/pt_BR/sdk.js";
    script.async = true;
    script.crossOrigin = "anonymous";
    script.onerror = () => rejeitar(new Error("sdk"));
    document.body.appendChild(script);
  });
}

/** Conexão do número de WhatsApp da empresa: botão da Meta (o caminho fácil), teste, envio sem template e, recolhida, a configuração manual. */
export function WhatsAppConexao({
  config,
  erroCarregamento,
  onAtualizado,
}: {
  config: ConfiguracaoWhatsApp | null;
  erroCarregamento: string | null;
  onAtualizado: () => Promise<void> | void;
}) {
  const [parametros, setParametros] = useState<ParametrosMeta | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [teste, setTeste] = useState<ResultadoConexao | null>(null);
  const [manualAberto, setManualAberto] = useState(false);
  const idsDaJanela = useRef<{ phone_number_id?: string; waba_id?: string }>({});

  useEffect(() => {
    api.get<ParametrosMeta>("/configuracao-whatsapp/conectar-meta/parametros").then(setParametros).catch(() => setParametros(null));
    // A janela da Meta avisa por mensagem qual número e conta foram escolhidos (cadastro incorporado).
    function ouvir(evento: MessageEvent) {
      try {
        if (!/(^|\.)facebook\.com$/.test(new URL(evento.origin).hostname)) return;
        const dados = typeof evento.data === "string" ? JSON.parse(evento.data) : evento.data;
        if (dados?.type === "WA_EMBEDDED_SIGNUP" && dados.data) {
          idsDaJanela.current = { phone_number_id: dados.data.phone_number_id, waba_id: dados.data.waba_id };
        }
      } catch {
        // mensagens de outros componentes da Meta não são JSON: ignorar
      }
    }
    window.addEventListener("message", ouvir);
    return () => window.removeEventListener("message", ouvir);
  }, []);

  async function executar(nome: string, acao: () => Promise<void>) {
    setErro(null);
    setAviso(null);
    setOcupado(nome);
    try {
      await acao();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível concluir. Tente de novo.");
    } finally {
      setOcupado(null);
    }
  }

  async function conectarComMeta() {
    if (!parametros?.disponivel) return;
    await executar("conectar", async () => {
      idsDaJanela.current = {};
      const fb = await carregarSdk(parametros);
      const codigo = await new Promise<string | null>((resolver) =>
        fb.login((resposta) => resolver(resposta.authResponse?.code ?? null), {
          config_id: parametros.config_id,
          response_type: "code",
          override_default_response_type: true,
          extras: { setup: {}, sessionInfoVersion: "3" },
        }),
      );
      if (!codigo) {
        setAviso("A janela da Meta foi fechada antes de terminar. Clique em Conectar de novo quando quiser.");
        return;
      }
      // A mensagem da janela com o número escolhido pode chegar logo depois do código: espera um instante. Se não vier, o
      // servidor descobre conta e número pelo próprio token.
      for (let i = 0; i < 10 && !idsDaJanela.current.phone_number_id; i += 1) {
        await new Promise((r) => setTimeout(r, 150));
      }
      const { phone_number_id, waba_id } = idsDaJanela.current;
      const resultado = await api.post<ResultadoConexao>("/configuracao-whatsapp/conectar-meta", {
        codigo,
        phone_number_id: phone_number_id ?? "",
        business_account_id: waba_id ?? "",
      });
      setTeste(resultado);
      if (resultado.avisos?.length) setAviso(resultado.avisos.join(" "));
      await onAtualizado();
    });
  }

  async function testar() {
    await executar("testar", async () => {
      setTeste(await api.post<ResultadoConexao & { ok: boolean }>("/configuracao-whatsapp/testar"));
      await onAtualizado();
    });
  }

  async function alternarDirectSend() {
    if (!config) return;
    await executar("direct-send", async () => {
      await api.put("/configuracao-whatsapp/direct-send", { habilitado: !config.direct_send_habilitado });
      await onAtualizado();
    });
  }

  async function salvarManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await executar("manual", async () => {
      await api.put("/configuracao-whatsapp", {
        phone_number_id: String(form.get("phone_number_id")).trim(),
        business_account_id: String(form.get("business_account_id")).trim(),
        access_token: String(form.get("access_token") ?? "").trim() || null,
      });
      await onAtualizado();
      setTeste(await api.post<ResultadoConexao & { ok: boolean }>("/configuracao-whatsapp/testar"));
    });
  }

  const numero = teste?.numero_exibicao ?? config?.numero_exibicao;
  const nome = teste?.nome_verificado ?? config?.nome_verificado;
  const qualidade = teste?.qualidade ?? config?.qualidade;
  const expiraEm = teste?.token_expira_em ?? config?.token_expira_em ?? null;
  const dias = diasAteVencer(expiraEm);

  return (
    <div className="flex flex-col gap-3">
      <div className="text-[11px] text-muted">
        Cada empresa usa o próprio número de WhatsApp Business. Sem número conectado aqui, nenhuma mensagem de WhatsApp sai.
      </div>

      {config ? (
        <div className="rounded-lg bg-surf2 p-2.5 text-[12px] text-text">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="green">Conectado</Badge>
            <span className="font-medium">{numero ?? "número ainda não lido"}</span>
            {nome && <span className="text-muted">· {nome}</span>}
            {qualidade && <Badge tone={TOM_QUALIDADE[qualidade] ?? "muted"}>{ROTULO_QUALIDADE[qualidade] ?? qualidade}</Badge>}
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {config.origem_conexao === "meta_conectar" ? "Conectado pelo botão da Meta" : "Configurado manualmente"} · token{" "}
            <span className="font-mono">{config.access_token_mascarado}</span>
          </div>
          {expiraEm && dias !== null && (
            <div className={`mt-1 text-[11px] ${dias < 0 ? "text-red" : dias <= DIAS_PARA_AVISAR ? "text-amber" : "text-muted"}`}>
              {dias < 0
                ? "O acesso à Meta venceu: nenhuma mensagem de WhatsApp sai. Clique em Reconectar com a Meta."
                : `Acesso à Meta vence em ${new Date(`${expiraEm}${expiraEm.endsWith("Z") ? "" : "Z"}`).toLocaleDateString("pt-BR")}` +
                  (dias <= DIAS_PARA_AVISAR ? ` (faltam ${dias} dia${dias === 1 ? "" : "s"}): clique em Reconectar com a Meta para renovar.` : ".")}
            </div>
          )}
          {teste?.erro && <div className="mt-1 text-[11px] text-red">A Meta não reconheceu a conexão: {teste.erro}</div>}
        </div>
      ) : (
        <div className="rounded-lg bg-surf2 p-2.5 text-[12px] text-muted">Nenhum número conectado.</div>
      )}
      {erroCarregamento && <div className="text-[12px] text-red">{erroCarregamento}</div>}

      <div className="flex flex-wrap gap-2">
        {parametros?.disponivel && (
          <Button type="button" disabled={ocupado !== null} onClick={conectarComMeta}>
            {ocupado === "conectar" ? "Conectando..." : config ? "Reconectar com a Meta" : "Conectar com a Meta"}
          </Button>
        )}
        {config && (
          <Button type="button" disabled={ocupado !== null} onClick={testar}>
            {ocupado === "testar" ? "Testando..." : "Testar conexão"}
          </Button>
        )}
      </div>
      {parametros?.disponivel && !config && (
        <div className="text-[11px] text-muted/70">
          Abre uma janela da própria Meta: entre com a conta do Facebook da empresa, escolha (ou crie) a conta do WhatsApp Business e o
          número, e confirme. Leva cerca de 2 minutos. O B2B ON não vê sua senha.
        </div>
      )}
      {aviso && <div className="text-[11px] text-amber">{aviso}</div>}
      {erro && <div className="text-[11px] text-red">{erro}</div>}

      {config && (
        <label className="flex items-start gap-2 text-[12px] text-muted">
          <input type="checkbox" className="mt-0.5" checked={config.direct_send_habilitado} disabled={ocupado !== null} onChange={alternarDirectSend} />
          <span>
            Envio sem template (Direct Send da Meta)
            <span className="block text-[11px] text-muted/70">
              Ligue só se o WhatsApp Manager mostrar sua conta como elegível. Serve para mensagens de utilidade (lembrete de reunião,
              resposta a quem falou com você), que passam a sair mesmo fora da janela de 24 h. Texto promocional nunca sai por aqui.
            </span>
            {config.direct_send_motivo_desligado && (
              <span className="block text-[11px] text-amber">Desligado pela Meta: {config.direct_send_motivo_desligado}</span>
            )}
          </span>
        </label>
      )}

      <button type="button" className="self-start text-[11px] text-cyan hover:underline" onClick={() => setManualAberto((v) => !v)}>
        {manualAberto ? "Ocultar configuração manual" : "Prefiro configurar manualmente (IDs e token)"}
      </button>
      {manualAberto && (
        <form key={config?.id ?? "novo"} onSubmit={salvarManual} className="flex flex-col gap-3">
          <div className="text-[11px] text-muted/70">
            No Meta for Developers: app → WhatsApp → Configuração da API. Copie o ID do número de telefone, o ID da conta do WhatsApp
            Business e um token permanente (usuário do sistema). Ao salvar, o B2B ON testa a conexão na hora.
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">ID do número de telefone</div>
            <Input name="phone_number_id" required inputMode="numeric" defaultValue={config?.phone_number_id} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">ID da conta do WhatsApp Business</div>
            <Input name="business_account_id" required inputMode="numeric" defaultValue={config?.business_account_id} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Token de acesso {config && !erroCarregamento ? "(deixe em branco para manter o atual)" : ""}
            </div>
            <Input name="access_token" type="password" required={!config || !!erroCarregamento} placeholder="EAAG..." />
          </div>
          <Button type="submit" disabled={ocupado !== null} className="w-full justify-center">
            {ocupado === "manual" ? "Salvando e testando..." : "Salvar e testar"}
          </Button>
        </form>
      )}
    </div>
  );
}
