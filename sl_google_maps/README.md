# Google Maps Integration

> Address Autocomplete, And Your Contacts On A Map

Start typing an address and Google finishes it, coordinates included. Then see any contact, or a whole selection of them, on a real map inside Odoo. And it still does something useful before you have an API key.

## Features

- **Addresses That Type Themselves** - Start typing on a contact and Google offers suggestions. Pick one and the street, city, postcode, state, country and coordinates are all filled in. No mistyped postcodes, and no contacts that cannot be found on a map later.
- **Use It On Your Own Models** - The autocomplete is a normal field widget. Put widget="sl_places_autocomplete" on any Char field in any model and it works there too.
- **One Contact On A Map** - A Show on Map button on the contact form opens it on a map inside Odoo, with a directions link ready to hand to a driver.
- **A Whole Selection At Once** - Select contacts in the list and pick Show on Map from the Action menu. You get one interactive map of all of them, with clickable markers that link straight back to each record.
- **Useful Before You Have A Key** - With no API key configured nothing breaks. The address field stays an ordinary input and the map buttons open google.com/maps, which needs no key. Add a key later and the same buttons start embedding maps.
- **Codes Resolved Properly** - Google returns countries and states as ISO codes. Those are matched against your own Odoo country and state records on the server, so a state is never guessed at or created by accident.

## Getting Started

1. Install the module and open Settings > General Settings > Google Maps.
2. Paste a browser API key with the Maps JavaScript API and Places API enabled.
3. Open any contact and start typing in the street field to see suggestions.
4. Select several contacts in the list and use Show on Map in the Action menu.

## Good To Know

- A Maps browser key is sent to Google by the visitor's browser, so it is public by design. Restrict it by HTTP referrer in the Google console.
- The key is only exposed to internal users, never to portal or public visitors.
- Markers on the multi-contact map need coordinates. Autocompleted addresses get them automatically; contacts entered by hand can be geocoded with Odoo's own Geolocalize feature.
- Everything server-side is covered by the module's tests. The autocomplete itself talks to Google from the browser, so it needs a real key to try.

## Supported Versions

`16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
