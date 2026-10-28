from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hospital_allow_cancellation = fields.Boolean(
        string="Allow Appointment Cancellation",
        default=True,
        config_parameter="om_hospital.cancel_appointment",
        help="When off, appointments cannot be cancelled with the Cancel wizard.",
    )
    hospital_cancel_days = fields.Integer(
        string="Minimum Cancellation Notice (days)",
        default=1,
        config_parameter="om_hospital.cancel_days",
        help="An appointment can only be cancelled at least this many days before its date. "
        "0 allows same-day cancellation; past appointments can never be cancelled.",
    )

    @api.constrains("hospital_cancel_days")
    def _check_hospital_cancel_days(self):
        for rec in self:
            if rec.hospital_cancel_days < 0:
                raise ValidationError(
                    self.env._("The cancellation notice cannot be negative.")
                )
