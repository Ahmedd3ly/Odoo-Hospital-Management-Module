from odoo import fields, models
from odoo.exceptions import UserError


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
        appointment = self.appointment_id
        # Compare calendar days in the user's timezone, not in UTC.
        appointment_day = fields.Datetime.context_timestamp(
            self, appointment.appointment_time
        ).date()
        if appointment_day <= fields.Date.context_today(self):
            raise UserError(
                self.env._(
                    "You cannot cancel an appointment scheduled for today "
                    "or a date that has already passed."
                )
            )
        appointment._cancel_with_reason(self.reason)
        return {"type": "ir.actions.client", "tag": "reload"}
