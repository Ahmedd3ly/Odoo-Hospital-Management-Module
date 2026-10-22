from odoo import fields, models
from odoo.exceptions import UserError


class TransferBedWizard(models.TransientModel):
    _name = "transfer.bed.wizard"
    _description = "Transfer Bed Wizard"

    admission_id = fields.Many2one(
        "hospital.admission",
        string="Admission",
        required=True,
        readonly=True,
    )
    current_bed_id = fields.Many2one(related="admission_id.bed_id", string="Current Bed")
    new_bed_id = fields.Many2one(
        "hospital.bed",
        string="New Bed",
        required=True,
        domain="[('is_occupied', '=', False)]",
    )
    reason = fields.Char(string="Reason")

    def action_transfer(self):
        self.ensure_one()
        admission = self.admission_id
        if admission.state != "admitted":
            raise UserError(self.env._("Only admitted patients can be transferred."))
        if self.new_bed_id == admission.bed_id:
            raise UserError(self.env._("The patient is already in this bed."))
        old_bed = admission.bed_id
        self.env["hospital.admission.transfer"].create(
            {
                "admission_id": admission.id,
                "from_bed_id": old_bed.id,
                "to_bed_id": self.new_bed_id.id,
                "reason": self.reason,
            }
        )
        admission.with_context(allow_bed_change=True).write({"bed_id": self.new_bed_id.id})
        admission.message_post(
            body=self.env._(
                "Transferred from %(old)s to %(new)s.",
                old=old_bed.display_name,
                new=self.new_bed_id.display_name,
            )
        )
        return {"type": "ir.actions.act_window_close"}
