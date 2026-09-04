# -*- coding: utf-8 -*-
{
    'name': 'PDF Watermark',
    'version': '14.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Print DRAFT, PAID or anything else across a document',
    'description': """
PDF Watermark
=============

A quotation printed for discussion and a quotation that has been accepted look
identical on paper. So do a paid invoice and an unpaid one. People find out
which one they were holding after they have already acted on it.

A rule says: for this kind of document, in this state, print this word behind
the text.

Behind the page, not in it
--------------------------
The watermark is drawn as an image tiled behind the page rather than a line of
text dropped into the layout, so it cannot push content down, cannot break a
table across a page boundary, and repeats down a long document.

Any document, any condition
---------------------------
Rules are written against a model and a domain, so DRAFT on unposted invoices,
PAID on settled ones and CANCELLED on cancelled orders are three rules and no
code. The first rule that fits is the one used, so a narrow exception can sit
above a broad rule.

Yours to look at
----------------
The word, its colour, how faint it is, the angle and the size are all on the
rule, so it can be a red DRAFT or a grey COPY without touching a template.

Nothing changes until you say so
--------------------------------
With no rules, every document prints exactly as it did before, and carries no
trace of this module at all.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'views/watermark_views.xml',
        'views/report_templates.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
