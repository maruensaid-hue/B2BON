import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Oferta {
  id: number;
  nome: string;
  descricao: string;
  diferenciais: string[];
  provas_sociais: string[];
  ativo: boolean;
}

interface ConfiguracaoComunicacao {
  id: number;
  tom: string;
  restricoes: string[];
}

function paraLista(texto: string): string[] {
  return texto
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function paraListaPorLinha(texto: string): string[] {
  return texto
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function OpcoesOferta({
  oferta,
  onEditar,
  onAtivar,
  onDesativar,
  onExcluir,
}: {
  oferta: Oferta;
  onEditar: () => void;
  onAtivar: () => void;
  onDesativar: () => void;
  onExcluir: () => void;
}) {
  const [aberto, setAberto] = useState(false);
  const [confirmandoExclusao, setConfirmandoExclusao] = useState(false);

  if (confirmandoExclusao) {
    return (
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="text-muted">Excluir "{oferta.nome}"?</span>
        <Button size="sm" variant="danger" onClick={onExcluir}>
          Confirmar
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setConfirmandoExclusao(false)}>
          Cancelar
        </Button>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setAberto((atual) => !atual)}
        className="rounded-md px-1.5 py-0.5 text-[13px] text-muted hover:bg-surf2 hover:text-text"
        aria-label="Opções da oferta"
      >
        ⋮
      </button>
      {aberto && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setAberto(false)} />
          <div className="absolute right-0 z-20 mt-1 flex w-44 flex-col overflow-hidden rounded-lg border border-border bg-surf shadow-lg">
            <button
              type="button"
              className="px-3 py-2 text-left text-[12px] hover:bg-surf2"
              onClick={() => {
                setAberto(false);
                onEditar();
              }}
            >
              Editar
            </button>
            {oferta.ativo ? (
              <button
                type="button"
                className="px-3 py-2 text-left text-[12px] hover:bg-surf2"
                onClick={() => {
                  setAberto(false);
                  onDesativar();
                }}
              >
                Desativar
              </button>
            ) : (
              <button
                type="button"
                className="px-3 py-2 text-left text-[12px] hover:bg-surf2"
                onClick={() => {
                  setAberto(false);
                  onAtivar();
                }}
              >
                Ativar
              </button>
            )}
            <button
              type="button"
              className="px-3 py-2 text-left text-[12px] text-red hover:bg-red/10"
              onClick={() => {
                setAberto(false);
                setConfirmandoExclusao(true);
              }}
            >
              Excluir
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function Configuracao() {
  const [ofertas, setOfertas] = useState<Oferta[]>([]);
  const [comunicacao, setComunicacao] = useState<ConfiguracaoComunicacao | null>(null);
  const [ofertaEmEdicaoId, setOfertaEmEdicaoId] = useState<number | null>(null);
  const [salvandoOferta, setSalvandoOferta] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  const ofertaEmEdicao = ofertas.find((oferta) => oferta.id === ofertaEmEdicaoId) ?? null;

  async function carregarTudo() {
    try {
      const [ofertasResp, comunicacaoResp] = await Promise.all([
        api.get<Oferta[]>("/ofertas"),
        api.get<ConfiguracaoComunicacao | null>("/comunicacao"),
      ]);
      setOfertas(ofertasResp);
      setComunicacao(comunicacaoResp);
    } catch {
      setErro("Não foi possível carregar a configuração.");
    }
  }

  useEffect(() => {
    carregarTudo();
  }, []);

  async function salvarOferta(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvandoOferta) return;
    const form = new FormData(event.currentTarget);
    const dados = {
      nome: String(form.get("nome")),
      descricao: String(form.get("descricao")),
      diferenciais: paraListaPorLinha(String(form.get("diferenciais") ?? "")),
      provas_sociais: paraListaPorLinha(String(form.get("provas_sociais") ?? "")),
    };
    setSalvandoOferta(true);
    setErro(null);
    try {
      if (ofertaEmEdicaoId !== null) {
        await api.put(`/ofertas/${ofertaEmEdicaoId}`, dados);
        setMensagem("Oferta atualizada.");
        setOfertaEmEdicaoId(null);
      } else {
        await api.post("/ofertas", dados);
        setMensagem("Oferta salva.");
      }
      event.currentTarget.reset();
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a oferta.");
    } finally {
      setSalvandoOferta(false);
    }
  }

  async function ativarOferta(id: number) {
    setErro(null);
    try {
      await api.post(`/ofertas/${id}/ativar`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível ativar a oferta.");
    }
  }

  async function desativarOferta(id: number) {
    setErro(null);
    try {
      await api.post(`/ofertas/${id}/desativar`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível desativar a oferta.");
    }
  }

  async function excluirOferta(id: number) {
    setErro(null);
    try {
      await api.delete(`/ofertas/${id}`);
      if (ofertaEmEdicaoId === id) setOfertaEmEdicaoId(null);
      setMensagem("Oferta excluída.");
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir a oferta.");
    }
  }

  async function salvarComunicacao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.put("/comunicacao", {
        tom: String(form.get("tom")),
        restricoes: paraLista(String(form.get("restricoes") ?? "")),
      });
      setMensagem("Comunicação salva.");
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a comunicação.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Configuração</div>
        <div className="mt-0.5 text-[11px] text-muted">
          Oferta e comunicação — pré-requisitos para o motor de prospecção gerar cadências
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card className="mb-4">
        <SectionLabel>Oferta</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Tudo que você preencher aqui — descrição, diferenciais e provas
          sociais — entra literalmente no texto que a IA usa para escrever
          cada mensagem de e-mail e WhatsApp da cadência. Não é um campo só
          descritivo/interno: escreva como se fosse a matéria-prima do
          discurso de vendas, não um resumo para uso interno.
        </div>
        <div className="mb-3 flex flex-col gap-1.5">
          {ofertas.map((oferta) => (
            <div key={oferta.id} className="flex items-center justify-between text-[12px]">
              <span className="font-semibold">{oferta.nome}</span>
              <div className="flex items-center gap-2">
                <Badge tone={oferta.ativo ? "green" : "muted"}>{oferta.ativo ? "ativa" : "inativa"}</Badge>
                <OpcoesOferta
                  oferta={oferta}
                  onEditar={() => setOfertaEmEdicaoId(oferta.id)}
                  onAtivar={() => ativarOferta(oferta.id)}
                  onDesativar={() => desativarOferta(oferta.id)}
                  onExcluir={() => excluirOferta(oferta.id)}
                />
              </div>
            </div>
          ))}
          {ofertas.length === 0 && <div className="text-[12px] text-muted">Nenhuma oferta cadastrada ainda.</div>}
        </div>
        <form key={ofertaEmEdicaoId ?? "nova"} onSubmit={salvarOferta} className="flex flex-col gap-3">
          {ofertaEmEdicao && (
            <div className="flex items-center justify-between rounded-lg bg-surf2 px-3 py-2 text-[11px] text-muted">
              Editando "{ofertaEmEdicao.nome}"
              <button
                type="button"
                className="text-cyan hover:underline"
                onClick={() => setOfertaEmEdicaoId(null)}
              >
                Cancelar edição
              </button>
            </div>
          )}
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
            <Input
              name="nome"
              required
              defaultValue={ofertaEmEdicao?.nome}
              placeholder="Ex.: Adequação LGPD completa"
            />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Descrição (usada pela IA para escrever as mensagens)
            </div>
            <Textarea
              name="descricao"
              required
              rows={3}
              defaultValue={ofertaEmEdicao?.descricao}
              placeholder="O que é a oferta e o problema que ela resolve — a IA usa esse texto como base direta do discurso de vendas."
            />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Diferenciais (um por linha — também entram na mensagem)
            </div>
            <Textarea
              name="diferenciais"
              rows={3}
              defaultValue={ofertaEmEdicao?.diferenciais.join("\n")}
              placeholder={"RIPD incluso\nDPO terceirizado\nResposta em 48h (mesmo em picos de demanda)"}
            />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Provas sociais (uma por linha — também entram na mensagem)
            </div>
            <Textarea
              name="provas_sociais"
              rows={3}
              defaultValue={ofertaEmEdicao?.provas_sociais.join("\n")}
              placeholder={"+40 clientes atendidos\nCertificação X (auditada anualmente)"}
            />
          </div>
          <Button type="submit" disabled={salvandoOferta} className="w-full justify-center">
            {salvandoOferta
              ? "Salvando..."
              : ofertaEmEdicao
                ? "Salvar alterações"
                : "Cadastrar oferta"}
          </Button>
        </form>
      </Card>

      <Card>
        <SectionLabel>Tom e restrições de comunicação</SectionLabel>
        <form onSubmit={salvarComunicacao} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tom</div>
            <Input name="tom" required defaultValue={comunicacao?.tom} placeholder="Ex.: consultivo" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Nunca mencionar (separado por vírgula)
            </div>
            <Input
              name="restricoes"
              defaultValue={comunicacao?.restricoes.join(", ")}
              placeholder="preço, concorrentes, desconto"
            />
          </div>
          <Button type="submit" className="w-full justify-center">
            Salvar
          </Button>
        </form>
      </Card>
    </div>
  );
}
