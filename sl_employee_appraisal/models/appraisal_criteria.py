# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AppraisalCategory(models.Model):
    _name = 'sl.appraisal.category'
    _description = 'Appraisal Category'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    criteria_ids = fields.One2many('sl.appraisal.criteria', 'category_id')
    active = fields.Boolean(default=True)


class AppraisalCriteria(models.Model):
    _name = 'sl.appraisal.criteria'
    _description = 'Appraisal Criteria'
    _order = 'category_id, sequence, name'

    name = fields.Char(string='Criterion', required=True)
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one(
        'sl.appraisal.category', string='Category', required=True, ondelete='cascade')
    weight = fields.Float(
        default=1.0, required=True,
        help="How much this criterion counts towards the final score, "
             "relative to the others.")
    description = fields.Text()
    active = fields.Boolean(default=True)

    @api.constrains('weight')
    def _check_weight(self):
        for criteria in self:
            if criteria.weight <= 0:
                raise ValidationError(_("A criterion must weigh more than zero."))

    @api.depends('name', 'category_id')
    def _compute_display_name(self):
        for criteria in self:
            criteria.display_name = '%s / %s' % (
                criteria.category_id.name or '', criteria.name or '')
