import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { SeletorArquivo } from "@/components/ui/SeletorArquivo";
import { api, ApiError, getBlob } from "@/lib/api";
import { detectarColunas, parseLinhasComMapa } from "@/lib/importarPlanilha";

type CampoNegocio =
  | "chave_importacao"
  | "empresa_nome"
  | "empresa_cnpj"
  | "decisor_nome"
  | "decisor_email"
  | "decisor_telefone"
  | "decisor_cargo"
  | "nome"
  | "valor"
  | "probabilidade"
  | "estagio_nome"
  | "motivo_perda"
  | "vendedor_email"
  | "criado_em"
  | "ganho_em"
  | "perdido_em"
  | "ignorar";

const CAMPOS_DISPONIVEIS: { valor: CampoNegocio; rotulo: string }[] = [
  { valor: "empresa_nome", rotulo: "Empresa" },
  { valor: "empresa_cnpj", rotulo: "CNPJ da empresa" },
  { valor: "nome", rotulo: "Nome do negócio" },
  { valor: "valor", rotulo: "Valor (R$)" },
  { valor: "probabilidade", rotulo: "Probabilidade (%)" },
  { valor: "estagio_nome", rotulo: "Estágio do funil" },
  { valor: "decisor_nome", rotulo: "Contato — nome" },
  { valor: "decisor_email", rotulo: "Contato — e-mail" },
  { valor: "decisor_telefone", rotulo: "Contato — telefone" },
  { valor: "decisor_cargo", rotulo: "Contato — cargo" },
  { valor: "vendedor_email", rotulo: "E-mail do vendedor responsável" },
  { valor: "motivo_perda", rotulo: "Motivo da perda" },
  { valor: "criado_em", rotulo: "Data de criação" },
  { valor: "ganho_em", rotulo: "Data de ganho" },
  { valor: "perdido_em", rotulo: "Data de perda" },
  { valor: "chave_importacao", rotulo: "ID externo (evita duplicar em reimportação)" },
  { valor: "ignorar", rotulo: "Ignorar" },
];

// Sinônimos comuns em exports de outras plataformas de CRM (e no nosso
// próprio export — que usa exatamente os nomes de campo canônicos, então
// reimportar um CSV da própria B2B ON não exige nenhum ajuste manual).
const SINONIMOS_CABECALHO: Record<string, CampoNegocio> = {
  chave_importacao: "chave_importacao",
  "id externo": "chave_importacao",
  id_externo: "chave_importacao",
  "deal id": "chave_importacao",
  negocio_id: "chave_importacao",
  id: "chave_importacao",
  empresa_nome: "empresa_nome",
  empresa: "empresa_nome",
  cliente: "empresa_nome",
  conta: "empresa_nome",
  "nome da empresa": "empresa_nome",
  empresa_cnpj: "empresa_cnpj",
  cnpj: "empresa_cnpj",
  decisor_nome: "decisor_nome",
  contato: "decisor_nome",
  responsavel: "decisor_nome",
  decisor: "decisor_nome",
  decisor_email: "decisor_email",
  email: "decisor_email",
  "e-mail": "decisor_email",
  decisor_telefone: "decisor_telefone",
  telefone: "decisor_telefone",
  fone: "decisor_telefone",
  celular: "decisor_telefone",
  decisor_cargo: "decisor_cargo",
  cargo: "decisor_cargo",
  funcao: "decisor_cargo",
  nome: "nome",
  negocio: "nome",
  oportunidade: "nome",
  "nome do negocio": "nome",
  titulo: "nome",
  valor: "valor",
  "valor do negocio": "valor",
  probabilidade: "probabilidade",
  estagio_nome: "estagio_nome",
  estagio: "estagio_nome",
  etapa: "estagio_nome",
  status: "estagio_nome",
  stage: "estagio_nome",
  motivo_perda: "motivo_perda",
  "motivo da perda": "motivo_perda",
  vendedor_email: "vendedor_email",
  vendedor: "vendedor_email",
  criado_em: "criado_em",
  "data de criacao": "criado_em",
  "criado em": "criado_em",
  ganho_em: "ganho_em",
  "data de fechamento": "ganho_em",
  "data ganho": "ganho_em",
  perdido_em: "perdido_em",
  "data perdido": "perdido_em",
};

// Mesma ordem do cabeçalho gerado por `crm_service.exportar_negocios_csv`
// — melhor palpite quando o cabeçalho da planilha não é reconhecido.
const ORDEM_PADRAO: CampoNegocio[] = [
  "chave_importacao",
  "empresa_nome",
  "empresa_cnpj",
  "decisor_nome",
  "decisor_email",
  "decisor_telefone",
  "decisor_cargo",
  "nome",
  "valor",
  "probabilidade",
  "estagio_nome",
  "motivo_perda",
  "vendedor_email",
  "criado_em",
  "ganho_em",
  "perdido_em",
];

