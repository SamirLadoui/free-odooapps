# Login Screen Branding

> Make The Odoo Login Screen Look Like Your Company

Replace the stock Odoo login screen with your own background, logo, colours and footer text. Everything lives in Settings, so there is no template to override and nothing to redo at the next upgrade.

## Features

- **Background Image Or Colour** - Drop in a full-bleed background image, pick a plain colour, or use both so the colour shows while the image loads.
- **Readable Over Any Photo** - An optional blur is applied to the background only, never to the login card, so your form stays crisp on top of a busy photograph.
- **A Login-Only Logo** - Upload a logo used on the login screen alone. Use a full wordmark here and keep the compact company logo everywhere else.
- **Card And Button Styling** - Set the width of the login card, the height of the logo, and the colour of the primary button to match your brand.
- **Your Own Footer** - Add a line of your own under the form, such as an internal support address, and hide the Manage Databases link or the whole footer.
- **Validated Settings** - Colours are checked as hex values before they ever reach the stylesheet, and every size is range-checked, so a typo cannot break the page you log in through.

## Getting Started

1. Install the module and open Settings > General Settings.
2. Scroll to the Login Screen block and set your background, logo and colours.
3. Save, then open /web/login in a private window to see the result.

## Good To Know

- Hiding the Manage Databases link removes it from the page but does not block the route. Set list_db = False in your Odoo configuration file if you need the database manager genuinely disabled.
- The login screen is reached before you log in, so it is branded with the main company of the database.
- The background and logo are served by dedicated public routes and cached for five minutes.

## Supported Versions

`15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
