from odoo import fields, models


class HospitalAdmissionTransfer(models.Model):
    """Log of bed changes during a stay. Created by the transfer wizard only."""

    _name = "hospital.admission.transfer"
    _description = "Admission Bed Transfer"
    _order = "transfer_date desc, id desc"

    admission_id = fields.Many2one(
        "hospital.admission",
        required=True,
        index=True,
        ondelete="cascade",
    )
    transfer_date = fields.Datetime(
        string="Date",
        required=True,
        default=fields.Datetime.now,
    )
    from_bed_id = fields.Many2one("hospital.bed", ondelete="restrict")
    to_bed_id = fields.Many2one("hospital.bed", required=True, ondelete="restrict")
    reason = fields.Char()
    user_id = fields.Many2one(
        "res.users",
        string="Done By",
        default=lambda self: self.env.user,
        readonly=True,
    )
