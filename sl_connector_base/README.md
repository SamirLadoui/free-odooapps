# Connector Base

> The shared half of any integration: links, log and retries

Connecting Odoo to something else is mostly not about the something else. It is retries, back-off, timeouts, knowing what was already imported, and being able to say afterwards what happened. Every integration writes that part again, slightly differently, and gets it slightly wrong. This is that part, written once.

## Features

- **The link table** - Which Odoo record is which record over there, stored rather than guessed at. Without it the second sync creates a second copy of everything.
- **Matching that does not drift** - Names change and references get edited, so an integration that re-identifies records by matching text will eventually match the wrong ones. The link is written once and kept.
- **A log that cannot be rewritten** - Every run leaves a line, and failures carry the message the other side actually sent rather than a paraphrase. A record of what happened that somebody can edit is not a record of what happened.
- **Asking politely** - Requests are retried when the answer says it is worth retrying - a 429, a 502, a dropped connection - and left alone when it is not, because asking again will not turn a 401 into a 200.
- **Testable without the other side** - Every real HTTP call goes through one method, so an integration built on this can be tested against recorded answers rather than a live service and a working network.
- **Yours to build on** - Inherit sl.connector.backend and the transport, the logging and the mapping helpers are already there.

## Getting Started

1. Install the module. On its own it adds a link table and a log, and nothing else.
2. Install a connector that uses it, or inherit sl.connector.backend in your own code.
3. Watch Settings > Technical > Connectors for what the syncs are doing.

## Good To Know

- Old log lines are pruned weekly by a scheduled action, which you can turn off or re-time.
- The link table is deliberately not tied to any particular connector, so one table serves all of them.
- Nothing here talks to any service by itself; it is the shared machinery a connector uses.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
