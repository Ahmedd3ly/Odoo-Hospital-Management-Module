from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged

from .common import HospitalCommon


@tagged("post_install", "-at_install", "om_hospital")
class TestAdmission(HospitalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ward = cls.env["hospital.ward"].create({"name": "Test Ward", "code": "tw"})
        cls.bed1, cls.bed2 = cls.env["hospital.bed"].create(
            [{"name": "B-1", "ward_id": cls.ward.id}, {"name": "B-2", "ward_id": cls.ward.id}]
        )

    def _admit(self, patient=None, bed=None, **kwargs):
        admission = self.env["hospital.admission"].create(
            {"patient_id": (patient or self.patient).id, "bed_id": (bed or self.bed1).id, **kwargs}
        )
        admission.action_admit()
        return admission

    def test_occupancy_follows_admissions(self):
        self.assertFalse(self.bed1.is_occupied)
        admission = self._admit()
        self.assertTrue(self.bed1.is_occupied)
        self.assertEqual(self.bed1.current_admission_id, admission)
        self.assertIn(self.bed1, self.env["hospital.bed"].search([("is_occupied", "=", True)]))
        admission.action_discharge()
        self.assertFalse(self.bed1.is_occupied)

    def test_bed_cannot_hold_two_patients(self):
        self._admit()
        other = self._make_patient("Second", "second@example.com")
        with self.assertRaises(ValidationError):
            self._admit(patient=other)

    def test_patient_cannot_be_admitted_twice(self):
        self._admit()
        with self.assertRaises(ValidationError):
            self._admit(bed=self.bed2)

    def test_admit_needs_a_bed(self):
        admission = self.env["hospital.admission"].create({"patient_id": self.patient.id})
        with self.assertRaises(UserError):
            admission.action_admit()

    def test_same_day_stay_counts_one_night(self):
        admission = self._admit()
        admission.action_discharge()
        self.assertEqual(admission.nights, 1)

    def test_nights_are_counted_per_midnight(self):
        admission = self._admit(admission_date=fields.Datetime.now() - timedelta(days=3))
        self.assertEqual(admission.nights, 3)

    def test_transfer_moves_patient_and_logs_it(self):
        admission = self._admit()
        wizard = self.env["transfer.bed.wizard"].create(
            {"admission_id": admission.id, "new_bed_id": self.bed2.id, "reason": "More space"}
        )
        wizard.action_transfer()
        self.assertEqual(admission.bed_id, self.bed2)
        self.assertEqual(admission.transfer_ids.from_bed_id, self.bed1)
        self.assertFalse(self.bed1.is_occupied)
        self.assertTrue(self.bed2.is_occupied)

    def test_bed_cannot_be_changed_directly_while_admitted(self):
        admission = self._admit()
        with self.assertRaises(UserError):
            admission.bed_id = self.bed2

    def test_discharged_admission_is_locked(self):
        admission = self._admit()
        admission.action_discharge()
        with self.assertRaises(UserError):
            admission.admission_date = fields.Datetime.now() - timedelta(days=9)

    def test_occupied_bed_and_ward_cannot_be_archived(self):
        self._admit()
        with self.assertRaises(ValidationError):
            self.bed1.active = False
        with self.assertRaises(ValidationError):
            self.ward.active = False

    def test_stay_is_billed_per_night(self):
        admission = self._admit(admission_date=fields.Datetime.now() - timedelta(days=2))
        with self.assertRaises(UserError):
            admission.action_create_quotation()  # not discharged yet
        admission.action_discharge()
        admission.action_create_quotation()
        order = admission.sale_order_ids
        bed_day = self.env.ref("om_hospital.product_bed_day")
        self.assertEqual(order.order_line.product_uom_qty, 2)
        self.assertEqual(order.amount_untaxed, 2 * bed_day.list_price)
