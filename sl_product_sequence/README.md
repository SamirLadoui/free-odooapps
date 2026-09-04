# Product Reference Numbering

> Give products an internal reference from a sequence

The internal reference is what everyone types into a search box, reads down the phone and writes on a shelf label. Odoo leaves it blank and lets people invent one per product, which is how a catalogue ends up holding CH-001, ch002 and "Chair 3" by the end of the month. A sequence settles it: point a product category at one and everything created in it is numbered as it is created.

## Features

- **Numbered as they are created** - A product created in a numbered category gets its reference immediately, with no extra step for anyone to forget.
- **Categories inherit** - A category with no numbering of its own uses the nearest parent that has one, so one sequence on Furniture covers everything beneath it.
- **A company-wide fallback** - Anything outside a numbered category falls back to the company's own sequence, so nothing is left unnumbered by accident.
- **What you typed is kept** - A reference entered by hand is never overwritten, and does not consume a number either. A manufacturer's part number is worth more than one we invented.
- **The products already there** - Select the ones that predate the numbering and assign in one go. The ones that already have a reference are skipped.
- **Off until you point it somewhere** - A sequence is provided, attached to nothing. Until a category or the company points at one, products are created exactly as before.

## Getting Started

1. Install the module.
2. Open a product category and set its Reference Numbering, or set the company default under Settings > Companies.
3. Create a product: it is numbered as it is saved.
4. For the products that came before, select them in the list and choose Assign References.

## Good To Know

- The prefix, padding and next number all live on the sequence itself, so they are changed where Odoo already keeps such things.
- Numbering is per template, which is where Odoo keeps the internal reference; variants inherit it as they always did.
- Nothing enforces uniqueness that Odoo does not already enforce.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
