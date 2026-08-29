# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Doctor(models.Model):
    _name = 'sl.hospital.doctor'
    _description = 'Doctor'
    _inherit = ['mail.thread']
    _order = 'name'
    _rec_names_search = ['name', 'code']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Doctor Number', copy=False, readonly=True, default='/')
    image = fields.Image(max_width=1024, max_height=1024)
    active = fields.Boolean(default=True)

    department_id = fields.Many2one(
        'sl.hospital.department', string='Department', tracking=True)
    specialisation = fields.Char()
    qualification = fields.Char()
    licence_number = fields.Char(string='Licence Number')

    email = fields.Char(tracking=True)
    phone = fields.Char()
    user_id = fields.Many2one(
        'res.users', string='Odoo User', ondelete='set null',
        help="Link the doctor to a login so they can see their own appointments.")

    consultation_fee = fields.Float(default=0.0)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)

    appointment_ids = fields.One2many(
        'sl.hospital.appointment', 'doctor_id', string='Appointments')
    appointment_count = fields.Integer(compute='_compute_appointment_count')

    @api.constrains('licence_number')
    def _check_licence_unique(self):
        """A python constraint rather than _sql_constraints: 19.0 dropped
        support for the latter and would silently create no constraint."""
        for doctor in self.filtered('licence_number'):
            if self.search_count([('id', '!=', doctor.id),
                                  ('licence_number', '=', doctor.licence_number)]):
                raise ValidationError(_(
                    "Licence number '%s' is already registered to another doctor.")
                    % doctor.licence_number)

    @api.depends('appointment_ids')
    def _compute_appointment_count(self):
        for doctor in self:
            doctor.appointment_count = len(doctor.appointment_ids)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for doctor in self:
            doctor.display_name = 'Dr. %s' % doctor.name if doctor.name else ''

    @api.constrains('email')
    def _check_email(self):
        for doctor in self.filtered('email'):
            if '@' not in doctor.email:
                raise ValidationError(_("'%s' does not look like an email address.") % doctor.email)

    @api.constrains('consultation_fee')
    def _check_fee(self):
        for doctor in self:
            if doctor.consultation_fee < 0:
                raise ValidationError(_("A consultation fee cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.hospital.doctor') or '/'
        return super().create(vals_list)

    def action_view_appointments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Appointments"),
            'res_model': 'sl.hospital.appointment',
            'view_mode': 'list,form',
            'domain': [('doctor_id', '=', self.id)],
            'context': {'default_doctor_id': self.id},
        }
