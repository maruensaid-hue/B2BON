import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError, postFile } from "@/lib/api";
import { MODALIDADES, type Licitacao } from "@/pages/bids/tipos";

interface Prazo {
  tipo: string;
  titulo: string;
  quando: string | null;
  dias: number | null;
  nivel: string;
  licitacao_id?: number;
}

interface DocumentoCofre {
  id: number;
  tipo: string;
  nome: string;
  emissor: string | null;
  valido_ate: string | null;
  status: string;
}

interface Concorrente {
  concorrente: string;
  disputas: number;
  ganhamos: number;
  eles_ganharam: number;
  taxa_vitoria_contra: number | null;
}

const TIPOS_COFRE = [
  "CERTIDAO",
  "CONTRATO_SOCIAL",
  "PROCURACAO",
  "BALANCO",
  "CERTIFICACAO",
  "ATESTADO",
  "CURRICULO",
  "ISO",
  "CARTA_FABRICANTE",
  "PARCERIA",
  "DECLARACAO",
  "JURIDICO",
  "OUTRO",
];

const TOM_NIVEL: Record<string, "red" | "amber" | "muted" | "green"> = {
  VENCIDO: "red",
  CRITICO: "red",
  ATENCAO: "amber",
  OK: "green",
  REFERENCIA: "muted",
};

const TOM_COFRE: Record<string, "red" | "amber" | "muted" | "green"> = {
  VENCIDO: "red",
  VENCENDO: "amber",
  VALIDO: "green",
  SEM_VALIDADE: "muted",
};

function data(valor: string | null): string {
  return valor ? new Date(valor).toLocaleDateString("pt-BR") : "—";
}

/** Bid Intelligence — Sell Side (Fase 9): licitações acompanhadas, prazos,
 * cofre de documentos e histórico contra concorrentes. */
