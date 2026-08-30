# REST API

> Read And Write Odoo From Anything That Speaks HTTP

Five predictable endpoints over any Odoo model, authenticated by an API key. Every request runs as the user the key names, with exactly that user's rights, so the API can never reach further than the person behind it.

## Features

- **The Five Endpoints You Expect** - Search, read one, create, update and delete, over any model. GET, POST, PUT and DELETE, doing what those verbs are supposed to do.
- **Paging Without Guessing** - A list response carries both the page of results and the total count, so a caller knows how far there is to go instead of fetching until it gets an empty page.
- **Keys Stored Hashed** - A key is shown once, at the moment you generate it, and only its SHA-256 hash is kept. A lost key is regenerated, never recovered, which is the only honest way to hold a secret.
- **The User's Rights, Not The Key's** - Every request runs as the user the key names, with that user's access rights and record rules. A key cannot reach anything its user could not already reach through the interface.
- **Narrow A Key Further** - Name models on a key and it can touch only those, which is how you give a warehouse scanner a key that reaches stock and nothing else. It narrows; it never widens.
- **Quiet About Failures** - Unknown, revoked and expired keys all return the same 401. A caller learns whether their key works, not why it does not.

## Getting Started

1. Install the module and open Settings > Technical > REST API Keys.
2. Create a key, name it, and choose the user it acts as.
3. Press Generate Key and copy the value immediately: it is not shown again.
4. Send it as an X-Api-Key header on your requests.

## Good To Know

- Keys can carry an expiry date and be revoked at any moment; each records its last use and call count.
- List responses are capped at 1000 records per call, defaulting to 80.
- Serve the API over HTTPS. An API key in a header is only as private as the connection carrying it.
- Odoo 15.0 is not supported: its HTTP layer classifies any request with a Content-Type of application/json as a JSON-RPC call, so a REST route cannot accept a standard JSON body there.

## Supported Versions

`16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
