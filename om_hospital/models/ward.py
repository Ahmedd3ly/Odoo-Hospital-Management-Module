from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HospitalWard(models.Model):
    _name = "hospital.ward"
    _description = "Hospital Ward"
    _inherit = ["mail.thread"]
    _order = "name"
    _rec_names_search = ["name", "code"]

    name = fields.Char(
        string="Ward",
        required=True,
        tracking=True,
        help="Name of the ward, for example General Ward or ICU.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        copy=False,
        help="Short uppercase code, for example GEN. Must be unique.",
    )
    ward_type = fields.Selection(
        [
            ("general", "General"),
            ("private", "Private"),
            ("icu", "Intensive Care"),
            ("pediatric", "Pediatric"),
            ("maternity", "Maternity"),
        ],
        string="Type",
        required=True,
        default="general",
    )
    location = fields.Char(string="Location", help="For example Building A, 4th floor.")
    bed_ids = fields.One2many("hospital.bed", "ward_id", string="Beds")
    bed_count = fields.Integer(string="Beds", compute="_compute_bed_counts")
    occupied_count = fields.Integer(string="Occupied", compute="_compute_bed_counts")
    available_count = fields.Integer(string="Available", compute="_compute_bed_counts")
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to archive the ward. A ward with patients in it cannot be archived.",
    )

    _name_uniq = models.Constraint("UNIQUE(name)", "A ward with this name already exists.")
    _code_uniq = models.Constraint("UNIQUE(code)", "A ward with this code already exists.")
    _name_not_blank = models.Constraint(
        "CHECK(TRIM(name) <> '')", "The ward name cannot be blank."
    )
    _code_not_blank = models.Constraint(
        "CHECK(TRIM(code) <> '')", "The ward code cannot be blank."
    )

    @api.depends("bed_ids", "bed_ids.is_occupied")
    def _compute_bed_counts(self):
        for rec in self:
            beds = rec.bed_ids
            occupied = len(beds.filtered("is_occupied"))
            rec.bed_count = len(beds)
            rec.occupied_count = occupied
            rec.available_count = len(beds) - occupied

    @api.constrains("active")
    def _check_no_patients_when_archiving(self):
        for rec in self.filtered(lambda w: not w.active):
            if rec.with_context(active_test=False).bed_ids.filtered("is_occupied"):
                raise ValidationError(
                    self.env._(
                        "%(ward)s still has admitted patients and cannot be archived.",
                        ward=rec.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        return super().write(vals)

    def action_view_beds(self):
        self.ensure_one()
        return {
            "name": self.env._("Beds"),
            "type": "ir.actions.act_window",
            "res_model": "hospital.bed",
            "view_mode": "list,form",
            "domain": [("ward_id", "=", self.id)],
            "context": {"default_ward_id": self.id},
        }
