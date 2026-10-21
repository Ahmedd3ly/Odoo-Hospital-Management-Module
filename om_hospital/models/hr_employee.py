from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # ------------------------------------------------------------------
    # Fields (prefixed to avoid clashes with other modules extending hr.employee)
    # ------------------------------------------------------------------

    # Clinical profile
    is_clinician = fields.Boolean(
        string="Is Clinician",
        tracking=True,
        help="Tick for employees who provide clinical care in the hospital.",
    )
    clinician_role = fields.Selection(
        [
            ("doctor", "Doctor"),
            ("nurse", "Nurse"),
            ("technician", "Lab / Radiology Technician"),
            ("other", "Other Clinical Staff"),
        ],
        string="Clinical Role",
        default="doctor",
        tracking=True,
        help="Clinical function of this employee. Only doctors can be assigned to appointments.",
    )
    hospital_specialty_id = fields.Many2one(
        "hospital.specialty",
        string="Specialty",
        ondelete="restrict",
        tracking=True,
        help="Medical specialty practised by this clinician.",
    )
    hospital_license_number = fields.Char(
        string="License Number",
        copy=False,
        tracking=True,
        help="Official medical registration or syndicate number. Must be unique when set.",
    )

    hospital_clinic_ids = fields.Many2many(
        "hospital.clinic",
        "hospital_clinic_clinician_rel",
        "employee_id",
        "clinic_id",
        string="Clinics",
        help="Clinics where this clinician works.",
    )

    # Fees
    hospital_currency_id = fields.Many2one(
        "res.currency",
        string="Hospital Currency",
        related="company_id.currency_id",
        help="Currency used for the consultation fee.",
    )
    hospital_consultation_fee = fields.Monetary(
        string="Consultation Fee",
        currency_field="hospital_currency_id",
        tracking=True,
        help="Default fee charged for one consultation with this clinician.",
    )

    # Appointments
    hospital_appointment_ids = fields.One2many(
        "hospital.appointment",
        "doctor_id",
        string="Appointments",
        help="Appointments assigned to this clinician.",
    )
    hospital_appointment_count = fields.Integer(
        string="Appointment Count",
        compute="_compute_hospital_appointment_count",
        help="Total number of appointments assigned to this clinician.",
    )

    # ------------------------------------------------------------------
    # SQL constraints (Odoo 19+ syntax: models.Constraint)
    # ------------------------------------------------------------------

    _hospital_license_uniq = models.Constraint(
        "UNIQUE(hospital_license_number)",
        "This license number is already registered to another employee.",
    )
    _hospital_fee_not_negative = models.Constraint(
        "CHECK(hospital_consultation_fee >= 0)",
        "The consultation fee cannot be negative.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends("hospital_appointment_ids")
    def _compute_hospital_appointment_count(self):
        counts = {
            doctor.id: count
            for doctor, count in self.env["hospital.appointment"]._read_group(
                [("doctor_id", "in", self.ids)],
                groupby=["doctor_id"],
                aggregates=["__count"],
            )
        }
        for rec in self:
            rec.hospital_appointment_count = counts.get(rec.id, 0)

    # ------------------------------------------------------------------
    # Python constraints
    # ------------------------------------------------------------------

    @api.constrains("is_clinician")
    def _check_clinician_in_use(self):
        """A clinician with appointments cannot be turned back into a plain employee."""
        for rec in self:
            if not rec.is_clinician and rec.hospital_appointment_ids:
                raise ValidationError(
                    self.env._(
                        "%(name)s still has appointments and cannot stop being a clinician.",
                        name=rec.name,
                    )
                )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_hospital_appointments(self):
        self.ensure_one()
        return {
            "name": self.env._("Appointments"),
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "hospital.appointment",
            "domain": [("doctor_id", "=", self.id)],
            "context": {"default_doctor_id": self.id},
        }
