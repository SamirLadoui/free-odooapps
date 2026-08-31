# -*- coding: utf-8 -*-
{
    'name': 'POS Cache Optimizer',
    'version': '16.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Advanced caching system for POS to handle large product catalogs efficiently',
    'description': """
POS Cache Optimizer
===================

This module provides advanced caching mechanisms to optimize POS performance 
when dealing with large product catalogs (10,000+ products).

Features:
---------
* Server-side product data caching and compression
* Client-side browser cache management (localStorage/IndexedDB)
* Smart lazy loading and pagination
* Category-based product loading
* Frequently used products prioritization
* Background cache warming and updates
* Cache analytics and monitoring
* Configurable cache strategies per POS session

Performance Benefits:
--------------------
* Reduce initial POS loading time by 60-80%
* Minimize memory usage in browser
* Improve product search performance
* Reduce server load with smart caching
* Offline capability with cached data

Technical Features:
------------------
* Redis/Memcached integration support
* Database query optimization
* Compressed JSON responses
* Smart prefetching algorithms
* Cache invalidation strategies
* Performance monitoring dashboard
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'point_of_sale',
        'product',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/pos_cache_security.xml',
        'data/pos_cache_data.xml',
        'views/pos_config_views.xml',
        'views/pos_cache_config_views.xml',
        'views/pos_cache_analytics_views.xml',
        'views/res_config_settings_views.xml',
        'views/pos_cache_menus.xml',
    ],
    'assets': {
        'point_of_sale.assets': [
            'pos_cache_optimizer/static/src/js/pos_cache_manager.js',
            'pos_cache_optimizer/static/src/js/pos_product_loader.js',
            'pos_cache_optimizer/static/src/js/pos_lazy_loader.js',
            'pos_cache_optimizer/static/src/js/pos_search_cache.js',
            'pos_cache_optimizer/static/src/css/pos_cache_optimizer.css',
        ],
        'web.assets_backend': [
            'pos_cache_optimizer/static/src/js/cache_analytics.js',
            'pos_cache_optimizer/static/src/css/cache_analytics.css',
        ],
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
    'price': 199.00,
    'currency': 'EUR',
    'maintainers': ['your_github_username'],
}
