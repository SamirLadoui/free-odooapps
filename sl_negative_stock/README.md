# Block Negative Stock

> Draw the line where it matters, and leave the rest of Odoo alone

Odoo lets stock go negative everywhere, on purpose: a shop that receives goods after it sells them could not trade otherwise. The cost is that a genuine picking mistake in a warehouse looks exactly like the intended behaviour in a shop, and nobody finds it until a stock count. This module lets you say where going below zero is refused, where it is merely worth recording, and where nothing should change at all.

## Features

- **Rules, not a switch** - A rule names a location, and optionally products or categories. Everywhere without a rule behaves exactly as Odoo always did.
- **Refuse or record** - Refusing the move is right in a warehouse that counts. Allowing it and writing it on the transfer is right where going under is normal but worth knowing about.
- **Checked when stock leaves** - The check runs when the transfer is validated, not when it is planned. A move created today for next week is never refused because the goods have not arrived yet.
- **On hand, not forecast** - A forecast counts what is expected to arrive. Stock that has not arrived cannot be picked off a shelf, so the quantity on hand is what is compared.
- **A rule covers its shelves** - A rule on a warehouse applies to every location under it by default, so you write one rule instead of one per shelf. It can be told not to.
- **Order decides** - Two rules about the same location is a question the sequence answers: the first rule that fits is the one applied, so a narrow exception can sit above a broad rule.

## Getting Started

1. Install the module. Nothing changes until you write a rule.
2. Go to Inventory > Configuration > Negative Stock Rules.
3. Create a rule, pick the location it covers, and choose whether to refuse the move or record it.
4. Leave Products and Categories empty to cover everything at that location, or name the ones that matter.

## Good To Know

- Receipts and returns are never refused: stock arriving is not coming off anybody's shelf.
- Only internal locations are checked. Suppliers, customers, scrap and inventory-adjustment locations are left alone.
- Services and non-storable products are skipped, since they have no quantity to go under.
- Rules are per company, and a rule cannot point at another company's location.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
