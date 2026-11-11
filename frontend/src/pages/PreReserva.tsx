import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface InfoPreReserva {
  marca: string;
  titulo: string;
  descricao: string | null;
  site: string | null;
  datas_livres: string[];
  antecedencia_minima_dias: number;
  horas_pre_reserva: number;
  valor_presencial: number | null;
  valor_online: number | null;
  percentual_sinal: number;
  formas_pagamento: string[];
  condicao_especial: string | null;
}

interface PreReservaCriada {
  data_evento: string;
  expira_em: string;
  valor: number;
  valor_sinal: number;
}

const NOMES_PAGAMENTO: Record<string, string> = {
  pix: "Pix",
  boleto: "Boleto",
  cartao_credito: "Cartão de crédito",
  cartao_debito: "Cartão de débito",
};

const DIAS_SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

function moeda(valor: number) {
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

/** "2026-12-03" → "qui, 03/12/2026" sem passar por fuso (a data do evento não tem hora). */
function dataPorExtenso(iso: string) {
  const [ano, mes, dia] = iso.split("-").map(Number);
  const semana = DIAS_SEMANA[new Date(Date.UTC(ano, mes - 1, dia)).getUTCDay()];
  return `${semana}, ${String(dia).padStart(2, "0")}/${String(mes).padStart(2, "0")}/${ano}`;
}

function Rotulo({ children }: { children: React.ReactNode }) {
  return <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{children}</div>;
}

/** Página pública de pré-reserva de data (sem login). Mostra a marca configurada pelo tenant — não a da plataforma — e só as datas que ainda estão livres.
 * Ao enviar, cai no CRM do tenant como conta + contato + negócio, e a data sai da lista para os próximos visitantes. */
export function PreReserva() {
  const { codigo } = useParams<{ codigo: string }>();
  const [info, setInfo] = useState<InfoPreReserva | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [criada, setCriada] = useState<PreReservaCriada | null>(null);
  const [formato, setFormato] = useState<"presencial" | "online">("presencial");

  function carregar() {
    if (!codigo) return;
    api
      .get<InfoPreReserva>(`/pre-reserva/${codigo}/info`)
      .catch(() => null)
      .then((resposta) => {
        if (resposta) {
          setInfo(resposta);
          if (resposta.valor_presencial == null && resposta.valor_online != null) setFormato("online");
        } else setErro("Este formulário não está disponível.");
      });
  }

  useEffect(carregar, [codigo]);

  useEffect(() => {
    if (info) document.title = `Pré-reserva · ${info.marca}`;
  }, [info]);

  const valorEscolhido = useMemo(() => {
    if (!info) return null;
    return formato === "presencial" ? info.valor_presencial : info.valor_online;
  }, [info, formato]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!codigo) return;
    setErro(null);
    setCarregando(true);
    const form = new FormData(event.currentTarget);
    const texto = (campo: string) => String(form.get(campo) || "").trim() || undefined;
    try {
      const resposta = await api.post<PreReservaCriada>(`/pre-reserva/${codigo}`, {
        data_evento: String(form.get("data_evento")),
        formato,
        cidade: formato === "presencial" ? texto("cidade") : undefined,
        participantes: texto("participantes") ? Number(form.get("participantes")) : undefined,
        forma_pagamento: String(form.get("forma_pagamento")),
        nome_empresa: String(form.get("nome_empresa")),
        cnpj: texto("cnpj"),
        nome_contato: String(form.get("nome_contato")),
        cargo_contato: texto("cargo_contato"),
        email_contato: String(form.get("email_contato")),
        telefone_contato: String(form.get("telefone_contato")),
        observacoes: texto("observacoes"),
        aceite_contato: form.get("aceite_contato") === "on",
      });
      setCriada(resposta);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar agora. Tente de novo em instantes.");
      carregar(); // a data pode ter acabado de sair: atualiza a lista
    } finally {
      setCarregando(false);
    }
  }

  if (erro && !info) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card glow className="w-full max-w-md text-center text-[13px] text-muted">
          {erro}
        </Card>
      </div>
    );
  }

  if (!info) {
    return <div className="flex min-h-screen items-center justify-center p-4 text-[12px] text-muted">Carregando...</div>;
  }

  if (criada) {
    const prazo = new Date(criada.expira_em.endsWith("Z") ? criada.expira_em : `${criada.expira_em}Z`);
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card glow className="w-full max-w-md text-center">
          <div className="font-head text-lg font-extrabold text-cyan">Data pré-reservada!</div>
          <div className="mt-3 text-[13px]">{dataPorExtenso(criada.data_evento)}</div>
          <div className="mt-3 text-[12.5px] leading-relaxed text-muted">
            A data fica guardada para você, sem custo, até{" "}
            <strong className="text-text">
              {prazo.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" })}
            </strong>
            . Depois disso enviamos a cobrança do sinal de {moeda(criada.valor_sinal)} na forma de pagamento que você escolheu. Com o sinal pago, a data
            está confirmada; sem o pagamento, a pré-reserva cai e a data volta para a agenda.
          </div>
          <div className="mt-3 text-[12px] text-muted">Vamos falar com você em breve para o briefing.</div>
          {info.site && (
            <a href={info.site} className="mt-4 inline-block text-[12px] text-cyan underline">
              Voltar para o site
            </a>
          )}
        </Card>
      </div>
    );
  }

  const semDatas = info.datas_livres.length === 0;
  const restoPercentual = 100 - info.percentual_sinal;

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card glow className="w-full max-w-lg">
        <div className="mb-5 text-center">
          <div className="text-[11px] tracking-wide text-muted uppercase">{info.marca}</div>
          <div className="mt-1 font-head text-lg font-extrabold">Pré-reserva: {info.titulo}</div>
          {info.descricao && <div className="mt-2 text-[12px] whitespace-pre-line text-muted">{info.descricao}</div>}
        </div>

        <div className="mb-5 rounded-lg border border-border bg-surf2 p-3 text-[12px] leading-relaxed">
          <div>
            {info.valor_presencial != null && <>Presencial: <strong>{moeda(info.valor_presencial)}</strong> (deslocamento à parte)</>}
            {info.valor_presencial != null && info.valor_online != null && " · "}
            {info.valor_online != null && <>Online: <strong>{moeda(info.valor_online)}</strong></>}
          </div>
          <div className="mt-1 text-muted">
            Pré-reserva sem custo por {info.horas_pre_reserva} h. Sinal de {info.percentual_sinal}% confirma a data
            {restoPercentual > 0 && <>; os outros {restoPercentual}% são pagos no dia do evento</>}. Antecedência mínima de{" "}
            {info.antecedencia_minima_dias} dias.
          </div>
          {info.formas_pagamento.length > 0 && (
            <div className="mt-1 text-muted">Pagamento: {info.formas_pagamento.map((f) => NOMES_PAGAMENTO[f] ?? f).join(", ")}.</div>
          )}
          {info.condicao_especial && <div className="mt-1 text-cyan">{info.condicao_especial}</div>}
        </div>

        {semDatas ? (
          <div className="text-center text-[12.5px] text-muted">
            Não há datas livres no momento.
            {info.site && (
              <>
                {" "}
                <a href={info.site} className="text-cyan underline">
                  Fale com a equipe pelo site.
                </a>
              </>
            )}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <div>
              <Rotulo>Data do evento ({info.datas_livres.length} livres)</Rotulo>
              <Select name="data_evento" required defaultValue="">
                <option value="" disabled>
                  Escolha a data
                </option>
                {info.datas_livres.map((d) => (
                  <option key={d} value={d}>
                    {dataPorExtenso(d)}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <Rotulo>Formato</Rotulo>
              <div className="flex gap-4 text-[12.5px]">
                {info.valor_presencial != null && (
                  <label className="flex items-center gap-1.5">
                    <input type="radio" name="formato" checked={formato === "presencial"} onChange={() => setFormato("presencial")} />
                    Presencial
                  </label>
                )}
                {info.valor_online != null && (
                  <label className="flex items-center gap-1.5">
                    <input type="radio" name="formato" checked={formato === "online"} onChange={() => setFormato("online")} />
                    Online
                  </label>
                )}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {formato === "presencial" && (
                <div>
                  <Rotulo>Cidade do evento</Rotulo>
                  <Input name="cidade" required placeholder="Ex.: Campinas/SP" />
                </div>
              )}
              <div>
                <Rotulo>Participantes (aprox.)</Rotulo>
                <Input name="participantes" type="number" min={1} placeholder="Ex.: 120" />
              </div>
            </div>

            <div>
              <Rotulo>Como prefere pagar o sinal</Rotulo>
              <Select name="forma_pagamento" required defaultValue={info.formas_pagamento[0]}>
                {info.formas_pagamento.map((f) => (
                  <option key={f} value={f}>
                    {NOMES_PAGAMENTO[f] ?? f}
                  </option>
                ))}
              </Select>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Rotulo>Empresa</Rotulo>
                <Input name="nome_empresa" required placeholder="Nome da empresa" />
              </div>
              <div>
                <Rotulo>CNPJ (opcional)</Rotulo>
                <Input name="cnpj" placeholder="00.000.000/0001-00" />
              </div>
              <div>
                <Rotulo>Seu nome</Rotulo>
                <Input name="nome_contato" required placeholder="Como você se chama" />
              </div>
              <div>
                <Rotulo>Cargo (opcional)</Rotulo>
                <Input name="cargo_contato" placeholder="Ex.: Diretor comercial" />
              </div>
              <div>
                <Rotulo>E-mail</Rotulo>
                <Input name="email_contato" type="email" required placeholder="voce@empresa.com.br" />
              </div>
              <div>
                <Rotulo>WhatsApp</Rotulo>
                <Input name="telefone_contato" required minLength={8} placeholder="(11) 99999-9999" />
              </div>
            </div>

            <div>
              <Rotulo>Sobre o evento (opcional)</Rotulo>
              <Textarea name="observacoes" rows={3} placeholder="Tipo de evento, público, horário previsto..." />
            </div>

            <label className="flex items-start gap-2 text-[11.5px] text-muted">
              <input type="checkbox" name="aceite_contato" required className="mt-0.5" />
              <span>
                Autorizo o uso destes dados para falarem comigo sobre esta pré-reserva e para o envio da cobrança do sinal ({info.marca}).
              </span>
            </label>

            {erro && <div className="text-[12px] text-red">{erro}</div>}

            <Button type="submit" disabled={carregando} className="mt-1 w-full justify-center">
              {carregando
                ? "Reservando..."
                : `Pré-reservar a data${valorEscolhido != null ? ` · ${moeda(valorEscolhido)}` : ""}`}
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
