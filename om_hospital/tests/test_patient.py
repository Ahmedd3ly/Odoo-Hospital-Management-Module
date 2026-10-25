from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import HospitalCommon


@tagged("post_install", "-at_install", "om_hospital")
class TestPatient(HospitalCommon):
    def test_reference_is_generated_and_unique(self):
        other = self._make_patient("Other Patient", "other@example.com")
        self.assertTrue(self.patient.reference.startswith("PAT/"))
        self.assertNotEqual(self.patient.reference, other.reference)

    def test_minor_needs_guardian(self):
        child_dob = fields.Date.today() - timedelta(days=365 * 8)
        with self.assertRaises(ValidationError):
            self._make_patient("Little One", "little@example.com", date_of_birth=child_dob)
        guardian = self.env["res.partner"].create({"name": "Parent Person"})
        child = self._make_patient(
            "Little One", "little@example.com", date_of_birth=child_dob, guardian_id=guardian.id
        )
        self.assertTrue(child.is_minor)

    def test_is_patient_filter_on_contacts(self):
        partners = self.env["res.partner"]
        non_patient = partners.create({"name": "Just A Contact"})
        patients = partners.search([("is_patient", "=", True)])
        others = partners.search([("is_patient", "=", False)])
        self.assertIn(self.patient.partner_id, patients)
        self.assertNotIn(non_patient, patients)
        self.assertIn(non_patient, others)
        self.assertNotIn(self.patient.partner_id, others)
        self.assertIn(self.patient.partner_id, partners.search([("is_patient", "!=", False)]))

    def test_future_birth_date_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_patient(
                "Future", "future@example.com", date_of_birth=fields.Date.today() + timedelta(days=2)
            )

    def test_phone_format_validated(self):
        with self.assertRaises(ValidationError):
            self._make_patient("Bad Phone", "badphone@example.com", phone="abc")

    @mute_logger("odoo.sql_db")
    def test_id_type_and_number_go_together(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.patient.id_type = "passport"
            self.patient.flush_recordset()

    @mute_logger("odoo.sql_db")
    def test_id_must_be_unique(self):
        self.patient.write({"id_type": "national_id", "id_number": "12345678901234"})
        other = self._make_patient("Other Patient", "other@example.com")
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            other.write({"id_type": "national_id", "id_number": "12345678901234"})
            other.flush_recordset()

    def test_condition_lines_keep_tags_in_sync(self):
        allergic = self.env.ref("om_hospital.tag_allergic")
        condition = self.env["hospital.patient.condition"].create(
            {"patient_id": self.patient.id, "condition_type": "allergy", "name": "Penicillin"}
        )
        self.assertIn(allergic, self.patient.tag_ids)
        condition.unlink()
        self.assertNotIn(allergic, self.patient.tag_ids)

    def test_single_primary_emergency_contact(self):
        partners = self.env["res.partner"].create([{"name": "Contact A"}, {"name": "Contact B"}])
        contacts = self.env["hospital.emergency.contact"]
        contacts.create(
            {"patient_id": self.patient.id, "partner_id": partners[0].id, "relationship": "parent", "is_primary": True}
        )
        with self.assertRaises(ValidationError):
            contacts.create(
                {"patient_id": self.patient.id, "partner_id": partners[1].id, "relationship": "friend", "is_primary": True}
            )

    def test_patient_cannot_be_own_emergency_contact(self):
        with self.assertRaises(ValidationError):
            self.env["hospital.emergency.contact"].create(
                {"patient_id": self.patient.id, "partner_id": self.patient.partner_id.id, "relationship": "other"}
            )

    def test_deceased_patient_gets_no_appointment(self):
        self.patient.deceased = True
        with self.assertRaises(ValidationError):
            self._make_appointment()
