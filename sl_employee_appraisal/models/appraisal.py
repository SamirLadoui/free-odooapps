# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

RATINGS = [
    ('1', 'Needs Improvement'),
    ('2', 'Below Expectations'),
    ('3', 'Meets Expectations'),
    ('4', 'Exceeds Expectations'),
    ('5', 'Outstanding'),
]
MAX_RATING = 5.0


class Appraisal(models.Model):
    _name = 'sl.appraisal'
    _description = 'Employee Appraisal'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_close desc, id desc'
    _rec_name = 'code'

    code = fields.Char(string='Reference', copy=False, readonly=True, default='/')
    employee_id = fields.Many2one(
        'hr.employee', required=True, ondelete='restrict', tracking=True)
    manager_id = fields.Many2one(
        'hr.employee', string='Appraised By', tracking=True,
        help="Defaults to the employee's manager.")
    department_id = fields.Many2one(
        related='employee_id.department_id', store=True)
    job_title = fields.Char(related='employee_id.job_title', store=True)

    date_start = fields.Date(string='Period From', required=True)
    date_end = fields.Date(string='Period To', required=True)
    date_close = fields.Date(string='Completed On', readonly=True, copy=False)

    state = fields.Selection(
        [('draft', 'Draft'), ('in_progress', 'In Progress'),
         ('done', 'Done'), ('cancelled', 'Cancelled')],
        default='draft', required=True, tracking=True)

    line_ids = fields.One2many('sl.appraisal.line', 'appraisal_id', string='Assessment')
    score = fields.Float(
        compute='_compute_score', store=True, tracking=True,
        help="Weighted average of the rated criteria, out of 5.")
    score_percent = fields.Float(compute='_compute_score', store=True)
    rated_count = fields.Integer(compute='_compute_score', store=True)

    strengths = fields.Text()
    improvements = fields.Text(string='Areas To Improve')
    employee_comment = fields.Text(string="Employee's Comment")
    company_id = fields.Many2one('res.company', related='employee_id.company_id', store=True)

    @api.depends('line_ids.rating', 'line_ids.weight')
    def _compute_score(self):
        """Weighted average over the criteria that were actually rated.

        Unrated lines are ignored rather than counted as zero: a half-finished
        appraisal should not read as a bad one.
        """
        for appraisal in self:
            rated = appraisal.line_ids.filtered('rating')
            total_weight = sum(rated.mapped('weight'))
            appraisal.rated_count = len(rated)
            if not total_weight:
                appraisal.score = 0.0
                appraisal.score_percent = 0.0
                continue
            weighted = sum(float(line.rating) * line.weight for line in rated)
            appraisal.score = weighted / total_weight
            appraisal.score_percent = (appraisal.score / MAX_RATING) * 100

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for appraisal in self:
            if appraisal.date_end < appraisal.date_start:
                raise ValidationError(_("The period ends before it starts."))

    @api.constrains('employee_id', 'date_start', 'date_end', 'state')
    def _check_no_overlap(self):
        """One appraisal per employee per period, or the history stops meaning
        anything."""
        for appraisal in self.filtered(lambda a: a.state != 'cancelled'):
            clash = self.search([
                ('id', '!=', appraisal.id),
                ('employee_id', '=', appraisal.employee_id.id),
                ('state', '!=', 'cancelled'),
                ('date_start', '<=', appraisal.date_end),
                ('date_end', '>=', appraisal.date_start),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "%(employee)s already has an appraisal covering "
                    "%(start)s to %(end)s.") % {
                        'employee': appraisal.employee_id.name,
                        'start': clash.date_start, 'end': clash.date_end})

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and not self.manager_id:
            self.manager_id = self.employee_id.parent_id

    @api.depends('code', 'employee_id')
    def _compute_display_name(self):
        for appraisal in self:
            appraisal.display_name = '%s - %s' % (
                appraisal.code or '/', appraisal.employee_id.name or '')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.appraisal') or '/'
        return super().create(vals_list)

    # -- workflow ----------------------------------------------------------

    def action_load_criteria(self):
        """Fill the assessment with every active criterion, at its own weight."""
        self.ensure_one()
        existing = self.line_ids.mapped('criteria_id')
        criteria = self.env['sl.appraisal.criteria'].search([])
        missing = criteria - existing
        self.line_ids = [(0, 0, {
            'criteria_id': criterion.id,
            'weight': criterion.weight,
        }) for criterion in missing]
        return True

    def action_start(self):
        for appraisal in self:
            if not appraisal.line_ids:
                appraisal.action_load_criteria()
        self.write({'state': 'in_progress'})

    def action_done(self):
        for appraisal in self:
            unrated = appraisal.line_ids.filtered(lambda l: not l.rating)
            if unrated:
                raise ValidationError(_(
                    "%(count)s criteria are still unrated for %(employee)s.") % {
                        'count': len(unrated), 'employee': appraisal.employee_id.name})
        self.write({'state': 'done', 'date_close': fields.Date.context_today(self)})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft', 'date_close': False})


class AppraisalLine(models.Model):
    _name = 'sl.appraisal.line'
    _description = 'Appraisal Line'
    _order = 'appraisal_id, sequence, id'

    sequence = fields.Integer(default=10)
    appraisal_id = fields.Many2one('sl.appraisal', required=True, ondelete='cascade')
    criteria_id = fields.Many2one(
        'sl.appraisal.criteria', string='Criterion', required=True, ondelete='restrict')
    category_id = fields.Many2one(related='criteria_id.category_id', store=True)
    weight = fields.Float(default=1.0, required=True)
    rating = fields.Selection(RATINGS)
    comment = fields.Char()

    @api.constrains('weight')
    def _check_weight(self):
        for line in self:
            if line.weight <= 0:
                raise ValidationError(_("A line must weigh more than zero."))

    @api.constrains('criteria_id', 'appraisal_id')
    def _check_criteria_once(self):
        for line in self:
            twin = self.search([
                ('id', '!=', line.id),
                ('appraisal_id', '=', line.appraisal_id.id),
                ('criteria_id', '=', line.criteria_id.id),
            ], limit=1)
            if twin:
                raise ValidationError(_(
                    "'%s' is already on this appraisal.") % line.criteria_id.display_name)

    @api.onchange('criteria_id')
    def _onchange_criteria_id(self):
        if self.criteria_id:
            self.weight = self.criteria_id.weight
