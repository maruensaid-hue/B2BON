import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { Modal } from "@/components/ui/Modal";
import { ContaDetalheModal } from "@/pages/prospeccao/ContaDetalheModal";
import { api, ApiError } from "@/lib/api";

export interface ICP {
  id: number;
  grupo_id: string;
  nome: string;
  versao: number;
  ativo: boolean;
  segmento: string;
  porte: string;
  regiao: string;
  dores: string[];
  gatilhos: string[];
  cnae_codigos: string[];
  ufs: string[];
}

export interface Conta {
  id: number;
  icp_id: number | null;
  cnpj: string | null;
  nome: string;
  dominio: string | null;
  score_aderencia: number | null;
  status: string;
  motivo_descarte: string | null;
}

export interface ListaProspeccao {
  id: number;
  nome: string;
  icp_id: number | null;
  cargos_alvo: string[] | null;
}

interface Franquia {
  limite: number;
  usado: number;
  restante: number;
}

interface ParticipanteEvento {
  nome: string;
  empresa: string;
  cargo?: string;
  email?: string;
  telefone?: string;
  observacoes?: string;
}

interface ImportarParticipantesResponse {
  contas_criadas: number;
  contas_reaproveitadas: number;
  decisores_criados: number;
  contas_enfileiradas_para_enriquecimento: number;
  contas: Conta[];
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

type CampoParticipante = "nome" | "empresa" | "cargo" | "email" | "telefone" | "observacoes" | "ignorar";

const CAMPOS_DISPONIVEIS: { valor: CampoParticipante; rotulo: string }[] = [
  { valor: "nome", rotulo: "Nome" },
  { valor: "empresa", rotulo: "Empresa" },
  { valor: "cargo", rotulo: "Cargo" },
  { valor: "email", rotulo: "E-mail" },
  { valor: "telefone", rotulo: "Telefone" },
  { valor: "observacoes", rotulo: "Observações" },
  { valor: "ignorar", rotulo: "Ignorar" },
];

// Sinônimos comuns em planilhas de organizadores de evento — a ordem das
// colunas varia de lista para lista (ex.: "Empresa, Nome, Telefone, E-mail"
// é tão comum quanto "Nome, Empresa, Cargo, E-mail, Telefone"). Só um
// palpite inicial pro mapeamento — o usuário confere/ajusta antes de
// importar (pedido: poder configurar pra onde cada coluna vai, ex. uma
// coluna extra virando parte das Observações da empresa).
const SINONIMOS_CABECALHO: Record<string, CampoParticipante> = {
  nome: "nome",
  participante: "nome",
  responsavel: "nome",
  contato: "nome",
  empresa: "empresa",
  organizacao: "empresa",
  instituicao: "empresa",
  cargo: "cargo",
  funcao: "cargo",
  posicao: "cargo",
  email: "email",
  "e-mail": "email",
  telefone: "telefone",
  fone: "telefone",
  celular: "telefone",
  whatsapp: "telefone",
  observacao: "observacoes",
  observacoes: "observacoes",
  obs: "observacoes",
  nota: "observacoes",
  notas: "observacoes",
  comentario: "observacoes",
  comentarios: "observacoes",
};

function normalizarCabecalho(texto: string): string {
  return texto
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

function detectarSeparador(linha: string): string {
  return linha.includes("\t") ? "\t" : linha.includes(";") ? ";" : ",";
}

const ORDEM_PADRAO: CampoParticipante[] = ["nome", "empresa", "cargo", "email", "telefone"];

/** Lê só a primeira linha do que foi colado pra sugerir um mapeamento de
 * coluna → campo (por sinônimo de cabeçalho reconhecido, ou pela ordem
 * padrão se não reconhecer nada) — o usuário revisa/ajusta esse
 * mapeamento na tela antes de confirmar a importação. */
function detectarColunas(texto: string): {
  colunas: string[];
  temCabecalho: boolean;
  mapeamentoInicial: CampoParticipante[];
} {
  const linhas = texto
    .split("\n")
    .map((linha) => linha.trim())
    .filter(Boolean);
  if (linhas.length === 0) return { colunas: [], temCabecalho: false, mapeamentoInicial: [] };

  const separador = detectarSeparador(linhas[0]);
  const colunas = linhas[0].split(separador).map((celula) => celula.trim());
  const mapaSugerido = colunas.map((celula) => SINONIMOS_CABECALHO[normalizarCabecalho(celula)]);
  const reconhecidos = mapaSugerido.filter(Boolean);
  const temCabecalho = reconhecidos.includes("nome") && reconhecidos.includes("empresa");
  const mapeamentoInicial = colunas.map((_, indice) => mapaSugerido[indice] ?? ORDEM_PADRAO[indice] ?? "ignorar");

  return { colunas, temCabecalho, mapeamentoInicial };
}

/** Aceita colar direto do Excel/Planilhas (separado por TAB) ou um CSV
 * (`;` ou `,`) — uma linha por participante. `mapa` vem confirmado/editado
 * pelo usuário na tela (não recalcula sozinho), aplicado por posição de
 * coluna em cada linha; `pularPrimeiraLinha` decide se ela é cabeçalho. */
function parseParticipantesComMapa(
  texto: string,
  mapa: CampoParticipante[],
  pularPrimeiraLinha: boolean,
): ParticipanteEvento[] {
  const linhas = texto
    .split("\n")
    .map((linha) => linha.trim())
    .filter(Boolean);
  const linhasDeDados = pularPrimeiraLinha ? linhas.slice(1) : linhas;

  return linhasDeDados
    .map((linha) => {
      const separador = detectarSeparador(linha);
      const campos = linha.split(separador).map((campo) => campo.trim());
      const valores: Partial<Record<CampoParticipante, string>> = {};
      mapa.forEach((campo, indice) => {
        if (campo !== "ignorar" && campos[indice]) valores[campo] = campos[indice];
      });
      return {
        nome: valores.nome ?? "",
        empresa: valores.empresa ?? "",
        cargo: valores.cargo || undefined,
        email: valores.email || undefined,
        telefone: valores.telefone || undefined,
        observacoes: valores.observacoes || undefined,
      };
    })
    .filter((participante) => participante.nome && participante.empresa);
}

function statusTone(status: string): "cyan" | "green" | "muted" {
  if (status === "priorizada") return "green";
  if (status === "descartada") return "muted";
  return "cyan";
}

export function Prospeccao() {
  const [icps, setIcps] = useState<ICP[]>([]);
  const [icpSelecionadoId, setIcpSelecionadoId] = useState<number | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);
  const [origemContas, setOrigemContas] = useState<"icp" | "leads" | "lista">("icp");
  const [leads, setLeads] = useState<Conta[]>([]);
  const [listas, setListas] = useState<ListaProspeccao[]>([]);
  const [listaSelecionadaId, setListaSelecionadaId] = useState<number | null>(null);
  const [contasDaLista, setContasDaLista] = useState<Conta[]>([]);
  const [franquia, setFranquia] = useState<Franquia | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [modalIcpAberto, setModalIcpAberto] = useState(false);
  const [icpEmEdicao, setIcpEmEdicao] = useState<ICP | null>(null);
  const [modalGerarAberto, setModalGerarAberto] = useState(false);
  const [modalListaAberto, setModalListaAberto] = useState(false);
  const [modalImportarAberto, setModalImportarAberto] = useState(false);
  const [contaSelecionadaId, setContaSelecionadaId] = useState<number | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [confirmandoExclusaoIcpId, setConfirmandoExclusaoIcpId] = useState<number | null>(null);
  const [excluindoIcp, setExcluindoIcp] = useState(false);

  const [textoParticipantes, setTextoParticipantes] = useState("");
  const [colunasDetectadas, setColunasDetectadas] = useState<string[]>([]);
  const [mapeamentoColunas, setMapeamentoColunas] = useState<CampoParticipante[]>([]);
  const [primeiraLinhaCabecalho, setPrimeiraLinhaCabecalho] = useState(true);

  const icpSelecionado = icps.find((icp) => icp.id === icpSelecionadoId) ?? null;
  const listaSelecionada = listas.find((lista) => lista.id === listaSelecionadaId) ?? null;

  async function carregarIcps() {
    try {
      const resposta = await api.get<ICP[]>("/icp");
      setIcps(resposta);
      if (resposta.length > 0 && icpSelecionadoId === null) {
        setIcpSelecionadoId(resposta.find((icp) => icp.ativo)?.id ?? resposta[0].id);
      }
    } catch {
      setErro("Não foi possível carregar os ICPs.");
    }
  }

  async function carregarContas(icpId: number) {
    try {
      setContas(await api.get<Conta[]>(`/icp/${icpId}/contas`));
    } catch {
      setErro("Não foi possível carregar as contas do ICP.");
    }
  }

  async function carregarLeads() {
    try {
      setLeads(await api.get<Conta[]>("/leads/contas"));
    } catch {
      setErro("Não foi possível carregar os clientes cadastrados.");
    }
  }

  async function carregarListas() {
    try {
      const resposta = await api.get<ListaProspeccao[]>("/listas-prospeccao");
      setListas(resposta);
      if (resposta.length > 0 && listaSelecionadaId === null) setListaSelecionadaId(resposta[0].id);
    } catch {
      setErro("Não foi possível carregar as listas de prospecção.");
    }
  }

  async function carregarContasDaLista(listaId: number) {
    try {
      setContasDaLista(await api.get<Conta[]>(`/listas-prospeccao/${listaId}/contas`));
    } catch {
      setErro("Não foi possível carregar as contas da lista.");
    }
  }

  async function carregarFranquia() {
    try {
      setFranquia(await api.get<Franquia>("/contas/franquia"));
    } catch {
      // franquia é informativa — falha aqui não bloqueia o resto da tela
    }
  }

  useEffect(() => {
    carregarIcps();
    carregarListas();
    carregarFranquia();
  }, []);

  useEffect(() => {
    if (icpSelecionadoId !== null) carregarContas(icpSelecionadoId);
  }, [icpSelecionadoId]);

  useEffect(() => {
    if (listaSelecionadaId !== null) carregarContasDaLista(listaSelecionadaId);
  }, [listaSelecionadaId]);

  useEffect(() => {
    if (origemContas === "leads" && leads.length === 0) carregarLeads();
  }, [origemContas]);

  async function salvarIcp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      nome: String(form.get("nome")),
      segmento: String(form.get("segmento")),
      porte: String(form.get("porte")),
      regiao: String(form.get("regiao")),
      dores: paraListaPorLinha(String(form.get("dores") ?? "")),
      gatilhos: paraListaPorLinha(String(form.get("gatilhos") ?? "")),
      cnae_codigos: paraLista(String(form.get("cnae_codigos") ?? "")),
      ufs: paraLista(String(form.get("ufs") ?? "")),
    };

