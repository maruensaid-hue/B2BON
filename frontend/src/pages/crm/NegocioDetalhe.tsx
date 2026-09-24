import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ListaAtividades, type Atividade } from "@/components/ListaAtividades";
import { PropostasNegocio } from "@/components/PropostasNegocio";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { ContaDetalheModal } from "@/pages/prospeccao/ContaDetalheModal";
import { api, ApiError } from "@/lib/api";

const ROTULOS_PAPEL_COMITE_COMPRA: Record<string, string> = {
  DECISION_MAKER: "Decisor final",
  ECONOMIC_BUYER: "Comprador econômico",
  CHAMPION: "Patrocinador interno",
  INFLUENCER: "Influenciador",
  TECHNICAL_EVALUATOR: "Avaliador técnico",
  PROCUREMENT: "Compras",
  LEGAL: "Jurídico",
  BLOCKER: "Bloqueador",
  UNKNOWN: "Desconhecido",
};

interface Negocio {
  id: number;
  conta_id: number;
  conta_nome: string;
  decisor_id: number | null;
  decisor_nome: string | null;
  estagio_id: number;
  oferta_id: number | null;
  nome: string;
  valor: number;
  probabilidade: number;
}

interface Conta {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  segmento: string | null;
  porte: string | null;
  regiao: string | null;
}

interface Decisor {
  id: number;
  nome: string;
  cargo: string | null;
  papel_confirmado: string | null;
  papel_sugerido: string | null;
}

interface OfertaResumo {
  id: number;
  nome: string;
}

/** Página expandida do negócio (raio-X 2026-09-22) — alternativa em tela
 * inteira ao modal condensado de `Kanban.tsx` (link "⤢ Abrir tela
 * completa"), mesmo padrão de rota própria já usado em
 * `LeadsAcoesConta.tsx`. Não existe `GET /crm/negocios/{id}` — reaproveita
 * a listagem completa e filtra pelo id, mesmo truque que o próprio
 * Kanban já usa hoje pro deep-link `?negocio_id=`. */
