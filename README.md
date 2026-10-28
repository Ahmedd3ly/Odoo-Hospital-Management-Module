# 🏥 Hospital Management System for Odoo 20 (`om_hospital`)

![Odoo](https://img.shields.io/badge/Odoo-20.0-714B67)
![License](https://img.shields.io/badge/license-LGPL--3-blue)
![Languages](https://img.shields.io/badge/languages-English%20%7C%20Arabic-green)

A hospital management module for **Odoo 20 Community** that covers the patient journey end to end: registration, clinic appointments, consultations and prescriptions, company-contract billing, and inpatient admissions with bed management.

It is built on standard Odoo (Contacts, Employees, Sales, Products) instead of replacing it, so patients are real contacts, doctors are real employees, and every bill is a regular quotation that flows into Odoo Sales and Invoicing.

> **Status:** feature-complete for a demo or a foundation to build on. Role-based security and record rules are intentionally **not implemented yet**; see [Security and privacy status](#security-and-privacy-status) before using real patient data.

> **Watch the quick walkthrough:**
> [![Hospital Management System Demo](static/description/demo.gif)](https://www.youtube.com/watch?v=ZU7Lrl-BBTk)
---

## Table of contents

- [Highlights](#highlights)
- [Feature tour](#feature-tour)
- [Architecture and design decisions](#architecture-and-design-decisions)
- [Data model](#data-model)
- [Project structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Quick start walkthrough](#quick-start-walkthrough)
- [PDF reports](#pdf-reports)
- [Translation](#translation)
- [Testing](#testing)
- [Search and performance](#search-and-performance)
- [Security and privacy status](#security-and-privacy-status)
- [Known limitations and roadmap](#known-limitations-and-roadmap)
- [Contributing](#contributing)
- [License and author](#license-and-author)

---

## Highlights

- **Patients are Odoo contacts.** The patient model delegates to `res.partner` (`_inherits`), so name, phone, email and photo live on the contact and the contact stays the single source of truth.
- **Doctors are Odoo employees.** Clinicians extend `hr.employee`, so nurses and technicians fit the same model and HR features come for free.
- **Clinics are data, not code.** Add a clinic, a ward, a bed or a specialty from the UI with no code change.
- **Double-booking protection** based on time windows, not just identical start times.
- **Structured clinical record:** complaint, diagnosis, vitals with computed BMI, prescriptions, follow-up scheduling, and a record that locks once the consultation is done.
- **Company contracts with split billing.** A contract gives a company's patients a discount per product category and splits each bill between the company and the patient.
- **Inpatient care:** wards, beds with computed occupancy, admissions, bed transfers with an audit log, and per-night billing.
- **Three PDF reports** and a **partial Arabic translation**.
- **Automated tests** (`TransactionCase`) that run against a real Odoo instance.

---

## Feature tour

### Patients
- Auto-generated patient reference (`PAT/00001`), date of birth with computed age, gender, blood group, deceased flag.
- ID document type and number (national ID, passport, residence permit), unique per type, optional.
- **Guardian required for minors**: any patient under 18 must have a guardian.
- **Medical conditions** (allergies and chronic conditions) as structured lines with severity, plus quick-filter tags (*Allergic*, *Chronic Condition*) that stay in sync automatically.
- **Emergency contacts** with relationship and a single primary contact per patient.
- Company / insurer link through the contact's parent company.
- Duplicate warning (same name and date of birth), phone and email validation.
- Birthday banner on the patient form.

### Clinicians, clinics and specialties
- `hr.employee` extension: clinician flag, clinical role (doctor, nurse, technician, other), specialty, license number, consultation fee, clinics.
- Clinics are records with a code, location, specialty, clinicians and a head of clinic; archiving is blocked while appointments are open.

### Appointments
- Workflow: **Draft → Confirmed → Ongoing → Done**, with cancellation from draft or confirmed.
- Choose the clinic first; the doctor list is limited to that clinic's doctors.
- **Overlap guard** using the appointment duration and a computed expected end time.
- **Consultation tab:** chief complaint, diagnosis, weight and height with computed BMI, systolic and diastolic blood pressure.
- A diagnosis is required before an appointment can be completed. Once done, the medical record and the prescription are locked.
- **Prescriptions** pick medicines from the product catalog (products flagged *Is Medicine*), with dose, frequency, duration, quantity and a *Bill* flag for medicines the patient buys elsewhere.
- **Follow-up:** set a date and create the follow-up appointment with one click.
- **Past visits** are computed from the patient's earlier completed appointments instead of being typed in.
- **Cancel wizard** with a mandatory reason, stored on the appointment and posted to the chatter.

### Billing and company contracts
- A **contract** links a company to a validity period, a default discount, discounts per product category, and the percentage of the bill the company pays.
- A patient is covered when their contact belongs to a company that has an active contract.
- **Create Quotation** (available once the appointment is done) bills the consultation fee plus the prescribed medicines. For contract patients it creates **two quotations**, one for the company and one for the patient, whose amounts add up to the discounted price.
- The line discount is a **computed field**, so it also applies to lines created by code or imports.
- A contract is resolved when the order is created. Changing a patient's company or a contract later never re-prices existing orders.

### Inpatient admissions
- **Wards and beds** with occupancy computed from admissions (never typed in).
- Admission workflow: **Draft → Admitted → Discharged**, with guards: one patient per bed, one active admission per patient, no admission for deceased patients.
- **Transfer Bed** wizard with an audit log; changing the bed directly on an admitted patient is blocked.
- **Per-night billing** at discharge using the standard *Bed Day* product (a midnight-count rule; a same-day stay counts as one night). Contract discounts and the company/patient split apply here too.
- Bed, patient and dates lock after discharge.

### Settings
- Settings page (**Hospital → Configuration → Settings**) to switch appointment cancellation on or off and to set the minimum cancellation notice in days.

---

## Architecture and design decisions

| Decision | Why |
|---|---|
| Patients use `_inherits = {"res.partner": "partner_id"}` | One contact record per person; no duplicated identity data and full compatibility with Sales and Invoicing |
| Clinicians extend `hr.employee`, not `res.users` | Not every clinician needs a login, and HR gives nurses, technicians and departments for free |
| Clinics, wards, beds, tests of the catalog are **records** | New ones need no code change and no deployment |
| Contract discount is a **`@api.depends` computed field** on the order line, not an `@api.onchange` | It must also apply to lines created by code, imports and the Create Quotation button, not only when someone edits a form |
| Consultation, medicines and bed days are **products** in hospital categories | Pricing, pricelists, taxes and invoicing all use standard Odoo; contract discounts are matched by product category |
| Occupancy, counts and past visits are **computed**, not stored by hand | Data cannot drift out of sync with the records it summarises |
| Counters use **`_read_group`** | One grouped query instead of loading whole record sets |
| Shared helper `models/search_utils.py` for computed-boolean search | Odoo may pass `('flag', '=', True)` or the normalised `('flag', 'in', [True])`; one helper handles every spelling |
| Medical record and billing inputs lock after completion | Billing stays consistent with what was actually delivered |
| Odoo 20 conventions: `models.Constraint`, `models.Index`, `self.env._()`, `list` views, `ir.access.csv` | Follows current framework standards |

---

## Data model

| Model | Purpose |
|---|---|
| `hospital.patient` | Patient (delegates to `res.partner`) |
| `hospital.patient.condition` | Allergy or chronic condition line |
| `hospital.emergency.contact` | Emergency contact with relationship |
| `hospital.tag` | Patient tags |
| `hospital.specialty` | Medical specialties |
| `hospital.clinic` | Clinics |
| `hr.employee` *(extended)* | Clinician fields |
| `hospital.appointment` | Appointment and clinical record |
| `hospital.prescription.line` | Prescribed medicine |
| `hospital.contract` / `hospital.contract.line` | Company contract and category discounts |
| `hospital.ward` / `hospital.bed` | Wards and beds |
| `hospital.admission` / `hospital.admission.transfer` | Inpatient stay and bed transfer log |
| `cancel.appointment.wizard` | Cancel appointment (transient) |
| `transfer.bed.wizard` | Transfer bed (transient) |
| `sale.order` / `sale.order.line` *(extended)* | Billing links, contract and payer, computed discount |
| `product.template` *(extended)* | *Is Medicine* flag |
| `res.partner` *(extended)* | *Is Patient* flag and patient shortcuts |
| `res.config.settings` *(extended)* | Cancellation settings |

---

## Project structure

```
om_hospital/
├── __init__.py
├── __manifest__.py
├── data/            # sequences, tags, product categories and products
├── demo/            # demonstration data
├── i18n/            # om_hospital.pot and ar.po (Arabic)
├── models/          # business logic, one file per model
├── report/          # QWeb PDF reports (actions and templates)
├── security/        # ir.access.csv
├── static/          # module icon and demo images
├── tests/           # TransactionCase test suite
├── views/           # views, actions and menus
└── wizard/          # cancel appointment and transfer bed wizards
```

---

## Installation

**Requirements:** Odoo 20.0 Community (or Enterprise) with the `base`, `mail`, `sale` and `hr` apps available.

1. Clone the repository into your custom add-ons directory. The folder **must** be named `om_hospital`:

   ```bash
   cd /path/to/custom_addons
   git clone https://github.com/<your-username>/om_hospital.git
   ```

2. Add that directory to `addons_path` in your Odoo configuration, then restart Odoo.

3. Create a database. To explore the module with sample data, tick **Demo data** in the database manager, or start with `--with-demo`.

4. Enable developer mode, open **Apps → Update Apps List**, search for **Hospital Management System** and click **Install**.

   Or from the command line:

   ```bash
   ./odoo-bin -d <database> -i om_hospital
   ```

5. To upgrade after pulling changes:

   ```bash
   ./odoo-bin -d <database> -u om_hospital
   ```

> The demo data refers to doctor images in `static/img/` and the app icon in `static/description/`. Keep those files in the repository.

---

## Configuration

- **Settings → Hospital** (or **Hospital → Configuration → Settings**): allow or block appointment cancellation, and set how many days in advance an appointment must be cancelled (default: 1 day).
- **Configuration menu:** clinics, clinicians, specialties, medicines, wards and beds.
- **Medicines:** any product can be flagged **Is Medicine**; the Medicines menu lists them. Put them in the *Hospital / Medicines* category so contract discounts apply.
- **Prices:** the consultation fee comes from the doctor's profile, medicine prices from the product, and the bed-day rate from the **Bed Day** product's sales price.

---

## Quick start walkthrough

1. **Register a patient** and add an allergy under *Medical Conditions*; the *Allergic* tag appears automatically.
2. **Book an appointment:** pick the clinic, then the doctor. Try an overlapping slot to see the guard.
3. **Run the consultation:** Confirm → Start Consultation → fill the Consultation and Prescription tabs → Mark As Done.
4. **Bill it:** Create Quotation. A patient covered by a company contract gets two quotations.
5. **Admit a patient:** Admit Patient → choose a bed → Transfer Bed if needed → Discharge → Create Quotation.
6. **Print:** use the **Print** menu on an appointment or admission to generate the PDFs.

With demo data you can follow this using the sample patients, the **Delta Industries** contract and the pre-admitted inpatient.

---

## PDF reports

| Report | Model | Contents |
|---|---|---|
| Prescription Slip | Appointment | Patient, doctor, medicines with dose, frequency, duration and quantity |
| Appointment Slip | Appointment | Date and time, doctor, clinic and location, arrival instructions |
| Discharge Summary | Admission | Stay dates, nights, ward and bed, reason, notes, bed transfers |

Reports are QWeb templates (`report/`) and are translated into Arabic.

---

## Translation

- `i18n/om_hospital.pot` is the template; `i18n/ar.po` is the Arabic translation.
- Translated: menus, field labels, selection values, buttons, tabs, error and chatter messages, and the three reports.
- Not translated: field help tooltips, and the labels of fields inherited from Odoo's own contact model (Odoo's own Arabic translation covers those).

To use it, enable Arabic under **Settings → Languages**, then switch your user's language. To regenerate the template after changing code:

```bash
./odoo-bin i18n export -c <your.conf> -d <database> -o i18n/om_hospital.pot om_hospital
```

---

## Testing

The test suite lives in `tests/` and uses Odoo's `TransactionCase`. It is **not loaded in normal operation**; Odoo only imports it when tests are requested, and every test rolls back its data.

```bash
./odoo-bin -d <database> -u om_hospital --test-tags /om_hospital --stop-after-init
```

Coverage includes:

- Patients: guardians, ID rules, tag synchronisation, emergency contacts, contact filters.
- Appointments: reference sequence, overlap guard, workflow, record lock, BMI and blood pressure, cancellation (including the chatter text), follow-ups, past visits.
- Billing: single and split quotations with exact amounts, medicine lines, the *Bill* flag, contract expiry, category rule precedence, no re-pricing of existing orders.
- Admissions: occupancy, one patient per bed, nights counting, transfers, archiving guards, bed-day billing.
- Reports: the three templates render with the expected content.

---

## Search and performance

- Trigram indexes on references and ID numbers for fast partial-text search.
- A composite partial index serving the double-booking check.
- Partial indexes on current admissions, used by the occupancy lookups.
- Grouped counters (`_read_group`) instead of loading whole record sets.

---

## Security and privacy status

Please read this before using the module with real data.

- **Roles and record rules are not implemented yet.** Every internal user currently has the same access to the hospital models (`security/ir.access.csv` grants the internal-user group full access). There is no separation between receptionist, doctor and manager.
- **No field-level protection** for sensitive data such as diagnoses, ID numbers or vitals.
- Patients are regular Odoo contacts, so they are visible to any user who can open Contacts. Restricting that is part of the planned security work.
- The module is designed with data minimisation in mind (for example, the medical record locks after completion and clinical values are kept out of chatter tracking), but it is **not** a certified or compliant system. It is not suitable for production patient data until the security layer is added and reviewed against the data-protection rules that apply to you (for example, Egypt's Personal Data Protection Law, Law 151 of 2020).

---

## Known limitations and roadmap

**Not included**
- Laboratory requests and results (designed and prototyped, then removed to keep the demo simple).
- Inpatient medication charts and nursing notes; medicines are prescribed through appointments only.
- Insurance claims, copay ceilings and pricing per ward type (a single bed-day rate is used).
- A uniqueness guarantee at database level for simultaneous bed admissions (enforced in Python only).
- PDF output was verified by rendering the report templates; always check the generated PDF in your environment (it needs `wkhtmltopdf`).

**Planned**
- Security groups (receptionist, doctor, manager), record rules and field-level restrictions.
- Restricting patient contacts to hospital staff.
- Lab module.
- Full translation of help texts.

---

## Contributing

Issues and pull requests are welcome.

1. Fork the repository and create a feature branch.
2. Follow the existing conventions: Odoo 20 ORM patterns, one model per file, `self.env._()` for user-facing strings, constraints and indexes declared with `models.Constraint` and `models.Index`.
3. Add or update tests in `tests/` and make sure the whole suite passes.
4. Open a pull request describing the change.

---

## License and author

Released under the [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html) license, the same license as Odoo's community modules.

**Author:** Ahmed Khatib