    try {
      const salvo = icpEmEdicao
        ? await api.put<ICP>(`/icp/${icpEmEdicao.id}`, body)
        : await api.post<ICP>("/icp", body);
      setModalIcpAberto(false);
      setIcpEmEdicao(null);
      await carregarIcps();
      setIcpSelecionadoId(salvo.id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o ICP.");
    }
  }

  async function clonarIcp(icp: ICP) {
    try {
      const clonado = await api.post<ICP>(`/icp/${icp.id}/clonar`);
      await carregarIcps();
      setIcpSelecionadoId(clonado.id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível clonar o ICP.");
    }
  }

  async function excluirIcp(icp: ICP) {
    if (excluindoIcp) return;
    setExcluindoIcp(true);
    try {
      await api.delete(`/icp/${icp.id}`);
      setConfirmandoExclusaoIcpId(null);
      if (icpSelecionadoId === icp.id) setIcpSelecionadoId(null);
      await carregarIcps();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir o ICP.");
    } finally {
      setExcluindoIcp(false);
    }
  }

  async function criarLista(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const icpIdBruto = String(form.get("icp_id") ?? "");
    const cargos = paraLista(String(form.get("cargos_alvo") ?? ""));
    try {
      const criada = await api.post<ListaProspeccao>("/listas-prospeccao", {
        nome: String(form.get("nome")),
        icp_id: icpIdBruto ? Number(icpIdBruto) : null,
        cargos_alvo: cargos.length > 0 ? cargos : null,
      });
      setModalListaAberto(false);
      await carregarListas();
      setListaSelecionadaId(criada.id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar a lista de prospecção.");
    }
  }

  async function gerarLista(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (icpSelecionadoId === null) return;
    const form = new FormData(event.currentTarget);
    try {
      await api.post(`/icp/${icpSelecionadoId}/contas/gerar`, { quantidade: Number(form.get("quantidade")) });
      setModalGerarAberto(false);
      await carregarContas(icpSelecionadoId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar a lista de contas.");
    }
  }

  function aoColarParticipantes(texto: string) {
    setTextoParticipantes(texto);
    const { colunas, temCabecalho, mapeamentoInicial } = detectarColunas(texto);
    setColunasDetectadas(colunas);
    setMapeamentoColunas(mapeamentoInicial);
    setPrimeiraLinhaCabecalho(temCabecalho);
  }

  function limparFormularioImportacao() {
    setTextoParticipantes("");
    setColunasDetectadas([]);
    setMapeamentoColunas([]);
    setPrimeiraLinhaCabecalho(true);
  }

  async function importarParticipantes(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (listaSelecionadaId === null) return;
    const participantes = parseParticipantesComMapa(textoParticipantes, mapeamentoColunas, primeiraLinhaCabecalho);
    if (participantes.length === 0) {
      setErro("Cole ao menos uma linha válida (Nome e Empresa são obrigatórios).");
      return;
    }
    try {
      const resultado = await api.post<ImportarParticipantesResponse>(
        `/listas-prospeccao/${listaSelecionadaId}/contas/importar-participantes`,
        { participantes },
      );
      setModalImportarAberto(false);
      limparFormularioImportacao();
      const avisoEnriquecimento =
        resultado.contas_enfileiradas_para_enriquecimento > 0
          ? ` ${resultado.contas_enfileiradas_para_enriquecimento} empresa(s) nova(s) entraram na fila de enriquecimento automático (site + contatos) — os dados aparecem aos poucos nos próximos minutos.`
          : "";
      setMensagem(
        `${resultado.contas_criadas} empresa(s) nova(s), ${resultado.contas_reaproveitadas} já existente(s) reaproveitada(s), ${resultado.decisores_criados} contato(s) adicionado(s).${avisoEnriquecimento}`,
      );
      await carregarContasDaLista(listaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível importar os participantes.");
    }
  }

  const contasVisiveis = origemContas === "icp" ? contas : origemContas === "lista" ? contasDaLista : leads;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Prospecção</div>
          <div className="mt-0.5 text-[11px] text-muted">ICPs e contas geradas pelo PREDATOR</div>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="violet"
            onClick={() => {
              setIcpEmEdicao(null);
              setModalIcpAberto(true);
            }}
          >
            + Criar ICP
          </Button>
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <div className="mb-4 grid grid-cols-3 gap-2.5">
        <KpiCard label="Franquia — limite" value={franquia?.limite ?? "—"} colorClassName="text-cyan" />
        <KpiCard label="Usado no mês" value={franquia?.usado ?? "—"} colorClassName="text-amber" />
        <KpiCard label="Restante" value={franquia?.restante ?? "—"} colorClassName="text-green" />
      </div>

      <Card className="mb-4">
        <div className="mb-3 flex gap-2">
          <button
            type="button"
            onClick={() => setOrigemContas("icp")}
            className={`rounded-lg border px-3 py-1.5 text-[12px] ${
              origemContas === "icp" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
            }`}
          >
            Por ICP
          </button>
          <button
            type="button"
            onClick={() => setOrigemContas("leads")}
            className={`rounded-lg border px-3 py-1.5 text-[12px] ${
              origemContas === "leads" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
            }`}
          >
            Clientes Cadastrados
          </button>
          <button
            type="button"
            onClick={() => setOrigemContas("lista")}
            className={`rounded-lg border px-3 py-1.5 text-[12px] ${
              origemContas === "lista" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
            }`}
          >
            Listas de Prospecção
          </button>
        </div>

        {origemContas === "icp" ? (
          <>
            <SectionLabel>ICPs</SectionLabel>
            <div className="flex flex-wrap gap-2">
              {icps.map((icp) => (
                <button
                  key={icp.id}
                  onClick={() => setIcpSelecionadoId(icp.id)}
                  className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                    icp.id === icpSelecionadoId
                      ? "border-cyan bg-cyan/15 text-cyan"
                      : "border-border text-muted hover:text-text"
                  }`}
                >
                  {icp.nome} <span className="opacity-60">v{icp.versao}</span>
                  {!icp.ativo && <span className="ml-1 opacity-50">(inativo)</span>}
                </button>
              ))}
              {icps.length === 0 && <div className="text-[12px] text-muted">Nenhum ICP cadastrado ainda.</div>}
            </div>

            {icpSelecionado && (
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                <div className="text-[11px] text-muted">
                  {icpSelecionado.segmento} · {icpSelecionado.porte} · {icpSelecionado.regiao} · CNAEs:{" "}
                  {icpSelecionado.cnae_codigos.join(", ") || "—"} · UFs: {icpSelecionado.ufs.join(", ") || "—"}
                </div>
                <div className="ml-auto flex gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setIcpEmEdicao(icpSelecionado);
                      setModalIcpAberto(true);
                    }}
                  >
                    Nova versão
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => clonarIcp(icpSelecionado)}>
                    Clonar
                  </Button>
                  <Button size="sm" onClick={() => setModalGerarAberto(true)}>
                    Gerar lista
                  </Button>
                  {confirmandoExclusaoIcpId === icpSelecionado.id ? (
                    <div className="flex items-center gap-1.5 text-[11px]">
                      <span className="text-muted">Excluir "{icpSelecionado.nome}"?</span>
                      <Button size="sm" variant="danger" disabled={excluindoIcp} onClick={() => excluirIcp(icpSelecionado)}>
                        {excluindoIcp ? "Excluindo..." : "Confirmar"}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmandoExclusaoIcpId(null)}>
                        Cancelar
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => setConfirmandoExclusaoIcpId(icpSelecionado.id)}
                    >
                      Excluir
                    </Button>
                  )}
                </div>
              </div>
            )}
          </>
        ) : origemContas === "lista" ? (
          <>
            <div className="mb-2 flex items-center justify-between">
              <SectionLabel>Listas de Prospecção</SectionLabel>
              <Button size="sm" variant="violet" onClick={() => setModalListaAberto(true)}>
                + Criar lista
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {listas.map((lista) => (
                <button
                  key={lista.id}
                  onClick={() => setListaSelecionadaId(lista.id)}
                  className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                    lista.id === listaSelecionadaId
                      ? "border-cyan bg-cyan/15 text-cyan"
                      : "border-border text-muted hover:text-text"
                  }`}
                >
                  {lista.nome}
                </button>
              ))}
              {listas.length === 0 && (
                <div className="text-[12px] text-muted">Nenhuma lista de prospecção criada ainda.</div>
              )}
            </div>

            {listaSelecionada && (
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                <div className="text-[11px] text-muted">
                  {listaSelecionada.icp_id ? "Vinculada a um ICP" : "Sem ICP vinculado"} · Cargos-alvo:{" "}
                  {listaSelecionada.cargos_alvo?.join(", ") || "padrão (C-Level, Diretoria, Gerência, Head)"}
                </div>
                <div className="ml-auto flex gap-2">
                  <Button size="sm" onClick={() => setModalImportarAberto(true)}>
                    Importar participantes
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="text-[11px] text-muted">
            Clientes já cadastrados no CRM sem estar vinculados a um ICP (indicação, evento, contato pessoal) —
            cadastrados pela tela de Leads.
          </div>
        )}
      </Card>

      <Card>
        <SectionLabel>
          Contas{" "}
          {origemContas === "icp"
            ? icpSelecionado
              ? `— ${icpSelecionado.nome}`
              : ""
            : origemContas === "lista"
              ? listaSelecionada
                ? `— ${listaSelecionada.nome}`
                : ""
              : "— Clientes Cadastrados"}
        </SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">CNPJ</th>
              <th className="p-2 text-left">Score</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Ações</th>
            </tr>
          </thead>
          <tbody>
            {contasVisiveis.map((conta) => (
              <tr key={conta.id} className="border-b border-border">
                <td className="p-2 font-semibold">{conta.nome}</td>
                <td className="p-2 text-muted">{conta.cnpj ?? "—"}</td>
                <td className="p-2 text-cyan">{conta.score_aderencia ?? "—"}</td>
                <td className="p-2">
                  <Badge tone={statusTone(conta.status)}>{conta.status}</Badge>
                </td>
                <td className="p-2">
                  <Button size="sm" variant="ghost" onClick={() => setContaSelecionadaId(conta.id)}>
                    Ver detalhes
                  </Button>
                </td>
              </tr>
            ))}
            {contasVisiveis.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-muted">
                  {origemContas === "icp"
                    ? "Nenhuma conta gerada para este ICP ainda."
                    : origemContas === "lista"
                      ? "Nenhuma conta importada para esta lista ainda."
                      : "Nenhum cliente cadastrado ainda."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        title={icpEmEdicao ? `Nova versão — ${icpEmEdicao.nome}` : "Criar ICP"}
        open={modalIcpAberto}
        onClose={() => setModalIcpAberto(false)}
      >
        <form onSubmit={salvarIcp} className="flex flex-col gap-3">
          {(
            [
              ["nome", "Nome"],
              ["segmento", "Segmento"],
              ["regiao", "Região"],
            ] as const
          ).map(([campo, rotulo]) => (
            <div key={campo}>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{rotulo}</div>
              <Input name={campo} required defaultValue={icpEmEdicao?.[campo as keyof ICP] as string} />
            </div>
          ))}
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Porte</div>
            <Select name="porte" defaultValue={icpEmEdicao?.porte ?? ""}>
              <option value="">Qualquer porte</option>
              <option value="MICRO">Micro</option>
              <option value="PEQUENO">Pequeno</option>
              <option value="DEMAIS">Demais (médio/grande)</option>
            </Select>
          </div>
          {(
            [
              ["cnae_codigos", "CNAEs (separados por vírgula)"],
              ["ufs", "UFs (separadas por vírgula)"],
            ] as const
          ).map(([campo, rotulo]) => (
            <div key={campo}>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{rotulo}</div>
              <Input name={campo} defaultValue={(icpEmEdicao?.[campo as keyof ICP] as string[])?.join(", ")} />
            </div>
          ))}
          {(
            [
              ["dores", "Dores (uma por linha)"],
              ["gatilhos", "Gatilhos (um por linha)"],
            ] as const
          ).map(([campo, rotulo]) => (
            <div key={campo}>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{rotulo}</div>
              <Textarea
                name={campo}
                rows={3}
                defaultValue={(icpEmEdicao?.[campo as keyof ICP] as string[])?.join("\n")}
              />
            </div>
          ))}
          <Button type="submit" className="mt-1 w-full justify-center">
            Salvar
          </Button>
        </form>
      </Modal>

      <Modal title="Gerar lista de contas" open={modalGerarAberto} onClose={() => setModalGerarAberto(false)}>
        <form onSubmit={gerarLista} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Quantidade</div>
            <Input name="quantidade" type="number" required defaultValue={10} min={1} />
          </div>
          <Button type="submit" className="w-full justify-center">
            Gerar
          </Button>
        </form>
      </Modal>

      <Modal title="Criar lista de prospecção" open={modalListaAberto} onClose={() => setModalListaAberto(false)}>
        <form onSubmit={criarLista} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
            <Input name="nome" required placeholder="Ex.: Evento Febraban 2026" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">ICP vinculado (opcional)</div>
            <Select name="icp_id" defaultValue="">
              <option value="">Nenhum — vira lead sem ICP</option>
              {icps.map((icp) => (
                <option key={icp.id} value={icp.id}>
                  {icp.nome}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Cargos-alvo pro enriquecimento (separados por vírgula, opcional)
            </div>
            <Input name="cargos_alvo" placeholder="Ex.: CISO, Diretor de Segurança da Informação, CTO" />
            <div className="mt-1 text-[11px] text-muted">
              Restringe a busca de decisores só a esses cargos — economiza consulta e evita trazer contato
              irrelevante pro projeto (ex.: diretor de logística numa lista de cibersegurança). Em branco, usa o
              padrão genérico (C-Level, Diretoria, Gerência, Head).
            </div>
          </div>
          <Button type="submit" className="w-full justify-center">
            Criar lista
          </Button>
        </form>
      </Modal>

      <Modal
        title={`Importar participantes${listaSelecionada ? ` — ${listaSelecionada.nome}` : ""}`}
        open={modalImportarAberto}
        onClose={() => {
          setModalImportarAberto(false);
          limparFormularioImportacao();
        }}
      >
        <form onSubmit={importarParticipantes} className="flex flex-col gap-3">
          <div className="text-[11px] text-muted">
            Cole direto do Excel/Planilhas — o mapeamento das colunas aparece abaixo pra você conferir e ajustar
            antes de importar (ex.: mandar uma coluna extra pras Observações da empresa). Empresas repetidas viram
            uma única conta; participantes duplicados (mesmo nome ou e-mail na mesma empresa) são ignorados.
          </div>
          <Textarea
            value={textoParticipantes}
            onChange={(event) => aoColarParticipantes(event.target.value)}
            required
            rows={8}
            placeholder={"Nome\tEmpresa\tCargo\tE-mail\tTelefone\nJoana Silva\tClinica Vida Plena\tDiretora\tjoana@vidaplena.com\t11999990000"}
          />
          {colunasDetectadas.length > 0 && (
            <div className="rounded-lg border border-border p-2.5">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-[10px] tracking-wide text-muted uppercase">Mapeamento de colunas</div>
                <label className="flex items-center gap-1.5 text-[11px] text-muted">
                  <input
                    type="checkbox"
                    checked={primeiraLinhaCabecalho}
                    onChange={(event) => setPrimeiraLinhaCabecalho(event.target.checked)}
                  />
                  Primeira linha é cabeçalho
                </label>
              </div>
              <div className="flex flex-col gap-1.5">
                {colunasDetectadas.map((coluna, indice) => (
                  <div key={indice} className="flex items-center gap-2 text-[12px]">
                    <div className="w-32 shrink-0 truncate text-muted" title={coluna}>
                      {coluna || `Coluna ${indice + 1}`}
                    </div>
                    <Select
                      value={mapeamentoColunas[indice] ?? "ignorar"}
                      onChange={(event) => {
                        const novoMapeamento = [...mapeamentoColunas];
                        novoMapeamento[indice] = event.target.value as CampoParticipante;
                        setMapeamentoColunas(novoMapeamento);
                      }}
                    >
                      {CAMPOS_DISPONIVEIS.map((campo) => (
                        <option key={campo.valor} value={campo.valor}>
                          {campo.rotulo}
                        </option>
                      ))}
                    </Select>
                  </div>
                ))}
              </div>
            </div>
          )}
          <Button type="submit" className="w-full justify-center">
            Importar
          </Button>
        </form>
      </Modal>

      {contaSelecionadaId !== null && (
        <ContaDetalheModal
          contaId={contaSelecionadaId}
          onClose={() => setContaSelecionadaId(null)}
          onAtualizado={() => {
            if (icpSelecionadoId !== null) carregarContas(icpSelecionadoId);
            if (listaSelecionadaId !== null) carregarContasDaLista(listaSelecionadaId);
          }}
        />
      )}
    </div>
  );
}
