# Hospital Management

> Patient Records And A Doctor's Diary That Actually Holds

Departments, doctors, patients and appointments, built around a booking rule that refuses double bookings instead of quietly accepting them. The mistake a paper diary makes is the one this module exists to prevent.

## Features

- **A Diary That Refuses Double Bookings** - A confirmed appointment occupies its doctor's time. A second confirmed booking that overlaps it is refused. Back-to-back slots are fine, other doctors are unaffected, and cancelling frees the slot immediately.
- **Pencil It In First** - Draft appointments do not hold the doctor's time, so reception can note a request before it is agreed, and only confirmed bookings compete for slots.
- **Calendar, Coloured Per Doctor** - The appointment diary opens as a week calendar coloured by doctor, with list and form views alongside and grouping by doctor, department, date or status.
- **Allergies Where You Will See Them** - Allergies recorded on a patient appear as a warning banner on every one of that patient's appointments, rather than sitting on a tab nobody opens.
- **No Empty Consultations** - An appointment cannot be closed without a diagnosis. Prescriptions live on the appointment as lines: medicine, dosage, and how many days for.
- **Patients Are Real Contacts** - Registering a patient creates a linked contact record, so Odoo invoicing and mailing work immediately. Age is computed from the date of birth, and a future date of birth is refused.

## Getting Started

1. Install the module and open the Hospital app.
2. Under Configuration, add your departments and then your doctors.
3. Register patients under Patients.
4. Book from Appointments, then Confirm to hold the doctor's slot.

## Good To Know

- Doctor licence numbers and department codes are unique; patient, doctor and appointment numbers come from sequences.
- A doctor's default consultation fee pre-fills on their appointments and can still be changed per visit.
- Three access levels: Receptionist books and registers, Doctor records diagnoses and prescriptions, Administrator manages doctors and departments.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
