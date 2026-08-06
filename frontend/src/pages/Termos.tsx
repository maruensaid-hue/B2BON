import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";

export function Termos() {
  return (
    <div className="mx-auto max-w-3xl p-5.5">
      <Link to="/login" className="mb-4 inline-block text-[12px] text-cyan hover:underline">
        ← Voltar
      </Link>

      <Card>
        <div className="mb-1 font-head text-xl font-bold">Termos de Uso — B2B ON</div>
        <div className="mb-5 text-[11px] text-muted">Última atualização: agosto de 2026</div>

        <div className="flex flex-col gap-4 text-[13px] leading-relaxed text-text">
          <div>
            <div className="mb-1.5 font-semibold text-cyan">1. O serviço</div>
            <p>
              A B2B ON é uma plataforma SaaS multi-tenant operada pela CyberFort, com módulos de
              CRM, prospecção B2B (PREDATOR), rede social entre empresas e MAP (Motor de Alta
              Performance). O acesso é por conta (tenant), com usuários vinculados a uma licença
              contratada.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">2. Uso aceitável da prospecção</div>
            <p>
              O motor de prospecção deve ser usado apenas para contato comercial B2B legítimo,
              respeitando o mecanismo de opt-out da plataforma — reenviar mensagem para quem já se
              descadastrou, ou usar os dados coletados para finalidade diferente da prospecção
              comercial declarada, viola estes termos e a base legal (legítimo interesse) sob a
              qual a plataforma opera.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">3. Responsabilidade pelos dados prospectados</div>
            <p>
              Ao usar o motor de prospecção, o cliente contratante é o controlador dos dados
              pessoais de terceiros que decide prospectar (ver Política de Privacidade) — a
              CyberFort fornece a tecnologia (operadora), mas a decisão de quem contatar e a
              responsabilidade por essa decisão são do cliente.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">4. Contas e acesso</div>
            <p>
              Cada usuário é responsável por manter sua senha em sigilo e por toda atividade
              realizada com sua conta. Papéis de acesso (usuário, admin, super admin) definem o
              que cada pessoa pode ver e fazer dentro do tenant — o cliente contratante é
              responsável por atribuir papéis com critério dentro da própria equipe.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">5. Disponibilidade</div>
            <p>
              A plataforma é fornecida "como está", com esforço razoável de disponibilidade, sem
              garantia de operação ininterrupta. Manutenções e atualizações podem causar
              indisponibilidade temporária, preferencialmente comunicada com antecedência quando
              planejada.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">6. Cancelamento</div>
            <p>
              O cliente pode cancelar a licença conforme as condições comerciais do seu contrato.
              Dados da conta são retidos pelo período contratual aplicável e depois eliminados ou
              anonimizados, conforme a Política de Privacidade.
            </p>
          </div>

          <div>
            <div className="mb-1.5 font-semibold text-cyan">7. Alterações destes termos</div>
            <p>
              Estes termos podem ser atualizados para refletir mudanças na plataforma ou em
              requisitos legais. A data no topo desta página indica a versão vigente.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