interface LinhaImportacaoNegocio {
  chave_importacao?: string;
  empresa_nome: string;
  empresa_cnpj?: string;
  decisor_nome?: string;
  decisor_email?: string;
  decisor_telefone?: string;
  decisor_cargo?: string;
  nome: string;
  valor?: number;
  probabilidade?: number;
  estagio_nome?: string;
  motivo_perda?: string;
  vendedor_email?: string;
  criado_em?: string;
  ganho_em?: string;
  perdido_em?: string;
}

interface ErroImportacaoNegocio {
  linha: number;
  motivo: string;
}

interface ImportarNegociosResponse {
  negocios_criados: number;
  negocios_atualizados: number;
  contas_criadas: number;
  contas_reaproveitadas: number;
  decisores_criados: number;
  erros: ErroImportacaoNegocio[];
}

/** Aceita "1.234,56" (pt-BR), "1234.56" ou "1234,56" — o último separador
 * encontrado é tratado como o decimal, o outro (se houver) como milhar. */
function parseValorMonetario(texto: string): number | undefined {
  const limpo = texto.replace(/[^\d,.-]/g, "").trim();
  if (!limpo) return undefined;
  let normalizado = limpo;
  if (limpo.includes(",") && limpo.includes(".")) {
    normalizado =
      limpo.lastIndexOf(",") > limpo.lastIndexOf(".")
        ? limpo.replace(/\./g, "").replace(",", ".")
        : limpo.replace(/,/g, "");
  } else if (limpo.includes(",")) {
    normalizado = limpo.replace(",", ".");
  }
  const numero = Number(normalizado);
  return Number.isFinite(numero) ? numero : undefined;
}

/** Aceita "AAAA-MM-DD" (com ou sem horário, ISO) ou "DD/MM/AAAA". */
function parseDataFlexivel(texto: string): string | undefined {
  const valor = texto.trim();
  if (!valor) return undefined;
  if (/^\d{4}-\d{2}-\d{2}/.test(valor)) {
    const data = new Date(valor);
    return Number.isNaN(data.getTime()) ? undefined : data.toISOString();
  }
  const brMatch = valor.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (brMatch) {
    const [, dia, mes, ano] = brMatch;
    const data = new Date(Number(ano), Number(mes) - 1, Number(dia));
    return Number.isNaN(data.getTime()) ? undefined : data.toISOString();
  }
  return undefined;
}

function parseLinhasNegocio(
  texto: string,
  mapa: CampoNegocio[],
  pularPrimeiraLinha: boolean,
): LinhaImportacaoNegocio[] {
  return parseLinhasComMapa(texto, mapa, pularPrimeiraLinha, "ignorar", (valores) => {
    if (!valores.empresa_nome || !valores.nome) return null;
    return {
      chave_importacao: valores.chave_importacao || undefined,
      empresa_nome: valores.empresa_nome,
      empresa_cnpj: valores.empresa_cnpj || undefined,
      decisor_nome: valores.decisor_nome || undefined,
      decisor_email: valores.decisor_email || undefined,
      decisor_telefone: valores.decisor_telefone || undefined,
      decisor_cargo: valores.decisor_cargo || undefined,
      nome: valores.nome,
      valor: valores.valor ? parseValorMonetario(valores.valor) : undefined,
      probabilidade: valores.probabilidade ? Number(valores.probabilidade.replace(/\D/g, "")) : undefined,
      estagio_nome: valores.estagio_nome || undefined,
      motivo_perda: valores.motivo_perda || undefined,
      vendedor_email: valores.vendedor_email || undefined,
      criado_em: valores.criado_em ? parseDataFlexivel(valores.criado_em) : undefined,
      ganho_em: valores.ganho_em ? parseDataFlexivel(valores.ganho_em) : undefined,
      perdido_em: valores.perdido_em ? parseDataFlexivel(valores.perdido_em) : undefined,
    };
  });
}

interface ImportarExportarNegociosProps {
  open: boolean;
  onClose: () => void;
  onImportado: () => void;
}

/** Import/export em lote de oportunidades via CSV (raio-X 2026-09-14):
 * cliente chegando de outra plataforma com histórico de negócios, ou
 * saindo da B2B ON e precisando levar os próprios dados embora. Restrito
 * a admin/super_admin — ver `app/api/v1/crm.py`. */
