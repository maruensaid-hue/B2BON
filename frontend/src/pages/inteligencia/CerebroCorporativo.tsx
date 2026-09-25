import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Corporate Brain do tenant (Fase 4 do Master Prompt v4): conhecimento
 * institucional que a IA usa como contexto. Itens "interno" nunca saem
 * da empresa; só itens marcados "rede" podem ser usados pelo Agente
 * Corporativo para responder outras empresas. */

interface Conhecimento {
  id: number;
  tipo: string;
  titulo: string;
  conteudo: string;
  visibilidade: "interno" | "rede";
  classificacao: string;
  fonte: string | null;
}

interface Perfil {
  dados: Record<string, unknown>;
  fontes: Record<string, string>;
  versao: number;
  atualizado_em: string | null;
}

interface Agente {
  id: string;
  nome: string;
  dominio: string;
  status: "ATIVO" | "PLANEJADO";
}

const ROTULOS_PERFIL: Record<string, string> = {
  tom_comunicacao: "Tom de comunicação",
  ofertas_ativas: "Ofertas ativas",
  icps_ativos: "ICPs ativos",
  regras_aprendidas: "Regras aprendidas",
  taxa_aprovacao_sem_edicao_ia: "Aprovação de rascunhos da IA sem edição",
  taxa_rejeicao_ia: "Rejeição de rascunhos da IA",
  canais_mais_usados: "Canais mais usados",
};

function formatar(valor: unknown): string {
  if (valor === null || valor === undefined) return "Dados insuficientes";
  if (Array.isArray(valor)) return valor.length ? valor.join(", ") : "—";
  if (typeof valor === "number" && valor <= 1 && valor >= 0 && !Number.isInteger(valor)) return `${(valor * 100).toFixed(0)}%`;
  return String(valor);
}

export function CerebroCorporativo() {
  const { usuario } = useAuth();
  const [itens, setItens] = useState<Conhecimento[]>([]);
  const [tipos, setTipos] = useState<string[]>([]);
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [agentes, setAgentes] = useState<Agente[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const podeEditar = usuario?.papel === "admin" || usuario?.papel === "super_admin";

  async function carregar() {
    try {
      const [itensResp, tiposResp, agentesResp] = await Promise.all([
        api.get<Conhecimento[]>("/inteligencia/conhecimento"),
        api.get<string[]>("/inteligencia/conhecimento/tipos"),
        api.get<Agente[]>("/inteligencia/agentes"),
      ]);
      setItens(itensResp);
      setTipos(tiposResp);
      setAgentes(agentesResp);
    } catch {
      setErro("Não foi possível carregar o Cérebro Corporativo.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function criar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    try {
      await api.post("/inteligencia/conhecimento", {
        tipo: String(form.get("tipo")),
        titulo: String(form.get("titulo")),
        conteudo: String(form.get("conteudo")),
        visibilidade: String(form.get("visibilidade")),
        fonte: String(form.get("fonte") || "") || null,
      });
      formulario.reset();
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar.");
    }
  }

  async function arquivar(id: number) {
    try {
      await api.delete(`/inteligencia/conhecimento/${id}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível arquivar.");
    }
  }

  async function consolidarPerfil() {
    try {
      setPerfil(await api.post<Perfil>("/inteligencia/perfil-empresa/consolidar", {}));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível consolidar o perfil.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Cérebro Corporativo</div>
        <div className="mt-0.5 text-[11px] text-muted">
          O que a IA da B2B ON sabe sobre a sua empresa. Itens internos nunca saem daqui; só itens marcados
          “rede” podem ser usados para responder outras empresas.
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      {podeEditar && (
        <Card className="mb-4">
          <SectionLabel>Adicionar conhecimento</SectionLabel>
          <form onSubmit={criar} className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <select name="tipo" required className="rounded-md border border-border bg-transparent px-2 py-1.5 text-[12px]">
                {tipos.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {tipo}
                  </option>
                ))}
              </select>
              <select name="visibilidade" className="rounded-md border border-border bg-transparent px-2 py-1.5 text-[12px]">
                <option value="interno">Interno (só a sua empresa)</option>
                <option value="rede">Rede (pode responder outras empresas)</option>
              </select>
            </div>
            <Input name="titulo" required placeholder="Título (ex.: Case Hospital São Lucas)" />
            <textarea
              name="conteudo"
              required
              rows={3}
              placeholder="Conteúdo"
              className="rounded-md border border-border bg-transparent p-2 text-[12px]"
            />
            <Input name="fonte" placeholder="Fonte (opcional: link, documento, responsável)" />
            <Button type="submit" className="self-start">
              Salvar
            </Button>
          </form>
        </Card>
      )}

      <Card className="mb-4">
        <SectionLabel>Conhecimento ({itens.length})</SectionLabel>
        {itens.length === 0 && <div className="text-[12px] text-muted">Nenhum item cadastrado.</div>}
        {itens.map((item) => (
          <div key={item.id} className="border-b border-border py-2 text-[12px]">
            <div className="flex items-center justify-between">
              <div>
                <span className="mr-2 rounded bg-black/20 px-1.5 py-0.5 text-[10px] uppercase">{item.tipo}</span>
                <span className="font-semibold">{item.titulo}</span>
                <span className={`ml-2 text-[10px] ${item.visibilidade === "rede" ? "text-cyan" : "text-muted"}`}>
                  {item.visibilidade === "rede" ? "compartilhável com a rede" : "interno"}
                </span>
              </div>
              {podeEditar && (
                <Button size="sm" variant="ghost" onClick={() => arquivar(item.id)}>
                  Arquivar
                </Button>
              )}
            </div>
            <div className="mt-1 whitespace-pre-line text-muted">{item.conteudo}</div>
            {item.fonte && <div className="mt-1 text-[10px] text-muted">Fonte: {item.fonte}</div>}
          </div>
        ))}
      </Card>

      <Card className="mb-4">
        <div className="mb-2 flex items-center justify-between">
          <SectionLabel>Perfil da empresa (consolidado)</SectionLabel>
          <Button size="sm" onClick={consolidarPerfil}>
            Consolidar agora
          </Button>
        </div>
        {!perfil && <div className="text-[12px] text-muted">Consolide para ver o perfil calculado a partir do seu histórico.</div>}
        {perfil && (
          <div className="grid grid-cols-1 gap-2 text-[12px] sm:grid-cols-2">
            {Object.entries(ROTULOS_PERFIL).map(([chave, rotulo]) => (
              <div key={chave}>
                <div className="text-[10px] text-muted uppercase">{rotulo}</div>
                <div>{formatar(perfil.dados[chave])}</div>
                {perfil.fontes[chave] && <div className="text-[10px] text-muted">{perfil.fontes[chave]}</div>}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <SectionLabel>Agentes da B2B ON Intelligence</SectionLabel>
        <div className="flex flex-wrap gap-2 text-[11px]">
          {agentes.map((agente) => (
            <span
              key={agente.id}
              className={`rounded-full border px-2 py-0.5 ${agente.status === "ATIVO" ? "border-green text-green" : "border-border text-muted"}`}
              title={agente.status === "ATIVO" ? "Ativo" : "Planejado — ainda não disponível"}
            >
              {agente.nome}
              {agente.status === "PLANEJADO" && " · em breve"}
            </span>
          ))}
        </div>
      </Card>
    </div>
  );
}
