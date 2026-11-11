import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Config {
  ativo: boolean;
  marca: string;
  titulo: string;
  descricao: string | null;
  site: string | null;
  datas_disponiveis: string[];
  antecedencia_minima_dias: number;
  horas_pre_reserva: number;
  valor_presencial: number | null;
  valor_online: number | null;
  percentual_sinal: number;
  formas_pagamento: string[];
  condicao_especial: string | null;
}

interface Reserva {
  id: number;
  negocio_id: number;
  nome_empresa: string;
  nome_contato: string;
  data_evento: string;
  formato: string;
  cidade: string | null;
  participantes: number | null;
  forma_pagamento: string | null;
  valor: number;
  status: "pre_reservada" | "confirmada" | "cancelada";
  expira_em: string;
}

const FORMAS = [
  ["pix", "Pix"],
  ["boleto", "Boleto"],
  ["cartao_credito", "Cartão de crédito"],
  ["cartao_debito", "Cartão de débito"],
] as const;

const VAZIA: Config = {
  ativo: true,
  marca: "",
  titulo: "",
  descricao: null,
  site: null,
  datas_disponiveis: [],
  antecedencia_minima_dias: 10,
  horas_pre_reserva: 48,
  valor_presencial: null,
  valor_online: null,
  percentual_sinal: 50,
  formas_pagamento: FORMAS.map(([v]) => v),
  condicao_especial: null,
};

const br = (iso: string) => iso.split("-").reverse().join("/");

/** Aceita uma data por linha (dd/mm/aaaa ou aaaa-mm-dd) e devolve ISO ordenado e sem repetição; linhas inválidas voltam à parte para avisar. */
function lerDatas(texto: string): { datas: string[]; invalidas: string[] } {
  const datas = new Set<string>();
  const invalidas: string[] = [];
  for (const bruta of texto.split(/[\n,;]+/)) {
    const linha = bruta.trim();
    if (!linha) continue;
    const br_ = linha.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    const iso = br_ ? `${br_[3]}-${br_[2].padStart(2, "0")}-${br_[1].padStart(2, "0")}` : linha;
    if (/^\d{4}-\d{2}-\d{2}$/.test(iso) && !Number.isNaN(Date.parse(iso))) datas.add(iso);
    else invalidas.push(linha);
  }
  return { datas: [...datas].sort(), invalidas };
}

