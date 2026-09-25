import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError, postFile } from "@/lib/api";

type Escopo = "compartilhado" | "interno";

interface Workspace {
  pode_escrever: boolean;
  documentos: {
    id: number;
    nome_arquivo: string;
    escopo: Escopo;
    da_minha_empresa: boolean;
  }[];
  tarefas: {
    id: number;
    titulo: string;
    escopo: Escopo;
    status: string;
    responsavel: "NOS" | "ELES" | null;
  }[];
  reunioes: {
    id: number;
    titulo: string;
    inicio: string;
    link: string | null;
    escopo: Escopo;
  }[];
  stakeholders: {
    id: number;
    nome: string;
    cargo: string | null;
    lado: string;
    papel: string;
    escopo: Escopo;
    notas: string | null;
  }[];
}

type Aba = "tarefas" | "reunioes" | "documentos" | "stakeholders";

function Escopo({ escopo }: { escopo: Escopo }) {
  return (
    <Badge tone={escopo === "interno" ? "amber" : "muted"}>
      {escopo === "interno" ? "Só nós" : "Compartilhado"}
    </Badge>
  );
}

/** Corporate/Buying Room (Fase 11): tarefas, reuniões, documentos e comitê
 * de compra. "Só nós" nunca aparece para a outra empresa. */
export function SalaWorkspacePainel({ salaId }: { salaId: number }) {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [aba, setAba] = useState<Aba>("tarefas");
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setWs(await api.get<Workspace>(`/rede-social/salas/${salaId}/workspace`));
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível carregar a sala.",
      );
    }
  }, [salaId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function enviar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    const escopo = String(form.get("escopo") ?? "compartilhado");
    setErro(null);
    try {
      if (aba === "tarefas") {
        await api.post(`/rede-social/salas/${salaId}/tarefas`, {
          titulo: String(form.get("titulo")),
          escopo,
        });
      } else if (aba === "reunioes") {
        await api.post(`/rede-social/salas/${salaId}/reunioes`, {
          titulo: String(form.get("titulo")),
          inicio: new Date(String(form.get("inicio"))).toISOString(),
          escopo,
        });
      } else if (aba === "stakeholders") {
        await api.post(`/rede-social/salas/${salaId}/stakeholders`, {
          nome: String(form.get("titulo")),
          lado: String(form.get("lado")),
          papel: String(form.get("papel")),
          escopo,
        });
      } else {
        const arquivo = form.get("arquivo") as File | null;
        if (!arquivo || arquivo.size === 0) return;
        await postFile(`/rede-social/salas/${salaId}/documentos`, arquivo, {
          escopo,
        });
      }
      formulario.reset();
      await carregar();
    } catch (error) {
      setErro(
        error instanceof ApiError ? error.message : "Não foi possível salvar.",
      );
    }
  }

  if (!ws)
    return erro ? (
      <div className="px-3 py-2 text-[11px] text-red">{erro}</div>
    ) : null;

  return (
    <div
      className="border-b border-border px-3 py-2 text-[11px]"
      data-testid="sala-workspace"
    >
      <div className="mb-1.5 flex gap-2">
        {(["tarefas", "reunioes", "documentos", "stakeholders"] as Aba[]).map(
          (item) => (
            <button
              key={item}
              type="button"
              onClick={() => setAba(item)}
              className={aba === item ? "font-bold text-cyan" : "text-muted"}
            >
              {item === "stakeholders" ? "comitê" : item}
            </button>
          ),
        )}
      </div>
      {erro && <div className="mb-1 text-red">{erro}</div>}
      <div className="flex max-h-28 flex-col gap-1 overflow-y-auto">
        {aba === "tarefas" &&
          ws.tarefas.map((t) => (
            <div key={t.id} className="flex items-center justify-between gap-2">
              <span className="text-text">
                {t.titulo} <span className="text-muted">· {t.status}</span>
              </span>
              <Escopo escopo={t.escopo} />
            </div>
          ))}
        {aba === "reunioes" &&
          ws.reunioes.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2">
              <span className="text-text">
                {r.titulo}{" "}
                <span className="text-muted">
                  · {new Date(r.inicio).toLocaleString("pt-BR")}
                </span>
              </span>
              <Escopo escopo={r.escopo} />
            </div>
          ))}
        {aba === "documentos" &&
          ws.documentos.map((d) => (
            <div key={d.id} className="flex items-center justify-between gap-2">
              <span className="text-text">{d.nome_arquivo}</span>
              <Escopo escopo={d.escopo} />
            </div>
          ))}
        {aba === "stakeholders" &&
          ws.stakeholders.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-2">
              <span className="text-text">
                {s.nome}{" "}
                <span className="text-muted">
                  · {s.lado} · {s.papel}
                </span>
                {s.notas && <span className="text-muted"> — {s.notas}</span>}
              </span>
              <Escopo escopo={s.escopo} />
            </div>
          ))}
      </div>
      {ws.pode_escrever && (
        <form
          onSubmit={enviar}
          className="mt-2 flex flex-wrap items-center gap-1.5"
        >
          {aba === "documentos" ? (
            <input name="arquivo" type="file" className="text-[11px]" />
          ) : (
            <Input
              name="titulo"
              required
              minLength={2}
              placeholder={aba === "stakeholders" ? "Nome" : "Título"}
              className="flex-1"
            />
          )}
          {aba === "reunioes" && (
            <Input
              name="inicio"
              type="datetime-local"
              required
              className="w-44"
            />
          )}
          {aba === "stakeholders" && (
            <>
              <Select name="lado" defaultValue="COMPRADOR" className="w-32">
                <option value="COMPRADOR">Comprador</option>
                <option value="VENDEDOR">Vendedor</option>
              </Select>
              <Select name="papel" defaultValue="UNKNOWN" className="w-40">
                {[
                  "DECISION_MAKER",
                  "ECONOMIC_BUYER",
                  "CHAMPION",
                  "INFLUENCER",
                  "TECHNICAL_EVALUATOR",
                  "PROCUREMENT",
                  "LEGAL",
                  "BLOCKER",
                  "UNKNOWN",
                ].map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </>
          )}
          <Select
            name="escopo"
            defaultValue={aba === "stakeholders" ? "interno" : "compartilhado"}
            className="w-36"
          >
            <option value="compartilhado">Compartilhado</option>
            <option value="interno">Só nós</option>
          </Select>
          <Button type="submit" size="sm">
            Adicionar
          </Button>
        </form>
      )}
    </div>
  );
}
