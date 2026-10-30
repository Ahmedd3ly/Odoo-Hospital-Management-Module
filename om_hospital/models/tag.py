from odoo import fields, models


class HospitalTag(models.Model):
    _name = "hospital.tag"
    _description = "Hospital Tag"
    _order = "name"

    name = fields.Char(string="Tag Name", required=True, help="Name of the tag.")
    color = fields.Integer(
        string="Color Index",
        help="Custom color selector for the tag badge in Odoo.",
    )

    _name_uniq = models.Constraint(
        "UNIQUE(name)",
        "This tag already exists.",
    )
