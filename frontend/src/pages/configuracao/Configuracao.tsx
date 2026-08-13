import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/Input";
import { api, ApiError, getBlob, postFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";

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

interface ConfiguracaoWhatsApp {
  id: number;
  phone_number_id: string;
  business_account_id: string;
  access_token_mascarado: string;
}

interface StatusConexoesLinkedin {
  total: number;
  atualizado_em: string | null;
}

interface TemplateProposta {
  id: number;
  texto_introdutorio: string | null;
  logo_tipo_mime: string | null;
  termo_aceite: string | null;
  mostrar_tabela_produtos: boolean;
  mostrar_tabela_servicos: boolean;
}

interface ItemTemplateProposta {
  id: number;
  tipo: "produto" | "servico";
  ordem: number;
  descricao: string;
  valor: number | null;
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

function ListaItensTemplate({
  titulo,
  itens,
  onAdicionar,
  onRemover,
}: {
  titulo: string;
  itens: ItemTemplateProposta[];
  onAdicionar: (descricao: string, valor: number | null) => Promise<void>;
  onRemover: (id: number) => Promise<void>;
}) {
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function adicionar() {
    if (!descricao.trim() || salvando) return;
    setSalvando(true);
    try {
      await onAdicionar(descricao.trim(), valor.trim() ? Number(valor) : null);
      setDescricao("");
      setValor("");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{titulo}</div>
      <div className="mb-2 flex flex-col gap-1.5">
        {itens.map((item) => (
          <div key={item.id} className="flex items-center justify-between gap-2 text-[12px]">
            <span>
              {item.descricao}
              {item.valor !== null && <span className="text-muted"> — R${item.valor.toFixed(2)}</span>}
            </span>
            <button type="button" className="text-[11px] text-muted hover:text-red" onClick={() => onRemover(item.id)}>
              Remover
            </button>
          </div>
        ))}
        {itens.length === 0 && <div className="text-[11px] text-muted">Nenhum item cadastrado ainda.</div>}
      </div>
      <div className="flex gap-2">
        <Input
          value={descricao}
          onChange={(event) => setDescricao(event.target.value)}
          placeholder="Descrição"
          className="flex-1"
        />
        <Input
          value={valor}
          onChange={(event) => setValor(event.target.value)}
          type="number"
          step="0.01"
          placeholder="R$"
          className="w-24"
        />
        <Button type="button" size="sm" disabled={!descricao.trim() || salvando} onClick={adicionar}>
          +
        </Button>
      </div>
    </div>
  );
}

export function Configuracao() {
  const { usuario } = useAuth();
  const isGestor = usuario?.papel === "admin" || usuario?.papel === "super_admin";

  const [ofertas, setOfertas] = useState<Oferta[]>([]);
  const [comunicacao, setComunicacao] = useState<ConfiguracaoComunicacao | null>(null);
  const [whatsapp, setWhatsapp] = useState<ConfiguracaoWhatsApp | null>(null);
  const [statusLinkedin, setStatusLinkedin] = useState<StatusConexoesLinkedin | null>(null);
  const [nomeArquivoLinkedin, setNomeArquivoLinkedin] = useState<string | null>(null);
  const [conteudoCsvLinkedin, setConteudoCsvLinkedin] = useState<string | null>(null);
  const [ofertaEmEdicaoId, setOfertaEmEdicaoId] = useState<number | null>(null);
  const [salvandoOferta, setSalvandoOferta] = useState(false);
  const [salvandoWhatsapp, setSalvandoWhatsapp] = useState(false);
  const [importandoLinkedin, setImportandoLinkedin] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [templateProposta, setTemplateProposta] = useState<TemplateProposta | null>(null);
  const [itensProdutos, setItensProdutos] = useState<ItemTemplateProposta[]>([]);
  const [itensServicos, setItensServicos] = useState<ItemTemplateProposta[]>([]);
  const [logoPreviewUrl, setLogoPreviewUrl] = useState<string | null>(null);
  const [salvandoTemplateProposta, setSalvandoTemplateProposta] = useState(false);
  const [enviandoLogo, setEnviandoLogo] = useState(false);

  const ofertaEmEdicao = ofertas.find((oferta) => oferta.id === ofertaEmEdicaoId) ?? null;

  async function carregarTemplateProposta() {
    try {
      const [template, produtos, servicos] = await Promise.all([
        api.get<TemplateProposta>("/template-proposta"),
        api.get<ItemTemplateProposta[]>("/template-proposta/itens?tipo=produto"),
        api.get<ItemTemplateProposta[]>("/template-proposta/itens?tipo=servico"),
      ]);
      setTemplateProposta(template);
      setItensProdutos(produtos);
      setItensServicos(servicos);
      if (template.logo_tipo_mime) {
        const blob = await getBlob("/template-proposta/logo");
        setLogoPreviewUrl(URL.createObjectURL(blob));
      } else {
        setLogoPreviewUrl(null);
      }
    } catch {
      // Modelo de proposta é opcional — silencioso se ainda não configurado.
    }
  }

  async function carregarTudo() {
    try {
      const [ofertasResp, comunicacaoResp] = await Promise.all([
        api.get<Oferta[]>("/ofertas"),
        api.get<ConfiguracaoComunicacao | null>("/comunicacao"),
      ]);
      setOfertas(ofertasResp);
      setComunicacao(comunicacaoResp);
      setStatusLinkedin(await api.get<StatusConexoesLinkedin>("/linkedin/conexoes/status"));
      if (isGestor) {
        setWhatsapp(await api.get<ConfiguracaoWhatsApp | null>("/configuracao-whatsapp"));
      }
      await carregarTemplateProposta();
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

  async function salvarWhatsapp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvandoWhatsapp) return;
    const form = new FormData(event.currentTarget);
    const accessToken = String(form.get("access_token") ?? "").trim();
    setSalvandoWhatsapp(true);
    setErro(null);
    try {
      const salvo = await api.put<ConfiguracaoWhatsApp>("/configuracao-whatsapp", {
        phone_number_id: String(form.get("phone_number_id")),
        business_account_id: String(form.get("business_account_id")),
        access_token: accessToken || null,
      });
      setWhatsapp(salvo);
      setMensagem("WhatsApp Business salvo.");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o WhatsApp Business.");
    } finally {
      setSalvandoWhatsapp(false);
    }
  }

  async function salvarTemplateProposta(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvandoTemplateProposta) return;
    const form = new FormData(event.currentTarget);
    setSalvandoTemplateProposta(true);
    setErro(null);
    try {
      const salvo = await api.put<TemplateProposta>("/template-proposta", {
        texto_introdutorio: String(form.get("texto_introdutorio") || "") || null,
        termo_aceite: String(form.get("termo_aceite") || "") || null,
        mostrar_tabela_produtos: form.get("mostrar_tabela_produtos") === "on",
        mostrar_tabela_servicos: form.get("mostrar_tabela_servicos") === "on",
      });
      setTemplateProposta(salvo);
      setMensagem("Modelo de proposta salvo.");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o modelo de proposta.");
    } finally {
      setSalvandoTemplateProposta(false);
    }
  }

  async function enviarLogoTemplate(arquivo: File) {
    if (enviandoLogo) return;
    setEnviandoLogo(true);
    setErro(null);
    try {
      await postFile("/template-proposta/logo", arquivo);
      await carregarTemplateProposta();
      setMensagem("Logo atualizada.");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar a logo.");
    } finally {
      setEnviandoLogo(false);
    }
  }

  async function adicionarItemTemplate(tipo: "produto" | "servico", descricao: string, valor: number | null) {
    await api.post("/template-proposta/itens", { tipo, descricao, valor });
    await carregarTemplateProposta();
  }

  async function removerItemTemplate(id: number) {
    await api.delete(`/template-proposta/itens/${id}`);
    await carregarTemplateProposta();
  }

  function selecionarArquivoLinkedin(event: ChangeEvent<HTMLInputElement>) {
    const arquivo = event.target.files?.[0];
    if (!arquivo) {
      setNomeArquivoLinkedin(null);
      setConteudoCsvLinkedin(null);
      return;
    }
    const leitor = new FileReader();
    leitor.onload = () => {
      setNomeArquivoLinkedin(arquivo.name);
      setConteudoCsvLinkedin(String(leitor.result ?? ""));
    };
    leitor.readAsText(arquivo);
  }

  async function importarConexoesLinkedin() {
    if (!conteudoCsvLinkedin || importandoLinkedin) return;
    setImportandoLinkedin(true);
    setErro(null);
    try {
      const resultado = await api.post<{ total_importado: number }>("/linkedin/conexoes/importar", {
        conteudo_csv: conteudoCsvLinkedin,
      });
      setMensagem(`${resultado.total_importado} conexões importadas.`);
      setNomeArquivoLinkedin(null);
      setConteudoCsvLinkedin(null);
      setStatusLinkedin(await api.get<StatusConexoesLinkedin>("/linkedin/conexoes/status"));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível importar as conexões.");
    } finally {
      setImportandoLinkedin(false);
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

      <Card className="mt-4">
        <SectionLabel>Minhas conexões do LinkedIn</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Sobe o CSV de conexões que você mesmo exporta do LinkedIn
          (Configurações → Privacidade de dados → "Obter uma cópia dos seus
          dados"). O sistema usa isso só para indicar, ao mapear decisores
          de uma conta, quem já é sua conexão e quem vale sugerir conectar —
          nunca envia convite nem faz nada automaticamente no LinkedIn.
        </div>
        <div className="mb-3 text-[12px] text-muted">
          {statusLinkedin && statusLinkedin.total > 0
            ? `${statusLinkedin.total} conexões importadas${
                statusLinkedin.atualizado_em
                  ? ` em ${new Date(statusLinkedin.atualizado_em).toLocaleString("pt-BR")}`
                  : ""
              }.`
            : "Nenhuma conexão importada ainda."}
        </div>
        <div className="flex flex-col gap-3">
          <input
            type="file"
            accept=".csv"
            onChange={selecionarArquivoLinkedin}
            className="text-[12px] text-muted"
          />
          <Button
            type="button"
            disabled={!conteudoCsvLinkedin || importandoLinkedin}
            onClick={importarConexoesLinkedin}
            className="w-full justify-center"
          >
            {importandoLinkedin
              ? "Importando..."
              : nomeArquivoLinkedin
                ? `Importar conexões (${nomeArquivoLinkedin})`
                : "Importar conexões"}
          </Button>
        </div>
      </Card>

      {isGestor && (
        <Card className="mt-4">
          <SectionLabel>WhatsApp Business</SectionLabel>
          <div className="mb-3 text-[11px] text-muted">
            Conta própria da Meta para este cliente. Sem isto, o envio usa o
            número compartilhado da plataforma — se outro cliente prospectar
            mal e a Meta restringir o número compartilhado, todos que ainda
            não configuraram a própria conta são afetados junto.
          </div>
          {whatsapp && (
            <div className="mb-3 text-[12px] text-muted">
              Token atual: <span className="font-mono">{whatsapp.access_token_mascarado}</span>
            </div>
          )}
          <form key={whatsapp?.id ?? "novo"} onSubmit={salvarWhatsapp} className="flex flex-col gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Phone Number ID</div>
              <Input name="phone_number_id" required defaultValue={whatsapp?.phone_number_id} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Business Account ID</div>
              <Input name="business_account_id" required defaultValue={whatsapp?.business_account_id} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
                Access Token {whatsapp ? "(deixe em branco para manter o atual)" : ""}
              </div>
              <Input name="access_token" type="password" required={!whatsapp} placeholder="EAAG..." />
            </div>
            <Button type="submit" disabled={salvandoWhatsapp} className="w-full justify-center">
              {salvandoWhatsapp ? "Salvando..." : "Salvar WhatsApp Business"}
            </Button>
          </form>
        </Card>
      )}

      <Card className="mt-4">
        <SectionLabel>Modelo de proposta</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Parte institucional (texto, logo, termo de aceite) usada em toda
          proposta gerada automaticamente para uma oportunidade — os itens de
          produtos e serviços aqui são o padrão, mas o vendedor pode ajustá-los
          por proposta sem alterar este modelo.
        </div>

        <div className="mb-3 flex items-center gap-3">
          {logoPreviewUrl && (
            <img src={logoPreviewUrl} alt="Logo atual" className="h-10 w-auto rounded border border-border" />
          )}
          <input
            type="file"
            accept="image/png,image/jpeg"
            disabled={enviandoLogo}
            onChange={(event) => {
              const arquivo = event.target.files?.[0];
              if (arquivo) enviarLogoTemplate(arquivo);
              event.target.value = "";
            }}
            className="text-[11px] text-muted"
          />
        </div>

        <form key={templateProposta?.id ?? "novo"} onSubmit={salvarTemplateProposta} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Texto introdutório</div>
            <Textarea
              name="texto_introdutorio"
              rows={3}
              defaultValue={templateProposta?.texto_introdutorio ?? ""}
              placeholder="Apresentação da empresa que abre toda proposta gerada."
            />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Termo de aceite</div>
            <Textarea
              name="termo_aceite"
              rows={3}
              defaultValue={templateProposta?.termo_aceite ?? ""}
              placeholder="Texto legal/condições que fecha a proposta."
            />
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-1.5 text-[12px] text-muted">
              <input
                type="checkbox"
                name="mostrar_tabela_produtos"
                defaultChecked={templateProposta?.mostrar_tabela_produtos ?? true}
              />
              Mostrar tabela de produtos
            </label>
            <label className="flex items-center gap-1.5 text-[12px] text-muted">
              <input
                type="checkbox"
                name="mostrar_tabela_servicos"
                defaultChecked={templateProposta?.mostrar_tabela_servicos ?? true}
              />
              Mostrar tabela de serviços
            </label>
          </div>
          <Button type="submit" disabled={salvandoTemplateProposta} className="w-full justify-center">
            {salvandoTemplateProposta ? "Salvando..." : "Salvar modelo"}
          </Button>
        </form>

        <div className="mt-4 flex flex-col gap-4">
          <ListaItensTemplate
            titulo="Produtos"
            itens={itensProdutos}
            onAdicionar={(descricao, valor) => adicionarItemTemplate("produto", descricao, valor)}
            onRemover={removerItemTemplate}
          />
          <ListaItensTemplate
            titulo="Serviços"
            itens={itensServicos}
            onAdicionar={(descricao, valor) => adicionarItemTemplate("servico", descricao, valor)}
            onRemover={removerItemTemplate}
          />
        </div>
      </Card>
    </div>
  );
}
