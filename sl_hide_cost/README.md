# Hide Cost Price

> Keep product cost to the people who are meant to see it

Odoo already keeps the cost of a product away from portal and public users. What it has no answer for is the salesperson, the stock clerk or the shop assistant who is a perfectly ordinary internal user and has no business knowing what the company pays for what it sells. This adds a group, Show Cost Price: members see the cost as they always did, and everybody else gets a product with no cost on it at all.

## Features

- **Gone, not merely hidden** - The cost is restricted with the same mechanism Odoo itself uses for the portal, so it disappears from every form, list, kanban, export and RPC call at once.
- **No view left behind** - Because the restriction is on the field, there is no screen somebody forgot to edit where the cost quietly shows up again.
- **Template and variants** - Both are covered. Hiding the cost on the variant and leaving it on the product would be the same as not hiding it.
- **Somebody can still see it** - Settings administrators keep the group from the moment it is installed, so an installation never ends with nobody able to price anything.
- **Given out one user at a time** - Add Show Cost Price to a purchase manager or an accountant from their user form, like any other Odoo group.
- **Prices that are not cost are left alone** - The sales price and the price on a purchase order line are untouched. Hiding those breaks the work rather than protecting anything.

## Getting Started

1. Install the module.
2. Open Settings > Users and give Show Cost Price to whoever needs it.
3. Everybody else sees a product form with no cost field on it.

## Good To Know

- A restricted field is refused rather than blanked, so an export or an RPC call cannot get at it either.
- Odoo already restricted this field to internal users; this narrows the same restriction rather than adding a second mechanism on top.
- Inventory valuation reports, where they exist, are governed by their own accounting groups and are not changed here.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
