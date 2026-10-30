from odoo import fields, models


class HospitalContractLine(models.Model):
    _name = "hospital.contract.line"
    _description = "Contract Category Discount"
    _order = "contract_id, id"

    contract_id = fields.Many2one(
        "hospital.contract",
        required=True,
        index=True,
        ondelete="cascade",
    )
    category_id = fields.Many2one(
        "product.category",
        string="Product Category",
        required=True,
        ondelete="restrict",
        help="Applies to products in this category and its sub-categories "
        "unless a more specific rule exists.",
    )
    discount = fields.Float(
        string="Discount (%)",
        digits="Discount",
        required=True,
    )

    _category_uniq = models.Constraint(
        "UNIQUE(contract_id, category_id)",
        "This category already has a rule in the contract.",
    )
    _discount_range = models.Constraint(
        "CHECK(discount >= 0 AND discount <= 100)",
        "The discount must be between 0 and 100.",
    )
