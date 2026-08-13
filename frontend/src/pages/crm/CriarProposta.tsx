import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { api, ApiError, getBlob } from "@/lib/api";

interface Negocio {
  id: number;
  conta_id: number;
  conta_nome: string;
  nome: string;
  valor: number;
}

interface TemplateProposta {
  texto_introdutorio: string | null;
  termo_aceite: string | null;
  mostrar_tabela_produtos: boolean;
  mostrar_tabela_servicos: boolean;
}

interface ItemTemplateProposta {
  descricao: string;
  valor: number | null;
}

interface ItemProposta {
  descricao: string;
  valor: number | null;
}

interface PropostaNegocio {
  id: number;
  versao: number;
  nome_arquivo: string;
}

function ListaItensEditavel({
  titulo,
  itens,
  onAlterar,
}: {
  titulo: string;
  itens: ItemProposta[];
  onAlterar: (itens: ItemProposta[]) => void;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[10px] tracking-wide text-muted uppercase">{titulo}</div>
        <button
          type="button"
          className="text-[11px] text-cyan hover:underline"
          onClick={() => onAlterar([...itens, { descricao: "", valor: null }])}
        >
          + Adicionar item
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {itens.map((item, indice) => (
          <div key={indice} className="flex gap-2">
            <Input
              value={item.descricao}
              placeholder="Descrição"
              onChange={(event) => {
                const proximos = [...itens];
                proximos[indice] = { ...item, descricao: event.target.value };
                onAlterar(proximos);
              }}
              className="flex-1"
            />
            <Input
              value={item.valor ?? ""}
              type="number"
              step="0.01"
              placeholder="R$"
              onChange={(event) => {
                const proximos = [...itens];
                proximos[indice] = { ...item, valor: event.target.value ? Number(event.target.value) : null };
                onAlterar(proximos);
              }}
              className="w-32 flex-shrink-0"
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onAlterar(itens.filter((_, i) => i !== indice))}
            >
              Remover
            </Button>
          </div>
        ))}
        {itens.length === 0 && <div className="text-[11px] text-muted">Nenhum item ainda — clique em "Adicionar item".</div>}
      </div>
    </div>
  );
}

