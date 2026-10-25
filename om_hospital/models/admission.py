from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Fields that billing depends on: frozen once the patient is discharged.
LOCKED_WHEN_DISCHARGED = {"patient_id", "bed_id", "admission_date", "discharge_date"}


class HospitalAdmission(models.Model):
    _name = "hospital.admission"
    _description = "Inpatient Admission"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "admission_date desc, id desc"
    _rec_names_search = ["name", "patient_id.name", "patient_id.reference"]

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        index="trigram",
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
    )
    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Appointment",
        index=True,
        ondelete="restrict",
        domain="[('patient_id', '=', patient_id)]",
        help="Consultation that led to this admission, if any.",
    )
    admitting_doctor_id = fields.Many2one(
        "hr.employee",
        string="Admitting Doctor",
        ondelete="restrict",
        tracking=True,
        domain="[('is_clinician', '=', True), ('clinician_role', '=', 'doctor')]",
    )
    bed_id = fields.Many2one(
        "hospital.bed",
        string="Bed",
        ondelete="restrict",
        index=True,
        tracking=True,
        domain="[('is_occupied', '=', False)]",
        help="Current bed. Change it during the stay with Transfer Bed.",
    )
    ward_id = fields.Many2one(related="bed_id.ward_id", string="Ward")
    admission_date = fields.Datetime(
        string="Admitted On",
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    discharge_date = fields.Datetime(
        string="Discharged On",
        readonly=True,
        copy=False,
        tracking=True,
    )
    nights = fields.Integer(
        string="Billable Nights",
        compute="_compute_nights",
        help="Midnights spent in hospital (a same-day stay counts as 1). "
        "While admitted it counts up to today.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("admitted", "Admitted"),
            ("discharged", "Discharged"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
        index=True,
        tracking=True,
    )
    reason = fields.Text(string="Reason for Admission")
    discharge_notes = fields.Text(string="Discharge Notes")
    transfer_ids = fields.One2many(
        "hospital.admission.transfer",
        "admission_id",
        string="Bed Transfers",
    )
    sale_order_ids = fields.One2many(
        "sale.order",
        "admission_id",
        string="Sales Orders",
    )
    sale_order_count = fields.Integer(
        string="Sales Order Count",
        compute="_compute_sale_order_count",
    )

    _name_uniq = models.Constraint("UNIQUE(name)", "The admission reference must be unique.")
    _admitted_bed_idx = models.Index("(bed_id) WHERE state = 'admitted'")
    _admitted_patient_idx = models.Index("(patient_id) WHERE state = 'admitted'")
    _dates_check = models.Constraint(
        "CHECK(discharge_date IS NULL OR discharge_date >= admission_date)",
        "The discharge cannot be before the admission.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends("admission_date", "discharge_date", "state")
    def _compute_nights(self):
        for rec in self:
            if rec.state in ("draft", "cancel") or not rec.admission_date:
                rec.nights = 0
                continue
            end = rec.discharge_date or fields.Datetime.now()
            first_day = fields.Datetime.context_timestamp(rec, rec.admission_date).date()
            last_day = fields.Datetime.context_timestamp(rec, end).date()
            rec.nights = max((last_day - first_day).days, 1)

    @api.depends("sale_order_ids")
    def _compute_sale_order_count(self):
        counts = {
            admission.id: count
            for admission, count in self.env["sale.order"]._read_group(
                [("admission_id", "in", self.ids)],
                groupby=["admission_id"],
                aggregates=["__count"],
            )
        }
        for rec in self:
            rec.sale_order_count = counts.get(rec.id, 0)

    # ------------------------------------------------------------------
    # Constraints and onchange
    # ------------------------------------------------------------------

    @api.constrains("bed_id", "state")
    def _check_bed_free(self):
        for rec in self.filtered(lambda a: a.state == "admitted" and a.bed_id):
            if self.search_count(
                [
                    ("id", "!=", rec.id),
                    ("bed_id", "=", rec.bed_id.id),
                    ("state", "=", "admitted"),
                ]
            ):
                raise ValidationError(
                    self.env._(
                        "Bed %(bed)s is already occupied.", bed=rec.bed_id.display_name
                    )
                )

    @api.constrains("patient_id", "state")
    def _check_single_active_admission(self):
        for rec in self.filtered(lambda a: a.state == "admitted"):
            if self.search_count(
                [
                    ("id", "!=", rec.id),
                    ("patient_id", "=", rec.patient_id.id),
                    ("state", "=", "admitted"),
                ]
            ):
                raise ValidationError(
                    self.env._(
                        "%(patient)s is already admitted.", patient=rec.patient_id.display_name
                    )
                )

    @api.constrains("patient_id")
    def _check_patient_alive(self):
        for rec in self:
            if rec.patient_id.deceased:
                raise ValidationError(
                    self.env._(
                        "%(patient)s is marked as deceased and cannot be admitted.",
                        patient=rec.patient_id.display_name,
                    )
                )

    @api.constrains("patient_id", "appointment_id")
    def _check_appointment_patient(self):
        for rec in self:
            if rec.appointment_id and rec.appointment_id.patient_id != rec.patient_id:
                raise ValidationError(
                    self.env._("The appointment belongs to a different patient.")
                )

    @api.onchange("appointment_id")
    def _onchange_appointment_id(self):
        if self.appointment_id:
            self.patient_id = self.appointment_id.patient_id
            self.admitting_doctor_id = self.appointment_id.doctor_id

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("hospital.admission") or "New"
        return super().create(vals_list)

    def write(self, vals):
        if LOCKED_WHEN_DISCHARGED & vals.keys() and any(
            rec.state in ("discharged", "cancel") for rec in self
        ):
            raise UserError(
                self.env._("A discharged or cancelled admission can no longer be changed.")
            )
        if (
            "bed_id" in vals
            and not self.env.context.get("allow_bed_change")
            and any(rec.state == "admitted" for rec in self)
        ):
            raise UserError(self.env._("Use Transfer Bed to move an admitted patient."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_processed(self):
        if any(rec.state not in ("draft", "cancel") for rec in self):
            raise UserError(self.env._("Only draft or cancelled admissions can be deleted."))

    # ------------------------------------------------------------------
    # Workflow: draft -> admitted -> discharged (cancel from draft)
    # ------------------------------------------------------------------

    def _ensure_state(self, allowed_states, error_message):
        if any(rec.state not in allowed_states for rec in self):
            raise UserError(error_message)

    def action_admit(self):
        self._ensure_state(("draft",), self.env._("Only draft admissions can be admitted."))
        for rec in self:
            if not rec.bed_id:
                raise UserError(
                    self.env._("Choose a bed for %(admission)s first.", admission=rec.name)
                )
            rec.state = "admitted"
            rec.message_post(
                body=self.env._(
                    "%(patient)s admitted to %(bed)s.",
                    patient=rec.patient_id.name,
                    bed=rec.bed_id.display_name,
                )
            )

    def action_discharge(self):
        self._ensure_state(
            ("admitted",), self.env._("Only admitted patients can be discharged.")
        )
        for rec in self:
            rec.write({"state": "discharged", "discharge_date": fields.Datetime.now()})
            rec.message_post(
                body=self.env._(
                    "%(patient)s discharged after %(nights)s night(s).",
                    patient=rec.patient_id.name,
                    nights=rec.nights,
                )
            )

    def action_cancel(self):
        self._ensure_state(
            ("draft",), self.env._("Only draft admissions can be cancelled. Discharge the patient instead.")
        )
        self.write({"state": "cancel"})

    def action_transfer_bed(self):
        self.ensure_one()
        self._ensure_state(("admitted",), self.env._("Only admitted patients can be transferred."))
        return {
            "name": self.env._("Transfer Bed"),
            "type": "ir.actions.act_window",
            "res_model": "transfer.bed.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_admission_id": self.id},
        }

    # ------------------------------------------------------------------
    # Billing and links
    # ------------------------------------------------------------------

    def action_create_quotation(self):
        """Bill the whole stay: bed days at the standard bed-day price."""
        self.ensure_one()
        if self.state != "discharged":
            raise UserError(self.env._("Discharge the patient before creating the quotation."))
        if self.sale_order_ids.filtered(lambda order: order.state != "cancel"):
            raise UserError(self.env._("This admission already has a quotation or sales order."))
        orders = self.env["sale.order"]._create_admission_quotations(self)
        self.message_post(
            body=self.env._(
                "Quotation(s) created: %(orders)s.", orders=", ".join(orders.mapped("name"))
            )
        )
        return self.action_view_sales_orders()

    def action_view_sales_orders(self):
        self.ensure_one()
        return {
            "name": self.env._("Sales Orders"),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("admission_id", "=", self.id)],
        }
