import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, mensagemErro } from "@/lib/api";
import {
  ROTULO_STATUS_SOURCING,
  TIPOS_SOURCING,
  type ProcessoSourcing,
} from "@/pages/sourcing/tipos";

/** Strategic Sourcing (Phase E): processos de compra privada do tenant. */
export function SourcingProcessos() {
  const [processos, setProcessos] = useState<ProcessoSourcing[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const navegar = useNavigate();

  const carregar = useCallback(async () => {
    try {
      setProcessos(await api.get<ProcessoSourcing[]>("/sourcing/processos"));
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível carregar os processos."));
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function criar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const valor = String(form.get("valor_estimado") ?? "");
    try {
      const criado = await api.post<ProcessoSourcing>("/sourcing/processos", {
        tipo_processo: String(form.get("tipo_processo")),
        titulo: String(form.get("titulo")),
        descricao: String(form.get("descricao") ?? "") || null,
        valor_estimado: valor ? Number(valor) : null,
      });
      navegar(`/sourcing/${criado.id}`);
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível criar o processo."));
    }
  }

  return (
    <div className="flex flex-col gap-3.5" data-testid="sourcing-processos">
      <div>
        <div className="font-head text-xl font-bold">Strategic Sourcing</div>
        <div className="text-[11px] text-muted">
          RFI, RFP, RFQ e qualificação de fornecedores. Dados do comprador:
          nunca vão para a rede, para o lado vendedor ou para a IA.
        </div>
      </div>
      {erro && <div className="text-[12px] text-red">{erro}</div>}
      <Card>
        <SectionLabel>Novo processo</SectionLabel>
        <form
          onSubmit={criar}
          className="grid grid-cols-1 gap-2 sm:grid-cols-5"
        >
          <Select name="tipo_processo" defaultValue="RFP">
            {Object.entries(TIPOS_SOURCING).map(([valor, rotulo]) => (
              <option key={valor} value={valor}>
                {rotulo}
              </option>
            ))}
          </Select>
          <Input
            name="titulo"
            required
            minLength={3}
            placeholder="Necessidade / título"
            className="sm:col-span-2"
          />
          <Input
            name="valor_estimado"
            type="number"
            min={0}
            step="0.01"
            placeholder="Valor estimado"
          />
          <Button type="submit">Criar</Button>
          <Input
            name="descricao"
            placeholder="Descrição (opcional)"
            className="sm:col-span-5"
          />
        </form>
      </Card>
      <Card>
        <SectionLabel>Processos</SectionLabel>
        <div className="flex flex-col gap-1.5">
          {processos.map((p) => (
            <Link
              key={p.id}
              to={`/sourcing/${p.id}`}
              className="flex items-center justify-between rounded-md border border-border p-2 text-[11px] hover:border-cyan"
            >
              <span>
                <span className="font-semibold text-text">{p.titulo}</span>
                <span className="text-muted">
                  {" "}
                  · {TIPOS_SOURCING[p.tipo_processo] ?? p.tipo_processo}
                </span>
              </span>
              <Badge>{ROTULO_STATUS_SOURCING[p.status] ?? p.status}</Badge>
            </Link>
          ))}
          {processos.length === 0 && (
            <div className="text-[11px] text-muted">Nenhum processo ainda.</div>
          )}
        </div>
      </Card>
    </div>
  );
}
