# Invoice Format Editor

> Change What The Invoice Shows, From Settings

Choose which columns appear on the printed invoice, rename the headings to your house style, and add a footer note to every one. No QWeb template to override and nothing to redo at the next upgrade.

## Features

- **Columns You Choose** - Show or hide the quantity, unit price and taxes columns, and optionally print the product image on each line, from a settings page rather than a template.
- **A Guard Rail Worth Having** - Quantity and unit price cannot both be hidden. Without either, a customer has no way to check how the subtotal was reached, and that is not a layout choice but a broken invoice.
- **Your Own Headings** - Rename the description, quantity, unit price and subtotal headings to match your house style. Qty and Rate instead of Quantity and Unit Price, if that is what your customers expect.
- **Translations Still Work** - Leave a heading empty and Odoo's own wording is used, which means it stays translated. You only override the ones you actually want to change.
- **A Footer On Every Invoice** - Payment terms, a bank reference or a legal notice, printed under every invoice and maintained by the person who cares about it rather than by a developer.
- **Per Company** - Every setting belongs to a company, so a multi-company database can print differently for each without any extra work.

## Getting Started

1. Install the module and open Settings > Accounting.
2. Scroll to the Invoice Layout block.
3. Pick your columns, type any headings you want to change, and add a footer note.
4. Print an invoice to check it.

## Good To Know

- An empty heading means Odoo's default is used, so translations are preserved.
- Hiding both the quantity and the unit price is refused on purpose.
- The module changes only the printed invoice; the form view is untouched.

## Supported Versions

`19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
