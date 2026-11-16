import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select, Textarea } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { ContaDetalheModal } from "@/pages/prospeccao/ContaDetalheModal";
import { TutorialRelatorioEntrega } from "@/pages/relatorio-entrega/TutorialRelatorioEntrega";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface SaudeCanalEmail {
  canal: string;
  enviados: number;
  bounces: number;
  spam_reports: number;
  taxa_bounce: number;
  taxa_spam: number;
  pausado: boolean;
  limiar_bounce: number;
  limiar_spam: number;
  amostra_minima: number;
  medido_pelo_provedor: boolean;
  // Recusas do servidor do destinatário por spam/reputação nos últimos 7 dias, sobre os e-mails que saíram no período.
  recusas_spam?: number;
  enviados_recusas?: number;
  taxa_recusa_spam?: number;
  limiar_recusa_spam_alerta?: number;
  limiar_recusa_spam_pausa?: number;
  nivel_recusa_spam?: "ok" | "alerta" | "critico";
  isento_pausa_spam?: boolean;
  pausado_por_spam?: boolean;
}

interface ContatoComBounce {
  decisor_id: number | null;
  conta_id: number | null;
  nome: string;
  email: string | null;
  conta_nome: string | null;
  canal: string;
  motivo_bounce: string | null;
  bounce_em: string;
}

// Totais dos últimos 7 dias contados nos próprios envios (não só nos retornos do provedor de envio).
interface ResumoEnvios {
  enviados: number;
  entregues: number;
  abertos: number;
  erros: number;
  nao_enviados: number;
  pendentes: number;
}

interface RelatorioEntrega {
  resumo_envios: ResumoEnvios;
  saude_email: SaudeCanalEmail;
  taxa_abertura_email: number | null;
  taxa_resposta_por_canal: Record<string, number>;
  contatos_com_bounce: ContatoComBounce[];
}

// Entrada da lista de bloqueio da empresa: e-mail e/ou telefone de quem pediu para não receber.
interface BloqueioContato {
  id: number;
  email: string | null;
  telefone: string | null;
  motivo: string;
  origem: string;
  criado_em: string;
}

interface EnvioEmail {
  origem: "cadencia" | "campanha";
  origem_nome: string;
  decisor_id: number | null;
  conta_id: number | null;
  nome: string;
  email: string | null;
  conta_nome: string | null;
  status: "erro" | "enviado" | "entregue" | "aberto" | "pendente" | "nao_enviado" | "cancelado";
  detalhe: string | null;
  enviado_em: string | null;
  criado_em: string;
}

interface ListaEnviosEmail {
  itens: EnvioEmail[];
  total: number;
  contagem_por_status: Record<string, number>;
}

const ROTULOS_CANAL: Record<string, string> = { email: "E-mail", whatsapp: "WhatsApp", linkedin: "LinkedIn" };

const ABAS_STATUS: { valor: string; rotulo: string }[] = [
  { valor: "todos", rotulo: "Todos" },
  { valor: "erro", rotulo: "Erro" },
  { valor: "enviado", rotulo: "Enviado" },
  { valor: "entregue", rotulo: "Entregue" },
  { valor: "aberto", rotulo: "Aberto" },
  { valor: "pendente", rotulo: "Pendente" },
  { valor: "nao_enviado", rotulo: "Não enviado" },
  { valor: "cancelado", rotulo: "Cancelado" },
];

// Cor do selo de cada status do e-mail.
const TOM_STATUS: Record<string, "red" | "green" | "violet" | "amber" | "muted" | "cyan"> = {
  erro: "red",
  enviado: "green",
  entregue: "cyan",
  aberto: "violet",
  pendente: "amber",
  nao_enviado: "muted",
  cancelado: "muted",
};

const ROTULO_STATUS: Record<string, string> = {
  erro: "Erro",
  enviado: "Enviado",
  entregue: "Entregue",
  aberto: "Aberto",
  pendente: "Pendente",
  nao_enviado: "Não enviado",
  cancelado: "Cancelado",
};

const LIMITE_POR_PAGINA = 50;
// Acima disso a lista de bloqueados começa recolhida: com centenas de linhas ela empurrava o resto da página para baixo.
const LIMITE_BLOQUEIOS_ABERTOS = 5;

