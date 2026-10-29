import re

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

PHONE_PATTERN = re.compile(r"^\+?[0-9 ()-]{6,20}$")
ADULT_AGE = 18


class HospitalPatient(models.Model):
    _name = "hospital.patient"
    _description = "Hospital Patient"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    # Name, email, phone, photo and address live on the linked contact (res.partner).
    _inherits = {"res.partner": "partner_id"}
    _order = "id desc"
    _rec_names_search = ["name", "reference", "id_number"]

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    # Identification
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        index=True,
        copy=False,
        ondelete="restrict",
        help="Odoo contact holding this patient's name, phone, email, photo and billing details.",
    )
    reference = fields.Char(
        string="Patient Reference",
        required=True,
        index="trigram",
        copy=False,
        readonly=True,
        default="New",
        help="Unique sequential reference code assigned to each registered patient.",
    )

    # Personal details
    date_of_birth = fields.Date(
        string="Date of Birth",
        required=True,
        tracking=True,
        help="Patient's date of birth used to compute their age automatically.",
    )
    age = fields.Integer(
        string="Age",
        compute="_compute_age",
        help="Computed age of the patient calculated from their date of birth.",
    )
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female")],
        string="Gender",
        required=True,
        tracking=True,
        help="Biological gender of the patient.",
    )
    blood_group = fields.Selection(
        [
            ("A+", "A+"),
            ("A-", "A-"),
            ("B+", "B+"),
            ("B-", "B-"),
            ("AB+", "AB+"),
            ("AB-", "AB-"),
            ("O+", "O+"),
            ("O-", "O-"),
        ],
        string="Blood Group",
        required=True,
        tracking=True,
        help="Patient's blood group and Rhesus factor classification.",
    )
    deceased = fields.Boolean(
        string="Deceased",
        tracking=True,
        help="Indicates if the patient is deceased.",
    )

    id_type = fields.Selection(
        [
            ("national_id", "National ID"),
            ("passport", "Passport"),
            ("residence", "Residence Permit"),
        ],
        string="ID Type",
        help="Kind of identity document recorded for the patient.",
    )
    id_number = fields.Char(
        string="ID Number",
        copy=False,
        index="trigram",
        help="Number of the identity document. Sensitive personal data.",
    )
    guardian_id = fields.Many2one(
        "res.partner",
        string="Guardian",
        ondelete="restrict",
        domain="[('is_company', '=', False)]",
        help="Parent or legal guardian. Required while the patient is under 18.",
    )
    contract_id = fields.Many2one(
        "hospital.contract",
        string="Company Contract",
        compute="_compute_contract_id",
        help="Active contract of the company this patient belongs to, if any.",
    )
    is_birthday = fields.Boolean(
        string="Is Birthday",
        compute="_compute_is_birthday",
        help="True on the patient's birthday, used to show a greeting banner on the form.",
    )
    is_minor = fields.Boolean(
        string="Is Minor",
        compute="_compute_is_minor",
        help="True while the patient is under 18.",
    )

    # Classification and relations
    tag_ids = fields.Many2many(
        "hospital.tag",
        "patient_tag_rel",
        "patient_id",
        "tag_id",
        string="Medical Tags",
        help="Medical conditions, allergies, or status tags associated with this patient.",
    )
    emergency_contact_ids = fields.One2many(
        "hospital.emergency.contact",
        "patient_id",
        string="Emergency Contacts",
        help="People to call in an emergency, with their relationship to the patient.",
    )
    condition_ids = fields.One2many(
        "hospital.patient.condition",
        "patient_id",
        string="Allergies & Chronic Conditions",
        help="Structured medical conditions. Quick-filter tags are kept in sync automatically.",
    )

    # Appointments
    appointment_ids = fields.One2many(
        "hospital.appointment",
        "patient_id",
        string="Appointments",
        help="List of all scheduled or completed appointments linked to this patient.",
    )
    appointment_count = fields.Integer(
        string="Appointment Count",
        compute="_compute_appointment_count",
        help="Total number of appointments recorded for this patient.",
    )

    # Status
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to archive this patient record without deleting historical data.",
    )

    # ------------------------------------------------------------------
    # SQL constraints (Odoo 19+ syntax: models.Constraint)
    # Constraints on name, email and phone are Python checks below, because
    # those columns now belong to the contact table.
    # ------------------------------------------------------------------

    _reference_uniq = models.Constraint(
        "UNIQUE(reference)",
        "The patient reference must be unique.",
    )
    _partner_uniq = models.Constraint(
        "UNIQUE(partner_id)",
        "This contact is already linked to another patient.",
    )
    _id_pair_check = models.Constraint(
        "CHECK((id_type IS NULL) = (id_number IS NULL))",
        "Set both the ID type and the ID number, or neither.",
    )
    _id_number_not_blank = models.Constraint(
        "CHECK(id_number IS NULL OR TRIM(id_number) <> '')",
        "The ID number cannot be blank.",
    )
    _id_uniq = models.Constraint(
        "UNIQUE(id_type, id_number)",
        "A patient with this ID already exists.",
    )
    _date_of_birth_min = models.Constraint(
        "CHECK(date_of_birth >= DATE '1900-01-01')",
        "The date of birth cannot be earlier than 1900-01-01.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends("date_of_birth")
    def _compute_age(self):
        today = fields.Date.today()
        for rec in self:
            dob = rec.date_of_birth
            if dob:
                had_birthday = (today.month, today.day) >= (dob.month, dob.day)
                rec.age = today.year - dob.year - (0 if had_birthday else 1)
            else:
                rec.age = 0

    @api.depends("date_of_birth")
    def _compute_is_birthday(self):
        today = fields.Date.context_today(self)
        for rec in self:
            dob = rec.date_of_birth
            rec.is_birthday = bool(dob) and (dob.month, dob.day) == (
                today.month,
                today.day,
            )

    @api.depends("partner_id.parent_id")
    def _compute_contract_id(self):
        contracts = self.env["hospital.contract"]
        for rec in self:
            rec.contract_id = contracts._get_contract_for_partner(rec.partner_id)

    @api.depends("date_of_birth", "age")
    def _compute_is_minor(self):
        for rec in self:
            rec.is_minor = bool(rec.date_of_birth) and rec.age < ADULT_AGE

    @api.depends("appointment_ids")
    def _compute_appointment_count(self):
        counts = {
            patient.id: count
            for patient, count in self.env["hospital.appointment"]._read_group(
                [("patient_id", "in", self.ids)],
                groupby=["patient_id"],
                aggregates=["__count"],
            )
        }
        for rec in self:
            rec.appointment_count = counts.get(rec.id, 0)

    @api.depends("name", "reference")
    def _compute_display_name(self):
        for rec in self:
            if rec.reference and rec.reference != "New":
                rec.display_name = f"[{rec.reference}] {rec.name}"
            else:
                rec.display_name = rec.name or ""

    # ------------------------------------------------------------------
    # Constraints and onchange
    # ------------------------------------------------------------------

    @api.constrains("date_of_birth")
    def _check_date_of_birth(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_of_birth and rec.date_of_birth >= today:
                raise ValidationError(
                    self.env._("Date of Birth cannot be today or in the future.")
                )

    @api.constrains("date_of_birth", "guardian_id")
    def _check_minor_guardian(self):
        for rec in self:
            if rec.is_minor and not rec.guardian_id:
                raise ValidationError(
                    self.env._(
                        "%(patient)s is under 18 and needs a guardian.",
                        patient=rec.name,
                    )
                )
            if rec.guardian_id and rec.guardian_id == rec.partner_id:
                raise ValidationError(
                    self.env._("A patient cannot be their own guardian.")
                )

    @api.constrains("partner_id", "name", "email", "phone")
    def _check_contact_details(self):
        """Every patient needs a name, an email and a well-formed phone number."""
        for rec in self:
            if not (rec.name or "").strip():
                raise ValidationError(self.env._("The patient name cannot be blank."))
            if not (rec.email or "").strip():
                raise ValidationError(
                    self.env._("An email address is required for every patient.")
                )
            if not PHONE_PATTERN.match(rec.phone or ""):
                raise ValidationError(
                    self.env._(
                        "The phone number may only contain digits, spaces, brackets, "
                        "dashes and an optional leading + (6 to 20 characters)."
                    )
                )

    @api.onchange("name", "date_of_birth")
    def _onchange_possible_duplicate(self):
        """Soft warning only: names are not unique, so this never blocks saving."""
        if not (self.name and self.date_of_birth):
            return None
        domain = [
            ("name", "=ilike", self.name.strip()),
            ("date_of_birth", "=", self.date_of_birth),
        ]
        if self._origin:
            domain.append(("id", "!=", self._origin.id))
        duplicate = self.with_context(active_test=False).search(domain, limit=1)
        if not duplicate:
            return None
        return {
            "warning": {
                "title": self.env._("Possible duplicate patient"),
                "message": self.env._(
                    "%(patient)s already has the same name and date of birth. "
                    "Make sure this is a different person before saving.",
                    patient=duplicate.display_name,
                ),
            }
        }

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = sequence.next_by_code("hospital.patient") or "New"
        # When partner_id is missing, Odoo creates the contact from name/email/phone.
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _sync_condition_tags(self):
        """Tick the Allergic / Chronic quick-filter tags from the structured lines."""
        tag_by_type = {
            "allergy": self.env.ref(
                "om_hospital.tag_allergic", raise_if_not_found=False
            ),
            "chronic": self.env.ref(
                "om_hospital.tag_chronic", raise_if_not_found=False
            ),
        }
        for patient in self:
            for condition_type, tag in tag_by_type.items():
                if not tag:
                    continue
                has_lines = any(
                    line.condition_type == condition_type
                    for line in patient.condition_ids
                )
                patient.tag_ids = [
                    Command.link(tag.id) if has_lines else Command.unlink(tag.id)
                ]

    def action_open_appointments(self):
        self.ensure_one()
        return {
            "name": self.env._("Appointments"),
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "hospital.appointment",
            "domain": [("patient_id", "=", self.id)],
            "context": {"default_patient_id": self.id},
        }

    def action_send_via_whatsapp(self):
        self.ensure_one()
        phone = self.partner_id.phone or self.partner_id.mobile
        if not phone:
            raise UserError(
                self.env._(
                    "This patient does not have a phone/mobile number configured."
                )
            )

        # Clean non-digit characters for WhatsApp URL
        clean_phone = re.sub(r"\D", "", phone)

        whatsapp_url = f"https://api.whatsapp.com/send?phone={clean_phone}"
        return {
            "type": "ir.actions.act_url",
            "url": whatsapp_url,
            "target": "new",
        }
