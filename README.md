# 🏥 Odoo Hospital Management System (`om_hospital`)

A comprehensive, enterprise-grade custom Odoo module built for Odoo 20 to manage hospital operations, patient health records, clinical workflows, appointments, contracts, and sales integrations.

---

## ✨ Key Features

* 👤 **Patient & Clinical Management**: Track detailed patient profiles, conditions, tags, and emergency contacts.
* 📅 **Appointments & Scheduling**: Manage patient appointments, clinic assignments, clinician coordination, and cancellation workflows via wizard actions.
* 📝 **Contracts & Prescriptions**: Handle service contracts, contract lines, and prescription lines seamlessly.
* 📦 **Product & Sales Integration**: Extend standard inventory templates and sale order views/models.
* 🔒 **Modernized Odoo 20 Security**: Utilizes the updated Odoo 20 `ir.access.csv` security rights architecture.

---

## 📂 Project Structure

```text
om_hospital/
├─ __init__.py
├─ __manifest__.py
├─ data/
│  ├── appointment_data.xml
│  ├── contract_data.xml
│  ├── patient_data.xml
│  ├── product_data.xml
│  └── tag_data.xml
├─ demo/
│  └── demo.xml
├─ models/
│  ├── __init__.py
│  ├── appointment.py
│  ├── clinic.py
│  ├── contract.py
│  ├── contract_line.py
│  ├── emergency_contact.py
│  ├── hr_employee.py
│  ├── patient.py
│  ├── patient_condition.py
│  ├── prescription_line.py
│  ├── product_template.py
│  ├── res_partner.py
│  ├── sale_order.py
│  ├── sale_order_line.py
│  ├── specialty.py
│  └── tag.py
├─ security/
│  └── ir.access.csv
├─ static/         # 🖼️ Contains UI icons and images
│  ├── description
│  └── img
├─ views/
│  ├── appointment_views.xml
│  ├── clinic_views.xml
│  ├── contract_views.xml
│  ├── hospital_menus.xml
│  ├── hr_employee_views.xml
│  ├── patient_views.xml
│  ├── product_views.xml
│  ├── res_partner_views.xml
│  ├── sale_order_views.xml
│  └── specialty_views.xml
└─ wizard/
   ├── __init__.py
   ├── cancel_appointment.py
   └── cancel_appointment_views.xml
