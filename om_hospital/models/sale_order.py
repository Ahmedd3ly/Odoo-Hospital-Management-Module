from odoo import Command, api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Hospital Appointment",
        index=True,
        copy=False,
        ondelete="restrict",
        help="Linked medical appointment for billing and tracking.",
    )
    admission_id = fields.Many2one(
        "hospital.admission",
        string="Admission",
        index=True,
        copy=False,
        ondelete="restrict",
        help="Inpatient admission billed by this order.",
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        compute="_compute_patient_id",
        store=True,
        index=True,
        readonly=True,
        help="Patient of the linked appointment or admission.",
    )
    hospital_contract_id = fields.Many2one(
        "hospital.contract",
        string="Company Contract",
        compute="_compute_hospital_contract_id",
        store=True,
        readonly=False,
        index=True,
        ondelete="restrict",
        copy=False,
        help="Contract whose discount and coverage split apply to this order. "
        "Found from the patient's company; clear it to bill at full price.",
    )
    hospital_payer = fields.Selection(
        [("patient", "Patient"), ("company", "Company")],
        string="Billed To",
        default="patient",
        required=True,
        copy=False,
        help="With a contract, each order carries one payer's share of the discounted amount.",
    )

    @api.depends("appointment_id.patient_id", "admission_id.patient_id")
    def _compute_patient_id(self):
        for order in self:
            order.patient_id = order.appointment_id.patient_id or order.admission_id.patient_id

    # The contract is found when the patient or partner is chosen, not afterwards:
    # confirmed orders must never be re-priced when a contract or a patient's company changes.
    @api.depends("patient_id", "partner_id")
    def _compute_hospital_contract_id(self):
        contracts = self.env["hospital.contract"]
        for order in self:
            beneficiary = order.patient_id.partner_id or order.partner_id
            on_date = fields.Date.context_today(order, order.date_order or fields.Datetime.now())
            order.hospital_contract_id = contracts._get_contract_for_partner(beneficiary, on_date)

    @api.onchange("appointment_id")
    def _onchange_appointment_id(self):
        partner = self.appointment_id.patient_id.partner_id
        if partner:
            self.partner_id = partner

    # ------------------------------------------------------------------
    # Hospital billing: one quotation per payer
    # ------------------------------------------------------------------

    @api.model
    def _create_hospital_quotations(
        self, patient, lines, appointment=None, admission=None, on_date=None
    ):
        """Create the quotation(s) for a patient: one per payer.

        Without a contract the patient pays everything. With an active contract of the
        patient's company, the company and the patient each get an order carrying their
        share; the line discount compute applies the contract discount and the split.
        """
        patient_partner = patient.partner_id
        contract = self.env["hospital.contract"]._get_contract_for_partner(
            patient_partner, on_date
        )
        payers = [("patient", patient_partner)]
        if contract:
            payers = []
            if contract.company_share < 100:
                payers.append(("patient", patient_partner))
            if contract.company_share > 0:
                payers.append(("company", contract.partner_id))

        return self.create(
            [
                {
                    "partner_id": partner.id,
                    "appointment_id": appointment.id if appointment else False,
                    "admission_id": admission.id if admission else False,
                    "hospital_contract_id": contract.id,
                    "hospital_payer": payer,
                    "order_line": lines,
                }
                for payer, partner in payers
            ]
        )

    @api.model
    def _create_appointment_quotations(self, appointment):
        """Bill a completed appointment: the consultation fee plus the prescribed medicines."""
        product = self.env.ref("om_hospital.product_consultation")
        fee = appointment.doctor_id.hospital_consultation_fee or product.lst_price
        lines = [
            Command.create({"product_id": product.id, "product_uom_qty": 1, "price_unit": fee})
        ]
        # No price_unit for medicines: Odoo takes it from the product and the pricelist.
        lines += [
            Command.create(
                {"product_id": line.medicine_id.id, "product_uom_qty": line.quantity}
            )
            for line in appointment.prescription_line_ids.filtered("to_bill")
        ]
        day = fields.Date.context_today(appointment, appointment.appointment_time)
        return self._create_hospital_quotations(
            appointment.patient_id, lines, appointment=appointment, on_date=day
        )

    @api.model
    def _create_admission_quotations(self, admission):
        """Bill an inpatient stay: one bed-day line, quantity = billable nights."""
        product = self.env.ref("om_hospital.product_bed_day")
        lines = [
            Command.create({"product_id": product.id, "product_uom_qty": admission.nights})
        ]
        # Contract coverage is judged at admission, not at discharge.
        day = fields.Date.context_today(admission, admission.admission_date)
        return self._create_hospital_quotations(
            admission.patient_id, lines, admission=admission, on_date=day
        )
