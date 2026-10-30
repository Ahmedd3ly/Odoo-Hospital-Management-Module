from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HospitalPatientCondition(models.Model):
    _name = "hospital.patient.condition"
    _description = "Patient Allergy or Chronic Condition"
    _order = "condition_type, id"

    patient_id = fields.Many2one(
        "hospital.patient",
        required=True,
        index=True,
        ondelete="cascade",
    )
    condition_type = fields.Selection(
        [("allergy", "Allergy"), ("chronic", "Chronic Condition")],
        string="Type",
        required=True,
        default="allergy",
        help="Allergies and chronic conditions are shown as quick-filter tags on the patient.",
    )
    name = fields.Char(
        string="Condition / Allergen",
        required=True,
        help="For example Penicillin (allergy) or Hypertension (chronic condition).",
    )
    severity = fields.Selection(
        [("mild", "Mild"), ("moderate", "Moderate"), ("severe", "Severe")],
        default="moderate",
    )
    since = fields.Date(
        help="Date the condition was first diagnosed or noticed, if known.",
    )
    notes = fields.Char(help="Reaction details or management notes.")

    _name_not_blank = models.Constraint(
        "CHECK(TRIM(name) <> '')",
        "The condition name cannot be blank.",
    )
    _patient_condition_uniq = models.Constraint(
        "UNIQUE(patient_id, condition_type, name)",
        "This condition is already recorded for the patient.",
    )

    @api.constrains("since")
    def _check_since(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.since and rec.since > today:
                raise ValidationError(
                    self.env._("The 'Since' date cannot be in the future."),
                )

    # Keep the patient's quick-filter tags in step with the structured lines.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.patient_id._sync_condition_tags()
        return records

    def write(self, vals):
        patients = self.patient_id
        result = super().write(vals)
        if {"condition_type", "patient_id"} & vals.keys():
            (patients | self.patient_id)._sync_condition_tags()
        return result

    def unlink(self):
        patients = self.patient_id
        result = super().unlink()
        patients._sync_condition_tags()
        return result