/** Todas as datas de segunda a sábado entre duas datas (inclusive) — atalho para montar a agenda. */
function segundaASabado(inicio: string, fim: string): string[] {
  const saida: string[] = [];
  const d = new Date(`${inicio}T12:00:00Z`);
  const ultimo = new Date(`${fim}T12:00:00Z`);
  while (d <= ultimo && saida.length < 400) {
    if (d.getUTCDay() !== 0) saida.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return saida;
}

/** Card da Configuração: formulário público de pré-reserva de data (palestra, workshop…). Quem preencher cai no CRM como conta + contato + negócio. */
export function PreReservaConfig() {
  const [codigo, setCodigo] = useState<string | null>(null);
  const [config, setConfig] = useState<Config>(VAZIA);
  const [existe, setExiste] = useState(false);
  const [datasTexto, setDatasTexto] = useState("");
  const [intervalo, setIntervalo] = useState({ inicio: "", fim: "" });
  const [reservas, setReservas] = useState<Reserva[]>([]);
  const [mensagem, setMensagem] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [copiado, setCopiado] = useState(false);

  async function carregarReservas() {
    setReservas(await api.get<Reserva[]>("/pre-reserva/reservas").catch(() => []));
  }

  useEffect(() => {
    api.get<{ codigo: string }>("/captura-lead/config").then((r) => setCodigo(r.codigo)).catch(() => null);
    api
      .get<Config | null>("/pre-reserva/config")
      .then((c) => {
        if (c) {
          setConfig(c);
          setExiste(true);
          setDatasTexto(c.datas_disponiveis.map(br).join("\n"));
        }
      })
      .catch(() => null);
    carregarReservas();
  }, []);

  const link = codigo ? `${window.location.origin}/pre-reserva/${codigo}` : null;
  const { datas, invalidas } = lerDatas(datasTexto);

  function acrescentarIntervalo() {
    if (!intervalo.inicio || !intervalo.fim) return;
    const todas = [...new Set([...datas, ...segundaASabado(intervalo.inicio, intervalo.fim)])].sort();
    setDatasTexto(todas.map(br).join("\n"));
  }

  async function salvar() {
    if (invalidas.length) {
      setMensagem({ tipo: "erro", texto: `Datas que não entendi: ${invalidas.join(", ")}` });
      return;
    }
    setSalvando(true);
    setMensagem(null);
    try {
      const salvo = await api.put<Config>("/pre-reserva/config", { ...config, datas_disponiveis: datas });
      setConfig(salvo);
      setExiste(true);
      setMensagem({ tipo: "ok", texto: "Formulário salvo." });
    } catch (error) {
      setMensagem({ tipo: "erro", texto: error instanceof ApiError ? error.message : "Não foi possível salvar." });
    } finally {
      setSalvando(false);
    }
  }

  async function mudarStatus(reserva: Reserva, status: "confirmada" | "cancelada") {
    const pergunta =
      status === "confirmada"
        ? `Confirmar que o sinal de ${reserva.nome_empresa} foi pago?`
        : `Cancelar a pré-reserva de ${reserva.nome_empresa}? A data ${br(reserva.data_evento)} volta para a agenda.`;
    if (!window.confirm(pergunta)) return;
    try {
      await api.post(`/pre-reserva/reservas/${reserva.id}/status`, { status });
      await carregarReservas();
    } catch (error) {
      setMensagem({ tipo: "erro", texto: error instanceof ApiError ? error.message : "Não foi possível alterar." });
    }
  }

  const campoNumero = (campo: keyof Config, valor: string) =>
    setConfig({ ...config, [campo]: valor === "" ? null : Number(valor) } as Config);

  return (
    <Card className="mt-4">
      <SectionLabel>Formulário de pré-reserva de data</SectionLabel>
      <div className="mb-3 text-[11px] text-muted">
        Página pública para o cliente segurar uma data (palestra, workshop, treinamento). Mostra só as datas que ainda estão livres; quem preencher cai no seu
        CRM como empresa, contato e negócio, e a data sai da lista na hora.
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Marca exibida na página" value={config.marca} onChange={(e) => setConfig({ ...config, marca: e.target.value })} placeholder="Ex.: O Vendedor Tubarão" />
        <Input label="O que está sendo reservado" value={config.titulo} onChange={(e) => setConfig({ ...config, titulo: e.target.value })} placeholder="Ex.: Palestra O Vendedor Tubarão" />
        <Input label="Site (link de volta)" value={config.site ?? ""} onChange={(e) => setConfig({ ...config, site: e.target.value || null })} placeholder="https://..." />
        <Input label="Condição especial (opcional)" value={config.condicao_especial ?? ""} onChange={(e) => setConfig({ ...config, condicao_especial: e.target.value || null })} placeholder="Ex.: bônus para quem confirmar até..." />
        <Input label="Valor presencial (R$)" type="number" min={0} value={config.valor_presencial ?? ""} onChange={(e) => campoNumero("valor_presencial", e.target.value)} placeholder="Vazio = não oferece" />
        <Input label="Valor online (R$)" type="number" min={0} value={config.valor_online ?? ""} onChange={(e) => campoNumero("valor_online", e.target.value)} placeholder="Vazio = não oferece" />
        <Input label="Sinal (%)" type="number" min={0} max={100} value={config.percentual_sinal} onChange={(e) => campoNumero("percentual_sinal", e.target.value)} />
        <Input label="Pré-reserva sem custo (horas)" type="number" min={1} value={config.horas_pre_reserva} onChange={(e) => campoNumero("horas_pre_reserva", e.target.value)} />
        <Input label="Antecedência mínima (dias)" type="number" min={0} value={config.antecedencia_minima_dias} onChange={(e) => campoNumero("antecedencia_minima_dias", e.target.value)} />
      </div>

      <div className="mt-3">
        <Textarea label="Descrição na página (opcional)" rows={3} value={config.descricao ?? ""} onChange={(e) => setConfig({ ...config, descricao: e.target.value || null })} />
      </div>

      <div className="mt-3">
        <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Formas de pagamento do sinal</div>
        <div className="flex flex-wrap gap-4 text-[12px]">
          {FORMAS.map(([valor, nome]) => (
            <label key={valor} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={config.formas_pagamento.includes(valor)}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    formas_pagamento: e.target.checked ? [...config.formas_pagamento, valor] : config.formas_pagamento.filter((f) => f !== valor),
                  })
                }
              />
              {nome}
            </label>
          ))}
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto]">
        <Textarea
          label={`Datas disponíveis (uma por linha, dd/mm/aaaa) · ${datas.length} datas`}
          rows={6}
          value={datasTexto}
          onChange={(e) => setDatasTexto(e.target.value)}
        />
        <div className="flex flex-col gap-2 sm:w-48">
          <div className="text-[10px] tracking-wide text-muted uppercase">Acrescentar segunda a sábado</div>
          <Input type="date" value={intervalo.inicio} onChange={(e) => setIntervalo({ ...intervalo, inicio: e.target.value })} aria-label="De" />
          <Input type="date" value={intervalo.fim} onChange={(e) => setIntervalo({ ...intervalo, fim: e.target.value })} aria-label="Até" />
          <Button size="sm" variant="ghost" onClick={acrescentarIntervalo}>
            Acrescentar
          </Button>
        </div>
      </div>

      <label className="mt-3 flex items-center gap-2 text-[12px]">
        <input type="checkbox" checked={config.ativo} onChange={(e) => setConfig({ ...config, ativo: e.target.checked })} />
        Formulário no ar
      </label>

      {mensagem && <div className={`mt-2 text-[12px] ${mensagem.tipo === "ok" ? "text-cyan" : "text-red"}`}>{mensagem.texto}</div>}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={salvar} disabled={salvando || !config.marca.trim() || !config.titulo.trim()}>
          {salvando ? "Salvando..." : "Salvar formulário"}
        </Button>
        {existe && link && (
          <>
            <Input readOnly value={link} className="min-w-0 flex-1" />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                navigator.clipboard.writeText(link);
                setCopiado(true);
                setTimeout(() => setCopiado(false), 2000);
              }}
            >
              {copiado ? "Copiado!" : "Copiar link"}
            </Button>
          </>
        )}
      </div>

      {reservas.length > 0 && (
        <div className="mt-5">
          <div className="mb-2 text-[10px] tracking-wide text-muted uppercase">Pré-reservas</div>
          <div className="flex flex-col gap-2">
            {reservas.map((r) => {
              const prazo = new Date(r.expira_em.endsWith("Z") ? r.expira_em : `${r.expira_em}Z`);
              return (
                <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surf2 px-3 py-2 text-[12px]">
                  <strong>{br(r.data_evento)}</strong>
                  <span>{r.nome_empresa}</span>
                  <span className="text-muted">
                    {r.nome_contato} · {r.formato}
                    {r.cidade ? ` (${r.cidade})` : ""} · {r.valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
                    {r.forma_pagamento ? ` · ${FORMAS.find(([v]) => v === r.forma_pagamento)?.[1] ?? r.forma_pagamento}` : ""}
                  </span>
                  <Badge tone={r.status === "confirmada" ? "green" : r.status === "cancelada" ? "muted" : "amber"}>
                    {r.status === "pre_reservada"
                      ? `pré-reservada · cobrar a partir de ${prazo.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" })}`
                      : r.status}
                  </Badge>
                  <Link to="/crm" className="text-cyan underline">
                    ver no CRM
                  </Link>
                  {r.status !== "cancelada" && (
                    <span className="ml-auto flex gap-1">
                      {r.status === "pre_reservada" && (
                        <Button size="sm" onClick={() => mudarStatus(r, "confirmada")}>
                          Sinal pago
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => mudarStatus(r, "cancelada")}>
                        Cancelar
                      </Button>
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}
