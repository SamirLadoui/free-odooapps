# Organisation Chart

> The Whole Company On One Page

Odoo shows you an employee's manager and their direct reports. This gives you the entire tree: every root, every branch, on one printable page, and the subtree beneath any single person.

## Features

- **The Whole Tree, Not A Neighbourhood** - Odoo's own chart shows one employee's immediate surroundings. This renders every reporting line in the company at once, starting from everyone who has no manager.
- **Any Subtree On Demand** - An Org Chart button on every employee opens the tree beneath just that person, which is what you actually want when a department has four hundred people in it.
- **Counts That Mean Something** - Each person shows how many people sit beneath them in total, not just their direct reports. That is the number that tells you the shape of the organisation.
- **Survives Bad Data** - If somebody ends up managing themselves through the chain, the chart marks that node and carries on rather than recursing until the server gives up. One bad record does not blank the page.
- **Built To Print** - A Print button and a print stylesheet, because an org chart's most common destination is a wall.
- **No Javascript** - Nested lists and CSS connector lines. Nothing to load, nothing to break at the next upgrade, and it renders the same in every browser.

## Getting Started

1. Install the module and open Employees > Organisation Chart.
2. Or open any employee and press the Org Chart button for their subtree.
3. Press Print to put it on a wall.

## Good To Know

- The chart shows only employees the logged-in user can already see; there is no elevation of privilege.
- An employee who would end up managing themselves is refused at entry, with a message naming them.
- Very deep charts are truncated at 25 levels, which in practice means the data is wrong rather than the company being that tall.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
