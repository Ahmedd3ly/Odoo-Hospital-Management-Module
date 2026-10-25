from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .search_utils import boolean_search_domain


class HospitalBed(models.Model):
    _name = "hospital.bed"
    _description = "Hospital Bed"
    _order = "ward_id, name"
    _rec_names_search = ["name", "ward_id.name"]

    name = fields.Char(
        string="Bed",
        required=True,
        help="Bed label inside its ward, for example G-101.",
    )
    ward_id = fields.Many2one(
        "hospital.ward",
        string="Ward",
        required=True,
        index=True,
        ondelete="restrict",
    )
    admission_ids = fields.One2many(
        "hospital.admission",
        "bed_id",
        string="Admissions",
    )
    is_occupied = fields.Boolean(
        string="Occupied",
        compute="_compute_occupancy",
        search="_search_is_occupied",
        help="True while a patient is admitted to this bed. Never typed in: it follows the admissions.",
    )
    current_admission_id = fields.Many2one(
        "hospital.admission",
        string="Current Admission",
        compute="_compute_occupancy",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to take the bed out of service. An occupied bed cannot be archived.",
    )

    _ward_name_uniq = models.Constraint(
        "UNIQUE(ward_id, name)",
        "This bed already exists in the ward.",
    )
    _name_not_blank = models.Constraint(
        "CHECK(TRIM(name) <> '')", "The bed name cannot be blank."
    )

    @api.depends("name", "ward_id.name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.ward_id.name} / {rec.name}" if rec.ward_id else rec.name or ""

    @api.depends("admission_ids.state")
    def _compute_occupancy(self):
        admissions = self.env["hospital.admission"].search(
            [("bed_id", "in", self.ids), ("state", "=", "admitted")]
        )
        by_bed = {admission.bed_id.id: admission for admission in admissions}
        for rec in self:
            admission = by_bed.get(rec.id)
            rec.current_admission_id = admission
            rec.is_occupied = bool(admission)

    def _search_is_occupied(self, operator, value):
        occupied_ids = self.env["hospital.admission"].search([("state", "=", "admitted")]).bed_id.ids
        return boolean_search_domain(
            operator,
            value,
            positive_domain=[("id", "in", occupied_ids)],
            negative_domain=[("id", "not in", occupied_ids)],
        )

    @api.constrains("active")
    def _check_not_occupied_when_archiving(self):
        for rec in self.filtered(lambda b: not b.active):
            if rec.is_occupied:
                raise ValidationError(
                    self.env._(
                        "Bed %(bed)s is occupied and cannot be archived.", bed=rec.display_name
                    )
                )
