# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Patient(models.Model):
    _name = 'sl.hospital.patient'
    _description = 'Patient'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _rec_names_search = ['name', 'code', 'phone']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Patient Number', copy=False, readonly=True, default='/')
    image = fields.Image(max_width=1024, max_height=1024)
    active = fields.Boolean(default=True)

    birth_date = fields.Date(tracking=True)
    age = fields.Integer(compute='_compute_age', store=True)
    gender = fields.Selection(
        [('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    blood_group = fields.Selection(
        [('a+', 'A+'), ('a-', 'A-'), ('b+', 'B+'), ('b-', 'B-'),
         ('ab+', 'AB+'), ('ab-', 'AB-'), ('o+', 'O+'), ('o-', 'O-')])

    email = fields.Char()
    phone = fields.Char(tracking=True)
    street = fields.Char()
    city = fields.Char()
    zip = fields.Char(string='ZIP')
    country_id = fields.Many2one('res.country', string='Country')

    emergency_contact_name = fields.Char(string='Emergency Contact')
    emergency_contact_phone = fields.Char(string='Emergency Phone')

    allergies = fields.Text(help="Noted on every appointment for this patient.")
    medical_history = fields.Text()

    partner_id = fields.Many2one(
        'res.partner', string='Contact', ondelete='set null', copy=False,
        help="Created on first registration so the patient can be billed or emailed.")

    appointment_ids = fields.One2many(
        'sl.hospital.appointment', 'patient_id', string='Appointments')
    appointment_count = fields.Integer(compute='_compute_appointment_count')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for patient in self:
            patient.display_name = ('%s (%s)' % (patient.name, patient.code)
                                    if patient.code and patient.code != '/' else patient.name)

    @api.depends('birth_date')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for patient in self:
            patient.age = (relativedelta(today, patient.birth_date).years
                           if patient.birth_date else 0)

    @api.depends('appointment_ids')
    def _compute_appointment_count(self):
        for patient in self:
            patient.appointment_count = len(patient.appointment_ids)

    @api.constrains('birth_date')
    def _check_birth_date(self):
        today = fields.Date.context_today(self)
        for patient in self.filtered('birth_date'):
            if patient.birth_date > today:
                raise ValidationError(_("A patient cannot be born in the future."))

    @api.constrains('email')
    def _check_email(self):
        for patient in self.filtered('email'):
            if '@' not in patient.email:
                raise ValidationError(_("'%s' does not look like an email address.") % patient.email)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.hospital.patient') or '/'
        records = super().create(vals_list)
        for patient in records:
            if not patient.partner_id:
                patient.partner_id = patient._create_partner()
        return records

    def _create_partner(self):
        self.ensure_one()
        return self.env['res.partner'].create({
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'street': self.street,
            'city': self.city,
            'zip': self.zip,
            'country_id': self.country_id.id,
        })

    def action_view_appointments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Appointments"),
            'res_model': 'sl.hospital.appointment',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }
