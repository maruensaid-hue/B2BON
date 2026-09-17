import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConversaModal } from "@/pages/rede-social/ConversaModal";
import { PerfilEmpresaDetalheModal } from "@/pages/rede-social/PerfilEmpresaDetalheModal";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export interface PerfilEmpresa {
  tenant_id: string;
  nome_exibicao: string;
  descricao: string | null;
  setor: string | null;
  site: string | null;
  logo_url: string | null;
  capa_url: string | null;
  cnae_principal: string | null;
  porte: string | null;
  sede_cidade: string | null;
  sede_uf: string | null;
  mercados: string[];
  produtos_servicos: string[];
  tecnologias: string[];
  certificacoes: string[];
  redes_sociais: Record<string, string>;
  status_verificacao: string;
}

const ROTULO_VERIFICACAO: Record<string, { texto: string; tone: "green" | "amber" | "muted" | "red" }> = {
  verificada: { texto: "Verificada", tone: "green" },
  pendente: { texto: "Verificação em análise", tone: "amber" },
  rejeitada: { texto: "Verificação recusada", tone: "red" },
  nao_verificada: { texto: "Não verificada", tone: "muted" },
};

function listaParaTexto(valores: string[]): string {
  return valores.join(", ");
}

function textoParaLista(texto: FormDataEntryValue | null): string[] {
  return String(texto ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

interface OfertaResumo {
  nome: string;
  descricao: string;
}

interface EmpresaDiretorio {
  perfil: PerfilEmpresa;
  status_conexao: "nenhuma" | "pendente_enviada" | "pendente_recebida" | "aceita" | "bloqueada";
  oferta_principal: OfertaResumo | null;
  seguindo: boolean;
}

interface PostRedeSocial {
  id: number;
  tenant_id: string;
  empresa_nome: string;
  empresa_logo_url: string | null;
  autor_nome: string;
  texto: string;
  imagem_url: string | null;
  link_url: string | null;
  criado_em: string;
  total_comentarios: number;
  total_reacoes: number;
  eu_reagi: boolean;
}

interface ComentarioPost {
  id: number;
  post_id: number;
  tenant_id: string;
  empresa_nome: string;
  autor_nome: string;
  texto: string;
  criado_em: string;
}

interface Conexao {
  id: number;
  tenant_id_origem: string;
  tenant_id_destino: string;
  status: string;
}

interface Intent {
  id: number;
  tenant_id: string;
  empresa_nome: string;
  categoria: string;
  titulo: string;
  descricao: string;
  requisitos: string[];
  faixa_orcamento: string | null;
  localizacao: string | null;
  prazo: string | null;
  perfil_fornecedor_desejado: string | null;
  visibilidade: "publica" | "conexoes";
  status: "aberta" | "atendida" | "expirada" | "cancelada";
  criado_em: string;
  expira_em: string | null;
}

const ROTULO_STATUS_INTENT: Record<string, { texto: string; tone: "green" | "amber" | "muted" | "red" }> = {
  aberta: { texto: "Aberta", tone: "green" },
  atendida: { texto: "Atendida", tone: "muted" },
  expirada: { texto: "Expirada", tone: "amber" },
  cancelada: { texto: "Cancelada", tone: "red" },
};

interface ConviteVitrine {
  id: number;
  codigo: string;
  status: string;
  validade_em: string | null;
  tenant_id_gerado: string | null;
  criado_em: string;
  email_enviado: boolean | null;
  gratuito: boolean;
}

function toneStatusConvite(status: string): "green" | "muted" | "red" {
  if (status === "disponivel") return "green";
  if (status === "usado") return "muted";
  return "red";
}

export function RedeSocial() {
  const { usuario } = useAuth();
  const [perfil, setPerfil] = useState<PerfilEmpresa | null>(null);
  const [empresas, setEmpresas] = useState<EmpresaDiretorio[]>([]);
  const [conexoesPendentes, setConexoesPendentes] = useState<Conexao[]>([]);
  const [conexoesAtivas, setConexoesAtivas] = useState<Conexao[]>([]);
  const [posts, setPosts] = useState<PostRedeSocial[]>([]);
  const [publicando, setPublicando] = useState(false);
  const [comentariosAbertos, setComentariosAbertos] = useState<Record<number, boolean>>({});
  const [comentariosPorPost, setComentariosPorPost] = useState<Record<number, ComentarioPost[]>>({});
  const [novoComentarioTexto, setNovoComentarioTexto] = useState<Record<number, string>>({});
  const [enviandoComentarioId, setEnviandoComentarioId] = useState<number | null>(null);
  const [reagindoId, setReagindoId] = useState<number | null>(null);
  const [intents, setIntents] = useState<Intent[]>([]);
  const [publicandoIntent, setPublicandoIntent] = useState(false);
  const [modalPerfilAberto, setModalPerfilAberto] = useState(false);
  const [modalVerificacaoAberto, setModalVerificacaoAberto] = useState(false);
  const [modalConviteAberto, setModalConviteAberto] = useState(false);
  const [conversaTenantId, setConversaTenantId] = useState<string | null>(null);
  const [perfilDetalheTenantId, setPerfilDetalheTenantId] = useState<string | null>(null);
  const [convites, setConvites] = useState<ConviteVitrine[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [filtroSetor, setFiltroSetor] = useState("");
  const [filtroPorte, setFiltroPorte] = useState("");
  const [filtroMercado, setFiltroMercado] = useState("");
  const [filtroApenasVerificadas, setFiltroApenasVerificadas] = useState(false);
  const [filtroBusca, setFiltroBusca] = useState("");

  function paramsDiretorio(): string {
    const params = new URLSearchParams();
    if (filtroSetor) params.set("setor", filtroSetor);
    if (filtroPorte) params.set("porte", filtroPorte);
    if (filtroMercado) params.set("mercado", filtroMercado);
    if (filtroApenasVerificadas) params.set("apenas_verificadas", "true");
    if (filtroBusca) params.set("busca", filtroBusca);
    const texto = params.toString();
    return texto ? `?${texto}` : "";
  }

  async function carregarEmpresas() {
    try {
      setEmpresas(await api.get<EmpresaDiretorio[]>(`/rede-social/empresas${paramsDiretorio()}`));
    } catch {
      setErro("Não foi possível carregar o diretório de empresas.");
    }
  }

  async function carregarTudo() {
    try {
      const [perfilResp, empresasResp, conexoesResp, conexoesAtivasResp, postsResp, convitesResp, intentsResp] =
        await Promise.all([
          api.get<PerfilEmpresa>("/rede-social/perfil"),
          api.get<EmpresaDiretorio[]>(`/rede-social/empresas${paramsDiretorio()}`),
          api.get<Conexao[]>("/rede-social/conexoes?status=pendente"),
          api.get<Conexao[]>("/rede-social/conexoes"),
          api.get<PostRedeSocial[]>("/rede-social/posts"),
          api.get<ConviteVitrine[]>("/convites/vitrine"),
          api.get<Intent[]>("/rede-social/intents"),
        ]);
      setPerfil(perfilResp);
      setEmpresas(empresasResp);
      setConexoesPendentes(conexoesResp);
      setConexoesAtivas(conexoesAtivasResp);
      setPosts(postsResp);
      setConvites(convitesResp);
      setIntents(intentsResp);
    } catch {
      setErro("Não foi possível carregar a Rede Social.");
    }
  }

  useEffect(() => {
    carregarTudo();
  }, []);

  useEffect(() => {
    carregarEmpresas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroSetor, filtroPorte, filtroMercado, filtroApenasVerificadas, filtroBusca]);

  function conexaoRecebidaDe(tenantId: string): Conexao | undefined {
    return conexoesPendentes.find(
      (conexao) => conexao.tenant_id_origem === tenantId && conexao.tenant_id_destino === usuario?.tenant_id,
    );
  }

  function conexaoComTenant(tenantId: string): Conexao | undefined {
    return conexoesAtivas.find(
      (conexao) => conexao.tenant_id_origem === tenantId || conexao.tenant_id_destino === tenantId,
    );
  }

  async function salvarPerfil(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.put("/rede-social/perfil", {
        nome_exibicao: String(form.get("nome_exibicao")),
        descricao: String(form.get("descricao") || "") || null,
        setor: String(form.get("setor") || "") || null,
        site: String(form.get("site") || "") || null,
        logo_url: String(form.get("logo_url") || "") || null,
        capa_url: String(form.get("capa_url") || "") || null,
        cnae_principal: String(form.get("cnae_principal") || "") || null,
        porte: String(form.get("porte") || "") || null,
        sede_cidade: String(form.get("sede_cidade") || "") || null,
        sede_uf: String(form.get("sede_uf") || "") || null,
        mercados: textoParaLista(form.get("mercados")),
        produtos_servicos: textoParaLista(form.get("produtos_servicos")),
        tecnologias: textoParaLista(form.get("tecnologias")),
        certificacoes: textoParaLista(form.get("certificacoes")),
        redes_sociais: form.get("linkedin") ? { linkedin: String(form.get("linkedin")) } : {},
      });
      setModalPerfilAberto(false);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o perfil.");
    }
  }

  async function solicitarVerificacao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setErro(null);
    try {
      await api.post("/verificacao-empresa", { email_verificacao: String(form.get("email_verificacao")) });
      setModalVerificacaoAberto(false);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível solicitar a verificação.");
    }
  }

  async function conectar(tenantId: string) {
    try {
      await api.post("/rede-social/conexoes", { tenant_id_destino: tenantId });
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível solicitar a conexão.");
    }
  }

  async function responder(conexaoId: number, aceitar: boolean) {
    try {
      await api.put(`/rede-social/conexoes/${conexaoId}`, { aceitar });
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível responder à conexão.");
    }
  }

  async function alternarSeguir(tenantId: string, jaSegue: boolean) {
    try {
      if (jaSegue) {
        await api.delete(`/rede-social/seguir/${tenantId}`);
      } else {
        await api.post("/rede-social/seguir", { tenant_id_seguido: tenantId });
      }
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível atualizar quem você segue.");
    }
  }

  async function bloquearEmpresa(tenantId: string) {
    try {
      await api.post(`/rede-social/bloquear/${tenantId}`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível bloquear esta empresa.");
    }
  }

  async function desbloquearConexao(conexaoId: number) {
    try {
      await api.post(`/rede-social/conexoes/${conexaoId}/desbloquear`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível desbloquear esta empresa.");
    }
  }

  async function desconectarConexao(conexaoId: number) {
    try {
      await api.post(`/rede-social/conexoes/${conexaoId}/desconectar`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível desconectar desta empresa.");
    }
  }

  async function publicarPost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (publicando) return;
    const form = event.currentTarget;
    const dados = new FormData(form);
    const texto = String(dados.get("texto") ?? "").trim();
    if (!texto) return;
    setPublicando(true);
    setErro(null);
    try {
      await api.post("/rede-social/posts", {
        texto,
        imagem_url: String(dados.get("imagem_url") || "") || null,
        link_url: String(dados.get("link_url") || "") || null,
      });
      form.reset();
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível publicar o post.");
    } finally {
      setPublicando(false);
    }
  }

  async function excluirPost(postId: number) {
    try {
      await api.delete(`/rede-social/posts/${postId}`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir o post.");
    }
  }

  async function reagirPost(postId: number) {
    if (reagindoId !== null) return;
    setReagindoId(postId);
    try {
      const resultado = await api.post<{ reagiu: boolean; total: number }>(`/rede-social/posts/${postId}/reagir`);
      setPosts((atual) =>
        atual.map((post) =>
          post.id === postId ? { ...post, eu_reagi: resultado.reagiu, total_reacoes: resultado.total } : post,
        ),
      );
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível reagir a este post.");
    } finally {
      setReagindoId(null);
    }
  }

  async function alternarComentarios(postId: number) {
    const abrindo = !comentariosAbertos[postId];
    setComentariosAbertos((atual) => ({ ...atual, [postId]: abrindo }));
    if (abrindo && !comentariosPorPost[postId]) {
      try {
        const comentarios = await api.get<ComentarioPost[]>(`/rede-social/posts/${postId}/comentarios`);
        setComentariosPorPost((atual) => ({ ...atual, [postId]: comentarios }));
      } catch {
        setErro("Não foi possível carregar os comentários.");
      }
    }
  }

  async function enviarComentario(postId: number) {
    const texto = (novoComentarioTexto[postId] ?? "").trim();
    if (!texto || enviandoComentarioId !== null) return;
    setEnviandoComentarioId(postId);
    try {
      const comentario = await api.post<ComentarioPost>(`/rede-social/posts/${postId}/comentarios`, { texto });
      setComentariosPorPost((atual) => ({ ...atual, [postId]: [...(atual[postId] ?? []), comentario] }));
      setNovoComentarioTexto((atual) => ({ ...atual, [postId]: "" }));
      setPosts((atual) =>
        atual.map((post) => (post.id === postId ? { ...post, total_comentarios: post.total_comentarios + 1 } : post)),
      );
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível comentar neste post.");
    } finally {
      setEnviandoComentarioId(null);
    }
  }

  async function publicarIntent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (publicandoIntent) return;
    const form = event.currentTarget;
    const dados = new FormData(form);
    const titulo = String(dados.get("titulo") ?? "").trim();
    const descricao = String(dados.get("descricao") ?? "").trim();
    if (!titulo || !descricao) return;
    setPublicandoIntent(true);
    setErro(null);
    try {
      const intent = await api.post<Intent>("/rede-social/intents", {
        categoria: String(dados.get("categoria") ?? "").trim() || "geral",
        titulo,
        descricao,
        requisitos: textoParaLista(dados.get("requisitos")),
        faixa_orcamento: String(dados.get("faixa_orcamento") || "") || null,
        localizacao: String(dados.get("localizacao") || "") || null,
        perfil_fornecedor_desejado: String(dados.get("perfil_fornecedor_desejado") || "") || null,
        visibilidade: String(dados.get("visibilidade") || "publica"),
      });
      setIntents((atual) => [intent, ...atual]);
      form.reset();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível publicar a necessidade.");
    } finally {
      setPublicandoIntent(false);
    }
  }

  async function encerrarIntent(intentId: number) {
    try {
      const atualizada = await api.post<Intent>(`/rede-social/intents/${intentId}/encerrar`);
      setIntents((atual) => atual.map((intent) => (intent.id === intentId ? atualizada : intent)));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível encerrar esta necessidade.");
    }
  }

  async function marcarIntentAtendida(intentId: number) {
    try {
      const atualizada = await api.post<Intent>(`/rede-social/intents/${intentId}/atender`);
      setIntents((atual) => atual.map((intent) => (intent.id === intentId ? atualizada : intent)));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível marcar esta necessidade como atendida.");
    }
  }

  async function gerarConviteVitrine(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setErro(null);
    setAviso(null);
    try {
      const emailDestinatario = String(form.get("email_destinatario") ?? "").trim();
      const criado = await api.post<ConviteVitrine>("/convites/vitrine", {
        validade_horas: Number(form.get("validade_horas")),
        email_destinatario: emailDestinatario || null,
        gratuito: form.get("gratuito") === "on",
      });
      if (emailDestinatario && criado.email_enviado === false) {
        setAviso(
          `Convite criado, mas o e-mail não pôde ser enviado automaticamente (envio de e-mail não está ` +
            `configurado no servidor). Use "Copiar link" e envie manualmente.`,
        );
      }
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar o convite.");
    }
  }

  async function revogarConviteVitrine(codigo: string) {
    try {
      await api.post(`/convites/vitrine/${codigo}/revogar`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível revogar o convite.");
    }
  }

  async function reativarConviteVitrine(codigo: string) {
    try {
      await api.post(`/convites/vitrine/${codigo}/reativar`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível reativar o convite.");
    }
  }

  async function excluirConviteVitrine(codigo: string) {
    try {
      await api.delete(`/convites/vitrine/${codigo}`);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir o convite.");
    }
  }

  function linkConvite(codigo: string): string {
    return `${window.location.origin}/convite-vitrine/${codigo}`;
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Rede Social</div>
          <div className="mt-0.5 text-[11px] text-muted">Perfil, diretório e mensageria B2B ON</div>
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {aviso && <div className="mb-4 text-[12px] text-amber">{aviso}</div>}

      <Card className="mb-4">
        <div className="flex items-start justify-between">
          <div>
            <SectionLabel>Meu perfil</SectionLabel>
            <div className="flex items-center gap-2">
              <div className="text-[14px] font-bold">{perfil?.nome_exibicao}</div>
              {perfil && <Badge tone={ROTULO_VERIFICACAO[perfil.status_verificacao]?.tone ?? "muted"}>{ROTULO_VERIFICACAO[perfil.status_verificacao]?.texto ?? perfil.status_verificacao}</Badge>}
            </div>
            <div className="mt-1 text-[11px] text-muted">
              {perfil?.setor ?? "Sem setor"} {perfil?.site ? `· ${perfil.site}` : ""}
            </div>
            {perfil?.descricao && <div className="mt-1 text-[11px] text-muted">{perfil.descricao}</div>}
          </div>
          <div className="flex flex-shrink-0 items-center gap-2">
            {(perfil?.status_verificacao === "nao_verificada" || perfil?.status_verificacao === "rejeitada") && (
              <Button size="sm" variant="violet" onClick={() => setModalVerificacaoAberto(true)}>
                Solicitar verificação
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => setModalPerfilAberto(true)}>
              Editar
            </Button>
          </div>
        </div>
      </Card>

      <Card className="mb-4">
        <div className="mb-2 flex items-center justify-between">
          <SectionLabel>Convites para empresas</SectionLabel>
          <Button size="sm" variant="violet" onClick={() => setModalConviteAberto(true)}>
            + Convidar empresa
          </Button>
        </div>
        <div className="mb-2 text-[11px] text-muted">
          Convide uma empresa parceira para entrar na Rede Social — ela cria um acesso próprio, sem virar cliente
          do CRM/MAP/PREDATOR até fazer upgrade de plano.
        </div>
        <div className="flex flex-col gap-1.5">
          {convites.map((convite) => (
            <div key={convite.id} className="flex items-center justify-between text-[12px]">
              <div className="flex items-center gap-2">
                <span className="font-head font-bold tracking-wide">{convite.codigo}</span>
                <Badge tone={toneStatusConvite(convite.status)}>{convite.status}</Badge>
                {convite.gratuito && <Badge tone="violet">gratuito</Badge>}
              </div>
              {convite.status === "disponivel" && (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => navigator.clipboard.writeText(linkConvite(convite.codigo))}
                  >
                    Copiar link
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => revogarConviteVitrine(convite.codigo)}>
                    Revogar
                  </Button>
                </div>
              )}
              {convite.status === "revogado" && (
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => reativarConviteVitrine(convite.codigo)}>
                    Reativar
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => excluirConviteVitrine(convite.codigo)}>
                    Excluir
                  </Button>
                </div>
              )}
            </div>
          ))}
          {convites.length === 0 && <div className="text-[12px] text-muted">Nenhum convite gerado ainda.</div>}
        </div>
      </Card>

      {conexoesPendentes.filter((conexao) => conexao.tenant_id_destino === usuario?.tenant_id).length > 0 && (
        <Card className="mb-4">
          <SectionLabel>Conexões pendentes</SectionLabel>
          <div className="flex flex-col gap-2">
            {conexoesPendentes
              .filter((conexao) => conexao.tenant_id_destino === usuario?.tenant_id)
              .map((conexao) => {
              const outroTenant =
                empresas.find((empresa) => empresa.perfil.tenant_id === conexao.tenant_id_origem)?.perfil
                  .nome_exibicao ?? conexao.tenant_id_origem;
              return (
                <div key={conexao.id} className="flex items-center justify-between text-[12px]">
                  <span>{outroTenant}</span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="green" onClick={() => responder(conexao.id, true)}>
                      Aceitar
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => responder(conexao.id, false)}>
                      Recusar
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card className="mb-4">
        <SectionLabel>Feed da Rede</SectionLabel>
        <form onSubmit={publicarPost} className="mb-3 flex flex-col gap-2">
          <Textarea name="texto" required rows={2} placeholder="Compartilhe uma novidade com a rede..." />
          <div className="flex gap-2">
            <Input name="imagem_url" placeholder="URL de imagem (opcional)" className="flex-1" />
            <Input name="link_url" placeholder="URL de link (opcional)" className="flex-1" />
            <Button type="submit" size="sm" disabled={publicando}>
              {publicando ? "Publicando..." : "Publicar"}
            </Button>
          </div>
        </form>
        <div className="flex flex-col gap-3">
          {posts.map((post) => (
            <div key={post.id} className="rounded-lg border border-border p-3 text-[12px]">
              <div className="mb-1 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {post.empresa_logo_url && (
                    <img src={post.empresa_logo_url} alt="" className="h-6 w-6 rounded object-cover" />
                  )}
                  <span className="font-semibold text-text">{post.empresa_nome}</span>
                  <span className="text-muted">· {post.autor_nome}</span>
                </div>
                <div className="flex items-center gap-2 text-muted">
                  <span>{new Date(post.criado_em).toLocaleString("pt-BR")}</span>
                  {post.tenant_id === usuario?.tenant_id && (
                    <Button size="sm" variant="ghost" onClick={() => excluirPost(post.id)}>
                      Excluir
                    </Button>
                  )}
                </div>
              </div>
              <div className="text-text">{post.texto}</div>
              {post.imagem_url && <img src={post.imagem_url} alt="" className="mt-2 max-h-48 w-full rounded-lg object-cover" />}
              {post.link_url && (
                <a href={post.link_url} target="_blank" rel="noreferrer" className="mt-1 block text-cyan">
                  {post.link_url}
                </a>
              )}
              <div className="mt-2 flex items-center gap-3 text-muted">
                <button
                  type="button"
                  onClick={() => reagirPost(post.id)}
                  disabled={reagindoId === post.id}
                  className={post.eu_reagi ? "font-semibold text-cyan" : ""}
                >
                  👍 {post.eu_reagi ? "Você reagiu" : "Reagir"} {post.total_reacoes > 0 && `(${post.total_reacoes})`}
                </button>
                <button type="button" onClick={() => alternarComentarios(post.id)}>
                  💬 Comentários {post.total_comentarios > 0 && `(${post.total_comentarios})`}
                </button>
              </div>
              {comentariosAbertos[post.id] && (
                <div className="mt-2 flex flex-col gap-2 border-t border-border pt-2">
                  {(comentariosPorPost[post.id] ?? []).map((comentario) => (
                    <div key={comentario.id} className="text-[11px]">
                      <span className="font-semibold text-text">{comentario.empresa_nome}</span>
                      <span className="text-muted"> · {comentario.autor_nome}: </span>
                      <span className="text-text">{comentario.texto}</span>
                    </div>
                  ))}
                  {(comentariosPorPost[post.id] ?? []).length === 0 && (
                    <div className="text-[11px] text-muted">Nenhum comentário ainda.</div>
                  )}
                  <div className="flex gap-2">
                    <Input
                      placeholder="Escreva um comentário..."
                      value={novoComentarioTexto[post.id] ?? ""}
                      onChange={(event) =>
                        setNovoComentarioTexto((atual) => ({ ...atual, [post.id]: event.target.value }))
                      }
                      onKeyDown={(event) => {
                        if (event.key === "Enter") enviarComentario(post.id);
                      }}
                    />
                    <Button
                      size="sm"
                      onClick={() => enviarComentario(post.id)}
                      disabled={enviandoComentarioId === post.id}
                    >
                      Enviar
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
          {posts.length === 0 && <div className="text-[12px] text-muted">Nenhum post publicado na rede ainda.</div>}
        </div>
      </Card>

      <Card className="mb-4">
        <SectionLabel>Necessidades da Rede</SectionLabel>
        <form onSubmit={publicarIntent} className="mb-3 flex flex-col gap-2">
          <div className="flex gap-2">
            <Input name="categoria" placeholder="Categoria (ex.: backup)" className="flex-1" />
            <Input name="titulo" required placeholder="Título da necessidade" className="flex-1" />
          </div>
          <Textarea name="descricao" required rows={2} placeholder="Descreva o que sua empresa está procurando..." />
          <div className="flex gap-2">
            <Input name="requisitos" placeholder="Requisitos (separados por vírgula, opcional)" className="flex-1" />
            <Input name="faixa_orcamento" placeholder="Faixa de orçamento (opcional)" className="flex-1" />
            <Input name="localizacao" placeholder="Localização (opcional)" className="flex-1" />
          </div>
          <div className="flex items-center gap-2">
            <Input
              name="perfil_fornecedor_desejado"
              placeholder="Perfil de fornecedor desejado (opcional)"
              className="flex-1"
            />
            <select
              name="visibilidade"
              defaultValue="publica"
              className="rounded-lg border border-border bg-surf2 px-3 py-2 text-[12.5px] text-text outline-none"
            >
              <option value="publica">Visível a toda a rede</option>
              <option value="conexoes">Só conexões aceitas</option>
            </select>
            <Button type="submit" size="sm" disabled={publicandoIntent}>
              {publicandoIntent ? "Publicando..." : "Publicar necessidade"}
            </Button>
          </div>
        </form>
        <div className="flex flex-col gap-2">
          {intents.map((intent) => {
            const rotulo = ROTULO_STATUS_INTENT[intent.status] ?? ROTULO_STATUS_INTENT.aberta;
            return (
              <div key={intent.id} className="rounded-lg border border-border p-3 text-[12px]">
                <div className="mb-1 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-text">{intent.titulo}</span>
                    <Badge tone={rotulo.tone}>{rotulo.texto}</Badge>
                    <span className="text-muted">· {intent.categoria}</span>
                  </div>
                  {intent.tenant_id === usuario?.tenant_id && intent.status === "aberta" && (
                    <div className="flex gap-2">
                      <Button size="sm" variant="ghost" onClick={() => marcarIntentAtendida(intent.id)}>
                        Marcar atendida
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => encerrarIntent(intent.id)}>
                        Encerrar
                      </Button>
                    </div>
                  )}
                </div>
                <div className="text-muted">{intent.empresa_nome}</div>
                <div className="mt-1 text-text">{intent.descricao}</div>
                {intent.requisitos.length > 0 && (
                  <div className="mt-1 text-muted">Requisitos: {listaParaTexto(intent.requisitos)}</div>
                )}
                <div className="mt-1 flex gap-3 text-muted">
                  {intent.faixa_orcamento && <span>💰 {intent.faixa_orcamento}</span>}
                  {intent.localizacao && <span>📍 {intent.localizacao}</span>}
                </div>
              </div>
            );
          })}
          {intents.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma necessidade publicada na rede ainda.</div>
          )}
        </div>
      </Card>

      <Card>
        <SectionLabel>Diretório de empresas</SectionLabel>
        <div className="mb-3 flex flex-wrap items-end gap-2.5">
          <div className="min-w-[140px] flex-1">
            <Input
              placeholder="Buscar por nome ou descrição"
              value={filtroBusca}
              onChange={(event) => setFiltroBusca(event.target.value)}
            />
          </div>
          <div className="w-[140px]">
            <Input placeholder="Setor" value={filtroSetor} onChange={(event) => setFiltroSetor(event.target.value)} />
          </div>
          <div className="w-[140px]">
            <Input placeholder="Porte" value={filtroPorte} onChange={(event) => setFiltroPorte(event.target.value)} />
          </div>
          <div className="w-[140px]">
            <Input placeholder="Mercado" value={filtroMercado} onChange={(event) => setFiltroMercado(event.target.value)} />
          </div>
          <label className="flex items-center gap-1.5 pb-2 text-[11px] text-muted">
            <input
              type="checkbox"
              checked={filtroApenasVerificadas}
              onChange={(event) => setFiltroApenasVerificadas(event.target.checked)}
            />
            Só verificadas
          </label>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {empresas.map((empresa) => (
            <div key={empresa.perfil.tenant_id} className="rounded-xl border border-border bg-surf2 p-3.5">
              <div className="mb-1 flex items-center justify-between">
                <button
                  type="button"
                  className="text-left text-[13px] font-bold hover:text-cyan"
                  onClick={() => setPerfilDetalheTenantId(empresa.perfil.tenant_id)}
                >
                  {empresa.perfil.nome_exibicao}
                </button>
                <Badge tone={empresa.status_conexao === "aceita" ? "green" : empresa.status_conexao === "bloqueada" ? "red" : "muted"}>
                  {empresa.status_conexao}
                </Badge>
              </div>
              <div className="mb-2 text-[11px] text-muted">{empresa.perfil.setor ?? "—"}</div>
              {empresa.oferta_principal && (
                <div className="mb-2 text-[11px] text-muted">
                  <span className="font-semibold text-text">{empresa.oferta_principal.nome}</span> —{" "}
                  {empresa.oferta_principal.descricao}
                </div>
              )}

              {empresa.status_conexao === "bloqueada" ? (
                <div className="flex flex-wrap gap-2">
                  {(() => {
                    const conexao = conexaoComTenant(empresa.perfil.tenant_id);
                    if (!conexao) return null;
                    return (
                      <Button size="sm" variant="ghost" onClick={() => desbloquearConexao(conexao.id)}>
                        Desbloquear
                      </Button>
                    );
                  })()}
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {empresa.status_conexao === "nenhuma" && (
                    <Button size="sm" onClick={() => conectar(empresa.perfil.tenant_id)}>
                      Conectar
                    </Button>
                  )}
                  {empresa.status_conexao === "pendente_enviada" && <Badge tone="amber">Pendente (enviada)</Badge>}
                  {empresa.status_conexao === "pendente_recebida" &&
                    (() => {
                      const conexao = conexaoRecebidaDe(empresa.perfil.tenant_id);
                      if (!conexao) return null;
                      return (
                        <>
                          <Button size="sm" variant="green" onClick={() => responder(conexao.id, true)}>
                            Aceitar
                          </Button>
                          <Button size="sm" variant="danger" onClick={() => responder(conexao.id, false)}>
                            Recusar
                          </Button>
                        </>
                      );
                    })()}
                  {empresa.status_conexao === "aceita" && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => setConversaTenantId(empresa.perfil.tenant_id)}>
                        Mensagens
                      </Button>
                      {(() => {
                        const conexao = conexaoComTenant(empresa.perfil.tenant_id);
                        if (!conexao) return null;
                        return (
                          <Button size="sm" variant="ghost" onClick={() => desconectarConexao(conexao.id)}>
                            Desconectar
                          </Button>
                        );
                      })()}
                    </>
                  )}
                  <Button
                    size="sm"
                    variant={empresa.seguindo ? "ghost" : "violet"}
                    onClick={() => alternarSeguir(empresa.perfil.tenant_id, empresa.seguindo)}
                  >
                    {empresa.seguindo ? "Deixar de seguir" : "Seguir"}
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => bloquearEmpresa(empresa.perfil.tenant_id)}>
                    Bloquear
                  </Button>
                </div>
              )}
            </div>
          ))}
          {empresas.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma outra empresa cadastrada na rede ainda.</div>
          )}
        </div>
      </Card>

      <Modal title="Editar perfil" open={modalPerfilAberto} onClose={() => setModalPerfilAberto(false)}>
        <form onSubmit={salvarPerfil} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome de exibição</div>
            <Input name="nome_exibicao" required defaultValue={perfil?.nome_exibicao} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Setor</div>
            <Input name="setor" defaultValue={perfil?.setor ?? ""} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Site</div>
            <Input name="site" defaultValue={perfil?.site ?? ""} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Descrição</div>
            <Input name="descricao" defaultValue={perfil?.descricao ?? ""} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Logo (URL)</div>
              <Input name="logo_url" defaultValue={perfil?.logo_url ?? ""} placeholder="https://..." />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Capa (URL)</div>
              <Input name="capa_url" defaultValue={perfil?.capa_url ?? ""} placeholder="https://..." />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNAE principal</div>
              <Input name="cnae_principal" defaultValue={perfil?.cnae_principal ?? ""} placeholder="6201500" />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Porte</div>
              <Input name="porte" defaultValue={perfil?.porte ?? ""} placeholder="PEQUENO/MEDIO/GRANDE" />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">LinkedIn</div>
              <Input name="linkedin" defaultValue={perfil?.redes_sociais?.linkedin ?? ""} placeholder="https://..." />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Cidade da sede</div>
              <Input name="sede_cidade" defaultValue={perfil?.sede_cidade ?? ""} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">UF da sede</div>
              <Input name="sede_uf" defaultValue={perfil?.sede_uf ?? ""} placeholder="SP" />
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Mercados atendidos (separados por vírgula)</div>
            <Input name="mercados" defaultValue={listaParaTexto(perfil?.mercados ?? [])} placeholder="Saúde, Educação" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Produtos/serviços (separados por vírgula)</div>
            <Textarea name="produtos_servicos" rows={2} defaultValue={listaParaTexto(perfil?.produtos_servicos ?? [])} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tecnologias (separadas por vírgula)</div>
            <Input name="tecnologias" defaultValue={listaParaTexto(perfil?.tecnologias ?? [])} placeholder="AWS, Kubernetes" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Certificações (separadas por vírgula)</div>
            <Input name="certificacoes" defaultValue={listaParaTexto(perfil?.certificacoes ?? [])} placeholder="ISO 27001" />
          </div>
          <Button type="submit" className="w-full justify-center">
            Salvar
          </Button>
        </form>
      </Modal>

      <Modal title="Solicitar verificação" open={modalVerificacaoAberto} onClose={() => setModalVerificacaoAberto(false)}>
        <form onSubmit={solicitarVerificacao} className="flex flex-col gap-3">
          <div className="text-[11px] text-muted">
            Informe um e-mail corporativo do domínio da sua empresa — se o domínio conferir com o site cadastrado
            no perfil, isso já ajuda na análise. Um administrador da B2B ON revisa e aprova ou recusa manualmente.
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail corporativo</div>
            <Input name="email_verificacao" type="email" required placeholder="voce@suaempresa.com.br" />
          </div>
          <Button type="submit" className="w-full justify-center">
            Enviar solicitação
          </Button>
        </form>
      </Modal>

      <Modal title="Convidar empresa" open={modalConviteAberto} onClose={() => setModalConviteAberto(false)}>
        <form
          onSubmit={async (event) => {
            await gerarConviteVitrine(event);
            setModalConviteAberto(false);
          }}
          className="flex flex-col gap-3"
        >
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Validade (horas)</div>
            <Input name="validade_horas" type="number" defaultValue={168} min={1} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              E-mail do convidado (opcional)
            </div>
            <Input name="email_destinatario" type="email" placeholder="contato@empresa.com" />
            <div className="mt-1 text-[11px] text-muted">
              Preenchendo, o convite é enviado por e-mail automaticamente. Deixe em branco para só copiar o link.
            </div>
          </div>
          {(usuario?.papel === "super_admin" || usuario?.papel === "admin") && (
            <label className="flex items-start gap-2 text-[11px] text-muted">
              <input type="checkbox" name="gratuito" className="mt-0.5" />
              <span>
                Convite gratuito — pula pagamento, cria a conta já no plano "Teste" sem prazo de expiração. Use só
                pra demonstração/teste, não pra cliente pagante.
              </span>
            </label>
          )}
          <Button type="submit" className="w-full justify-center">
            Gerar convite
          </Button>
        </form>
      </Modal>

      {conversaTenantId !== null && (
        <ConversaModal
          tenantId={conversaTenantId}
          nomeExibicao={
            empresas.find((empresa) => empresa.perfil.tenant_id === conversaTenantId)?.perfil.nome_exibicao ??
            conversaTenantId
          }
          onClose={() => setConversaTenantId(null)}
        />
      )}

      {perfilDetalheTenantId !== null && (
        <PerfilEmpresaDetalheModal
          perfil={empresas.find((empresa) => empresa.perfil.tenant_id === perfilDetalheTenantId)?.perfil ?? null}
          onClose={() => setPerfilDetalheTenantId(null)}
        />
      )}
    </div>
  );
}
