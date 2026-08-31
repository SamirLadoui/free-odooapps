# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo import fields


@tagged('post_install', '-at_install')
class TestHospital(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.department = self.env['sl.hospital.department'].create({
            'name': 'Cardiology', 'code': 'CARD'})
        self.doctor = self.env['sl.hospital.doctor'].create({
            'name': 'Ada Heart', 'department_id': self.department.id,
            'consultation_fee': 50.0})
        self.other_doctor = self.env['sl.hospital.doctor'].create({
            'name': 'Grace Lung', 'department_id': self.department.id})
        self.patient = self.env['sl.hospital.patient'].create({'name': 'John Smith'})
        self.other_patient = self.env['sl.hospital.patient'].create({'name': 'Jane Doe'})
        self.slot = datetime(2026, 6, 1, 9, 0, 0)

    def _appointment(self, **values):
        return self.env['sl.hospital.appointment'].create(dict({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'appointment_date': self.slot,
            'duration': 1.0,
        }, **values))

    # -- numbering and contacts --------------------------------------------

    def test_records_get_numbers(self):
        self.assertTrue(self.patient.code.startswith('PAT/'), self.patient.code)
        self.assertTrue(self.doctor.code.startswith('DOC/'), self.doctor.code)
        self.assertTrue(self._appointment().code.startswith('APP/'))

    def test_patient_gets_a_contact(self):
        patient = self.env['sl.hospital.patient'].create({
            'name': 'Contact Test', 'email': 'ct@example.com'})
        self.assertTrue(patient.partner_id)
        self.assertEqual(patient.partner_id.email, 'ct@example.com')

    def test_doctor_display_name_is_prefixed(self):
        self.assertEqual(self.doctor.display_name, 'Dr. Ada Heart')

    def test_department_display_name_includes_code(self):
        self.assertEqual(self.department.display_name, '[CARD] Cardiology')

    # -- patient rules -----------------------------------------------------

    def test_age_is_computed(self):
        born = date.today() - timedelta(days=365 * 30 + 8)
        patient = self.env['sl.hospital.patient'].create({
            'name': 'Aged', 'birth_date': born})
        self.assertEqual(patient.age, 30)

    def test_birth_date_cannot_be_in_the_future(self):
        with self.assertRaises(ValidationError):
            self.env['sl.hospital.patient'].create({
                'name': 'Future', 'birth_date': fields.Date.context_today(self.env.user) + timedelta(days=1)})

    def test_patient_email_is_checked(self):
        with self.assertRaises(ValidationError):
            self.env['sl.hospital.patient'].create({
                'name': 'Bad Email', 'email': 'nope'})

    # -- scheduling --------------------------------------------------------

    def test_end_date_follows_duration(self):
        appointment = self._appointment(duration=1.5)
        self.assertEqual(appointment.end_date, self.slot + timedelta(hours=1.5))

    def test_duration_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._appointment(duration=0)

    def test_double_booking_is_refused(self):
        """The whole point of keeping the diary in Odoo."""
        self._appointment().action_confirm()
        overlapping = self._appointment(
            patient_id=self.other_patient.id,
            appointment_date=self.slot + timedelta(minutes=30))
        with self.assertRaises(ValidationError):
            overlapping.action_confirm()

    def test_back_to_back_bookings_are_allowed(self):
        """Ending exactly when the next starts is not an overlap."""
        self._appointment(duration=1.0).action_confirm()
        following = self._appointment(
            patient_id=self.other_patient.id,
            appointment_date=self.slot + timedelta(hours=1))
        following.action_confirm()
        self.assertEqual(following.state, 'confirmed')

    def test_another_doctor_can_take_the_same_slot(self):
        self._appointment().action_confirm()
        parallel = self._appointment(
            doctor_id=self.other_doctor.id, patient_id=self.other_patient.id)
        parallel.action_confirm()
        self.assertEqual(parallel.state, 'confirmed')

    def test_draft_appointments_do_not_block_the_slot(self):
        self._appointment()
        confirmed = self._appointment(patient_id=self.other_patient.id)
        confirmed.action_confirm()
        self.assertEqual(confirmed.state, 'confirmed')

    def test_cancelling_frees_the_slot(self):
        first = self._appointment()
        first.action_confirm()
        first.action_cancel()
        second = self._appointment(patient_id=self.other_patient.id)
        second.action_confirm()
        self.assertEqual(second.state, 'confirmed')

    # -- workflow ----------------------------------------------------------

    def test_closing_requires_a_diagnosis(self):
        appointment = self._appointment()
        appointment.action_confirm()
        appointment.action_start()
        with self.assertRaises(ValidationError):
            appointment.action_done()
        appointment.diagnosis = 'Nothing serious'
        appointment.action_done()
        self.assertEqual(appointment.state, 'done')

    def test_fee_defaults_from_the_doctor(self):
        appointment = self.env['sl.hospital.appointment'].new({
            'patient_id': self.patient.id, 'doctor_id': self.doctor.id})
        appointment._onchange_doctor_id()
        self.assertEqual(appointment.consultation_fee, 50.0)

    def test_fee_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self._appointment(consultation_fee=-1.0)

    def test_department_follows_the_doctor(self):
        self.assertEqual(self._appointment().department_id, self.department)

    def test_allergies_surface_on_the_appointment(self):
        self.patient.allergies = 'Penicillin'
        self.assertEqual(self._appointment().patient_allergies, 'Penicillin')

    # -- prescriptions -----------------------------------------------------

    def test_prescription_lines(self):
        appointment = self._appointment()
        appointment.prescription_ids = [(0, 0, {
            'medicine': 'Amoxicillin', 'dosage': '500 mg twice a day',
            'duration_days': 7})]
        self.assertEqual(len(appointment.prescription_ids), 1)

    def test_prescription_must_run_at_least_a_day(self):
        appointment = self._appointment()
        with self.assertRaises(ValidationError):
            appointment.prescription_ids = [(0, 0, {
                'medicine': 'Nothing', 'duration_days': 0})]

    def test_licence_number_is_unique(self):
        self.doctor.licence_number = 'LIC-1'
        with self.assertRaises(ValidationError):
            self.env['sl.hospital.doctor'].create({
                'name': 'Impostor', 'licence_number': 'LIC-1'})

    def test_department_code_is_unique(self):
        with self.assertRaises(ValidationError):
            self.env['sl.hospital.department'].create({
                'name': 'Duplicate', 'code': 'CARD'})
