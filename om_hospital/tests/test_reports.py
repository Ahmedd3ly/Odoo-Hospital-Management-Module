from odoo.tests.common import tagged

from .common import HospitalCommon


@tagged("post_install", "-at_install", "om_hospital")
class TestReports(HospitalCommon):
    def _html(self, report_xmlid, record):
        report = self.env.ref(report_xmlid)
        html, _report_type = report._render_qweb_html(report.report_name, record.ids)
        return html.decode()

    def test_prescription_slip_lists_medicines(self):
        appointment = self._make_appointment()
        medicine = self.env["product.product"].create(
            {"name": "Report Medicine", "type": "consu", "is_medicine": True},
        )
        self.env["hospital.prescription.line"].create(
            {
                "appointment_id": appointment.id,
                "medicine_id": medicine.id,
                "dose": "500mg",
            },
        )
        html = self._html("om_hospital.action_report_prescription", appointment)
        self.assertIn("Report Medicine", html)
        self.assertIn("500mg", html)
        self.assertIn(self.patient.name, html)

    def test_appointment_slip(self):
        appointment = self._make_appointment()
        html = self._html("om_hospital.action_report_appointment_slip", appointment)
        self.assertIn(appointment.name, html)
        self.assertIn("Test Clinic", html)

    def test_discharge_summary(self):
        ward = self.env["hospital.ward"].create({"name": "Report Ward", "code": "rw"})
        bed = self.env["hospital.bed"].create({"name": "R-1", "ward_id": ward.id})
        admission = self.env["hospital.admission"].create(
            {"patient_id": self.patient.id, "bed_id": bed.id, "reason": "Observation"},
        )
        admission.action_admit()
        admission.action_discharge()
        html = self._html("om_hospital.action_report_discharge_summary", admission)
        self.assertIn(admission.name, html)
        self.assertIn("Observation", html)
