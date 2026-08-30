# POS Stock Enhancements

> Real-time stock checks in the Point of Sale, by configurable location

Stop the Point of Sale selling what you do not have. Choose which stock
locations a Point of Sale should count, and every line added to an order is
checked against them.

## Features

- **A product with no stock is refused**, with a message naming it.
- **A quantity beyond what is left is reduced** to what is actually available,
  and the cashier is told why rather than silently corrected.
- **Quantities already on the order count** against the total, so adding the
  same product twice cannot walk past the limit.
- **Per Point of Sale.** The check is switched on per POS with its own list of
  locations: a shop counts its own shelves, a warehouse counter counts the
  warehouse.
- **Misconfiguration is caught at save.** A POS that enforces the check with no
  locations chosen is refused; without one, every product would read as out of
  stock and the module would look broken.

## Getting Started

1. Open Point of Sale > Configuration > Point of Sale and pick your POS.
2. Tick **Enforce Stock Check in POS**.
3. Choose the **Available Stock Locations** it should count.
4. Open the POS and try adding more of a product than you hold.

## Good To Know

- Only stock in the chosen locations counts; stock anywhere else is ignored.
- Every route into an order - clicking a product, scanning a barcode, typing a
  quantity - passes through the same check.
- Odoo rewrote the Point of Sale twice between 14.0 and 19.0, so this module
  carries a separate javascript implementation per generation behind one shared
  Python core.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
