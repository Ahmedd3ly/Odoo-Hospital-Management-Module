from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class CancelAppointmentWizard(models.TransientModel):
    _name = "cancel.appointment.wizard"
    _description = "Cancel Appointment Wizard"

    appointment_id = fields.Many2one(
        "hospital.appointment",
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
        params = self.env["ir.config_parameter"].sudo()
        if not params.get_bool("om_hospital.cancel_appointment", True):
            raise UserError(
                self.env._("Appointment cancellation is turned off in the settings."),
            )
        notice_days = params.get_int("om_hospital.cancel_days", 1)
        appointment = self.appointment_id
        # Compare calendar days in the user's timezone, not in UTC.
        appointment_day = fields.Datetime.context_timestamp(
            self,
            appointment.appointment_time,
        ).date()
        if appointment_day < fields.Date.context_today(self) + timedelta(
            days=notice_days,
        ):
            raise UserError(
                self.env._(
                    "An appointment can only be cancelled at least %(days)s day(s) in advance.",
                    days=notice_days,
                ),
            )
        appointment._cancel_with_reason(self.reason)
        return {"type": "ir.actions.client", "tag": "reload"}
