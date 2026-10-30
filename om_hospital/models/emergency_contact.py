from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HospitalEmergencyContact(models.Model):
    _name = "hospital.emergency.contact"
    _description = "Patient Emergency Contact"
    _order = "is_primary desc, id"

    patient_id = fields.Many2one(
        "hospital.patient",
        required=True,
        index=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
        domain="[('is_company', '=', False)]",
        help="Person to call in an emergency. Created as a regular Odoo contact.",
    )
    relationship = fields.Selection(
        [
            ("spouse", "Spouse"),
            ("parent", "Parent"),
            ("child", "Child"),
            ("sibling", "Sibling"),
            ("friend", "Friend"),
            ("other", "Other"),
        ],
        required=True,
    )
    is_primary = fields.Boolean(
        string="Primary",
        help="The first person to call. Only one primary contact per patient.",
    )
    phone = fields.Char(related="partner_id.phone", string="Phone")

    _patient_partner_uniq = models.Constraint(
        "UNIQUE(patient_id, partner_id)",
        "This contact is already listed for the patient.",
    )

    @api.constrains("is_primary", "patient_id")
    def _check_single_primary(self):
        for rec in self.filtered("is_primary"):
            others = self.search_count(
                [
                    ("patient_id", "=", rec.patient_id.id),
                    ("is_primary", "=", True),
                    ("id", "!=", rec.id),
                ],
            )
            if others:
                raise ValidationError(
                    self.env._(
                        "A patient can only have one primary emergency contact.",
                    ),
                )

    @api.constrains("partner_id", "patient_id")
    def _check_not_the_patient(self):
        for rec in self:
            if rec.partner_id == rec.patient_id.partner_id:
                raise ValidationError(
                    self.env._("A patient cannot be their own emergency contact."),
                )
