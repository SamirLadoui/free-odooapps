# -*- coding: utf-8 -*-
{
    'name': 'Currency Rate Update',
    'version': '15.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Fetch daily exchange rates automatically from the European Central Bank',
    'description': """
Currency Rate Update
====================

Keeps ``res.currency.rate`` up to date from a free public feed, on a schedule.
No account, no API key, no subscription.

Providers
---------
* **European Central Bank** - the official daily reference feed.
* **Frankfurter** - the same ECB data served as JSON.

Correct for any company currency
--------------------------------
The ECB quotes everything against the euro. Odoo stores rates as *units of the
foreign currency per one unit of the company currency*, so a company trading in
dollars or pounds needs the feed re-expressed against its own currency. This
module does that rebasing before writing anything, so the figures are right
whatever your company currency is - not only for euro companies.

Behaviour
---------
* One provider per company, with an explicit list of the currencies you deal in.
  Nothing else is touched.
* Running twice in a day updates that day's rate instead of adding a second one.
* A currency the feed does not quote is skipped and noted, not treated as an error.
* One unreachable provider does not stop the others in the same scheduled run.
* Every run records its outcome and message on the provider.

The **Update Currency Rates** scheduled action ships disabled. Enable it once you
have pressed *Update Now* and confirmed the result.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/currency_rate_provider_views.xml',
    ],
    'external_dependencies': {'python': ['requests', 'lxml']},
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