export function ImportarExportarNegocios({ open, onClose, onImportado }: ImportarExportarNegociosProps) {
  const [texto, setTexto] = useState("");
  const [colunasDetectadas, setColunasDetectadas] = useState<string[]>([]);
  const [mapeamentoColunas, setMapeamentoColunas] = useState<CampoNegocio[]>([]);
  const [primeiraLinhaCabecalho, setPrimeiraLinhaCabecalho] = useState(true);
  const [importando, setImportando] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ImportarNegociosResponse | null>(null);

  function reiniciar() {
    setTexto("");
    setColunasDetectadas([]);
    setMapeamentoColunas([]);
    setPrimeiraLinhaCabecalho(true);
    setErro(null);
    setResultado(null);
  }

  function fechar() {
    reiniciar();
    onClose();
  }

  function aoMudarTexto(novoTexto: string) {
    setTexto(novoTexto);
    setResultado(null);
    const { colunas, temCabecalho, mapeamentoInicial } = detectarColunas(
      novoTexto,
      SINONIMOS_CABECALHO,
      ORDEM_PADRAO,
      "ignorar",
      ["empresa_nome", "nome"],
    );
    setColunasDetectadas(colunas);
    setMapeamentoColunas(mapeamentoInicial);
    setPrimeiraLinhaCabecalho(temCabecalho);
  }

  function aoSelecionarArquivo(arquivo: File) {
    const leitor = new FileReader();
    leitor.onload = () => aoMudarTexto(String(leitor.result ?? ""));
    leitor.readAsText(arquivo, "utf-8");
  }

  const chaveMapeada = mapeamentoColunas.includes("chave_importacao");

  async function importar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (importando) return;
    const linhas = parseLinhasNegocio(texto, mapeamentoColunas, primeiraLinhaCabecalho);
    if (linhas.length === 0) {
      setErro("Cole ou selecione um arquivo com ao menos uma linha válida (Empresa e Nome do negócio são obrigatórios).");
      return;
    }
    setImportando(true);
    setErro(null);
    try {
      const resposta = await api.post<ImportarNegociosResponse>("/crm/negocios/importar", { linhas });
      setResultado(resposta);
      onImportado();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível importar as oportunidades.");
    } finally {
      setImportando(false);
    }
  }

  async function exportar() {
    if (exportando) return;
    setExportando(true);
    setErro(null);
    try {
      const blob = await getBlob("/crm/negocios/exportar.csv");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "oportunidades.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setErro("Não foi possível exportar as oportunidades.");
    } finally {
      setExportando(false);
    }
  }

  return (
    <Modal title="Importar/exportar oportunidades (CSV)" open={open} onClose={fechar}>
      <div className="flex flex-col gap-4">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Exportar</div>
          <div className="mb-2 text-[11px] text-muted">
            Baixe todas as oportunidades deste tenant num CSV — útil pra levar o histórico a outra plataforma, ou
            como backup.
          </div>
          <Button type="button" variant="ghost" onClick={exportar} disabled={exportando}>
            {exportando ? "Gerando..." : "Exportar CSV"}
          </Button>
        </div>

        <div className="border-t border-border pt-4">
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Importar</div>

          {erro && <div className="mb-2 text-[12px] text-red">{erro}</div>}

          {resultado ? (
            <div className="flex flex-col gap-2 text-[12px]">
              <div>
                {resultado.negocios_criados} negócio(s) criado(s), {resultado.negocios_atualizados} atualizado(s),{" "}
                {resultado.contas_criadas} empresa(s) nova(s), {resultado.contas_reaproveitadas} reaproveitada(s),{" "}
                {resultado.decisores_criados} contato(s) adicionado(s).
              </div>
              {resultado.erros.length > 0 && (
                <div className="rounded-lg border border-red/30 bg-red/5 p-2.5 text-red">
                  <div className="mb-1 font-bold">{resultado.erros.length} linha(s) com erro:</div>
                  <ul className="flex flex-col gap-0.5">
                    {resultado.erros.map((item) => (
                      <li key={item.linha}>
                        Linha {item.linha}: {item.motivo}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Button type="button" variant="ghost" onClick={reiniciar}>
                Importar outro arquivo
              </Button>
            </div>
          ) : (
            <form onSubmit={importar} className="flex flex-col gap-3">
              <div className="text-[11px] text-muted">
                Cole o conteúdo de um CSV/planilha ou selecione o arquivo — o mapeamento de colunas aparece abaixo
                pra você conferir e ajustar antes de importar.
              </div>
              <SeletorArquivo
                accept=".csv,text/csv"
                onSelecionar={aoSelecionarArquivo}
                rotulo="Selecionar arquivo .csv"
              />
              <Textarea
                value={texto}
                onChange={(event) => aoMudarTexto(event.target.value)}
                rows={6}
                placeholder={
                  "Empresa,CNPJ,Nome do negócio,Valor,Estágio\nAcme Ltda,12.345.678/0001-90,Licença anual,15000,Negociação"
                }
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
                            novoMapeamento[indice] = event.target.value as CampoNegocio;
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
                  {!chaveMapeada && (
                    <div className="mt-2 text-[11px] text-amber">
                      Nenhuma coluna mapeada para "ID externo" — se você reimportar este mesmo arquivo depois, as
                      oportunidades serão duplicadas em vez de atualizadas.
                    </div>
                  )}
                </div>
              )}
              <Button type="submit" disabled={importando} className="w-full justify-center">
                {importando ? "Importando..." : "Importar"}
              </Button>
            </form>
          )}
        </div>
      </div>
    </Modal>
  );
}
