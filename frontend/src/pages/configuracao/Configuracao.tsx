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

export function Configuracao() {
  const [ofertas, setOfertas] = useState<Oferta[]>([]);
  const [comunicacao, setComunicacao] = useState<ConfiguracaoComunicacao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

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
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/ofertas", {
        nome: String(form.get("nome")),
        descricao: String(form.get("descricao")),
        diferenciais: paraLista(String(form.get("diferenciais") ?? "")),
        provas_sociais: paraLista(String(form.get("provas_sociais") ?? "")),
      });
      event.currentTarget.reset();
      setMensagem("Oferta salva.");
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a oferta.");
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

  const ofertaAtiva = ofertas.find((oferta) => oferta.ativo);

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
              <Badge tone={oferta.ativo ? "green" : "muted"}>{oferta.ativo ? "ativa" : "inativa"}</Badge>
            </div>
          ))}
          {ofertas.length === 0 && <div className="text-[12px] text-muted">Nenhuma oferta cadastrada ainda.</div>}
        </div>
        <form onSubmit={salvarOferta} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
            <Input name="nome" required placeholder="Ex.: Adequação LGPD completa" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Descrição (usada pela IA para escrever as mensagens)
            </div>
            <Textarea name="descricao" required rows={3} placeholder="O que é a oferta e o problema que ela resolve — a IA usa esse texto como base direta do discurso de vendas." />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Diferenciais (separados por vírgula — também entram na mensagem)
            </div>
            <Input name="diferenciais" placeholder="RIPD incluso, DPO terceirizado, resposta em 48h" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Provas sociais (separadas por vírgula — também entram na mensagem)
            </div>
            <Input name="provas_sociais" placeholder="+40 clientes atendidos, certificação X" />
          </div>
          <Button type="submit" className="w-full justify-center">
            {ofertaAtiva ? "Cadastrar nova oferta" : "Cadastrar oferta"}
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
