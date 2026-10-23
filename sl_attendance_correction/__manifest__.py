# Copyright 2026 Samir Ladoui
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
{  # noqa: B018 -- Odoo manifests are literal dictionaries.
    'name': 'Attendance Correction Requests',
    'version': '19.0.1.0.0',
    'summary': 'Employee attendance corrections with a protected manager decision',
    'description': '''
Internal employees request corrections to their own attendance or a missing
closed shift. Native attendance approvers make a single decision, with protected
submission originals, frozen proposals and an immutable decision trail.
Approval uses the approver's native attendance rights. No device-log rewriting,
portal, payroll workflow, scheduled jobs or paid dependencies are added.
''',
    'category': 'Human Resources/Attendances',
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['hr_attendance'],
    'data': ['security/ir.model.access.csv', 'security/attendance_correction_security.xml',
             'views/attendance_correction_views.xml'],
    'images': ['static/description/banner.png'],
    'application': True,
    'installable': True,
    'auto_install': False,
}
