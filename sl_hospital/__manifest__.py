# -*- coding: utf-8 -*-
{
    'name': 'Hospital Management',
    'version': '17.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Departments, doctors, patients and an appointment diary that refuses double bookings',
    'description': """
Hospital Management
===================

Patient records and a doctor's diary that actually holds.

Appointments
------------
Book a patient with a doctor for a slot and a duration. A confirmed appointment
occupies that doctor's time: a second confirmed booking that **overlaps** it is
refused, not quietly accepted. Back-to-back slots are fine, other doctors are
unaffected, and cancelling frees the slot immediately. Draft bookings do not
hold time, so reception can pencil things in.

The diary opens as a calendar, coloured per doctor, with list and form views
alongside.

Patients
--------
Numbered automatically, with age computed from the date of birth, blood group,
emergency contact, allergies and medical history. Registering a patient creates
a linked contact, so existing Odoo invoicing and mailing work with no extra
setup. Recorded allergies are shown as a warning on every one of that patient's
appointments.

Consultation
------------
An appointment moves draft to confirmed to in consultation to done. Closing it
requires a diagnosis, so the record cannot be finished empty. Prescriptions are
kept as lines on the appointment: medicine, dosage, and how many days for.

Doctors and departments
-----------------------
Doctors carry a number, department, specialisation, qualification, a unique
licence number and a default consultation fee, which pre-fills on their
appointments.

Access
------
Three levels: **Receptionist** registers patients and books appointments,
**Doctor** adds diagnoses and prescriptions, **Administrator** manages doctors
and departments.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/hospital_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/hospital_views.xml',
        'views/appointment_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
