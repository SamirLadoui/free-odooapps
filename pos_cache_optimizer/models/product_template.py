# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
import json
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Cache-related fields
    cache_priority = fields.Integer(
        string='Cache Priority',
        default=0,
        help='Priority for caching (higher = more important)'
    )
    
    pos_cache_enabled = fields.Boolean(
        string='Enable POS Cache',
        default=True,
        help='Include this product in POS cache'
    )
    
    frequent_access = fields.Boolean(
        string='Frequently Accessed',
        compute='_compute_frequent_access',
        store=True,
        help='Product is frequently accessed in POS'
    )
    
    cache_size_bytes = fields.Integer(
        string='Cache Size (Bytes)',
        compute='_compute_cache_size',
        help='Estimated cache size for this product'
    )

    @api.depends('sale_ok', 'available_in_pos')
    def _compute_frequent_access(self):
        """Compute if product is frequently accessed"""
        for product in self:
            # This could be enhanced with actual POS analytics
            # For now, mark products with high priority or recent sales
            product.frequent_access = (
                product.sale_ok and 
                product.available_in_pos and 
                product.cache_priority > 5
            )

    @api.depends('name', 'description_sale', 'image_1920')
    def _compute_cache_size(self):
        """Estimate cache size for product data"""
        for product in self:
            size = 0
            
            # Text fields
            if product.name:
                size += len(product.name.encode('utf-8'))
            if product.description_sale:
                size += len(product.description_sale.encode('utf-8'))
            
            # Image size (rough estimate)
            if product.image_1920:
                size += len(product.image_1920) * 0.75  # Base64 overhead
            
            # Base product data (JSON overhead)
            size += 500  # Approximate JSON structure size
            
            product.cache_size_bytes = int(size)

    def _get_pos_product_data(self):
        """Get optimized product data for POS cache"""
        products_data = []
        
        for product in self.product_variant_ids.filtered('available_in_pos'):
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
                'cache_priority': self.cache_priority,
                'frequent_access': self.frequent_access,
                'cache_size_bytes': self.cache_size_bytes,
            }
            
            products_data.append(data)
        
        return products_data

    @api.model
    def get_products_for_pos_cache(self, config_id, limit=None, offset=0, category_id=None):
        """Get products optimized for POS cache loading"""
        config = self.env['pos.config'].browse(config_id)
        domain = [
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True),
            ('pos_cache_enabled', '=', True),
        ]
        
        # Filter by POS configuration
        if config.iface_available_categ_ids:
            domain.append(('pos_categ_id', 'in', config.iface_available_categ_ids.ids))
        
        if category_id:
            domain.append(('pos_categ_id', '=', category_id))
        
        # Order by cache priority and name
        order = 'cache_priority desc, frequent_access desc, name'
        
        products = self.env['product.product'].search(
            domain, 
            limit=limit, 
            offset=offset, 
            order=order
        )
        
        return products

    @api.model
    def update_cache_priority_from_usage(self, usage_data):
        """Update cache priorities based on POS usage analytics"""
        try:
            for product_id, usage_count in usage_data.items():
                product = self.env['product.product'].browse(int(product_id))
                if product.exists():
                    # Calculate new priority based on usage
                    # More usage = higher priority
                    new_priority = min(10, max(0, int(usage_count / 10)))
                    product.product_tmpl_id.cache_priority = new_priority
            
            _logger.info(f"Updated cache priorities for {len(usage_data)} products")
            
        except Exception as e:
            _logger.error(f"Error updating cache priorities: {e}")

    def action_optimize_for_cache(self):
        """Action to optimize product for cache performance"""
        for product in self:
            # Enable cache for frequently sold products
            if product.sale_ok and product.available_in_pos:
                product.pos_cache_enabled = True
                
                # Set priority based on product characteristics
                priority = 0
                
                # High priority for products with images
                if product.image_1920:
                    priority += 2
                    
                # High priority for products with categories
                if product.pos_categ_id:
                    priority += 1
                    
                # High priority for products with barcodes
                if product.barcode:
                    priority += 1
                    
                product.cache_priority = min(10, priority)

    @api.model
    def get_cache_analytics_data(self):
        """Get analytics data for cache optimization"""
        products = self.search([
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True)
        ])
        
        total_products = len(products)
        cached_products = len(products.filtered('pos_cache_enabled'))
        total_cache_size = sum(products.mapped('cache_size_bytes'))
        high_priority_products = len(products.filtered(lambda p: p.cache_priority >= 7))
        
        return {
            'total_products': total_products,
            'cached_products': cached_products,
            'cache_coverage': (cached_products / total_products * 100) if total_products > 0 else 0,
            'total_cache_size_mb': total_cache_size / (1024 * 1024),
            'high_priority_products': high_priority_products,
            'avg_cache_priority': sum(products.mapped('cache_priority')) / total_products if total_products > 0 else 0,
        }
