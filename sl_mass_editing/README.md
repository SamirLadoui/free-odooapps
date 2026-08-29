# Mass Editing

> Change The Same Fields On Many Records At Once

Select a hundred records in any list view and update the same fields on all of them in one step. An administrator decides which fields a bulk edit may touch; users get a form limited to exactly those, straight from the Action menu.

## Features

- **No Code, No Server Action** - Pick a model, tick the fields that may be changed, save. The entry appears in that model's Action menu immediately, with no developer involved.
- **Set Or Clear Any Field** - Text, numbers, dates, yes/no, selections and links to other records. Choose Set to give a new value, or Clear to empty the field on every selected record.
- **Add And Remove Tags** - On tag-style fields you can add or remove one linked record without disturbing the others. Stack several lines to add several tags in the same pass.
- **The Field List Is Enforced** - The configured field list is a real boundary checked on the server, not just a filter in the form. A request naming any other field is rejected rather than quietly applied.
- **Your Own Access Rights Still Apply** - Records are written as the user who pressed Apply, with no elevation of privilege, so nobody can bulk edit what they could not edit one at a time.
- **Typos Caught Before They Land** - Selection values are checked against the field's real options, and a record chosen for the wrong kind of link is refused, so a mistake stops at the form instead of breaking records.

## Getting Started

1. Install the module and open Settings > Technical > Bulk Edits.
2. Create one: choose the model, then tick the fields it may change.
3. Go to that model's list view, select some records, and open the Action menu.
4. Pick your bulk edit, add the changes you want, and press Apply.

## Good To Know

- Odoo's own bookkeeping fields, such as create date and write user, can never be added to a bulk edit.
- The form tells you how many records are about to change and asks for confirmation. There is no undo, so check the count.
- Archiving a bulk edit removes its entry from the Action menu; restoring it puts it back.

## Supported Versions

`16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
