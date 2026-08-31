# -*- coding: utf-8 -*-
{
    'name': 'Organisation Chart',
    'version': '14.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'The whole reporting structure on one printable page',
    'description': """
Organisation Chart
==================

Odoo shows you an employee's manager and their direct reports. That is useful
when you are looking at one person, and useless when somebody asks what the
company actually looks like.

This renders the whole tree.

* **Organisation Chart** under Employees draws every reporting line at once,
  starting from everybody who has no manager.
* An **Org Chart** button on any employee draws the subtree beneath just that
  person, which is what you want when a department has four hundred people in it.
* Each person shows how many people sit beneath them **in total**, not just
  their direct reports.

Built to survive your data
--------------------------
If somebody ends up managing themselves through the chain, the chart marks that
node and carries on instead of recursing until the server gives up. One bad
record does not blank the page. Creating such a loop through the interface is
refused outright, with a message naming the person.

Built to print
--------------
A Print button and a print stylesheet, because an org chart's most common
destination is a wall.

No javascript
-------------
Nested lists and CSS connector lines. Nothing to load, nothing to conflict with,
and nothing to break at the next upgrade.

The chart shows only the employees the logged-in user can already see. There is
no elevation of privilege anywhere in it.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['hr'],
    'data': [
        'views/org_chart_templates.xml',
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'sl_hr_org_chart/static/src/css/org_chart.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
