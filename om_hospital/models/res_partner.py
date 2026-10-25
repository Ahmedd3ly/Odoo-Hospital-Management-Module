from odoo import api, fields, models

from .search_utils import boolean_search_domain


class ResPartner(models.Model):
    _inherit = "res.partner"

    hospital_patient_ids = fields.One2many(
        "hospital.patient",
        "partner_id",
        string="Patient Records",
        help="Hospital patient records linked to this contact.",
    )
    is_patient = fields.Boolean(
        string="Is Patient",
        compute="_compute_is_patient",
        search="_search_is_patient",
        help="True when this contact has a hospital patient record.",
    )

    @api.depends("hospital_patient_ids")
    def _compute_is_patient(self):
        for rec in self:
            rec.is_patient = bool(rec.hospital_patient_ids)

    def _search_is_patient(self, operator, value):
        return boolean_search_domain(
            operator,
            value,
            positive_domain=[("hospital_patient_ids", "!=", False)],
            negative_domain=[("hospital_patient_ids", "=", False)],
        )

    def action_open_patient_record(self):
        self.ensure_one()
        patients = self.hospital_patient_ids
        action = {
            "name": self.env._("Patient Record"),
            "type": "ir.actions.act_window",
            "res_model": "hospital.patient",
            "domain": [("partner_id", "=", self.id)],
        }
        if len(patients) == 1:
            action.update({"view_mode": "form", "res_id": patients.id})
        else:
            action.update({"view_mode": "list,form"})
        return action

    def action_create_patient_record(self):
        """Open a new patient form pre-linked to this contact."""
        self.ensure_one()
        return {
            "name": self.env._("New Patient"),
            "type": "ir.actions.act_window",
            "res_model": "hospital.patient",
            "view_mode": "form",
            "context": {"default_partner_id": self.id},
        }
