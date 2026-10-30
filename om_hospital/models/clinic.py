from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HospitalClinic(models.Model):
    _name = "hospital.clinic"
    _description = "Hospital Clinic"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"
    _rec_names_search = ["name", "code"]

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    # Identification
    name = fields.Char(
        string="Clinic",
        required=True,
        tracking=True,
        help="Name of the clinic, for example Eye Care Clinic.",
    )
    code = fields.Char(
        required=True,
        copy=False,
        tracking=True,
        help="Short uppercase code of the clinic, for example EYE. Must be unique.",
    )
    specialty_id = fields.Many2one(
        "hospital.specialty",
        ondelete="restrict",
        tracking=True,
        help="Medical specialty practised in this clinic.",
    )
    location = fields.Char(
        help="Where the clinic is found inside the hospital, for example Building B, 2nd floor.",
    )

    # Staff
    clinician_ids = fields.Many2many(
        "hr.employee",
        "hospital_clinic_clinician_rel",
        "clinic_id",
        "employee_id",
        string="Clinicians",
        domain="[('is_clinician', '=', True)]",
        help="Clinicians who work in this clinic. Appointments here can only be given to them.",
    )
    head_id = fields.Many2one(
        "hr.employee",
        string="Head of Clinic",
        domain="[('id', 'in', clinician_ids)]",
        ondelete="restrict",
        tracking=True,
        help="Clinician responsible for this clinic. Must be one of its clinicians.",
    )

    # Appointments
    appointment_ids = fields.One2many(
        "hospital.appointment",
        "clinic_id",
        string="Appointments",
        help="Appointments booked in this clinic.",
    )
    appointment_count = fields.Integer(
        compute="_compute_appointment_count",
        help="Total number of appointments booked in this clinic.",
    )

    # Status
    active = fields.Boolean(
        default=True,
        help="Uncheck to archive this clinic without deleting past appointments.",
    )

    # ------------------------------------------------------------------
    # SQL constraints (Odoo 19+ syntax: models.Constraint)
    # ------------------------------------------------------------------

    _name_uniq = models.Constraint(
        "UNIQUE(name)",
        "A clinic with this name already exists.",
    )
    _code_uniq = models.Constraint(
        "UNIQUE(code)",
        "A clinic with this code already exists.",
    )
    _name_not_blank = models.Constraint(
        "CHECK(TRIM(name) <> '')",
        "The clinic name cannot be blank.",
    )
    _code_not_blank = models.Constraint(
        "CHECK(TRIM(code) <> '')",
        "The clinic code cannot be blank.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends("appointment_ids")
    def _compute_appointment_count(self):
        counts = {
            clinic.id: count
            for clinic, count in self.env["hospital.appointment"]._read_group(
                [("clinic_id", "in", self.ids)],
                groupby=["clinic_id"],
                aggregates=["__count"],
            )
        }
        for rec in self:
            rec.appointment_count = counts.get(rec.id, 0)

    # ------------------------------------------------------------------
    # Python constraints
    # ------------------------------------------------------------------

    @api.constrains("head_id", "clinician_ids")
    def _check_head_in_clinicians(self):
        for rec in self:
            if rec.head_id and rec.head_id not in rec.clinician_ids:
                raise ValidationError(
                    self.env._(
                        "%(head)s must be one of the clinicians of %(clinic)s to head it.",
                        head=rec.head_id.name,
                        clinic=rec.name,
                    ),
                )

    @api.constrains("active")
    def _check_no_open_appointments(self):
        """A clinic with open appointments cannot be archived."""
        for rec in self:
            if rec.active:
                continue
            open_appointments = rec.appointment_ids.filtered(
                lambda a: a.state in ("draft", "confirmed", "ongoing"),
            )
            if open_appointments:
                raise ValidationError(
                    self.env._(
                        "%(clinic)s still has open appointments and cannot be archived.",
                        clinic=rec.name,
                    ),
                )

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        return super().write(vals)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_appointments(self):
        self.ensure_one()
        return {
            "name": self.env._("Appointments"),
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "hospital.appointment",
            "domain": [("clinic_id", "=", self.id)],
            "context": {"default_clinic_id": self.id},
        }
