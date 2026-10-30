import re
from datetime import datetime, time, timedelta
from urllib.parse import quote

import pytz
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

PAST_VISITS_LIMIT = 20
DASHBOARD_PERIODS = ("today", "week", "month")
DASHBOARD_TOP_LIMIT = 5
OPEN_STATES = ["draft", "confirmed", "ongoing"]
URGENT_PRIORITIES = ["2", "3"]
# Medical record fields that are frozen once the appointment is done.
LOCKED_WHEN_DONE = {
    "chief_complaint",
    "diagnosis",
    "weight",
    "height",
    "systolic_bp",
    "diastolic_bp",
    "follow_up_date",
    "note",
}


class HospitalAppointment(models.Model):
    _name = "hospital.appointment"
    _description = "Hospital Appointment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "appointment_time desc, id desc"
    _rec_names_search = ["name", "patient_id.name", "patient_id.reference"]

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    # Identification
    name = fields.Char(
        string="Appointment Reference",
        required=True,
        index="trigram",
        copy=False,
        readonly=True,
        default="New",
        help="Unique reference code generated automatically for this consultation.",
    )

    # Patient
    patient_id = fields.Many2one(
        "hospital.patient",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
        help="Select the registered patient receiving medical care during this visit.",
    )
    reference = fields.Char(
        string="Patient Reference",
        related="patient_id.reference",
        help="Reference code of the associated patient.",
    )
    gender = fields.Selection(
        related="patient_id.gender",
        help="Biological gender of the associated patient.",
    )

    # Scheduling
    booking_date = fields.Date(
        default=fields.Date.today,
        tracking=True,
        help="Date when the appointment booking was registered.",
    )
    appointment_time = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
        index=True,
        tracking=True,
        help="Scheduled date and time for the doctor consultation.",
    )
    duration = fields.Float(
        default=0.5,
        help="Expected length of the consultation in hours (0.5 = 30 minutes). "
        "Used to prevent overlapping bookings for the same doctor.",
    )
    appointment_end = fields.Datetime(
        string="Expected End",
        compute="_compute_appointment_end",
        store=True,
        index=True,
        help="Appointment time plus duration.",
    )
    clinic_id = fields.Many2one(
        "hospital.clinic",
        index=True,
        ondelete="restrict",
        tracking=True,
        help="Clinic where the consultation takes place.",
    )
    clinic_clinician_ids = fields.Many2many(
        related="clinic_id.clinician_ids",
        string="Clinic Clinicians",
        help="Clinicians of the selected clinic, used to limit the doctor choices.",
    )
    doctor_id = fields.Many2one(
        "hr.employee",
        domain="[('is_clinician', '=', True), ('clinician_role', '=', 'doctor'), ('id', 'in', clinic_clinician_ids)]",
        index=True,
        ondelete="restrict",
        tracking=True,
        help="Doctor assigned to this appointment. Choose the clinic first: only its doctors are offered.",
    )
    priority = fields.Selection(
        [("0", "Low"), ("1", "Normal"), ("2", "High"), ("3", "Very High")],
        default="1",
        tracking=True,
        help="Indicates the clinical priority level or urgency of the case.",
    )

    # Workflow
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("ongoing", "Ongoing"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
        index=True,
        tracking=True,
        help="Current workflow phase of the appointment.",
    )
    confirmed_by = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
        tracking=True,
        help="User who confirmed this appointment.",
    )
    confirmation_date = fields.Datetime(
        string="Confirmed On",
        readonly=True,
        copy=False,
        help="Date and time the appointment was confirmed.",
    )
    consultation_start = fields.Datetime(
        string="Consultation Started",
        readonly=True,
        copy=False,
        help="Date and time the doctor started the consultation.",
    )
    consultation_end = fields.Datetime(
        string="Consultation Ended",
        readonly=True,
        copy=False,
        help="Date and time the consultation was completed.",
    )
    cancelled_by = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
        tracking=True,
        help="User who cancelled this appointment.",
    )
    cancellation_date = fields.Datetime(
        string="Cancelled On",
        readonly=True,
        copy=False,
        help="Date and time the appointment was cancelled.",
    )
    cancellation_reason = fields.Text(
        readonly=True,
        copy=False,
        help="Reason given when the appointment was cancelled.",
    )

    # Clinical
    note = fields.Html(
        string="Medical Notes",
        help="Record clinical observations, diagnoses, or comments during the consultation.",
    )
    chief_complaint = fields.Text(
        help="Main reason the patient came in, in the patient's own words.",
    )
    diagnosis = fields.Text(
        help="Doctor's diagnosis. Required before the consultation can be completed.",
    )
    weight = fields.Float(
        string="Weight (kg)",
        digits=(5, 1),
        help="Patient weight in kilograms, measured during this visit.",
    )
    height = fields.Float(
        string="Height (cm)",
        digits=(5, 1),
        help="Patient height in centimetres, measured during this visit.",
    )
    bmi = fields.Float(
        string="BMI",
        digits=(4, 1),
        compute="_compute_bmi",
        store=True,
        help="Body mass index: weight (kg) divided by height (m) squared.",
    )
    systolic_bp = fields.Integer(
        string="Systolic BP",
        help="Systolic blood pressure in mmHg (the upper number).",
    )
    diastolic_bp = fields.Integer(
        string="Diastolic BP",
        help="Diastolic blood pressure in mmHg (the lower number).",
    )
    follow_up_date = fields.Date(
        string="Follow-up Date",
        help="Date on which the doctor wants to see the patient again.",
    )
    follow_up_appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Follow-up Appointment",
        readonly=True,
        copy=False,
        ondelete="set null",
        help="Appointment created from this visit's follow-up date.",
    )
    prescription_line_ids = fields.One2many(
        "hospital.prescription.line",
        "appointment_id",
        string="Prescriptions",
        help="Medications prescribed during this appointment.",
    )
    previous_appointment_ids = fields.Many2many(
        "hospital.appointment",
        string="Past Visits",
        compute="_compute_previous_appointment_ids",
        help="The patient's most recent completed appointments before this one.",
    )

    # Billing
    sale_order_ids = fields.One2many(
        "sale.order",
        "appointment_id",
        string="Sales Orders",
        help="Sales orders linked to this appointment for billing and procedures.",
    )
    admission_ids = fields.One2many(
        "hospital.admission",
        "appointment_id",
        string="Admissions",
        help="Inpatient admissions that started from this appointment.",
    )
    admission_count = fields.Integer(
        compute="_compute_admission_count",
    )
    sale_order_count = fields.Integer(
        string="Sales Order Count",
        compute="_compute_sale_order_count",
        help="Total number of sales orders generated for this appointment.",
    )

    # ------------------------------------------------------------------
    # SQL constraints
    # ------------------------------------------------------------------

    _name_uniq = models.Constraint(
        "UNIQUE(name)",
        "The appointment reference must be unique.",
    )
    _doctor_window_idx = models.Index(
        "(doctor_id, appointment_time, appointment_end) WHERE state != 'cancel'",
    )
    _vitals_not_negative = models.Constraint(
        "CHECK(weight >= 0 AND height >= 0 AND systolic_bp >= 0 AND diastolic_bp >= 0)",
        "Vitals cannot be negative.",
    )
    _duration_positive = models.Constraint(
        "CHECK(duration > 0)",
        "The appointment duration must be greater than zero.",
    )
    _consultation_dates_check = models.Constraint(
        "CHECK(consultation_end IS NULL OR consultation_start IS NULL "
        "OR consultation_end >= consultation_start)",
        "The consultation cannot end before it starts.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends("appointment_time", "duration")
    def _compute_appointment_end(self):
        for rec in self:
            rec.appointment_end = (
                rec.appointment_time + timedelta(hours=rec.duration)
                if rec.appointment_time
                else False
            )

    @api.depends("weight", "height")
    def _compute_bmi(self):
        for rec in self:
            rec.bmi = (
                rec.weight / (rec.height / 100) ** 2
                if rec.weight and rec.height
                else 0.0
            )

    @api.depends("patient_id", "appointment_time")
    def _compute_previous_appointment_ids(self):
        for rec in self:
            if not (rec.patient_id and rec.appointment_time):
                rec.previous_appointment_ids = False
                continue
            rec.previous_appointment_ids = self.search(
                [
                    ("patient_id", "=", rec.patient_id.id),
                    ("id", "!=", rec._origin.id),
                    ("state", "=", "done"),
                    ("appointment_time", "<", rec.appointment_time),
                ],
                order="appointment_time desc",
                limit=PAST_VISITS_LIMIT,
            )

    @api.depends("admission_ids")
    def _compute_admission_count(self):
        counts = {
            appointment.id: count
            for appointment, count in self.env["hospital.admission"]._read_group(
                [("appointment_id", "in", self.ids)],
                groupby=["appointment_id"],
                aggregates=["__count"],
            )
        }
        for rec in self:
            rec.admission_count = counts.get(rec.id, 0)

    @api.depends("sale_order_ids")
    def _compute_sale_order_count(self):
        counts = {
            appointment.id: count
            for appointment, count in self.env["sale.order"]._read_group(
                [("appointment_id", "in", self.ids)],
                groupby=["appointment_id"],
                aggregates=["__count"],
            )
        }
        for rec in self:
            rec.sale_order_count = counts.get(rec.id, 0)

    # ------------------------------------------------------------------
    # Python constraints
    # ------------------------------------------------------------------

    @api.constrains("doctor_id", "appointment_time", "duration", "state")
    def _check_doctor_double_booking(self):
        """A doctor cannot hold two active appointments with overlapping time windows."""
        for rec in self:
            if not (rec.doctor_id and rec.appointment_time) or rec.state == "cancel":
                continue
            end = rec.appointment_time + timedelta(hours=rec.duration)
            clash = self.search_count(
                [
                    ("id", "!=", rec.id),
                    ("doctor_id", "=", rec.doctor_id.id),
                    ("state", "!=", "cancel"),
                    ("appointment_time", "<", end),
                    ("appointment_end", ">", rec.appointment_time),
                ],
            )
            if clash:
                local_time = fields.Datetime.context_timestamp(
                    rec,
                    rec.appointment_time,
                )
                raise ValidationError(
                    self.env._(
                        "%(doctor)s already has an appointment overlapping %(time)s.",
                        doctor=rec.doctor_id.display_name,
                        time=local_time.strftime("%Y-%m-%d %H:%M"),
                    ),
                )

    @api.constrains("systolic_bp", "diastolic_bp")
    def _check_blood_pressure(self):
        for rec in self:
            if (
                rec.systolic_bp
                and rec.diastolic_bp
                and rec.systolic_bp <= rec.diastolic_bp
            ):
                raise ValidationError(
                    self.env._(
                        "Systolic pressure must be higher than diastolic pressure.",
                    ),
                )

    @api.constrains("follow_up_date", "appointment_time")
    def _check_follow_up_date(self):
        for rec in self:
            if not (rec.follow_up_date and rec.appointment_time):
                continue
            visit_day = fields.Datetime.context_timestamp(
                rec,
                rec.appointment_time,
            ).date()
            if rec.follow_up_date <= visit_day:
                raise ValidationError(
                    self.env._(
                        "The follow-up date must be after the appointment date.",
                    ),
                )

    @api.constrains("patient_id")
    def _check_patient_alive(self):
        """New or re-assigned appointments cannot target a deceased patient."""
        for rec in self:
            if rec.patient_id.deceased:
                raise ValidationError(
                    self.env._(
                        "%(patient)s is marked as deceased and cannot be given an appointment.",
                        patient=rec.patient_id.display_name,
                    ),
                )

    @api.constrains("clinic_id", "doctor_id")
    def _check_doctor_in_clinic(self):
        """The assigned doctor must work in the selected clinic."""
        for rec in self:
            if (
                rec.clinic_id
                and rec.doctor_id
                and rec.doctor_id not in rec.clinic_id.clinician_ids
            ):
                raise ValidationError(
                    self.env._(
                        "%(doctor)s does not work in %(clinic)s.",
                        doctor=rec.doctor_id.display_name,
                        clinic=rec.clinic_id.name,
                    ),
                )

    @api.onchange("clinic_id")
    def _onchange_clinic_id(self):
        """Clear the doctor when the new clinic does not include them."""
        if self.doctor_id and self.doctor_id not in self.clinic_id.clinician_ids:
            self.doctor_id = False

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("hospital.appointment")
                    or "New"
                )
        return super().create(vals_list)

    def write(self, vals):
        if LOCKED_WHEN_DONE & vals.keys() and any(rec.state == "done" for rec in self):
            raise UserError(
                self.env._("The medical record of a completed appointment is locked."),
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active_appointment(self):
        if any(rec.state not in ("draft", "cancel") for rec in self):
            raise UserError(
                self.env._("Only draft or cancelled appointments can be deleted."),
            )

    # ------------------------------------------------------------------
    # Workflow actions
    # draft -> confirmed -> ongoing -> done, with cancel from draft/confirmed
    # ------------------------------------------------------------------

    def _ensure_state(self, allowed_states, error_message):
        if any(rec.state not in allowed_states for rec in self):
            raise UserError(error_message)

    def _get_formatted_appointment_time(self):
        """Formats appointment_time into a friendly string including the weekday and ordinal suffixes."""
        self.ensure_one()
        if not self.appointment_time:
            return self.env._("your scheduled time")

        local_time = fields.Datetime.context_timestamp(self, self.appointment_time)

        weekday_name = local_time.strftime("%A")
        day = local_time.day
        suffix = (
            "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        )
        month_name = local_time.strftime("%B")

        # Format time (e.g., "12 PM" if on the hour, or "12:30 PM" if minutes exist)
        time_format = "%I:%M %p" if local_time.minute != 0 else "%I %p"
        formatted_time = local_time.strftime(time_format).lstrip("0")

        return f"{weekday_name}, {day}{suffix} of {month_name} at {formatted_time}"

    def _get_confirmation_message(self):
        """Generates the raw confirmation text payload for communications."""
        self.ensure_one()
        patient_name = self.patient_id.name or self.env._("Patient")
        appt_num = self.name or "No."
        doctor_name = getattr(self, "doctor_id", False) and (
            self.doctor_id.name or self.env._("our doctor")
        )
        appointment_time_str = self._get_formatted_appointment_time()

        return (
            f"Hello *{patient_name}*, this is a confirmation for your appointment with "
            f"*{doctor_name}* on *{appointment_time_str}*.\n"
            f"Your Appointment Number is: *{appt_num}*."
        )

    def _send_confirmation_email(self):
        """Posts a message to the chatter and sends email notification to the patient."""
        self.ensure_one()
        patient_partner = self.patient_id.partner_id
        if not patient_partner or not patient_partner.email:
            return

        subject = self.env._("Appointment Confirmation - %s") % (self.name or "")

        # Clean plain text message formatting for the email body
        raw_msg = self._get_confirmation_message().replace("*", "")
        body_html = Markup(
            f"<p>Dear <strong>{patient_partner.name}</strong>,</p>"
            f"<p>{raw_msg.replace(chr(10), '<br/>')}</p>"
            f"<p>Thank you for choosing our clinic!</p>",
        )

        self.message_post(
            body=body_html,
            subject=subject,
            partner_ids=[patient_partner.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def action_confirm(self):
        self._ensure_state(
            ("draft",),
            self.env._("Only draft appointments can be confirmed."),
        )
        for rec in self:
            if not rec.clinic_id:
                raise UserError(
                    self.env._(
                        "Assign a clinic to %(appointment)s before confirming it.",
                        appointment=rec.name,
                    ),
                )
            if not rec.doctor_id:
                raise UserError(
                    self.env._(
                        "Assign a doctor to %(appointment)s before confirming it.",
                        appointment=rec.name,
                    ),
                )
            rec.write(
                {
                    "state": "confirmed",
                    "confirmed_by": self.env.user.id,
                    "confirmation_date": fields.Datetime.now(),
                },
            )
            rec.message_post(
                body=self.env._(
                    "Appointment for %(patient)s has been confirmed.",
                    patient=rec.patient_id.name,
                ),
            )
            # Send Email Confirmation
            rec._send_confirmation_email()

    def action_start_consultation(self):
        self._ensure_state(
            ("confirmed",),
            self.env._("Only confirmed appointments can start a consultation."),
        )
        for rec in self:
            rec.write(
                {
                    "state": "ongoing",
                    "consultation_start": fields.Datetime.now(),
                },
            )
            rec.message_post(
                body=self.env._(
                    "Consultation for %(patient)s has started.",
                    patient=rec.patient_id.name,
                ),
            )

    def action_done(self):
        self._ensure_state(
            ("ongoing",),
            self.env._("Start the consultation before marking it as done."),
        )
        for rec in self:
            if not (rec.diagnosis or "").strip():
                raise UserError(
                    self.env._(
                        "Enter a diagnosis for %(appointment)s before completing it.",
                        appointment=rec.name,
                    ),
                )
            rec.write(
                {
                    "state": "done",
                    "consultation_end": fields.Datetime.now(),
                },
            )
            rec.message_post(
                body=self.env._(
                    "Appointment for %(patient)s has been marked as done.",
                    patient=rec.patient_id.name,
                ),
            )

    def action_cancel(self):
        """Open the cancel wizard; the wizard records who cancelled and when."""
        self.ensure_one()
        self._ensure_state(
            ("draft", "confirmed"),
            self.env._("Only draft or confirmed appointments can be cancelled."),
        )
        return {
            "name": self.env._("Cancel Appointment"),
            "type": "ir.actions.act_window",
            "res_model": "cancel.appointment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_appointment_id": self.id},
        }

    def action_send_via_whatsapp(self):
        self.ensure_one()
        phone = self.patient_id.partner_id.phone or self.patient_id.partner_id.mobile
        if not phone:
            raise UserError(
                self.env._(
                    "This patient does not have a phone/mobile number configured.",
                ),
            )

        clean_phone = re.sub(r"\D", "", phone)
        message = self._get_confirmation_message()
        encoded_message = quote(message)
        whatsapp_url = (
            f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_message}"
        )

        return {
            "type": "ir.actions.act_url",
            "url": whatsapp_url,
            "target": "new",
        }

    def action_schedule_follow_up(self):
        """Create a draft appointment on the follow-up date, same patient, clinic and doctor."""
        self.ensure_one()
        if self.state not in ("ongoing", "done"):
            raise UserError(
                self.env._(
                    "Follow-ups can only be scheduled during or after the consultation.",
                ),
            )
        if not self.follow_up_date:
            raise UserError(self.env._("Set a follow-up date first."))
        if self.follow_up_appointment_id:
            raise UserError(self.env._("A follow-up appointment already exists."))
        visit_day = fields.Datetime.context_timestamp(
            self,
            self.appointment_time,
        ).date()
        follow_up = self.create(
            {
                "patient_id": self.patient_id.id,
                "clinic_id": self.clinic_id.id,
                "doctor_id": self.doctor_id.id,
                "duration": self.duration,
                "priority": self.priority,
                # Same time of day, on the follow-up date.
                "appointment_time": self.appointment_time
                + (self.follow_up_date - visit_day),
            },
        )
        self.follow_up_appointment_id = follow_up
        self.message_post(
            body=self.env._(
                "Follow-up appointment %(reference)s scheduled for %(date)s.",
                reference=follow_up.name,
                date=self.follow_up_date,
            ),
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "hospital.appointment",
            "res_id": follow_up.id,
            "view_mode": "form",
        }

    def action_create_quotation(self):
        """Bill the completed appointment: consultation fee plus prescribed medicines.

        Contract patients get a patient and a company quotation.
        """
        self.ensure_one()
        if self.state != "done":
            raise UserError(
                self.env._("Complete the appointment before creating a quotation."),
            )
        if self.sale_order_ids.filtered(lambda order: order.state != "cancel"):
            raise UserError(
                self.env._("This appointment already has a quotation or sales order."),
            )
        orders = self.env["sale.order"]._create_appointment_quotations(self)
        self.message_post(
            body=self.env._(
                "Quotation(s) created: %(orders)s.",
                orders=", ".join(orders.mapped("name")),
            ),
        )
        return self.action_view_sales_orders()

    def _cancel_with_reason(self, reason):
        """Single entry point used by the cancel wizard: state, audit trail and reason."""
        self._ensure_state(
            ("draft", "confirmed"),
            self.env._("Only draft or confirmed appointments can be cancelled."),
        )
        for rec in self:
            rec.write(
                {
                    "state": "cancel",
                    "cancelled_by": self.env.user.id,
                    "cancellation_date": fields.Datetime.now(),
                    "cancellation_reason": reason,
                },
            )
            rec.message_post(
                body=Markup("<br/>").join(
                    [
                        self.env._(
                            "Appointment for %(patient)s was cancelled by %(user)s.",
                            patient=rec.patient_id.name,
                            user=self.env.user.name,
                        ),
                        self.env._("Reason: %(reason)s", reason=reason),
                    ],
                ),
            )

    def action_draft(self):
        self._ensure_state(
            ("cancel",),
            self.env._("Only cancelled appointments can be reset to draft."),
        )
        for rec in self:
            rec.write(
                {
                    "state": "draft",
                    "confirmed_by": False,
                    "confirmation_date": False,
                    "consultation_start": False,
                    "consultation_end": False,
                    "cancelled_by": False,
                    "cancellation_date": False,
                    "cancellation_reason": False,
                },
            )
            rec.message_post(
                body=self.env._(
                    "Appointment for %(patient)s has been reset to draft.",
                    patient=rec.patient_id.name,
                ),
            )

    # ------------------------------------------------------------------
    # Dashboard (aggregates only: no patient data leaves the server)
    # ------------------------------------------------------------------

    @api.model
    def _get_dashboard_period_bounds(self, period):
        """Return the [start, end) UTC datetimes of a period, aligned on the user's calendar days."""
        today = fields.Date.context_today(self)
        if period == "week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=7)
        elif period == "month":
            start = today.replace(day=1)
            end = (start + timedelta(days=32)).replace(day=1)
        else:
            start, end = today, today + timedelta(days=1)
        tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")

        def to_utc(day):
            local_midnight = tz.localize(datetime.combine(day, time.min))
            return local_midnight.astimezone(pytz.utc).replace(tzinfo=None)

        return to_utc(start), to_utc(end)

    @api.model
    def _get_dashboard_top(self, domain, field_name):
        """Busiest records (clinic or doctor) of a period, cancelled visits excluded."""
        rows = self._read_group(
            domain + [(field_name, "!=", False), ("state", "!=", "cancel")],
            groupby=[field_name],
            aggregates=["__count"],
            order="__count desc",
            limit=DASHBOARD_TOP_LIMIT,
        )
        return [
            {"id": record.id, "name": record.display_name, "count": count}
            for record, count in rows
        ]

    @api.model
    def get_dashboard_data(self, period="today"):
        """Counters for the appointment dashboard, restricted to what the user may read."""
        if period not in DASHBOARD_PERIODS:
            raise UserError(self.env._("Unknown dashboard period."))
        start, end = self._get_dashboard_period_bounds(period)
        domain = [("appointment_time", ">=", start), ("appointment_time", "<", end)]
        urgent_domain = [
            ("state", "in", OPEN_STATES),
            ("priority", "in", URGENT_PRIORITIES),
        ]
        by_state = dict(
            self._read_group(domain, groupby=["state"], aggregates=["__count"]),
        )
        counts = {
            state: by_state.get(state, 0)
            for state, _label in self._fields["state"].selection
        }
        return {
            "period": period,
            "domain": [
                ["appointment_time", ">=", fields.Datetime.to_string(start)],
                ["appointment_time", "<", fields.Datetime.to_string(end)],
            ],
            "urgent_domain": [list(leaf) for leaf in urgent_domain],
            "total": sum(counts.values()),
            "counts": counts,
            "urgent": self.search_count(domain + urgent_domain),
            "by_clinic": self._get_dashboard_top(domain, "clinic_id"),
            "by_doctor": self._get_dashboard_top(domain, "doctor_id"),
        }

    # ------------------------------------------------------------------
    # Smart button actions
    # ------------------------------------------------------------------

    def action_admit_patient(self):
        """Open a new admission pre-filled from this appointment."""
        self.ensure_one()
        return {
            "name": self.env._("Admit Patient"),
            "type": "ir.actions.act_window",
            "res_model": "hospital.admission",
            "view_mode": "form",
            "context": {
                "default_patient_id": self.patient_id.id,
                "default_appointment_id": self.id,
                "default_admitting_doctor_id": self.doctor_id.id,
            },
        }

    def action_view_admissions(self):
        self.ensure_one()
        return {
            "name": self.env._("Admissions"),
            "type": "ir.actions.act_window",
            "res_model": "hospital.admission",
            "view_mode": "list,form",
            "domain": [("appointment_id", "=", self.id)],
        }

    def action_view_sales_orders(self):
        self.ensure_one()
        return {
            "name": self.env._("Sales Orders"),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("appointment_id", "=", self.id)],
            "context": {
                "default_appointment_id": self.id,
                "default_partner_id": self.patient_id.partner_id.id,
            },
        }
