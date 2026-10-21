from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # A computed field (not an onchange) so the discount is also applied to lines created
    # by code, imports and the billing button, and follows the contract and the payer.
    @api.depends("order_id.hospital_contract_id", "order_id.hospital_payer")
    def _compute_discount(self):
        super()._compute_discount()
        for line in self:
            contract = line.order_id.hospital_contract_id
            if not contract or not line.product_id or line.display_type or line.combo_item_id:
                continue
            line.discount = contract._get_line_discount(
                line.product_id, line.order_id.hospital_payer
            )
