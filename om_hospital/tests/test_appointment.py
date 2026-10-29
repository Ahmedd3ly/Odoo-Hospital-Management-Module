from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged

from .common import HospitalCommon


@tagged("post_install", "-at_install", "om_hospital")
class TestAppointment(HospitalCommon):
    def test_reference_sequence(self):
        self.assertTrue(self._make_appointment().name.startswith("APT/"))

    def test_confirm_needs_clinic_and_doctor(self):
        appointment = self._make_appointment(clinic_id=False, doctor_id=False)
        with self.assertRaises(UserError):
            appointment.action_confirm()

    def test_doctor_must_work_in_clinic(self):
        outsider_doctor = self.env["hr.employee"].create(
            {"name": "Dr. Elsewhere", "is_clinician": True, "clinician_role": "doctor"}
        )
        with self.assertRaises(ValidationError):
            self._make_appointment(doctor_id=outsider_doctor.id)

    def test_overlapping_appointments_blocked(self):
        start = fields.Datetime.now() + timedelta(days=5)
        self._make_appointment(appointment_time=start)
        other_patient = self._make_patient("Second", "second@example.com")
        with self.assertRaises(ValidationError):
            self._make_appointment(
                patient_id=other_patient.id,
                appointment_time=start + timedelta(minutes=15),
            )

    def test_back_to_back_and_other_doctor_allowed(self):
        start = fields.Datetime.now() + timedelta(days=5)
        self._make_appointment(appointment_time=start)
        other_patient = self._make_patient("Second", "second@example.com")
        self._make_appointment(
            patient_id=other_patient.id, appointment_time=start + timedelta(minutes=30)
        )
        self._make_appointment(
            patient_id=other_patient.id,
            doctor_id=self.doctor2.id,
            appointment_time=start,
        )

    def test_cancelled_appointment_frees_the_slot(self):
        start = fields.Datetime.now() + timedelta(days=5)
        first = self._make_appointment(appointment_time=start)
        first._cancel_with_reason("No show")
        other_patient = self._make_patient("Second", "second@example.com")
        self._make_appointment(patient_id=other_patient.id, appointment_time=start)

    def test_cannot_complete_without_diagnosis(self):
        appointment = self._make_appointment()
        appointment.action_confirm()
        appointment.action_start_consultation()
        with self.assertRaises(UserError):
            appointment.action_done()

    def test_workflow_and_record_lock(self):
        appointment = self._complete_appointment(self._make_appointment())
        self.assertEqual(appointment.state, "done")
        with self.assertRaises(UserError):
            appointment.diagnosis = "Changed afterwards"
        with self.assertRaises(UserError):
            self.env["hospital.prescription.line"].create(
                {
                    "appointment_id": appointment.id,
                    "medicine_id": self._medicine().id,
                }
            )

    def test_bmi_and_blood_pressure(self):
        appointment = self._make_appointment(weight=82, height=178)
        self.assertAlmostEqual(appointment.bmi, 25.9, places=1)
        with self.assertRaises(ValidationError):
            appointment.write({"systolic_bp": 80, "diastolic_bp": 120})

    def test_cancel_stores_reason_and_chatter_is_not_escaped(self):
        appointment = self._make_appointment(
            appointment_time=fields.Datetime.now() + timedelta(days=4)
        )
        wizard = self.env["cancel.appointment.wizard"].create(
            {"appointment_id": appointment.id, "reason": "No Show"}
        )
        wizard.action_cancel_appointment()
        self.assertEqual(appointment.state, "cancel")
        self.assertEqual(appointment.cancellation_reason, "No Show")
        body = str(appointment.message_ids[0].body)
        self.assertIn("Reason: No Show", body)
        self.assertNotIn("&lt;br", body)

    def test_cannot_cancel_todays_appointment(self):
        appointment = self._make_appointment(
            appointment_time=fields.Datetime.now() + timedelta(minutes=30)
        )
        wizard = self.env["cancel.appointment.wizard"].create(
            {"appointment_id": appointment.id, "reason": "Too late"}
        )
        with self.assertRaises(UserError):
            wizard.action_cancel_appointment()

    def test_follow_up_creates_draft_appointment(self):
        appointment = self._make_appointment()
        appointment.action_confirm()
        appointment.action_start_consultation()
        visit_day = fields.Datetime.context_timestamp(
            appointment, appointment.appointment_time
        ).date()
        appointment.follow_up_date = visit_day + timedelta(days=7)
        appointment.action_schedule_follow_up()
        follow_up = appointment.follow_up_appointment_id
        self.assertEqual(follow_up.state, "draft")
        self.assertEqual(follow_up.doctor_id, appointment.doctor_id)
        self.assertEqual(
            follow_up.appointment_time - appointment.appointment_time, timedelta(days=7)
        )

    def test_past_visits_list_completed_visits_only(self):
        old = self._complete_appointment(
            self._make_appointment(
                appointment_time=fields.Datetime.now() + timedelta(days=2)
            )
        )
        upcoming = self._make_appointment(
            appointment_time=fields.Datetime.now() + timedelta(days=9)
        )
        self.assertEqual(upcoming.previous_appointment_ids, old)

    def _medicine(self):
        return self.env["product.product"].create(
            {
                "name": "Test Medicine",
                "type": "consu",
                "is_medicine": True,
                "list_price": 100,
            }
        )

    def test_dashboard_counts_follow_period_and_state(self):
        model = self.env["hospital.appointment"]
        before = model.get_dashboard_data("today")
        self._make_appointment(appointment_time=fields.Datetime.now())
        self._make_appointment(
            appointment_time=fields.Datetime.now() + timedelta(days=40)
        )
        after = model.get_dashboard_data("today")
        self.assertEqual(after["counts"]["draft"], before["counts"]["draft"] + 1)
        self.assertEqual(after["total"], before["total"] + 1)
        with self.assertRaises(UserError):
            model.get_dashboard_data("decade")
