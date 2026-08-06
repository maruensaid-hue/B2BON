import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";

export function Privacidade() {
  return (
    <div className="mx-auto max-w-3xl p-5.5">
      <Link to="/login" className="mb-4 inline-block text-[12px] text-cyan hover:underline">
        ← Voltar
      </Link>

      <Card>
        <div className="mb-1 font-head text-xl font-bold">Política de Privacidade — B2B ON</div>
        <div className="mb-5 text-[11px] text-muted">Última atualização: agosto de 2026</div>

        <div className="flex flex-col gap-4 text-[13px] leading-relaxed text-text">
          <p>
            A B2B ON é uma plataforma operada pela CyberFort para times comerciais B2B — CRM,
            prospecção (PREDATOR), rede social entre empresas e MAP (Motor de Alta Performance).
            Esta política explica que dados a plataforma trata, com qual base legal e quais
            direitos cada pessoa tem sobre eles, nos termos da Lei Geral de Proteção de Dados
            (Lei 13.709/2018).
          </p>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">1. Dois grupos de dados distintos</div>
            <p>
              A plataforma trata dois grupos de dados pessoais, com papéis diferentes sob a LGPD:
            </p>
            <ul className="mt-2 list-inside list-disc space-y-1.5">
              <li>
                <b>Dados de quem usa a plataforma</b> (nome, e-mail, senha com hash, papel de
                acesso) — aqui a CyberFort é <b>controladora</b>: decide como esses dados são
                tratados para operar a conta e a autenticação.
              </li>
              <li>
                <b>Dados de terceiros prospectados</b> por um cliente da plataforma através do
                motor de prospecção (nome, cargo, e-mail, telefone e/ou LinkedIn de decisores de
                empresas-alvo) — aqui quem decide iniciar a prospecção é o cliente contratante, e
                é ele o <b>controlador</b>; a CyberFort atua como <b>operadora</b>, fornecendo a
                tecnologia que viabiliza o tratamento em nome do cliente.
              </li>
            </ul>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">2. Base legal da prospecção</div>
            <p>
              A prospecção B2B feita através da plataforma se apoia no <b>legítimo interesse</b>{" "}
              (art. 7º, IX da LGPD) — contato comercial entre empresas, sem uso de dados
              sensíveis, com finalidade legítima e específica. Fontes usadas: bases públicas
              (ex.: Receita Federal) e o próprio site institucional da empresa prospectada. Todo
              contato enviado através da plataforma inclui um mecanismo de descadastro — a partir
              do momento em que alguém se descadastra, a supressão é permanente e vale para todos
              os canais e cadências.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">3. Retenção</div>
            <p>
              Dados de pessoas prospectadas que nunca interagem e nunca se tornam cliente do
              contratante são anonimizados automaticamente após 24 meses sem nenhuma interação —
              a plataforma não acumula dado pessoal de prospecção por tempo indefinido. Quem se
              torna cliente do contratante segue retido pelo tempo da relação contratual, base
              legal distinta (execução de contrato).
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">4. Direitos do titular</div>
            <p>Qualquer pessoa cujo dado seja tratado pela plataforma pode solicitar:</p>
            <ul className="mt-2 list-inside list-disc space-y-1">
              <li>Confirmação de que seu dado está sendo tratado e acesso a ele;</li>
              <li>Correção de dado incompleto, inexato ou desatualizado;</li>
              <li>Eliminação dos dados tratados com base no legítimo interesse;</li>
              <li>Portabilidade a outro fornecedor, mediante requisição expressa.</li>
            </ul>
            <p className="mt-2">
              Para dados de prospecção, o caminho mais rápido é o link de descadastro presente em
              toda mensagem recebida, ou contato direto com a empresa que iniciou a abordagem —
              ela é a controladora e a responsável por atender a solicitação, com o suporte
              técnico da CyberFort. Para dados da própria conta de acesso à plataforma, o pedido
              deve ser feito diretamente à CyberFort pelo canal de suporte do seu contrato.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">5. Segurança</div>
            <p>
              Senhas nunca são armazenadas em texto puro (hash bcrypt); sessões usam token
              assinado (JWT) com expiração; comunicação é sempre criptografada (HTTPS/TLS); e o
              acesso a dados de cada cliente é isolado por conta (multi-tenant) — um cliente nunca
              enxerga dados de outro.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">6. Alterações</div>
            <p>
              Esta política pode ser atualizada para refletir mudanças na plataforma ou na
              legislação. A data no topo desta página indica a versão vigente.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
