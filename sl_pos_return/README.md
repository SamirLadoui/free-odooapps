# Product Return In POS

> Give Items Back Against A Past Receipt

A customer comes back with a receipt and two of the four things they bought. The cashier types the receipt number, and what is still returnable is put on the order as a refund, recorded against the original sale.

## Features

- **Find It However It Was Printed** - The order is matched on the receipt reference or the order name, because which one your receipts show depends on how the shop is set up.
- **Only What Is Left** - Bring three of five back today and two of five next week, and the till offers two, not five. Returns accumulate across visits so the same unit cannot be refunded twice.
- **Recorded Against The Sale** - A return is an ordinary point of sale order with negative quantities, the way the point of sale already records a refund, linked back to the order it came from.
- **Nonsense Is Refused** - A return cannot itself be returned, and an order cannot be a return of itself. Both are stopped rather than quietly producing a broken record.
- **The Till Cannot Overshoot** - The server decides what is returnable, so however the lines are edited at the till, a cashier cannot give back more than was bought.
- **Per Point Of Sale** - Turned on for the tills that take returns. A shop that sends customers to the counter instead does not get the button.

## Getting Started

1. Install the module and open Point of Sale settings.
2. Under PoS Interface, tick Allow Returns for each till that takes them.
3. Open a session, use Return, and type the receipt number.

## Good To Know

- Returned lines arrive as everything still returnable; the cashier trims quantities with the ordinary numpad.
- A product removed from the point of sale since the sale is skipped rather than blocking the whole return.
- The link to the original order is visible on the order form in the back office.

## Supported Versions

`16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
