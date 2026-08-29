# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# States a doctor's diary should treat as occupying their time.
BLOCKING_STATES = ('confirmed', 'in_consultation')


class Appointment(models.Model):
    _name = 'sl.hospital.appointment'
    _description = 'Appointment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'appointment_date desc, id desc'
    _rec_name = 'code'

    code = fields.Char(string='Reference', copy=False, readonly=True, default='/')
    patient_id = fields.Many2one(
        'sl.hospital.patient', string='Patient', required=True,
        ondelete='restrict', tracking=True)
    doctor_id = fields.Many2one(
        'sl.hospital.doctor', string='Doctor', required=True,
        ondelete='restrict', tracking=True)
    department_id = fields.Many2one(
        related='doctor_id.department_id', string='Department', store=True)

    appointment_date = fields.Datetime(
        string='Scheduled For', required=True, tracking=True,
        default=fields.Datetime.now)
    duration = fields.Float(
        string='Duration (hours)', default=0.5, required=True)
    end_date = fields.Datetime(compute='_compute_end_date', store=True)

    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed'),
         ('in_consultation', 'In Consultation'), ('done', 'Done'),
         ('cancelled', 'Cancelled')],
        default='draft', required=True, tracking=True)

    reason = fields.Text(string='Reason For Visit')
    diagnosis = fields.Text()
    patient_allergies = fields.Text(
        related='patient_id.allergies', string='Known Allergies')
    prescription_ids = fields.One2many(
        'sl.hospital.prescription.line', 'appointment_id', string='Prescription')

    consultation_fee = fields.Float(tracking=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)

    @api.depends('appointment_date', 'duration')
    def _compute_end_date(self):
        for appointment in self:
            appointment.end_date = (
                appointment.appointment_date + timedelta(hours=appointment.duration)
                if appointment.appointment_date else False)

    @api.onchange('doctor_id')
    def _onchange_doctor_id(self):
        if self.doctor_id and not self.consultation_fee:
            self.consultation_fee = self.doctor_id.consultation_fee

    @api.constrains('duration')
    def _check_duration(self):
        for appointment in self:
            if appointment.duration <= 0:
                raise ValidationError(_("An appointment must last longer than zero."))

    @api.constrains('consultation_fee')
    def _check_fee(self):
        for appointment in self:
            if appointment.consultation_fee < 0:
                raise ValidationError(_("A consultation fee cannot be negative."))

    @api.constrains('doctor_id', 'appointment_date', 'duration', 'state')
    def _check_no_double_booking(self):
        """Two confirmed appointments must not overlap for one doctor.

        This is the mistake a paper diary makes and the reason to keep the
        schedule in Odoo at all.
        """
        for appointment in self.filtered(lambda a: a.state in BLOCKING_STATES):
            clash = self.search([
                ('id', '!=', appointment.id),
                ('doctor_id', '=', appointment.doctor_id.id),
                ('state', 'in', BLOCKING_STATES),
                ('appointment_date', '<', appointment.end_date),
                ('end_date', '>', appointment.appointment_date),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "%(doctor)s is already booked from %(start)s to %(end)s "
                    "for %(patient)s.") % {
                        'doctor': appointment.doctor_id.display_name,
                        'start': clash.appointment_date,
                        'end': clash.end_date,
                        'patient': clash.patient_id.display_name})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'sl.hospital.appointment') or '/'
        return super().create(vals_list)

    # -- workflow ----------------------------------------------------------

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_start(self):
        self.write({'state': 'in_consultation'})

    def action_done(self):
        for appointment in self:
            if not appointment.diagnosis:
                raise ValidationError(_(
                    "Record a diagnosis for %s before closing the appointment.")
                    % appointment.patient_id.display_name)
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})


class PrescriptionLine(models.Model):
    _name = 'sl.hospital.prescription.line'
    _description = 'Prescription Line'
    _order = 'appointment_id, sequence, id'

    sequence = fields.Integer(default=10)
    appointment_id = fields.Many2one(
        'sl.hospital.appointment', required=True, ondelete='cascade')
    medicine = fields.Char(required=True)
    dosage = fields.Char(help="For example 500 mg, twice a day.")
    duration_days = fields.Integer(string='For (days)', default=1)
    note = fields.Char()

    @api.constrains('duration_days')
    def _check_duration_days(self):
        for line in self:
            if line.duration_days < 1:
                raise ValidationError(_("A prescription must run for at least one day."))
