from odoo import Command, api, fields, models
from odoo.exceptions import UserError


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
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        related="appointment_id.patient_id",
        store=True,
        index=True,
        readonly=True,
        help="Patient of the linked appointment.",
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

    # The contract is found when the patient or partner is chosen, not afterwards:
    # confirmed orders must never be re-priced when a contract or a patient's company changes.
    @api.depends("appointment_id", "partner_id")
    def _compute_hospital_contract_id(self):
        contracts = self.env["hospital.contract"]
        for order in self:
            beneficiary = order.appointment_id.patient_id.partner_id or order.partner_id
            on_date = fields.Date.context_today(order, order.date_order or fields.Datetime.now())
            order.hospital_contract_id = contracts._get_contract_for_partner(beneficiary, on_date)

    @api.onchange("appointment_id")
    def _onchange_appointment_id(self):
        partner = self.appointment_id.patient_id.partner_id
        if partner:
            self.partner_id = partner

    @api.model
    def _create_appointment_quotations(self, appointment):
        """Bill a completed appointment: the consultation fee plus the prescribed medicines.

        One quotation per payer (patient and/or contract company), each carrying the same
        lines; the contract discount and payer share are applied by the line discount compute.
        """
        product = self.env.ref("om_hospital.product_consultation")
        patient_partner = appointment.patient_id.partner_id
        day = fields.Date.context_today(appointment, appointment.appointment_time)
        contract = self.env["hospital.contract"]._get_contract_for_partner(patient_partner, day)

        payers = [("patient", patient_partner)]
        if contract:
            payers = []
            if contract.company_share < 100:
                payers.append(("patient", patient_partner))
            if contract.company_share > 0:
                payers.append(("company", contract.partner_id))

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
        return self.create(
            [
                {
                    "partner_id": partner.id,
                    "appointment_id": appointment.id,
                    "hospital_contract_id": contract.id,
                    "hospital_payer": payer,
                    "order_line": lines,
                }
                for payer, partner in payers
            ]
        )
