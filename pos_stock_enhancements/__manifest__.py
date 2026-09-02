# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Stock Enhancements',
    'version': '14.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Enhances POS with real-time stock checks and configurable stock locations.',

    'description': """
This module significantly enhances the Point of Sale experience by providing salespersons with
real-time stock information based on configurable inventory locations.

Key Features:
--------------
- Real-time Stock Check: Displays available stock quantities directly on the POS screen for selected products.
- Configurable Stock Locations: Allows defining specific stock locations (warehouses) that a POS configuration should check for product availability.
- Automatic Quantity Adjustment: If a salesperson attempts to add a quantity exceeding the available stock in the configured locations, the quantity is automatically reset to the maximum allowed, and a clear warning is displayed.
- Out-of-Stock Prevention: Displays a popup warning when trying to add a product that has zero stock in the configured locations.
- Enforce Stock Check: A boolean option per POS config to enable or disable these enhanced stock checking features.

This module helps prevent overselling, improves inventory accuracy within the POS, and provides sales staff with immediate stock visibility, leading to better customer service.

Important Considerations:
   If the 'Enforce Stock Check in POS' option is enabled, you MUST configure at least one 'Available Stock Location' for that POS. Failure to do so will result in an error when attempting to open the Point of Sale interface.

For a more detailed guide, including screenshots and setup instructions, please refer to the documentation available via the links below (or included in the detailed description page).
""",

    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',

    'depends': [
        'point_of_sale',
        'stock'
    ],

    'data': [
        'views/pos_config_views.xml',
        'views/pos_assets.xml',
    ],

    'images': ['static/description/banner.gif'],

    'installable': True,
    'application': False
}