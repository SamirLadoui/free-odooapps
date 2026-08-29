# -*- coding: utf-8 -*-
{
    'name': 'Google Maps Integration',
    'version': '17.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Google Places address autocomplete, and your contacts on a map',
    'description': """
Google Maps Integration
=======================

Two things, both where you already work.

Address autocomplete
--------------------
Start typing an address on a contact and Google offers suggestions. Pick one and
the street, city, postcode, state, country **and coordinates** are filled in for
you. No more mistyped postcodes, and no more contacts that cannot be found on a
map later.

The widget is available as ``widget="sl_places_autocomplete"`` on any Char
field, so you can put it on your own models too.

Your contacts on a map
----------------------
* **Show on Map** on a contact opens it on a map inside Odoo.
* Select several contacts in the list, then **Show on Map** in the Action menu,
  and you get one interactive map of all of them: markers you can click, each
  linking straight back to its record.

Works before you have a key
---------------------------
No API key configured? Nothing breaks. The address field stays an ordinary text
input, and the map buttons open google.com/maps in a new tab, which needs no key
at all. Add a key later and the same buttons start embedding maps in Odoo.

Setup
-----
Settings > General Settings > Google Maps. Paste a browser key with the **Maps
JavaScript API** and **Places API** enabled. Restrict it by HTTP referrer in the
Google console: a Maps browser key is sent to Google by the visitor's browser,
so it is public by design.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'base_setup', 'web'],
    'data': [
        'views/map_templates.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sl_google_maps/static/src/js/places_autocomplete.js',
            'sl_google_maps/static/src/xml/places_autocomplete.xml',
        ],
        'web.assets_frontend': [
            'sl_google_maps/static/src/css/map.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
