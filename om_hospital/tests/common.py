from datetime import timedelta

from odoo import Command, fields
from odoo.tests.common import TransactionCase


class HospitalCommon(TransactionCase):
    """Shared fixtures: a clinic with two doctors and a patient."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        employees = cls.env["hr.employee"]
        cls.doctor = employees.create(
            {
                "name": "Dr. Dan",
                "is_clinician": True,
                "clinician_role": "doctor",
                "hospital_consultation_fee": 500,
            },
        )
        cls.doctor2 = employees.create(
            {
                "name": "Dr. Dina",
                "is_clinician": True,
                "clinician_role": "doctor",
                "hospital_consultation_fee": 300,
            },
        )
        cls.clinic = cls.env["hospital.clinic"].create(
            {
                "name": "Test Clinic",
                "code": "tst",
                "clinician_ids": [Command.set((cls.doctor | cls.doctor2).ids)],
            },
        )
        cls.patient = cls._make_patient("Test Patient", "test.patient@example.com")

    @classmethod
    def _make_patient(cls, name, email, **kwargs):
        vals = {
            "name": name,
            "email": email,
            "phone": "+20 100 000 9999",
            "date_of_birth": fields.Date.today() - timedelta(days=365 * 30),
            "gender": "female",
            "blood_group": "O+",
        }
        vals.update(kwargs)
        return cls.env["hospital.patient"].create(vals)

    def _make_appointment(self, **kwargs):
        vals = {
            "patient_id": self.patient.id,
            "clinic_id": self.clinic.id,
            "doctor_id": self.doctor.id,
            "appointment_time": fields.Datetime.now() + timedelta(days=5),
        }
        vals.update(kwargs)
        return self.env["hospital.appointment"].create(vals)

    def _complete_appointment(self, appointment, diagnosis="Test diagnosis"):
        appointment.action_confirm()
        appointment.action_start_consultation()
        appointment.diagnosis = diagnosis
        appointment.action_done()
        return appointment