export function NegocioDetalhe() {
  const { id } = useParams<{ id: string }>();
  const negocioId = Number(id);

  const [negocio, setNegocio] = useState<Negocio | null>(null);
  const [conta, setConta] = useState<Conta | null>(null);
  const [decisoresDaConta, setDecisoresDaConta] = useState<Decisor[]>([]);
  const [ofertas, setOfertas] = useState<OfertaResumo[]>([]);
  const [atividades, setAtividades] = useState<Atividade[]>([]);
  const [meetingBrief, setMeetingBrief] = useState<string | null>(null);
  const [gerandoBrief, setGerandoBrief] = useState(false);
  const [contaModalAberta, setContaModalAberta] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [naoEncontrado, setNaoEncontrado] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      const negocios = await api.get<Negocio[]>("/crm/negocios");
      const encontrado = negocios.find((item) => item.id === negocioId);
      if (!encontrado) {
        setNaoEncontrado(true);
        return;
      }
      setNegocio(encontrado);
      const [contaResp, decisoresResp, atividadesResp, ofertasResp] = await Promise.all([
        api.get<Conta>(`/contas/${encontrado.conta_id}`),
        api.get<Decisor[]>(`/contas/${encontrado.conta_id}/decisores`),
        api.get<Atividade[]>(`/crm/negocios/${negocioId}/atividades`),
        api.get<OfertaResumo[]>("/ofertas"),
      ]);
      setConta(contaResp);
      setDecisoresDaConta(decisoresResp);
      setAtividades(atividadesResp);
      setOfertas(ofertasResp);
    } catch {
      setNaoEncontrado(true);
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [negocioId]);

  async function salvarEdicao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!negocio || salvando) return;
    const form = new FormData(event.currentTarget);
    setSalvando(true);
    setErro(null);
    try {
      const decisorId = Number(form.get("decisor_id"));
      if (!decisorId) {
        setErro("Selecione o contato responsável pela oportunidade.");
        return;
      }
      await api.put(`/crm/negocios/${negocio.id}`, {
        nome: String(form.get("nome")),
        valor: Number(form.get("valor") || 0),
        probabilidade: Number(form.get("probabilidade") || 50),
        decisor_id: decisorId,
        oferta_id: Number(form.get("oferta_id") || 0) || null,
      });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar as alterações do negócio.");
    } finally {
      setSalvando(false);
    }
  }

  async function gerarMeetingBrief() {
    if (!negocio || gerandoBrief) return;
    setGerandoBrief(true);
    setErro(null);
    try {
      const resultado = await api.post<{ brief: string }>(`/crm/negocios/${negocio.id}/meeting-brief`);
      setMeetingBrief(resultado.brief);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível preparar o briefing da reunião.");
    } finally {
      setGerandoBrief(false);
    }
  }

  async function registrarAtividade(tipo: string, descricao: string) {
    if (!negocio) return;
    await api.post(`/crm/negocios/${negocio.id}/atividades`, { tipo, descricao });
    setAtividades(await api.get<Atividade[]>(`/crm/negocios/${negocio.id}/atividades`));
  }

  if (carregando) {
    return <div className="p-5.5 text-[12px] text-muted">Carregando...</div>;
  }

  if (naoEncontrado || !negocio) {
    return (
      <div className="p-5.5">
        <Link to="/crm" className="text-[12px] text-cyan hover:underline">
          ← Voltar para o Pipeline
        </Link>
        <div className="mt-4 text-[12px] text-muted">Negócio não encontrado.</div>
      </div>
    );
  }

  return (
    <div className="p-5.5">
      <Link to="/crm" className="mb-4 inline-block text-[12px] text-cyan hover:underline">
        ← Voltar para o Pipeline
      </Link>

      <div className="mb-5">
        <div className="font-head text-xl font-bold">{negocio.nome}</div>
        <div className="mt-0.5 text-[11px] text-muted">
          {negocio.conta_nome} · R$ {negocio.valor.toLocaleString("pt-BR")}
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <SectionLabel>Detalhes do negócio</SectionLabel>
          <div className="flex items-center justify-between text-[11px] text-muted">
            <span>
              Empresa: <span className="font-semibold text-text">{negocio.conta_nome}</span>
            </span>
            <button type="button" className="text-cyan hover:underline" onClick={() => setContaModalAberta(true)}>
              Editar empresa / enriquecer contatos
            </button>
          </div>
          <form onSubmit={salvarEdicao} className="mt-3 flex flex-col gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do negócio</div>
              <Input name="nome" required defaultValue={negocio.nome} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Valor (R$)</div>
              <Input name="valor" type="number" step="0.01" defaultValue={negocio.valor} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Probabilidade (%)</div>
              <Input name="probabilidade" type="number" min={0} max={100} defaultValue={negocio.probabilidade} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Contato responsável</div>
              <Select name="decisor_id" required defaultValue={negocio.decisor_id ?? ""}>
                <option value="" disabled>
                  Selecione o contato
                </option>
                {decisoresDaConta.map((decisor) => (
                  <option key={decisor.id} value={decisor.id}>
                    {decisor.nome}
                  </option>
                ))}
              </Select>
            </div>
            {ofertas.length > 0 && (
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Oferta (opcional)</div>
                <Select name="oferta_id" defaultValue={negocio.oferta_id ?? ""}>
                  <option value="">Nenhuma</option>
                  {ofertas.map((oferta) => (
                    <option key={oferta.id} value={oferta.id}>
                      {oferta.nome}
                    </option>
                  ))}
                </Select>
              </div>
            )}
            <Button type="submit" disabled={salvando} className="w-full justify-center">
              {salvando ? "Salvando..." : "Salvar alterações"}
            </Button>
          </form>
        </Card>

        <Card>
          <SectionLabel>Sobre a conta</SectionLabel>
          {conta && (
            <div className="flex flex-col gap-2 text-[12px]">
              <div>
                <span className="text-muted">Empresa: </span>
                <span className="text-text">{conta.nome_fantasia ?? conta.nome}</span>
              </div>
              <div className="flex flex-wrap gap-3 text-[11px] text-muted">
                <span>Segmento: {conta.segmento ?? "—"}</span>
                <span>Porte: {conta.porte ?? "—"}</span>
                <span>Região: {conta.regiao ?? "—"}</span>
              </div>
              <div className="mt-1.5 text-[10px] tracking-wide text-muted uppercase">Decisores</div>
              {decisoresDaConta.length === 0 ? (
                <div className="text-[11px] text-muted">Nenhum decisor cadastrado ainda.</div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {decisoresDaConta.map((decisor) => (
                    <div key={decisor.id} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="text-text">
                        {decisor.nome}
                        {decisor.cargo && <span className="text-muted"> — {decisor.cargo}</span>}
                      </span>
                      {decisor.papel_confirmado ? (
                        <Badge tone="cyan">{ROTULOS_PAPEL_COMITE_COMPRA[decisor.papel_confirmado] ?? decisor.papel_confirmado}</Badge>
                      ) : decisor.papel_sugerido && decisor.papel_sugerido !== "UNKNOWN" ? (
                        <Badge tone="muted">
                          Sugestão: {ROTULOS_PAPEL_COMITE_COMPRA[decisor.papel_sugerido] ?? decisor.papel_sugerido}
                        </Badge>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>

        <Card>
          <SectionLabel>Preparar reunião</SectionLabel>
          <button type="button" onClick={gerarMeetingBrief} disabled={gerandoBrief} className="text-[11px] text-cyan">
            {gerandoBrief ? "Preparando..." : "🧠 Preparar reunião"}
          </button>
          <div className="mt-2 rounded-md bg-surf2 p-2 text-[11px] whitespace-pre-line text-text">
            {meetingBrief ?? <span className="text-muted">Nenhum resumo gerado ainda.</span>}
          </div>
        </Card>

        <Card>
          <ListaAtividades atividades={atividades} aoRegistrar={registrarAtividade} />
        </Card>

        <Card className="lg:col-span-2">
          <PropostasNegocio negocioId={negocio.id} />
        </Card>
      </div>

      {contaModalAberta && (
        <ContaDetalheModal contaId={negocio.conta_id} onClose={() => setContaModalAberta(false)} onAtualizado={carregar} />
      )}
    </div>
  );
}