export function Licitacoes() {
  const [licitacoes, setLicitacoes] = useState<Licitacao[]>([]);
  const [prazos, setPrazos] = useState<Prazo[]>([]);
  const [cofre, setCofre] = useState<DocumentoCofre[]>([]);
  const [concorrentes, setConcorrentes] = useState<Concorrente[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const [l, p, c, k] = await Promise.all([
        api.get<Licitacao[]>("/bids/licitacoes"),
        api.get<Prazo[]>("/bids/prazos"),
        api.get<DocumentoCofre[]>("/bids/cofre"),
        api.get<Concorrente[]>("/bids/concorrentes"),
      ]);
      setLicitacoes(l);
      setPrazos(
        p.filter((item) => item.nivel !== "OK" && item.nivel !== "REFERENCIA"),
      );
      setCofre(c);
      setConcorrentes(k);
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível carregar as licitações.",
      );
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function criar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    const prazo = String(form.get("prazo_proposta") ?? "");
    const valor = String(form.get("valor_estimado") ?? "");
    try {
      await api.post("/bids/licitacoes", {
        titulo: String(form.get("titulo")),
        orgao_nome: String(form.get("orgao_nome") ?? "") || null,
        modalidade: String(form.get("modalidade")),
        prazo_proposta: prazo ? new Date(prazo).toISOString() : null,
        valor_estimado: valor ? Number(valor) : null,
      });
      formulario.reset();
      await carregar();
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível cadastrar a licitação.",
      );
    }
  }

  async function adicionarAoCofre(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    const arquivo = form.get("arquivo") as File | null;
    const campos: Record<string, string> = {};
    for (const campo of ["tipo", "nome", "emissor", "valido_ate"]) {
      const valor = String(form.get(campo) ?? "");
      if (valor) campos[campo] = valor;
    }
    try {
      await postFile(
        "/bids/cofre",
        arquivo && arquivo.size > 0 ? arquivo : null,
        campos,
      );
      formulario.reset();
      await carregar();
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível adicionar o documento.",
      );
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="bids-licitacoes">
      <div>
        <div className="font-head text-xl font-bold">Licitações</div>
        <div className="text-[11px] text-muted">
          Bid Intelligence — editais e RFPs que a sua empresa acompanha. A
          plataforma recomenda; quem decide o Go/No-Go é você.
        </div>
      </div>
      {erro && <div className="text-[12px] text-red">{erro}</div>}

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <SectionLabel>Em acompanhamento</SectionLabel>
          {licitacoes.length === 0 ? (
            <div className="text-[11px] text-muted">
              Nenhuma licitação cadastrada.
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {licitacoes.map((l) => (
                <Link
                  key={l.id}
                  to={`/bids/${l.id}`}
                  className="flex items-center justify-between rounded-md border border-border p-2 text-[11px] hover:border-cyan"
                >
                  <span>
                    <span className="font-semibold text-text">{l.titulo}</span>
                    <span className="text-muted">
                      {" "}
                      · {l.orgao_nome ?? "órgão não informado"} ·{" "}
                      {MODALIDADES[l.modalidade] ?? l.modalidade} · proposta{" "}
                      {data(l.prazo_proposta)}
                    </span>
                  </span>
                  <Badge
                    tone={
                      l.status === "GO" || l.status === "GANHA"
                        ? "green"
                        : l.status === "NO_GO"
                          ? "red"
                          : "muted"
                    }
                  >
                    {l.status}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
          <form
            onSubmit={criar}
            className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-5"
          >
            <Input
              name="titulo"
              required
              minLength={3}
              placeholder="Título / número do edital"
              className="sm:col-span-2"
            />
            <Input name="orgao_nome" placeholder="Órgão / comprador" />
            <Select name="modalidade" defaultValue="PUBLIC_TENDER">
              {Object.entries(MODALIDADES).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </Select>
            <Input name="prazo_proposta" type="datetime-local" />
            <Input
              name="valor_estimado"
              type="number"
              min={0}
              step="0.01"
              placeholder="Valor estimado (R$)"
            />
            <Button type="submit" className="sm:col-span-1">
              Cadastrar
            </Button>
          </form>
        </Card>

        <Card>
          <SectionLabel>Prazos que pedem atenção</SectionLabel>
          {prazos.length === 0 ? (
            <div className="text-[11px] text-muted">Nada vencendo.</div>
          ) : (
            <div className="flex flex-col gap-1.5 text-[11px]">
              {prazos.map((p, indice) => (
                <div
                  key={indice}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="text-text">{p.titulo}</span>
                  <Badge tone={TOM_NIVEL[p.nivel] ?? "muted"}>
                    {p.dias !== null ? `${p.dias}d` : p.nivel}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <SectionLabel>Cofre de documentos</SectionLabel>
          <div className="flex flex-col gap-1 text-[11px]">
            {cofre.map((d) => (
              <div
                key={d.id}
                className="flex items-center justify-between gap-2"
              >
                <span>
                  <span className="text-text">{d.nome}</span>
                  <span className="text-muted">
                    {" "}
                    · {d.tipo} · {d.emissor ?? "emissor não informado"} · válido
                    até {data(d.valido_ate)}
                  </span>
                </span>
                <Badge tone={TOM_COFRE[d.status] ?? "muted"}>{d.status}</Badge>
              </div>
            ))}
            {cofre.length === 0 && (
              <div className="text-muted">Nenhum documento no cofre.</div>
            )}
          </div>
          <form
            onSubmit={adicionarAoCofre}
            className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-5"
          >
            <Select name="tipo" defaultValue="CERTIDAO">
              {TIPOS_COFRE.map((tipo) => (
                <option key={tipo} value={tipo}>
                  {tipo}
                </option>
              ))}
            </Select>
            <Input
              name="nome"
              required
              minLength={2}
              placeholder="Nome (ex.: CND Federal)"
              className="sm:col-span-2"
            />
            <Input name="emissor" placeholder="Emissor" />
            <Input name="valido_ate" type="date" />
            <input
              name="arquivo"
              type="file"
              className="text-[11px] sm:col-span-3"
            />
            <Button type="submit" className="sm:col-span-2">
              Adicionar ao cofre
            </Button>
          </form>
        </Card>

        <Card>
          <SectionLabel>Concorrentes (seu histórico)</SectionLabel>
          {concorrentes.length === 0 ? (
            <div className="text-[11px] text-muted">
              Informe concorrentes nas licitações para ver o histórico.
            </div>
          ) : (
            <div className="flex flex-col gap-1 text-[11px]">
              {concorrentes.map((c) => (
                <div key={c.concorrente} className="flex justify-between gap-2">
                  <span className="text-text">{c.concorrente}</span>
                  <span className="text-muted">
                    {c.disputas} disputa(s) ·{" "}
                    {c.taxa_vitoria_contra === null
                      ? "sem resultado"
                      : `${Math.round(c.taxa_vitoria_contra * 100)}% de vitória`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
