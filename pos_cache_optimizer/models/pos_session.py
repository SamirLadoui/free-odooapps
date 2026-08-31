# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
import json
import gzip
import base64
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    cache_analytics_id = fields.Many2one(
        'pos.cache.analytics',
        string='Cache Analytics',
        readonly=True
    )
    
    cache_enabled = fields.Boolean(
        string='Cache Enabled',
        related='config_id.enable_product_cache',
        readonly=True
    )
    
    products_cached_count = fields.Integer(
        string='Products Cached',
        readonly=True
    )
    
    cache_hit_ratio = fields.Float(
        string='Cache Hit Ratio (%)',
        readonly=True
    )

    def _get_pos_ui_product_product(self, params):
        """Override to implement caching strategy"""
        if not self.config_id.enable_product_cache:
            return super()._get_pos_ui_product_product(params)
        
        cache_config = self.config_id.get_cache_config(self.config_id.id)
        strategy = cache_config.get('cache_strategy', 'hybrid')
        
        if strategy == 'lazy':
            return self._get_products_lazy_loading(params)
        elif strategy == 'category':
            return self._get_products_category_based(params)
        elif strategy == 'priority':
            return self._get_products_priority_based(params)
        else:  # hybrid
            return self._get_products_hybrid_strategy(params)

    def _get_products_lazy_loading(self, params):
        """Lazy loading strategy - minimal initial load"""
        limit = params.get('limit', self.config_id.preload_products_count)
        offset = params.get('offset', 0)
        category_id = params.get('category_id')
        
        if offset == 0 and not category_id:
            # Initial load - only priority products
            products = self.config_id.get_prioritized_products(limit)
        else:
            # Subsequent loads
            domain = self.config_id._get_available_product_domain()
            if category_id:
                domain.append(('pos_categ_id', '=', category_id))
                
            products = self.env['product.product'].search(
                domain, offset=offset, limit=limit
            )
        
        return self._prepare_product_data(products, compress=True)

    def _get_products_category_based(self, params):
        """Category-based loading strategy"""
        category_id = params.get('category_id')
        limit = params.get('limit', 100)
        offset = params.get('offset', 0)
        
        if category_id:
            products = self.config_id.get_products_by_category(
                self.config_id.id, category_id, offset, limit
            )
        else:
            # Load priority categories first
            if self.config_id.priority_categories and offset == 0:
                domain = self.config_id._get_available_product_domain()
                domain.append(('pos_categ_id', 'in', self.config_id.priority_categories.ids))
                products = self.env['product.product'].search(domain, limit=limit)
            else:
                products = self.config_id.get_prioritized_products(limit)
        
        return self._prepare_product_data(products, compress=True)

    def _get_products_priority_based(self, params):
        """Priority-based loading strategy"""
        limit = params.get('limit', self.config_id.preload_products_count)
        offset = params.get('offset', 0)
        
        if offset == 0:
            # First load - prioritized products
            products = self.config_id.get_prioritized_products(limit)
        else:
            # Subsequent loads - remaining products
            priority_products = self.config_id.get_prioritized_products()
            domain = self.config_id._get_available_product_domain()
            domain.append(('id', 'not in', priority_products.ids))
            
            products = self.env['product.product'].search(
                domain, offset=offset - len(priority_products), limit=limit
            )
        
        return self._prepare_product_data(products, compress=True)

    def _get_products_hybrid_strategy(self, params):
        """Hybrid strategy - combination of priority and lazy loading"""
        limit = params.get('limit', self.config_id.preload_products_count)
        offset = params.get('offset', 0)
        category_id = params.get('category_id')
        search_term = params.get('search_term')
        
        if offset == 0 and not category_id and not search_term:
            # Initial load - priority products + frequently used
            products = self._get_hybrid_initial_products(limit)
        elif search_term:
            # Search - use optimized search
            products = self._get_products_by_search(search_term, limit, offset)
        elif category_id:
            # Category-specific load
            products = self.config_id.get_products_by_category(
                self.config_id.id, category_id, offset, limit
            )
        else:
            # Lazy load remaining products
            products = self._get_remaining_products(offset, limit)
        
        return self._prepare_product_data(products, compress=True)

    def _get_hybrid_initial_products(self, limit):
        """Get initial products for hybrid strategy"""
        # Split limit between priority and recent products
        priority_limit = int(limit * 0.7)
        recent_limit = limit - priority_limit
        
        # Get priority products
        priority_products = self.config_id.get_prioritized_products(priority_limit)
        
        # Get recently sold products (if sale analytics available)
        recent_domain = self.config_id._get_available_product_domain()
        recent_domain.append(('id', 'not in', priority_products.ids))
        
        recent_products = self.env['product.product'].search(
            recent_domain,
            order='write_date desc',
            limit=recent_limit
        )
        
        return priority_products + recent_products

    def _get_products_by_search(self, search_term, limit, offset):
        """Optimized product search"""
        domain = self.config_id._get_available_product_domain()
        
        # Enhanced search domain
        search_domain = [
            '|', '|', '|',
            ('name', 'ilike', search_term),
            ('default_code', 'ilike', search_term),
            ('barcode', 'ilike', search_term),
            ('description_sale', 'ilike', search_term)
        ]
        
        domain.extend(search_domain)
        
        return self.env['product.product'].search(
            domain, offset=offset, limit=limit, order='name'
        )

    def _get_remaining_products(self, offset, limit):
        """Get remaining products for lazy loading"""
        domain = self.config_id._get_available_product_domain()
        
        return self.env['product.product'].search(
            domain, offset=offset, limit=limit, order='name'
        )

    def _prepare_product_data(self, products, compress=False):
        """Prepare product data with optional compression"""
        if not products:
            return []
        
        # Get optimized product data
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
            if not self.config_id.enable_image_lazy_loading:
                data['image_128'] = product.image_128
            
            product_data.append(data)
        
        if compress and self.config_id.cache_compression:
            return self._compress_product_data(product_data)
        
        return product_data

    def _compress_product_data(self, product_data):
        """Compress product data for transmission"""
        try:
            json_data = json.dumps(product_data)
            compressed = gzip.compress(json_data.encode('utf-8'))
            encoded = base64.b64encode(compressed).decode('utf-8')
            
            return {
                'compressed': True,
                'data': encoded,
                'original_size': len(json_data),
                'compressed_size': len(encoded)
            }
        except Exception as e:
            _logger.error(f"Error compressing product data: {e}")
            return product_data

    @api.model
    def get_products_for_cache(self, config_id, params=None):
        """API endpoint for getting products with caching"""
        if not params:
            params = {}
            
        config = self.env['pos.config'].browse(config_id)
        session = self.search([
            ('config_id', '=', config_id),
            ('state', '=', 'opened')
        ], limit=1)
        
        if not session:
            # Create temporary session for product loading
            session = self.env['pos.session'].create({
                'config_id': config_id,
                'user_id': self.env.user.id,
            })
        
        return session._get_pos_ui_product_product(params)

    def start_cache_analytics(self):
        """Start cache analytics tracking"""
        if self.config_id.enable_product_cache:
            analytics = self.env['pos.cache.analytics'].create_analytics_record(
                self.config_id.id,
                self.id,
                {'strategy_used': self.config_id.cache_strategy}
            )
            self.cache_analytics_id = analytics

    def update_cache_metrics(self, metrics):
        """Update cache metrics during session"""
        if self.cache_analytics_id:
            self.cache_analytics_id.write(metrics)
            
            # Update session fields
            self.products_cached_count = metrics.get('total_products_cached', 0)
            self.cache_hit_ratio = metrics.get('cache_hit_ratio', 0)

    def close_session_and_validate(self):
        """Override to finalize cache analytics"""
        result = super().close_session_and_validate()
        
        if self.cache_analytics_id:
            self.cache_analytics_id.session_end_time = fields.Datetime.now()
        
        return result
