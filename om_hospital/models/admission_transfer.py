from odoo import fields, models


class HospitalAdmissionTransfer(models.Model):
    """Log of bed changes during a stay. Created by the transfer wizard only."""

    _name = "hospital.admission.transfer"
    _description = "Admission Bed Transfer"
    _order = "transfer_date desc, id desc"

    admission_id = fields.Many2one(
        "hospital.admission",
        string="Admission",
        required=True,
        index=True,
        ondelete="cascade",
    )
    transfer_date = fields.Datetime(
        string="Date",
        required=True,
        default=fields.Datetime.now,
    )
    from_bed_id = fields.Many2one("hospital.bed", string="From Bed", ondelete="restrict")
    to_bed_id = fields.Many2one("hospital.bed", string="To Bed", required=True, ondelete="restrict")
    reason = fields.Char(string="Reason")
    user_id = fields.Many2one(
        "res.users",
        string="Done By",
        default=lambda self: self.env.user,
        readonly=True,
    )