export function CriarProposta() {
  const [searchParams] = useSearchParams();
  const negocioIdPreSelecionado = Number(searchParams.get("negocio_id")) || null;
  const [negocios, setNegocios] = useState<Negocio[]>([]);
  const [negocioId, setNegocioId] = useState<number | null>(null);
  const [carregandoTemplate, setCarregandoTemplate] = useState(false);
  const [textoIntrodutorio, setTextoIntrodutorio] = useState("");
  const [termoAceite, setTermoAceite] = useState("");
  const [mostrarProdutos, setMostrarProdutos] = useState(true);
  const [mostrarServicos, setMostrarServicos] = useState(true);
  const [itensProdutos, setItensProdutos] = useState<ItemProposta[]>([]);
  const [itensServicos, setItensServicos] = useState<ItemProposta[]>([]);
  const [gerando, setGerando] = useState(false);
  const [propostaGerada, setPropostaGerada] = useState<PropostaNegocio | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Negocio[]>("/crm/negocios")
      .then((resultado) => {
        setNegocios(resultado);
        if (negocioIdPreSelecionado && resultado.some((n) => n.id === negocioIdPreSelecionado)) {
          selecionarNegocio(negocioIdPreSelecionado);
        }
      })
      .catch(() => setErro("Não foi possível carregar as oportunidades."));
  }, []);

  const negocioSelecionado = negocios.find((n) => n.id === negocioId) ?? null;

  async function selecionarNegocio(id: number) {
    setNegocioId(id);
    setPropostaGerada(null);
    setErro(null);
    setCarregandoTemplate(true);
    try {
      const [template, produtos, servicos] = await Promise.all([
        api.get<TemplateProposta>("/template-proposta"),
        api.get<ItemTemplateProposta[]>("/template-proposta/itens?tipo=produto"),
        api.get<ItemTemplateProposta[]>("/template-proposta/itens?tipo=servico"),
      ]);
      setTextoIntrodutorio(template.texto_introdutorio ?? "");
      setTermoAceite(template.termo_aceite ?? "");
      setMostrarProdutos(template.mostrar_tabela_produtos);
      setMostrarServicos(template.mostrar_tabela_servicos);
      setItensProdutos(produtos.map((item) => ({ descricao: item.descricao, valor: item.valor })));
      setItensServicos(servicos.map((item) => ({ descricao: item.descricao, valor: item.valor })));
    } catch {
      setErro("Não foi possível carregar o modelo de proposta.");
    } finally {
      setCarregandoTemplate(false);
    }
  }

  async function gerar() {
    if (!negocioId || gerando) return;
    setGerando(true);
    setErro(null);
    try {
      const proposta = await api.post<PropostaNegocio>(`/crm/negocios/${negocioId}/propostas/gerar`, {
        texto_introdutorio: textoIntrodutorio,
        termo_aceite: termoAceite,
        mostrar_tabela_produtos: mostrarProdutos,
        mostrar_tabela_servicos: mostrarServicos,
        itens_produtos: itensProdutos,
        itens_servicos: itensServicos,
      });
      setPropostaGerada(proposta);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar a proposta.");
    } finally {
      setGerando(false);
    }
  }

  async function baixar() {
    if (!negocioId || !propostaGerada) return;
    try {
      const blob = await getBlob(`/crm/negocios/${negocioId}/propostas/${propostaGerada.id}/download`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = propostaGerada.nome_arquivo;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setErro("Não foi possível baixar a proposta.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Criar Proposta</div>
        <div className="mt-0.5 text-[11px] text-muted">
          Gera uma nova versão de proposta em PDF para a oportunidade escolhida — a parte institucional vem do{" "}
          <Link to="/configuracao" className="text-cyan hover:underline">
            modelo salvo em Configuração
          </Link>
          , mas tudo abaixo é editável só para esta proposta.
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card className="mb-4">
        <SectionLabel>Oportunidade</SectionLabel>
        <Select
          value={negocioId ?? ""}
          onChange={(event) => {
            const id = Number(event.target.value);
            if (id) selecionarNegocio(id);
          }}
        >
          <option value="">Selecione a oportunidade</option>
          {negocios.map((negocio) => (
            <option key={negocio.id} value={negocio.id}>
              {negocio.conta_nome} — {negocio.nome} (R${Math.round(negocio.valor / 1000)}k)
            </option>
          ))}
        </Select>
      </Card>

      {carregandoTemplate && <div className="text-[12px] text-muted">Carregando modelo...</div>}

      {negocioSelecionado && !carregandoTemplate && (
        <>
          <Card className="mb-4">
            <SectionLabel>Texto e termo desta proposta</SectionLabel>
            <div className="flex flex-col gap-3">
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Texto introdutório</div>
                <Textarea rows={4} value={textoIntrodutorio} onChange={(event) => setTextoIntrodutorio(event.target.value)} />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Termo de aceite</div>
                <Textarea rows={4} value={termoAceite} onChange={(event) => setTermoAceite(event.target.value)} />
              </div>
              <div className="flex gap-4">
                <label className="flex items-center gap-1.5 text-[12px] text-muted">
                  <input type="checkbox" checked={mostrarProdutos} onChange={(event) => setMostrarProdutos(event.target.checked)} />
                  Mostrar tabela de produtos
                </label>
                <label className="flex items-center gap-1.5 text-[12px] text-muted">
                  <input type="checkbox" checked={mostrarServicos} onChange={(event) => setMostrarServicos(event.target.checked)} />
                  Mostrar tabela de serviços
                </label>
              </div>
            </div>
          </Card>

          <Card className="mb-4">
            <SectionLabel>Itens desta proposta</SectionLabel>
            <div className="flex flex-col gap-4">
              <ListaItensEditavel titulo="Produtos" itens={itensProdutos} onAlterar={setItensProdutos} />
              <ListaItensEditavel titulo="Serviços" itens={itensServicos} onAlterar={setItensServicos} />
            </div>
          </Card>

          <Card>
            {propostaGerada ? (
              <div className="flex items-center justify-between">
                <div className="text-[12px] text-green">Proposta v{propostaGerada.versao} gerada com sucesso.</div>
                <div className="flex gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={baixar}>
                    Baixar PDF
                  </Button>
                  <Button type="button" size="sm" onClick={gerar} disabled={gerando}>
                    {gerando ? "Gerando..." : "Gerar nova versão"}
                  </Button>
                </div>
              </div>
            ) : (
              <Button type="button" onClick={gerar} disabled={gerando} className="w-full justify-center">
                {gerando ? "Gerando..." : "Gerar e anexar proposta"}
              </Button>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
