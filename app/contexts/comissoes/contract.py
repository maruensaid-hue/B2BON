"""Contrato público do Commission Engine (D-074): Tax Profile, Infrastructure Cost Model, apuração da Margem
Comissionável Líquida, ciclo de status e waterfall. Único lugar onde comissão é calculada."""

from app.contexts.comissoes import infraestrutura, motor, tipos, tributos, waterfall

__all__ = ["infraestrutura", "motor", "tipos", "tributos", "waterfall"]