// O que fazer quando os servidores dos destinatários recusam os e-mails como spam: o que mais pesa na reputação de quem envia.
function ChecklistReputacao() {
  return (
    <ul className="mt-2 list-disc pl-5 text-[11px] text-muted">
      <li>Confirme a autenticação do domínio de envio (SPF, DKIM e DMARC) com quem cuida do seu e-mail.</li>
      <li>Limpe a lista: tire endereços antigos, genéricos (contato@, vendas@) e quem nunca abriu.</li>
      <li>Reduza o volume diário por algumas semanas e aumente aos poucos (aquecimento).</li>
      <li>Evite links encurtados, muitos links, anexos e palavras de promoção agressiva; personalize o texto.</li>
      <li>Mantenha o link de descadastro visível e responda a quem pedir para sair.</li>
    </ul>
  );
}

function paraPercentual(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `${(valor * 100).toFixed(1)}%`;
}

export function RelatorioEntrega() {
  const { usuario, marcarTutorialModuloVisto } = useAuth();
  // Tutorial do módulo (raio-X 2026-09-21) — abre sozinho na primeira
  // visita, coexiste com o tour grande.
  const [tutorialAberto, setTutorialAberto] = useState(false);
  const [carregado, setCarregado] = useState(false);
  useEffect(() => {
    if (usuario && carregado && !(usuario.tutoriais_modulo_vistos ?? []).includes("relatorio-entrega")) setTutorialAberto(true);
  }, [usuario, carregado]);
  function fecharTutorial() {
    setTutorialAberto(false);
    if (usuario && !(usuario.tutoriais_modulo_vistos ?? []).includes("relatorio-entrega")) marcarTutorialModuloVisto("relatorio-entrega");
  }
  const [relatorio, setRelatorio] = useState<RelatorioEntrega | null>(null);
  const [envios, setEnvios] = useState<ListaEnviosEmail | null>(null);
  const [filtroStatus, setFiltroStatus] = useState("todos");
  const [pagina, setPagina] = useState(0);
  const [carregandoEnvios, setCarregandoEnvios] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [reativando, setReativando] = useState(false);
  const [suprimindoDecisorId, setSuprimindoDecisorId] = useState<number | null>(null);
  const [contaEmEdicaoId, setContaEmEdicaoId] = useState<number | null>(null);
  const [textoBounces, setTextoBounces] = useState("");
  const [tipoBounces, setTipoBounces] = useState<"auto" | "inexistente" | "spam">("auto");
  // O resultado do registro aparece dentro do próprio cartão (o aviso do topo da página fica fora da tela, perto do botão não mudava nada).
  const [retornoBounces, setRetornoBounces] = useState<{ tipo: "ok" | "aviso" | "erro"; linhas: string[] } | null>(null);
  const [bloqueios, setBloqueios] = useState<BloqueioContato[]>([]);
  const [liberandoId, setLiberandoId] = useState<number | null>(null);
  // null = ainda não escolhido: a lista começa recolhida quando é grande (escondia o resto da página) e aberta quando é curta.
  const [bloqueiosAbertos, setBloqueiosAbertos] = useState<boolean | null>(null);
  const [registrandoBounces, setRegistrandoBounces] = useState(false);

  async function carregar() {
    try {
      setRelatorio(await api.get<RelatorioEntrega>("/relatorio-entrega"));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o relatório.");
    } finally {
      setCarregado(true);
    }
  }

  // Lista de bloqueio: complemento do relatório; se falhar, o resto da tela segue funcionando.
  async function carregarBloqueios() {
    try {
      setBloqueios(await api.get<BloqueioContato[]>("/bloqueios-contato"));
    } catch {
      // a lista é um complemento do relatório: se falhar, o resto da tela segue funcionando
    }
  }

  // Desfaz um bloqueio (só administrador); o contato volta a poder receber campanhas.
  async function liberarBloqueio(bloqueio: BloqueioContato) {
    if (liberandoId !== null) return;
    setLiberandoId(bloqueio.id);
    setErro(null);
    try {
      await api.delete(`/bloqueios-contato/${bloqueio.id}`);
      setMensagem("Contato liberado: ele volta a poder receber campanhas.");
      await carregarBloqueios();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível liberar o contato.");
    } finally {
      setLiberandoId(null);
    }
  }

  async function carregarEnvios(status: string, offset: number) {
    setCarregandoEnvios(true);
    try {
      const params = new URLSearchParams({
        status,
        limite: String(LIMITE_POR_PAGINA),
        offset: String(offset * LIMITE_POR_PAGINA),
      });
      setEnvios(await api.get<ListaEnviosEmail>(`/relatorio-entrega/envios?${params.toString()}`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o detalhamento de envios.");
    } finally {
      setCarregandoEnvios(false);
    }
  }

  useEffect(() => {
    carregar();
    carregarBloqueios();
  }, []);

  useEffect(() => {
    carregarEnvios(filtroStatus, pagina);
  }, [filtroStatus, pagina]);

  async function reativarCanalEmail() {
    if (reativando) return;
    setReativando(true);
    setErro(null);
    try {
      await api.post("/canais/email/reativar");
      setMensagem("Canal de e-mail reativado.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível reativar o canal.");
    } finally {
      setReativando(false);
    }
  }

  // Com conta de e-mail própria (SMTP) o aviso de "não entregue" chega na caixa de entrada do usuário, não ao sistema: ele cola aqui os endereços.
  async function registrarBounces() {
    if (registrandoBounces || !textoBounces.trim()) return;
    setRegistrandoBounces(true);
    setErro(null);
    setMensagem(null);
    setRetornoBounces(null);
    try {
      const resposta = await api.post<{
        registrados: string[];
        recusados_spam?: string[];
        ja_registrados: string[];
        nao_encontrados: string[];
        motivo_nao_encontrados: string | null;
      }>("/relatorio-entrega/bounces-manuais", { texto: textoBounces, tipo: tipoBounces });
      const linhas: string[] = [];
      if (resposta.registrados.length > 0) {
        linhas.push(
          `${resposta.registrados.length} endereço(s) registrado(s) como inexistente(s): ${resposta.registrados.slice(0, 8).join(", ")}${resposta.registrados.length > 8 ? "…" : ""}. Eles não recebem mais nada da plataforma (campanhas, cadências e webmail).`,
        );
      }
      const recusadosSpam = resposta.recusados_spam ?? [];
      if (recusadosSpam.length > 0) {
        linhas.push(
          `Desses, ${recusadosSpam.length} contaram como recusa por spam ou reputação (entram na taxa de recusas por spam): ${recusadosSpam.slice(0, 8).join(", ")}${recusadosSpam.length > 8 ? "…" : ""}. Se algum foi classificado errado, libere em “Contatos bloqueados” e registre de novo escolhendo o motivo.`,
        );
      }
      if (resposta.ja_registrados.length > 0) {
        linhas.push(`${resposta.ja_registrados.length} já estavam registrado(s): ${resposta.ja_registrados.slice(0, 8).join(", ")}${resposta.ja_registrados.length > 8 ? "…" : ""}.`);
      }
      if (resposta.nao_encontrados.length > 0) {
        linhas.push(
          `${resposta.nao_encontrados.length} não registrado(s): ${resposta.nao_encontrados.slice(0, 8).join(", ")}${resposta.nao_encontrados.length > 8 ? "…" : ""}. Cada um ${resposta.motivo_nao_encontrados ?? "não foi encontrado."}`,
        );
      }
      setRetornoBounces({ tipo: resposta.registrados.length + resposta.ja_registrados.length > 0 ? "ok" : "aviso", linhas });
      if (resposta.registrados.length > 0 || resposta.ja_registrados.length > 0) setTextoBounces(resposta.nao_encontrados.join("\n"));
      await carregar();
      await carregarBloqueios();
      await carregarEnvios(filtroStatus, pagina);
    } catch (error) {
      setRetornoBounces({ tipo: "erro", linhas: [error instanceof ApiError ? error.message : "Não foi possível registrar os e-mails."] });
    } finally {
      setRegistrandoBounces(false);
    }
  }

  async function suprimirContato(decisorId: number, contaId: number | null) {
    if (suprimindoDecisorId !== null) return;
    setSuprimindoDecisorId(decisorId);
    setErro(null);
    try {
      // A rota vive sob /contas/{conta_id}/..., mas `optout_service` só
      // precisa do decisor_id — qualquer conta_id no path funciona; usamos
      // a conta real só por clareza semântica da URL.
      await api.post(`/contas/${contaId ?? 0}/decisores/${decisorId}/suprimir`);
      setMensagem("Contato excluído — não vai mais receber mensagens.");
      await carregar();
      await carregarEnvios(filtroStatus, pagina);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir o contato.");
    } finally {
      setSuprimindoDecisorId(null);
    }
  }

  const saude = relatorio?.saude_email;
  const podeLiberar = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const resumo = relatorio?.resumo_envios;
  const medidoPeloProvedor = saude?.medido_pelo_provedor ?? true;
  const nivelSpam = saude?.nivel_recusa_spam ?? "ok";
  const pausadoPorSpam = saude?.pausado_por_spam ?? false;
  const listaBloqueiosAberta = bloqueiosAbertos ?? bloqueios.length <= LIMITE_BLOQUEIOS_ABERTOS;
  const totalPaginas = envios ?Math.max(1, Math.ceil(envios.total / LIMITE_POR_PAGINA)) : 1;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="flex items-center gap-2">
          <div className="font-head text-xl font-bold">Relatório de Entrega</div>
          <button type="button" onClick={() => setTutorialAberto(true)} className="text-[11px] text-muted hover:text-cyan">
            🔄 Rever tutorial
          </button>
        </div>
        <div className="mt-0.5 text-[11px] text-muted">
          Entregabilidade de e-mail e taxa de resposta por canal — o que a plataforma consegue medir de verdade
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card className="mb-4" data-tutorial-id="relatorio-entrega:saude">
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>E-mail — últimos 7 dias</SectionLabel>
          <Badge tone={saude?.pausado ? "red" : "green"}>{saude?.pausado ? "Pausado" : "Saudável"}</Badge>
        </div>
        <div className="mb-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <KpiCard label="Enviados" value={resumo?.enviados ?? "—"} sub="e-mails que saíram" />
          <KpiCard
            label="Entregues"
            value={resumo ? (medidoPeloProvedor ? resumo.entregues : "não medido") : "—"}
            sub={medidoPeloProvedor ? "confirmados pelo serviço de envio" : "só com o envio por API (em Configuração)"}
          />
          <KpiCard label="Abertos" value={resumo?.abertos ?? "—"} sub="pelo pixel (indicador aproximado)" colorClassName="text-violet" />
          <KpiCard
            label="Com erro"
            value={resumo?.erros ?? "—"}
            sub="recusados no envio"
            colorClassName={resumo && resumo.erros > 0 ? "text-red" : "text-cyan"}
          />
          <KpiCard label="Não enviados" value={resumo?.nao_enviados ?? "—"} sub="sem e-mail válido" />
          <KpiCard
            label="Taxa de bounce"
            value={saude ? (medidoPeloProvedor ? paraPercentual(saude.taxa_bounce) : "não medido") : "—"}
            sub={
              saude
                ? medidoPeloProvedor
                  ? `limite: ${paraPercentual(saude.limiar_bounce)} (vale a partir de ${saude.amostra_minima} envios)`
                  : "sua conta de e-mail não devolve bounce ao sistema"
                : undefined
            }
            colorClassName={saude?.pausado ? "text-red" : "text-cyan"}
          />
          <KpiCard
            label="Taxa de spam"
            value={saude ? (medidoPeloProvedor ? paraPercentual(saude.taxa_spam) : "não medido") : "—"}
            sub={saude && medidoPeloProvedor ? `limite: ${paraPercentual(saude.limiar_spam)}` : undefined}
          />
          <KpiCard
            label="Recusados por spam"
            value={saude ? `${saude.recusas_spam ?? 0} · ${paraPercentual(saude.taxa_recusa_spam ?? 0)}` : "—"}
            sub={
              saude
                ? `servidor do destinatário recusou por spam/reputação · pausa a partir de ${paraPercentual(saude.limiar_recusa_spam_pausa ?? 0.02)} (com ${saude.amostra_minima}+ envios)${saude.isento_pausa_spam ? " · empresa isenta da pausa" : ""}`
                : undefined
            }
            colorClassName={nivelSpam === "critico" ? "text-red" : nivelSpam === "alerta" ? "text-amber" : "text-cyan"}
          />
          <KpiCard label="Taxa de abertura" value={paraPercentual(relatorio?.taxa_abertura_email)} colorClassName="text-violet" />
        </div>
        {saude && nivelSpam !== "ok" && !pausadoPorSpam && (
          <div className={`mb-2 rounded-lg p-3 text-[12px] text-text ${nivelSpam === "critico" ? "bg-red/10" : "bg-amber/10"}`}>
            {nivelSpam === "critico" && saude.isento_pausa_spam
              ? `As recusas por spam passaram de ${paraPercentual(saude.limiar_recusa_spam_pausa ?? 0.02)} dos e-mails enviados nos últimos 7 dias. Sua empresa está isenta da pausa automática, mas a reputação do remetente está sendo prejudicada.`
              : `Atenção: ${paraPercentual(saude.taxa_recusa_spam ?? 0)} dos e-mails dos últimos 7 dias foram recusados como spam. A partir de ${paraPercentual(saude.limiar_recusa_spam_pausa ?? 0.02)} o canal de e-mail pausa e novas campanhas e cadências ficam bloqueadas até a taxa cair.`}
            <ChecklistReputacao />
          </div>
        )}
        {pausadoPorSpam && (
          <div className="mb-2 rounded-lg bg-red/10 p-3 text-[12px] text-text">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                Canal de e-mail pausado: {paraPercentual(saude?.taxa_recusa_spam ?? 0)} dos seus e-mails dos últimos 7 dias foram recusados como spam (limite{" "}
                {paraPercentual(saude?.limiar_recusa_spam_pausa ?? 0.02)}). Novas campanhas e cadências de e-mail ficam bloqueadas e os envios agendados
                aguardam. O canal volta sozinho quando a taxa cair abaixo do limite, ou depois de revisão do administrador da plataforma.
              </span>
              {usuario?.papel === "super_admin" && (
                <Button size="sm" variant="danger" disabled={reativando} onClick={reativarCanalEmail}>
                  {reativando ? "Reativando..." : "Reativar canal (revisado)"}
                </Button>
              )}
            </div>
            <ChecklistReputacao />
          </div>
        )}
        {saude?.pausado && !pausadoPorSpam && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red/10 p-3 text-[12px] text-text">
            <span>
              {relatorio && relatorio.contatos_com_bounce.length > 0
                ? "Canal de e-mail pausado automaticamente — taxa de bounce/spam acima do limite. Corrija ou exclua os contatos problemáticos abaixo antes de reativar."
                : "Canal de e-mail pausado automaticamente, mas nenhum contato das suas cadências ou campanhas aparece com bounce — o alerta pode ter vindo de e-mails de sistema ou de uma amostra pequena. Não há o que corrigir ou excluir; pode reativar o canal."}
            </span>
            <Button size="sm" variant="danger" disabled={reativando} onClick={reativarCanalEmail}>
              {reativando ? "Reativando..." : "Reativar canal"}
            </Button>
          </div>
        )}
      </Card>

      <Card className="mb-4" data-tutorial-id="relatorio-entrega:resposta">
        <SectionLabel>Taxa de resposta por canal</SectionLabel>
        <div className="flex flex-wrap gap-2.5">
          {Object.entries(relatorio?.taxa_resposta_por_canal ?? {}).map(([canal, taxa]) => (
            <KpiCard key={canal} label={ROTULOS_CANAL[canal] ?? canal} value={paraPercentual(taxa)} />
          ))}
          {relatorio && Object.keys(relatorio.taxa_resposta_por_canal).length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma mensagem enviada ainda nesse período.</div>
          )}
        </div>
        <div className="mt-3 text-[11px] text-muted">
          WhatsApp e LinkedIn não têm confirmação de entrega/leitura rastreada — só a taxa de resposta acima é
          medida pra esses dois canais. A pausa automática por bounce depende do retorno do provedor de envio e só
          considera e-mails de cadência e campanha. Contas com SMTP próprio (como o Gmail) não recebem esse retorno: o
          sistema só vê a recusa que o servidor de e-mail dá na hora do envio, que aparece como "Erro" ou "Não enviado" no
          detalhamento abaixo. Um endereço que não existe costuma ser recusado depois, com um aviso de falha na sua caixa
          de entrada, e esse aviso o sistema ainda não lê: cole-o em “Registrar e-mails que voltaram”, que separa endereço inexistente de recusa por spam.
        </div>
      </Card>

      <Card className="mb-4">
        <div className="flex items-center justify-between gap-2">
          <SectionLabel>Contatos bloqueados ({bloqueios.length})</SectionLabel>
          {bloqueios.length > 0 && (
            <Button size="sm" variant="ghost" aria-expanded={listaBloqueiosAberta} onClick={() => setBloqueiosAbertos(!listaBloqueiosAberta)}>
              {listaBloqueiosAberta ? "Recolher ▲" : "Expandir ▼"}
            </Button>
          )}
        </div>
        <div className="mb-2 text-[11px] text-muted">
          Quem pediu para não receber mais nada (marcado por você em “Não quer receber”, nas campanhas) e os e-mails registrados como inexistentes (que voltaram como não entregues).
          Esses endereços e telefones não recebem nada da plataforma; “Liberar” desfaz o bloqueio.
        </div>
        {bloqueios.length === 0 ? (
          <div className="text-[12px] text-muted">Ninguém bloqueado.</div>
        ) : !listaBloqueiosAberta ? (
          <button type="button" className="text-[12px] text-cyan hover:underline" onClick={() => setBloqueiosAbertos(true)}>
            Lista recolhida — mostrar os {bloqueios.length} contatos bloqueados
          </button>
        ) : (
          <div className="flex flex-col gap-1.5">
            {bloqueios.map((bloqueio) => (
              <div key={bloqueio.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2 text-[12px]">
                <div>
                  <div className="font-semibold text-text">{[bloqueio.email, bloqueio.telefone].filter(Boolean).join(" · ")}</div>
                  <div className="text-[11px] text-muted">
                    {bloqueio.motivo} · {new Date(bloqueio.criado_em).toLocaleDateString("pt-BR")}
                  </div>
                </div>
                {podeLiberar && (
                  <Button size="sm" variant="ghost" disabled={liberandoId === bloqueio.id} onClick={() => liberarBloqueio(bloqueio)}>
                    {liberandoId === bloqueio.id ? "Liberando..." : "Liberar"}
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="mb-4">
        <SectionLabel>Registrar e-mails que voltaram</SectionLabel>
        <div className="mb-2 text-[11px] text-muted">
          Quando o Gmail devolve um e-mail (endereço inexistente ou mensagem bloqueada como spam), o aviso de falha chega na sua caixa de entrada, não aqui.
          Cole abaixo o próprio aviso ou os endereços que voltaram (um por linha). Pelo aviso colado o sistema separa endereço inexistente de recusa por
          spam, que entra na taxa de recusas por spam e pode pausar o canal; só com o endereço, escolha o motivo. Eles passam a constar como erro e o sistema deixa de enviar para esses endereços em qualquer área —
          campanhas, cadências, webmail, lembretes e pesquisas. Só entram endereços que já aparecem em alguma campanha, cadência ou contato; se foi engano, libere em “Contatos bloqueados”.
        </div>
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
          <span className="text-muted">Motivo:</span>
          <Select value={tipoBounces} onChange={(event) => setTipoBounces(event.target.value as "auto" | "inexistente" | "spam")}>
            <option value="auto">Detectar pelo aviso colado</option>
            <option value="inexistente">Endereço inexistente</option>
            <option value="spam">Recusado como spam / bloqueio de reputação</option>
          </Select>
        </div>
        <Textarea
          rows={3}
          value={textoBounces}
          onChange={(event) => setTextoBounces(event.target.value)}
          placeholder={"fulano@empresa.com.br\nbeltrano@outraempresa.com"}
        />
        <div className="mt-2">
          <Button size="sm" disabled={registrandoBounces || !textoBounces.trim()} onClick={registrarBounces}>
            {registrandoBounces ? "Registrando..." : "Registrar como erro"}
          </Button>
        </div>
        {retornoBounces && (
          <div
            role="status"
            className={`mt-2 flex flex-col gap-1 text-[12px] ${retornoBounces.tipo === "ok" ? "text-green" : retornoBounces.tipo === "erro" ? "text-red" : "text-amber"}`}
          >
            {retornoBounces.linhas.map((linha) => (
              <div key={linha}>{linha}</div>
            ))}
          </div>
        )}
      </Card>

      <Card data-tutorial-id="relatorio-entrega:detalhamento">
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>Detalhamento de envios de e-mail — por destinatário</SectionLabel>
          <span className="text-[11px] text-muted">{envios?.total ?? 0} destinatário(s) no filtro atual</span>
        </div>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {ABAS_STATUS.map((aba) => {
            // `envios.total` reflete só o filtro selecionado no momento —
            // pra rotular a aba "Todos" com o total geral, soma-se
            // `contagem_por_status`, que o backend sempre calcula sem filtro.
            const totalGeral = envios
              ? Object.values(envios.contagem_por_status).reduce((soma, valor) => soma + valor, 0)
              : undefined;
            const contagem = envios?.contagem_por_status[aba.valor];
            const totalAba = aba.valor === "todos" ? totalGeral : contagem;
            return (
              <Button
                key={aba.valor}
                size="sm"
                variant={filtroStatus === aba.valor ? "primary" : "ghost"}
                onClick={() => {
                  setFiltroStatus(aba.valor);
                  setPagina(0);
                }}
              >
                {aba.rotulo} {totalAba !== undefined && `(${totalAba})`}
              </Button>
            );
          })}
        </div>

        {carregandoEnvios && <div className="text-[12px] text-muted">Carregando...</div>}
        {!carregandoEnvios && envios && envios.itens.length === 0 && (
          <div className="text-[12px] text-muted">Nenhum envio de e-mail nesse filtro.</div>
        )}

        <div className="flex flex-col gap-2">
          {!carregandoEnvios &&
            envios?.itens.map((item, indice) => (
              <div
                key={`${item.decisor_id ?? "avulso"}-${item.origem}-${item.criado_em}-${indice}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5 text-[12px]"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <Badge tone={TOM_STATUS[item.status]}>{ROTULO_STATUS[item.status]}</Badge>
                    <span className="font-semibold text-text">
                      {item.nome} {item.conta_nome && <span className="text-muted">· {item.conta_nome}</span>}
                    </span>
                  </div>
                  <div className="text-muted">
                    {item.email ?? "sem e-mail"} · {item.origem_nome}
                    {item.detalhe && <> · {item.detalhe}</>} ·{" "}
                    {new Date(item.enviado_em ?? item.criado_em).toLocaleString("pt-BR")}
                  </div>
                </div>
                {item.status === "erro" && (
                  <div className="flex flex-shrink-0 items-center gap-2">
                    {item.conta_id !== null && (
                      <Button size="sm" onClick={() => setContaEmEdicaoId(item.conta_id)}>
                        Editar e-mail
                      </Button>
                    )}
                    {item.decisor_id !== null && (
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={suprimindoDecisorId === item.decisor_id}
                        onClick={() => suprimirContato(item.decisor_id!, item.conta_id)}
                      >
                        {suprimindoDecisorId === item.decisor_id ? "Excluindo..." : "Excluir contato"}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            ))}
        </div>

        {envios && envios.total > LIMITE_POR_PAGINA && (
          <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
            <Button size="sm" variant="ghost" disabled={pagina === 0} onClick={() => setPagina((p) => Math.max(0, p - 1))}>
              ← Anterior
            </Button>
            <span>
              Página {pagina + 1} de {totalPaginas}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={pagina + 1 >= totalPaginas}
              onClick={() => setPagina((p) => p + 1)}
            >
              Próxima →
            </Button>
          </div>
        )}
      </Card>

      {contaEmEdicaoId !== null && (
        <ContaDetalheModal
          contaId={contaEmEdicaoId}
          onClose={() => setContaEmEdicaoId(null)}
          onAtualizado={carregar}
        />
      )}

      <TutorialRelatorioEntrega open={tutorialAberto} onClose={fecharTutorial} />
    </div>
  );
}
