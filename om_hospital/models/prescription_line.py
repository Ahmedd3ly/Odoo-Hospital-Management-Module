from odoo import api, fields, models
from odoo.exceptions import UserError


class HospitalPrescriptionLine(models.Model):
    _name = "hospital.prescription.line"
    _description = "Hospital Prescription Line"
    _order = "appointment_id desc, id"

    appointment_id = fields.Many2one(
        "hospital.appointment",
        required=True,
        index=True,
        ondelete="cascade",
        help="Appointment during which this medication was prescribed.",
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        related="appointment_id.patient_id",
        store=True,
        index=True,
        help="Patient receiving this medication, taken from the appointment.",
    )
    medicine_id = fields.Many2one(
        "product.product",
        required=True,
        index=True,
        ondelete="restrict",
        domain="[('is_medicine', '=', True)]",
        help="Medicine from the product catalog (products flagged as medicines).",
    )
    dose = fields.Char(
        string="Dosage",
        help="Specific dosage instructions (e.g., 500mg, 1 tablet).",
    )
    frequency = fields.Char(
        help="How often the medication should be taken (e.g., Twice a day).",
    )
    quantity = fields.Float(
        default=1.0,
        help="Units or packs to dispense. This is the quantity billed on the quotation.",
    )
    to_bill = fields.Boolean(
        string="Bill",
        default=True,
        help="Untick when the patient will buy this medicine elsewhere: "
        "it stays on the prescription but is left off the quotation.",
    )
    duration_days = fields.Integer(
        string="Duration (Days)",
        help="Number of days the medication should be taken. Leave 0 if not specified.",
    )
    instructions = fields.Text(
        help="Extra directions for the patient, for example take with food.",
    )

    _quantity_positive = models.Constraint(
        "CHECK(quantity > 0)",
        "The quantity must be greater than zero.",
    )
    _duration_not_negative = models.Constraint(
        "CHECK(duration_days >= 0)",
        "The duration cannot be negative.",
    )

    # ------------------------------------------------------------------
    # A completed appointment is a closed medical and billing record
    # ------------------------------------------------------------------

    def _check_appointments_open(self, appointments):
        if any(appointment.state == "done" for appointment in appointments):
            raise UserError(
                self.env._("The prescription of a completed appointment is locked."),
            )

    @api.model_create_multi
    def create(self, vals_list):
        appointments = self.env["hospital.appointment"].browse(
            [
                vals["appointment_id"]
                for vals in vals_list
                if vals.get("appointment_id")
            ],
        )
        self._check_appointments_open(appointments)
        return super().create(vals_list)

    def write(self, vals):
        appointments = self.appointment_id
        if vals.get("appointment_id"):
            appointments |= self.env["hospital.appointment"].browse(
                vals["appointment_id"],
            )
        self._check_appointments_open(appointments)
        return super().write(vals)

    def unlink(self):
        self._check_appointments_open(self.appointment_id)
        return super().unlink()
