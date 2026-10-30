from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged

from .common import HospitalCommon


@tagged("post_install", "-at_install", "om_hospital")
class TestBilling(HospitalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.partner"].create(
            {"name": "Acme Corp", "is_company": True},
        )
        cls.covered_patient = cls._make_patient(
            "Covered Patient",
            "covered@example.com",
            parent_id=cls.company.id,
        )
        cls.contract = cls.env["hospital.contract"].create(
            {
                "partner_id": cls.company.id,
                "date_start": fields.Date.today() - timedelta(days=30),
                "date_end": fields.Date.today() + timedelta(days=300),
                "default_discount": 10,
                "company_share": 80,
                "line_ids": [
                    Command.create(
                        {
                            "category_id": cls.env.ref(
                                "om_hospital.product_category_consultation",
                            ).id,
                            "discount": 20,
                        },
                    ),
                    Command.create(
                        {
                            "category_id": cls.env.ref(
                                "om_hospital.product_category_medicine",
                            ).id,
                            "discount": 5,
                        },
                    ),
                ],
            },
        )
        cls.contract.action_activate()
        cls.medicine = cls.env["product.product"].create(
            {
                "name": "Test Medicine",
                "type": "consu",
                "is_medicine": True,
                "list_price": 100,
                "categ_id": cls.env.ref("om_hospital.product_category_medicine").id,
            },
        )

    def test_quotation_only_after_done(self):
        appointment = self._make_appointment()
        appointment.action_confirm()
        with self.assertRaises(UserError):
            appointment.action_create_quotation()

    def test_patient_without_contract_pays_everything(self):
        appointment = self._complete_appointment(self._make_appointment())
        appointment.action_create_quotation()
        order = appointment.sale_order_ids
        self.assertEqual(len(order), 1)
        self.assertEqual(order.partner_id, self.patient.partner_id)
        self.assertEqual(order.amount_untaxed, 500)

    def test_contract_splits_discounted_consultation(self):
        appointment = self._complete_appointment(
            self._make_appointment(patient_id=self.covered_patient.id),
        )
        appointment.action_create_quotation()
        orders = appointment.sale_order_ids
        by_payer = {order.hospital_payer: order for order in orders}
        self.assertEqual(by_payer["company"].partner_id, self.company)
        self.assertEqual(
            by_payer["patient"].partner_id,
            self.covered_patient.partner_id,
        )
        # 500 less the 20% consultation discount = 400: company pays 80%, patient 20%
        self.assertAlmostEqual(by_payer["company"].amount_untaxed, 320.0, places=2)
        self.assertAlmostEqual(by_payer["patient"].amount_untaxed, 80.0, places=2)

    def test_prescribed_medicines_are_billed_and_flag_respected(self):
        appointment = self._make_appointment()
        appointment.action_confirm()
        appointment.action_start_consultation()
        other_medicine = self.medicine.copy({"name": "Bought Elsewhere"})
        self.env["hospital.prescription.line"].create(
            [
                {
                    "appointment_id": appointment.id,
                    "medicine_id": self.medicine.id,
                    "quantity": 2,
                },
                {
                    "appointment_id": appointment.id,
                    "medicine_id": other_medicine.id,
                    "to_bill": False,
                },
            ],
        )
        appointment.diagnosis = "Test"
        appointment.action_done()
        appointment.action_create_quotation()
        order = appointment.sale_order_ids
        self.assertEqual(
            len(order.order_line),
            2,
        )  # consultation + billed medicine only
        self.assertEqual(order.amount_untaxed, 500 + 2 * 100)

    def test_one_quotation_per_appointment(self):
        appointment = self._complete_appointment(self._make_appointment())
        appointment.action_create_quotation()
        with self.assertRaises(UserError):
            appointment.action_create_quotation()

    def test_existing_order_is_not_repriced_when_company_changes(self):
        appointment = self._complete_appointment(
            self._make_appointment(patient_id=self.covered_patient.id),
        )
        appointment.action_create_quotation()
        before = appointment.sale_order_ids.mapped("amount_untaxed")
        self.covered_patient.parent_id = False
        self.assertEqual(appointment.sale_order_ids.mapped("amount_untaxed"), before)

    def test_only_one_active_contract_per_company_at_a_time(self):
        overlapping = self.env["hospital.contract"].create(
            {"partner_id": self.company.id, "date_start": fields.Date.today()},
        )
        with self.assertRaises(ValidationError):
            overlapping.action_activate()

    def test_expired_contract_does_not_apply(self):
        self.contract.date_end = fields.Date.today() - timedelta(days=1)
        found = self.env["hospital.contract"]._get_contract_for_partner(
            self.covered_patient.partner_id,
        )
        self.assertFalse(found)

    def test_most_specific_category_rule_wins(self):
        self.assertEqual(self.contract._get_category_discount(self.medicine), 5)
        unrelated = self.env["product.product"].create(
            {"name": "Other", "type": "service"},
        )
        self.assertEqual(self.contract._get_category_discount(unrelated), 10)
