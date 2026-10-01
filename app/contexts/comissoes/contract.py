"""Contrato público do Commission Engine (D-074): Tax Profile, Infrastructure Cost Model, apuração da Margem
Comissionável Líquida (Tax Engine e Commission Policy da margem, D-075), ciclo de status e waterfall. Único lugar onde comissão é calculada."""

from app.contexts.comissoes import infraestrutura, motor, politica, tipos, tributos, waterfall

__all__ = ["infraestrutura", "motor", "politica", "tipos", "tributos", "waterfall"]
