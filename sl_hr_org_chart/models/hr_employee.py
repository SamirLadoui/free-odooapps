# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# A chart deeper than this is either a very unusual company or a data problem.
MAX_DEPTH = 25


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def action_open_org_chart(self):
        """The whole tree beneath this employee, on its own page."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/sl_hr_org_chart/employee/%d' % self.id,
            'target': 'new',
        }

    @api.model
    def action_open_full_org_chart(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/sl_hr_org_chart/company',
            'target': 'new',
        }

    # -- building the tree -------------------------------------------------

    @api.model
    def _org_roots(self):
        """Everyone with no manager. These are where the chart starts."""
        return self.search([('parent_id', '=', False)], order='name')

    def _org_tree(self, seen=None, depth=0):
        """Nested dicts describing this employee and everyone beneath them.

        `seen` guards against a management cycle: somebody entered as their own
        manager, directly or through a loop, would otherwise recurse until the
        server gave up. A cycle is reported in the node rather than raised, so
        one bad record does not blank the whole chart.
        """
        self.ensure_one()
        seen = set() if seen is None else seen

        if self.id in seen:
            return {'id': self.id, 'name': self.name, 'job_title': '',
                    'department': '', 'children': [], 'cycle': True,
                    'report_count': 0}
        if depth >= MAX_DEPTH:
            return {'id': self.id, 'name': self.name,
                    'job_title': self.job_title or '',
                    'department': self.department_id.name or '',
                    'children': [], 'truncated': True, 'report_count': 0}

        seen = seen | {self.id}
        children = [child._org_tree(seen, depth + 1)
                    for child in self.child_ids.sorted('name')]
        return {
            'id': self.id,
            'name': self.name,
            'job_title': self.job_title or '',
            'department': self.department_id.name or '',
            'children': children,
            'cycle': False,
            'report_count': self._org_total_reports(children),
        }

    @api.model
    def _org_total_reports(self, children):
        """Everyone beneath a node, not just the direct reports."""
        total = 0
        for child in children:
            total += 1 + child.get('report_count', 0)
        return total

    @api.constrains('parent_id')
    def _check_no_management_cycle(self):
        """Odoo's own recursion check covers the parent chain, but a clear
        message here beats a generic one when somebody builds a loop."""
        for employee in self:
            seen, current = set(), employee
            while current.parent_id:
                if current.parent_id.id in seen or current.parent_id == employee:
                    raise ValidationError(_(
                        "%s would end up managing themselves through the "
                        "management chain.") % employee.name)
                seen.add(current.parent_id.id)
                current = current.parent_id
