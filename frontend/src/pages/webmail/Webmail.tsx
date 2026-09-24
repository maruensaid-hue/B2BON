import { useEffect, useRef, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface ResultadoBuscaDecisor {
  tipo: string;
  id: number | string;
  titulo: string;
  subtitulo: string | null;
}

interface EmailEnviado {
  id: number;
  decisor_id: number;
  decisor_nome: string;
  decisor_email: string | null;
  conta_id: number;
  conta_nome: string;
  remetente_nome: string;
  assunto: string;
  corpo: string;
  status: string;
  motivo_falha: string | null;
  enviado_em: string | null;
  criado_em: string;
}

interface ConfiguracaoAgente {
  email_nome_exibicao: string | null;
  email_assinatura: string | null;
}

type Aba = "escrever" | "enviados" | "configuracoes";

/** Webmail / agente de e-mail direto (raio-X 2026-09-24) — comunicação
 * direta com leads do CRM, síncrona (sem fila de aprovação, diferente
 * das mensagens de cadência), com histórico registrado por conta.
 * Reaproveita o MESMO provider (SendGrid/SMTP) já configurado pro
 * tenant — nunca uma conta pessoal de Gmail/Outlook via OAuth, que não
 * existe no projeto. */
export function Webmail() {
  const [aba, setAba] = useState<Aba>("escrever");

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Webmail</div>
        <div className="mt-0.5 text-[11px] text-muted">E-mail direto com seus leads</div>
      </div>

      <div className="mb-4 flex gap-2">
        <Button size="sm" variant={aba === "escrever" ? "primary" : "ghost"} onClick={() => setAba("escrever")}>
          ✎ Escrever
        </Button>
        <Button size="sm" variant={aba === "enviados" ? "primary" : "ghost"} onClick={() => setAba("enviados")}>
          📤 Enviados
        </Button>
        <Button size="sm" variant={aba === "configuracoes" ? "primary" : "ghost"} onClick={() => setAba("configuracoes")}>
          ⚙️ Configurações
        </Button>
      </div>

      {aba === "escrever" && <AbaEscrever aoEnviar={() => setAba("enviados")} />}
      {aba === "enviados" && <AbaEnviados />}
      {aba === "configuracoes" && <AbaConfiguracoes />}
    </div>
  );
}

