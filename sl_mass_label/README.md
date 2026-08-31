# Mass Label Reporting

> Label Sheets For Any Records You Select

Select records in any list, choose a grid, and print a sheet of labels. Odoo prints product labels in a fixed layout; this prints labels for any model on a grid that matches the label paper you actually bought.

## Features

- **Any Model, Not Just Products** - Products, variants, contacts. The same wizard works anywhere, and fields a model does not have are simply left off the label.
- **The Grid Is Yours** - Set labels per row and rows per page to match your label sheets, up to 10 across and 30 down.
- **Copies Of Each** - Print ten labels for one product without selecting it ten times.
- **Reference, Barcode, Price** - Tick what belongs on the label. The barcode is printed as a real scannable Code128, not just the digits.
- **Labels That Line Up** - The last row is padded with empty cells so every label stays aligned with the sheet. Without that padding the final row stretches and each label on it prints in the wrong place.
- **Safe About Your Data** - Access rights are checked before anything is read, and records deleted between opening the wizard and printing are dropped rather than crashing the print.

## Getting Started

1. Install the module.
2. Open any product or contact list and tick the records you want.
3. Choose Print Labels from the actions menu.
4. Set the grid to match your label sheet and print.

## Good To Know

- Reference, barcode and price only appear on models that have those fields.
- Grid limits are 10 columns and 30 rows; past that the text no longer fits a label.
- The sheet is a normal Odoo PDF report, so it can be customised like any other.

## Supported Versions

`15.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
