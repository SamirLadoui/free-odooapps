# Read Only User

> One group that lets a user see everything and change nothing

The auditor, the accountant's assistant, the owner who wants to look at the numbers without the risk of nudging one. Odoo can express this only by going through every model in the access rights table and unticking three boxes on each, which nobody finishes and nobody maintains afterwards. This is one group instead.

## Features

- **One tick box** - Give a user the Read Only group and every create, write and delete is refused, on every model, whatever the access rights say.
- **Nothing to route around** - The check sits where Odoo already asks whether an operation is allowed, so the web client, an import, an automated action and an XML-RPC call all pass through the same refusal.
- **They keep what they could see** - Their other groups still decide what they can look at. This decides only what they can change.
- **Their own preferences still work** - Language, timezone, signature and password are handled by Odoo itself and keep working, which is the one thing a read-only account genuinely needs.
- **It cannot undo itself** - Giving themselves another group goes through the same refusal as anything else, so a read-only account cannot quietly stop being one.
- **The server is unaffected** - Code running as superuser - logging in, scheduled actions, the client's own housekeeping - is untouched, because refusing that breaks the session rather than protecting anything.

## Getting Started

1. Install the module.
2. Open Settings > Users, pick the user, and tick Read Only.
3. Leave their other groups exactly as they are: those still decide what the account can see.

## Good To Know

- A read-only account can still run reports and export what it is allowed to read.
- The refusal message says the account is read-only, so the user is not left guessing at an access rights problem.
- Handful of models the web client writes to purely to function - what it remembers per user, presence, read receipts - are left alone, since refusing those protects no data and breaks every page.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
