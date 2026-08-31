# Web Digital Signature

> Capture A Hand-Drawn Signature On Any Record, With A Full Audit Trail

Mark any model as signable and a Sign this record entry appears in its Action menu. Users draw a signature, and Odoo keeps a permanent record of who signed, when, and from where.

## Features

- **Any Model, No Development** - An administrator ticks a model and names the menu entry. The signing action appears in that model's list and form views immediately, with no code and no custom fields.
- **A Real Audit Trail** - Every signature keeps the signer's name and email, the image itself, the exact timestamp, the originating IP address, and which Odoo user captured it. None of it is editable afterwards.
- **The Signature Travels With The Record** - A PNG copy is attached to the signed record, so it goes wherever the record goes: into exports, into emails, into the customer's copy.
- **Noted In The Chatter** - Signing posts a line in the record's own chatter naming the signer and the date, so the history reads correctly without opening another screen.
- **Write Access Required** - Someone who cannot edit a record cannot sign it. Signing is checked against normal Odoo access rights, not just hidden from the menu.
- **Outlives The Record** - The log survives deletion of the record it refers to. Entries show the record as deleted rather than vanishing, which is the whole point of keeping one.

## Getting Started

1. Install the module and open Settings > Signatures > Signable Models.
2. Add the models you want signable and, if you like, a default purpose.
3. Go to one of those models, select a record, and use Sign this record in the Action menu.
4. Review everything captured under Settings > Signatures > Captured Signatures.

## Good To Know

- Signatures are read-only for ordinary users; only Settings administrators can amend or delete them.
- The IP address is recorded for the audit trail only and is never used to grant or deny access.
- Several records can be signed in one pass: each gets its own signature record and its own attachment.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
