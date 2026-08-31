# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class OrgChart(http.Controller):

    def _readable(self, employees):
        """No sudo: the chart shows what this user may already see."""
        try:
            employees.read(['name'])
        except AccessError:
            raise request.not_found()
        return employees

    @http.route('/sl_hr_org_chart/company', type='http', auth='user', sitemap=False)
    def company_chart(self, **kw):
        Employee = request.env['hr.employee']
        roots = self._readable(Employee._org_roots())
        return request.render('sl_hr_org_chart.chart_page', {
            'title': request.env.company.name,
            'subtitle': '%s employee(s)' % Employee.search_count([]),
            'nodes': [root._org_tree() for root in roots],
        })

    @http.route('/sl_hr_org_chart/employee/<int:employee_id>', type='http',
                auth='user', sitemap=False)
    def employee_chart(self, employee_id, **kw):
        employee = request.env['hr.employee'].browse(employee_id).exists()
        if not employee:
            raise request.not_found()
        self._readable(employee)
        tree = employee._org_tree()
        return request.render('sl_hr_org_chart.chart_page', {
            'title': employee.name,
            'subtitle': '%s people reporting, directly or indirectly'
                        % tree['report_count'],
            'nodes': [tree],
        })
