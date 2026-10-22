from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cancel_appointment = fields.Boolean(
        string="Cancel Appointments",
        config_parameter="om_hospital.cancel_appointment",
        help="Allow doctors to cancel appointments.",
    )

    cancel_days = fields.Integer(
        string="Cancel Days",
        config_parameter="om_hospital.cancel_days",
        help="Number of days before an appointment can be cancelled.",
    )
