# -*- coding: utf-8 -*-
{
    'name': 'Employee Appraisal',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Periodic employee appraisals with weighted criteria and a real score',
    'description': """
Employee Appraisal
==================

Run appraisals against criteria you define, and get a score that reflects what
your organisation actually cares about.

Weighted, not averaged
----------------------
Every criterion carries a weight. If quality matters three times as much as
punctuality, say so once and every appraisal reflects it. The score is a
weighted average out of five, shown as a percentage too.

Criteria that are not yet rated are **ignored**, not counted as zero, so a
half-finished appraisal does not read as a bad one.

A workflow that holds
---------------------
Draft, in progress, done. Starting an appraisal loads every active criterion
ready to rate, and it cannot be completed while anything is still unrated - so
you never end up with a score based on half the questions.

One per employee per period
---------------------------
Overlapping appraisals for the same employee are refused, because two competing
reviews of the same six months make the history meaningless. Cancelling one
frees the period again.

Also
----
* Criteria grouped into categories, ordered as you like.
* A per-line weight override, for the appraisal where one thing mattered more.
* Strengths, areas to improve, and the employee's own comment.
* An Appraisals button and the last score on the employee form.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/appraisal_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
