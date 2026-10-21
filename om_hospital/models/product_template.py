from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_medicine = fields.Boolean(
        string="Is Medicine",
        help="Tick for products that doctors can prescribe. Only these appear on prescriptions.",
    )
