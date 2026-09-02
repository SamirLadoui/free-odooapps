# Password Policy

> Complexity rules, no reuse of old passwords, and expiry

Odoo ships a minimum password length and nothing else. Every security questionnaire asks for more than that, and the usual answer is a policy written in a document that nothing enforces. This module makes the rules real: what a password has to contain, how many of the old ones are remembered, and how long one lasts.

## Features

- **What a password must contain** - A capital letter, a small letter, a digit, a symbol - any combination, each one a switch in the settings beside Odoo's own minimum length.
- **No going round in circles** - The last few passwords on an account are remembered, so the same two cannot be swapped back and forth forever.
- **Expiry, with a way back in** - Passwords can be made to expire after a number of days. Members of the Password Never Expires group are never asked, so the account that has to keep working keeps working.
- **Checked everywhere it is set** - The rules hang off the hook Odoo already has, so the user form, the change password wizard, the signup page and the reset link are all covered by the same check.
- **Nothing kept in the clear** - Previous passwords are stored as hashes, using the same hashing Odoo uses for the live password. The table can answer "you have had this one before" without being worth stealing.
- **Off until you turn it on** - Installing it changes nothing. Every rule starts at zero or off, so the policy is exactly the one you set.

## Getting Started

1. Install the module.
2. Go to Settings > General Settings and find the password blocks beside Odoo's minimum length.
3. Switch on the rules you need, and set how many passwords to remember and after how many days one expires.
4. Add anybody who must never be locked out to the Password Never Expires group.

## Good To Know

- Turning expiry on does not lock out existing users: a password with no recorded change date counts as fresh until it is next changed.
- An expired password is refused at login with a message pointing at the Reset password link.
- Odoo's own minimum length setting still applies and is unchanged.
- Nothing is checked for a password Odoo itself does not set, such as one written straight into the database.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
