from odoo import fields, models


class HospitalSpecialty(models.Model):
    _name = "hospital.specialty"
    _description = "Medical Specialty"
    _order = "name"

    name = fields.Char(
        string="Specialty",
        required=True,
        help="Name of the medical specialty, for example Cardiology.",
    )
    clinician_ids = fields.One2many(
        "hr.employee",
        "hospital_specialty_id",
        string="Clinicians",
        help="Clinicians practising this specialty.",
    )

    _name_uniq = models.Constraint(
        "UNIQUE(name)",
        "This specialty already exists.",
    )
    _name_not_blank = models.Constraint(
        "CHECK(TRIM(name) <> '')",
        "The specialty name cannot be blank.",
    )
