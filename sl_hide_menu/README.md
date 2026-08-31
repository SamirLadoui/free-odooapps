# Hide Menus Per User

> A Tidier Interface, Not A Security Control

Pick the menus a particular user does not need and they disappear from their interface. Per user, reversible, and honest about what it is: a way to make a cluttered Odoo manageable, not a way to keep anyone out of anything.

## Features

- **Hiding A Parent Takes Its Children** - Hide a top-level menu and everything beneath it goes too. Otherwise the sub-menus are left stranded in the app switcher with no route back, which is worse than leaving the branch alone.
- **Per User** - Tidying one person's interface never touches anybody else's. Two people in the same group can have completely different menus.
- **Reversible In One Click** - Untick a menu and it comes straight back. Nothing is deleted, nothing is archived, and no configuration is destroyed.
- **Set Where You Already Manage Users** - The list sits on the user's own Access Rights tab, beside the groups, which is where anyone looking for it will go first.
- **Honest About Its Limits** - This removes menus from the interface and nothing else. The user keeps every access right they had, and anything reachable by a direct link, a related record or the API is still reachable.

## Getting Started

1. Install the module and open Settings > Users.
2. Open a user and go to the Access Rights tab.
3. Add the menus they should not see under Hidden Menus.
4. They will see the change next time their interface loads.

## Good To Know

- This is not a security feature. If somebody must genuinely not see data, change their groups or add a record rule.
- Hiding a parent hides its whole branch; hiding a child leaves the parent visible.
- Nothing is deleted: unticking restores the menu exactly as it was.

## Supported Versions

`18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
