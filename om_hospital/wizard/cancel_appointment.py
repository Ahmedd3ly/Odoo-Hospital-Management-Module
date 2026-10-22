from odoo import fields, models
from odoo.exceptions import UserError
from datetime import timedelta


class CancelAppointmentWizard(models.TransientModel):
    _name = "cancel.appointment.wizard"
    _description = "Cancel Appointment Wizard"

    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Appointment",
        required=True,
        domain="[('state', 'in', ('draft', 'confirmed'))]",
    )
    reason = fields.Text(
        string="Reason for Cancellation",
        required=True,
        help="Specify why this appointment is being cancelled.",
    )

    def action_cancel_appointment(self):
        self.ensure_one()

        icp = self.env["ir.config_parameter"].sudo()
        cancel_allowed = icp.get_str("om_hospital.cancel_appointment", default="True")

        if str(cancel_allowed).lower() in ("false", "0", "no", "f", "none"):
            raise UserError(
                self.env._(
                    "Appointment cancellations have been disabled in the settings."
                )
            )

        appointment = self.appointment_id
        appointment_day = fields.Datetime.context_timestamp(
            self, appointment.appointment_time
        ).date()

        cancel_days = icp.get_int("om_hospital.cancel_days", default=0)
        allowed_latest_date = fields.Date.context_today(self) + timedelta(
            days=cancel_days
        )

        if appointment_day <= allowed_latest_date:
            raise UserError(
                self.env._(
                    "Appointments must be cancelled at least %(days)d day(s) in advance.",
                    days=cancel_days,
                )
            )

        appointment._cancel_with_reason(self.reason)
        return {"type": "ir.actions.client", "tag": "reload"}
