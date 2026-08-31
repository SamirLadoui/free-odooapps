# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
import json
import logging

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # Cache Configuration
    enable_product_cache = fields.Boolean(
        string='Enable Product Cache',
        default=True,
        help='Enable advanced caching for products in POS'
    )
    
    cache_strategy = fields.Selection([
        ('lazy', 'Lazy Loading'),
        ('category', 'Category Based'),
        ('priority', 'Priority Based'),
        ('hybrid', 'Hybrid (Recommended)')
    ], string='Cache Strategy', default='hybrid',
       help='Strategy for loading and caching products')
    
    cache_size_limit = fields.Integer(
        string='Cache Size Limit (MB)',
        default=50,
        help='Maximum memory usage for product cache in browser'
    )
    
    preload_products_count = fields.Integer(
        string='Preload Products Count',
        default=500,
        help='Number of products to preload immediately'
    )
    
    enable_image_lazy_loading = fields.Boolean(
        string='Enable Image Lazy Loading',
        default=True,
        help='Load product images only when needed'
    )
    
    cache_compression = fields.Boolean(
        string='Enable Cache Compression',
        default=True,
        help='Compress cached data to save memory'
    )
    
    priority_categories = fields.Many2many(
        'pos.category',
        'pos_config_priority_category_rel',
        'pos_config_id',
        'category_id',
        string='Priority Categories',
        help='Categories to load first for faster access'
    )
    
    cache_expiry_hours = fields.Integer(
        string='Cache Expiry (hours)',
        default=24,
        help='How long to keep cache before refreshing'
    )
    
    enable_background_sync = fields.Boolean(
        string='Enable Background Sync',
        default=True,
        help='Update cache in background while POS is running'
    )

    @api.model
    def get_cache_config(self, config_id):
        """Get cache configuration for POS session"""
        config = self.browse(config_id)
        return {
            'enable_product_cache': config.enable_product_cache,
            'cache_strategy': config.cache_strategy,
            'cache_size_limit': config.cache_size_limit,
            'preload_products_count': config.preload_products_count,
            'enable_image_lazy_loading': config.enable_image_lazy_loading,
            'cache_compression': config.cache_compression,
            'priority_categories': config.priority_categories.ids,
            'cache_expiry_hours': config.cache_expiry_hours,
            'enable_background_sync': config.enable_background_sync,
        }

    def get_prioritized_products(self, limit=None):
        """Get prioritized product list based on configuration"""
        domain = self._get_available_product_domain()
        
        if self.priority_categories:
            # First get products from priority categories
            priority_domain = domain + [('pos_categ_id', 'in', self.priority_categories.ids)]
            priority_products = self.env['product.product'].search(
                priority_domain, 
                limit=limit or self.preload_products_count
            )
            return priority_products
        
        # Fallback to most sold products or recently created
        products = self.env['product.product'].search(
            domain, 
            order='create_date desc',
            limit=limit or self.preload_products_count
        )
        return products

    def _get_available_product_domain(self):
        """Get domain for available products in this POS"""
        domain = [
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True),
        ]
        
        if self.iface_available_categ_ids:
            domain.append(('pos_categ_id', 'in', self.iface_available_categ_ids.ids))
            
        if self.limit_categories and self.iface_available_categ_ids:
            domain.append(('pos_categ_id', 'in', self.iface_available_categ_ids.ids))
            
        return domain

    @api.model
    def get_products_by_category(self, config_id, category_id=None, offset=0, limit=100):
        """Get products by category with pagination"""
        config = self.browse(config_id)
        domain = config._get_available_product_domain()
        
        if category_id:
            domain.append(('pos_categ_id', '=', category_id))
        
        products = self.env['product.product'].search(
            domain,
            offset=offset,
            limit=limit,
            order='name'
        )
        
        # Prepare product data for cache
        product_data = []
        for product in products:
            data = {
                'id': product.id,
                'display_name': product.display_name,
                'lst_price': product.lst_price,
                'standard_price': product.standard_price,
                'categ_id': product.categ_id.id if product.categ_id else False,
                'pos_categ_id': product.pos_categ_id.id if product.pos_categ_id else False,
                'taxes_id': product.taxes_id.ids,
                'barcode': product.barcode,
                'default_code': product.default_code,
                'to_weight': product.to_weight,
                'uom_id': product.uom_id.id,
                'description_sale': product.description_sale,
                'description': product.description,
                'product_tmpl_id': product.product_tmpl_id.id,
                'tracking': product.tracking,
                'available_in_pos': product.available_in_pos,
            }
            
            # Add image data conditionally
            if not config.enable_image_lazy_loading:
                data['image_128'] = product.image_128
            
            product_data.append(data)
        
        return product_data

    def get_cache_statistics(self):
        """Get cache performance statistics"""
        analytics = self.env['pos.cache.analytics'].search([
            ('pos_config_id', '=', self.id)
        ], limit=1, order='create_date desc')
        
        if analytics:
            return {
                'cache_hit_ratio': analytics.cache_hit_ratio,
                'avg_load_time': analytics.avg_load_time,
                'total_products_cached': analytics.total_products_cached,
                'cache_size_mb': analytics.cache_size_mb,
            }
        
        return {
            'cache_hit_ratio': 0,
            'avg_load_time': 0,
            'total_products_cached': 0,
            'cache_size_mb': 0,
        }
