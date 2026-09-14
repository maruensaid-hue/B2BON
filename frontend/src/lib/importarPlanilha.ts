/** Parsing genérico de planilha colada/arquivo CSV com mapeamento de
 * coluna configurável pelo usuário — extraído de `Prospeccao.tsx`
 * (import de participantes de evento) pra ser reaproveitado também na
 * importação de oportunidades do CRM (raio-X 2026-09-14). Aceita colar
 * direto do Excel/Planilhas (separado por TAB) ou um CSV (`;` ou `,`).
 * A lógica de mapeamento por si só é agnóstica de domínio — cada tela
 * define seus próprios campos/sinônimos e decide o que fazer com cada
 * linha mapeada. */

export function normalizarCabecalho(texto: string): string {
  return texto
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

export function detectarSeparador(linha: string): string {
  return linha.includes("\t") ? "\t" : linha.includes(";") ? ";" : ",";
}

/** Lê só a primeira linha do texto pra sugerir um mapeamento de
 * coluna → campo (por sinônimo de cabeçalho reconhecido, ou pela ordem
 * padrão se não reconhecer nada) — a tela chamadora deixa o usuário
 * revisar/ajustar esse mapeamento antes de confirmar a importação.
 * `camposObrigatoriosParaCabecalho` decide se a 1ª linha deve ser tratada
 * como cabeçalho (todos eles precisam ter sido reconhecidos) ou como
 * a primeira linha de dados. */
export function detectarColunas<TCampo extends string>(
  texto: string,
  sinonimos: Record<string, TCampo>,
  ordemPadrao: TCampo[],
  campoIgnorar: TCampo,
  camposObrigatoriosParaCabecalho: TCampo[],
): { colunas: string[]; temCabecalho: boolean; mapeamentoInicial: TCampo[] } {
  const linhas = texto
    .split("\n")
    .map((linha) => linha.trim())
    .filter(Boolean);
  if (linhas.length === 0) return { colunas: [], temCabecalho: false, mapeamentoInicial: [] };

  const separador = detectarSeparador(linhas[0]);
  const colunas = linhas[0].split(separador).map((celula) => celula.trim());
  const mapaSugerido = colunas.map((celula) => sinonimos[normalizarCabecalho(celula)]);
  const reconhecidos = mapaSugerido.filter(Boolean);
  const temCabecalho = camposObrigatoriosParaCabecalho.every((campo) => reconhecidos.includes(campo));
  const mapeamentoInicial = colunas.map((_, indice) => mapaSugerido[indice] ?? ordemPadrao[indice] ?? campoIgnorar);

  return { colunas, temCabecalho, mapeamentoInicial };
}

/** Aplica um mapeamento de coluna → campo (já confirmado/editado pelo
 * usuário na tela) a cada linha de dados, por posição de coluna;
 * `pularPrimeiraLinha` decide se ela é cabeçalho. `montarLinha` recebe os
 * valores mapeados de uma linha e decide o formato/validação final —
 * retornar `null` descarta a linha (ex.: campos obrigatórios ausentes). */
export function parseLinhasComMapa<TCampo extends string, TResultado>(
  texto: string,
  mapa: TCampo[],
  pularPrimeiraLinha: boolean,
  campoIgnorar: TCampo,
  montarLinha: (valores: Partial<Record<TCampo, string>>) => TResultado | null,
): TResultado[] {
  const linhas = texto
    .split("\n")
    .map((linha) => linha.trim())
    .filter(Boolean);
  const linhasDeDados = pularPrimeiraLinha ? linhas.slice(1) : linhas;

  const resultado: TResultado[] = [];
  for (const linha of linhasDeDados) {
    const separador = detectarSeparador(linha);
    const campos = linha.split(separador).map((campo) => campo.trim());
    const valores: Partial<Record<TCampo, string>> = {};
    mapa.forEach((campo, indice) => {
      if (campo !== campoIgnorar && campos[indice]) valores[campo] = campos[indice];
    });
    const item = montarLinha(valores);
    if (item !== null) resultado.push(item);
  }
  return resultado;
}
