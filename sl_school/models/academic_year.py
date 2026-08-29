# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AcademicYear(models.Model):
    _name = 'sl.academic.year'
    _description = 'Academic Year'
    _order = 'date_start desc, id desc'

    name = fields.Char(required=True, help="For example 2025 / 2026.")
    code = fields.Char(required=True)
    date_start = fields.Date(string='Starts On', required=True)
    date_end = fields.Date(string='Ends On', required=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Running'), ('closed', 'Closed')],
        default='draft', required=True)
    standard_ids = fields.One2many('sl.school.standard', 'academic_year_id', string='Classes')
    standard_count = fields.Integer(compute='_compute_standard_count')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'That academic year code is already used.'),
    ]

    @api.depends('standard_ids')
    def _compute_standard_count(self):
        for year in self:
            year.standard_count = len(year.standard_ids)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for year in self:
            if year.date_end <= year.date_start:
                raise ValidationError(_("An academic year must end after it starts."))

    @api.constrains('state', 'date_start', 'date_end')
    def _check_single_running_year(self):
        """Two running years at once makes 'the current class list' meaningless."""
        for year in self.filtered(lambda y: y.state == 'open'):
            clash = self.search([
                ('id', '!=', year.id),
                ('state', '=', 'open'),
                ('date_start', '<=', year.date_end),
                ('date_end', '>=', year.date_start),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "Academic year '%(clash)s' is already running over the same dates. "
                    "Close it before opening '%(year)s'.")
                    % {'clash': clash.display_name, 'year': year.display_name})

    def action_open(self):
        self.write({'state': 'open'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_view_standards(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Classes"),
            'res_model': 'sl.school.standard',
            'view_mode': 'list,form',
            'domain': [('academic_year_id', '=', self.id)],
            'context': {'default_academic_year_id': self.id},
        }