function AbaEscrever({ aoEnviar }: { aoEnviar: () => void }) {
  const [busca, setBusca] = useState("");
  const [sugestoes, setSugestoes] = useState<ResultadoBuscaDecisor[]>([]);
  const [destinatario, setDestinatario] = useState<ResultadoBuscaDecisor | null>(null);
  const [assunto, setAssunto] = useState("");
  const [corpo, setCorpo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const controladorRef = useRef<AbortController | null>(null);

  useEffect(() => {
    controladorRef.current?.abort();
    const termo = busca.trim();
    if (!termo || destinatario) {
      setSugestoes([]);
      return;
    }
    const controlador = new AbortController();
    controladorRef.current = controlador;
    const temporizador = setTimeout(async () => {
      try {
        const dados = await api.get<ResultadoBuscaDecisor[]>(`/busca?q=${encodeURIComponent(termo)}`, {
          signal: controlador.signal,
        });
        setSugestoes(dados.filter((item) => item.tipo === "decisor"));
      } catch {
        // busca é só conveniência — falha silenciosa, usuário pode tentar de novo
      }
    }, 250);
    return () => clearTimeout(temporizador);
  }, [busca, destinatario]);

  async function enviar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!destinatario || enviando) return;
    setEnviando(true);
    setErro(null);
    setMensagem(null);
    try {
      await api.post("/email-direto", { decisor_id: destinatario.id, assunto, corpo });
      setMensagem("E-mail enviado.");
      setDestinatario(null);
      setBusca("");
      setAssunto("");
      setCorpo("");
      aoEnviar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar o e-mail.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Card>
      {erro && <div className="mb-3 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-3 text-[12px] text-green">{mensagem}</div>}
      <form onSubmit={enviar} className="flex flex-col gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Para</div>
          {destinatario ? (
            <div className="flex items-center justify-between rounded-md border border-border bg-surf2 p-2 text-[12px]">
              <span>
                {destinatario.titulo}
                {destinatario.subtitulo && <span className="text-muted"> — {destinatario.subtitulo}</span>}
              </span>
              <button type="button" className="text-[11px] text-muted hover:text-red" onClick={() => setDestinatario(null)}>
                Trocar
              </button>
            </div>
          ) : (
            <div className="relative">
              <Input
                value={busca}
                onChange={(event) => setBusca(event.target.value)}
                placeholder="Buscar contato por nome ou e-mail..."
              />
              {sugestoes.length > 0 && (
                <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-surf shadow-lg">
                  {sugestoes.map((sugestao) => (
                    <button
                      key={sugestao.id}
                      type="button"
                      className="block w-full px-3 py-2 text-left text-[12px] hover:bg-surf2"
                      onClick={() => {
                        setDestinatario(sugestao);
                        setSugestoes([]);
                      }}
                    >
                      {sugestao.titulo}
                      {sugestao.subtitulo && <span className="text-muted"> — {sugestao.subtitulo}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Assunto</div>
          <Input value={assunto} onChange={(event) => setAssunto(event.target.value)} required />
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Mensagem</div>
          <Textarea rows={10} value={corpo} onChange={(event) => setCorpo(event.target.value)} required />
        </div>
        <Button type="submit" disabled={!destinatario || enviando} className="w-full justify-center">
          {enviando ? "Enviando..." : "Enviar"}
        </Button>
      </form>
    </Card>
  );
}

function AbaEnviados() {
  const [itens, setItens] = useState<EmailEnviado[]>([]);
  const [expandidoId, setExpandidoId] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<EmailEnviado[]>("/email-direto")
      .then(setItens)
      .catch(() => setErro("Não foi possível carregar os e-mails enviados."));
  }, []);

  if (erro) return <div className="text-[12px] text-red">{erro}</div>;

  if (itens.length === 0) {
    return (
      <Card>
        <div className="text-center text-[12px] text-muted">Nenhum e-mail enviado ainda.</div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {itens.map((item) => {
        const expandido = expandidoId === item.id;
        return (
          <Card key={item.id}>
            <button
              type="button"
              onClick={() => setExpandidoId((atual) => (atual === item.id ? null : item.id))}
              className="flex w-full items-center gap-1.5 rounded-md bg-surf2 p-2 text-left text-[11px] text-text hover:border-cyan/50"
            >
              <span className="text-muted">{expandido ? "▾" : "▸"}</span>
              <span className="truncate">
                Para: <span className="font-semibold">{item.decisor_nome}</span>{" "}
                <span className="text-muted">&lt;{item.decisor_email ?? "sem e-mail"}&gt;</span>
                {" · "}
                {new Date(item.criado_em).toLocaleDateString("pt-BR")}
                {" · "}
                <span className="font-semibold">{item.assunto}</span>
              </span>
              <Badge tone={item.status === "enviado" ? "green" : "red"}>{item.status}</Badge>
            </button>
            {expandido && (
              <div className="mt-2 whitespace-pre-line rounded-md bg-surf2 p-2 text-[12px] text-text">
                {item.corpo}
                {item.motivo_falha && <div className="mt-2 text-red">Motivo da falha: {item.motivo_falha}</div>}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function AbaConfiguracoes() {
  const [config, setConfig] = useState<ConfiguracaoAgente | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ConfiguracaoAgente>("/email-direto/configuracao")
      .then(setConfig)
      .catch(() => setErro("Não foi possível carregar as configurações."));
  }, []);

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    setSalvando(true);
    setErro(null);
    setMensagem(null);
    try {
      const atualizado = await api.put<ConfiguracaoAgente>("/email-direto/configuracao", {
        email_nome_exibicao: String(form.get("email_nome_exibicao") ?? "").trim() || null,
        email_assinatura: String(form.get("email_assinatura") ?? "").trim() || null,
      });
      setConfig(atualizado);
      setMensagem("Configurações salvas.");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar as configurações.");
    } finally {
      setSalvando(false);
    }
  }

  if (!config) return <div className="text-[12px] text-muted">Carregando...</div>;

  return (
    <Card>
      {erro && <div className="mb-3 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-3 text-[12px] text-green">{mensagem}</div>}
      <div className="mb-3 text-[11px] text-muted">
        Sem nome de exibição, seus e-mails saem com o seu nome de usuário. Sem assinatura pessoal, cai na
        assinatura padrão da empresa.
      </div>
      <form key={`${config.email_nome_exibicao}-${config.email_assinatura}`} onSubmit={salvar} className="flex flex-col gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome de exibição</div>
          <Input name="email_nome_exibicao" defaultValue={config.email_nome_exibicao ?? ""} placeholder="Como seu nome aparece pro lead" />
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Assinatura</div>
          <Textarea name="email_assinatura" rows={4} defaultValue={config.email_assinatura ?? ""} placeholder="Atenciosamente,&#10;Seu nome" />
        </div>
        <Button type="submit" disabled={salvando} className="w-full justify-center">
          {salvando ? "Salvando..." : "Salvar"}
        </Button>
      </form>
    </Card>
  );
}
