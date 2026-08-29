# Currency Rate Update

> Daily Exchange Rates From The European Central Bank, Automatically

Keeps your currency rates current from a free public feed, on a schedule. No account, no API key, no subscription, and correct whatever currency your company trades in.

## Features

- **Free, Official Data** - Rates come from the European Central Bank's daily reference feed, either directly or through the Frankfurter JSON mirror of the same data. Neither needs registration.
- **Right For Any Company Currency** - The ECB quotes everything against the euro, but Odoo stores rates against your company currency. This module rebases the feed before writing, so a dollar or pound company gets correct figures, not euro ones.
- **Only The Currencies You Use** - List the currencies you actually deal in. Nothing else in your database is touched, and your company currency is refused outright since its rate is always one.
- **Safe To Run Twice** - Running again on the same day updates that day's rate rather than adding a second one, so a manual refresh never leaves duplicate entries behind.
- **Honest About Gaps** - A currency the feed does not quote is skipped and named in the run's result message, rather than silently written as zero or blowing up the whole update.
- **One Failure Does Not Stop The Rest** - In a scheduled run, an unreachable provider is logged and the others still complete. Every provider records the outcome and message of its last run.

## Getting Started

1. Install the module and open Settings > Currency Rates > Rate Providers.
2. Create a provider, choose the source, and list the currencies you deal in.
3. Press Update Now and check the result message.
4. Enable the Update Currency Rates scheduled action under Settings > Technical > Scheduled Actions. It ships disabled so nothing runs until you say so.

## Good To Know

- The ECB publishes on business days only, so a weekend run simply repeats Friday's rates.
- One provider per company: on a multi-company database, create one for each.
- Rates are written against the company currency of the provider's company, which is what Odoo's own conversion expects.

## Supported Versions

`18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
