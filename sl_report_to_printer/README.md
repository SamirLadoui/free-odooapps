# Report to Printer

> Press Print And The Paper Comes Out

Send Odoo reports straight to a CUPS printer instead of downloading a PDF and opening it yourself. Which printer, and whether to print at all, is decided by a clear order of precedence you control.

## Features

- **Most Specific Wins** - The report decides first, then the user, then the company. Delivery slips can always go to the warehouse label printer while everything else follows the person printing it.
- **Never Prints Into The Void** - A report set to print with no printer configured anywhere falls back to a normal download. Silently printing nowhere is worse than a PDF you can actually see.
- **Pull In Your Queues** - Add a CUPS server and press Update Printers. Every queue arrives with its make and model, location and live status. Running it again refreshes them instead of creating duplicates.
- **One Default, Enforced** - A single printer can be marked the default and the module refuses a second one, so the last-resort choice is never ambiguous.
- **Prove It Before You Rely On It** - A Print Test Page button on every printer, so a new queue is confirmed working before someone depends on it during a busy morning.
- **Users Choose For Themselves** - Each user picks their own printer and whether their reports print or download, from their own preferences page. No administrator needed.

## Getting Started

1. Install pycups on the Odoo server: pip install pycups
2. Install the module and open Settings > Printing > Print Servers.
3. Add your CUPS server and press Test Connection, then Update Printers.
4. Mark one printer as the default, then print a test page.
5. Set the company behaviour to Send to a printer, and override per report or per user where needed.

## Good To Know

- Odoo talks to CUPS, so the printer must be a queue the Odoo server itself can reach, not one attached to the user's own computer.
- Without pycups the module still installs and configures cleanly, and tells you exactly what is missing the first time you try to print.
- Only PDF reports are sent to printers; other report types download as usual.

## Supported Versions

`17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
