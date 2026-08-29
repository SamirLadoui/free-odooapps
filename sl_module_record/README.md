# Configuration Recorder

> Turn What You Clicked Into An Installable Module

Configure something in the Odoo interface, then take that configuration away as a real module: a manifest and a data file of XML records, ready for version control or another database.

## Features

- **Record, Configure, Download** - Pick the models you are about to touch, press Start, go and configure anywhere in Odoo, then come back and stop. What changed is waiting for you.
- **A Real Module, Not A Dump** - The download is a proper zip with a manifest, an __init__.py and a data file of XML records, ready to drop straight into an addons path.
- **Nothing Is Patched** - Changes are found by comparing write timestamps in your window. The ORM is untouched, nothing is slowed down while you are not recording, and a recording survives a server restart.
- **Review Before You Ship** - Every captured row is listed with its model, record and whether it was created or updated. Untick anything you do not want and it stays out of the module.
- **Links That Actually Work** - A link to another record becomes a proper ref to its external ID. When the target has no external ID the link is deliberately left out, because a raw database id would point at the wrong row on another database.
- **Honest About Its Limits** - Lists of records, binary fields and Odoo's own bookkeeping fields are not exported, and the module says so rather than writing something that looks right and is not.

## Getting Started

1. Install the module and open Settings > Technical > Configuration Recorder.
2. Create a recording, name the module it will generate, and pick the models to watch.
3. Press Start Recording, make your configuration changes, then press Stop Recording.
4. Review the captured list, untick what you do not need, and press Download Module.

## Good To Know

- Read the generated XML before relying on it. This produces a very good first draft of a configuration module, not a substitute for reviewing it.
- Only the models you selected are watched, so an unrelated change made at the same time is not swept up.
- Restricted to Settings administrators.

## Supported Versions

`16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
