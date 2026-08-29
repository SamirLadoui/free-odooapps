# Standard Accounting Report

> General Ledger, Trial Balance And Partner Ledger, As PDF Or Excel

The three reports every accountant asks for on day one, with the filters they actually use. Opening balances are computed properly, so the closing figure on the page is the real one.

## Features

- **General Ledger** - Every account with its opening balance and each entry in the period beneath it, showing date, entry number, journal, label and whether the line is reconciled.
- **Trial Balance** - One summary line per account: opening, debit, credit and closing balance, with totals that balance.
- **Partner Ledger** - The same detail split by partner as well as by account, which is what you need when you are chasing a specific customer's balance.
- **Opening Balances Done Properly** - Everything dated before the period start is summed into an opening balance rather than dropped or mixed into the period. An account with an opening balance and no movement still appears when you asked for it.
- **The Filters You Use** - Date range, posted only or posted plus draft, and any combination of journals, accounts and partners. Choose whether to show accounts with movement, with a non-zero balance, or all of them.
- **PDF Or Spreadsheet** - PDF through Odoo's own report engine, so it picks up your layout, header and paper format. Excel with a frozen header row, ready to sort and pivot.

## Getting Started

1. Install the module.
2. Go to Accounting > Reporting > Standard Reports.
3. Pick the report, the period and any filters, then press Print PDF or Export Excel.

## Good To Know

- Draft entries are excluded unless you explicitly ask for them, so the default output matches your posted books.
- Access follows Odoo's own accounting groups: anyone who can read accounting can run the reports.
- Excel export requires the xlsxwriter Python package, which ships with a standard Odoo install.

## Supported Versions

`15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
