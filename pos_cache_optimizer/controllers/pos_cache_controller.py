# -*- coding: utf-8 -*-

import json
import gzip
import base64
import time
from odoo import http, tools
from odoo.http import request
from odoo.addons.point_of_sale.controllers.main import PosController
import logging

_logger = logging.getLogger(__name__)


class PosCacheController(http.Controller):

    @http.route('/pos_cache/products', type='json', auth='user', csrf=False)
    def get_cached_products(self, config_id, **params):
        """Get products with caching optimization"""
        start_time = time.time()
        
        try:
            # Get POS session
            session = request.env['pos.session'].search([
                ('config_id', '=', config_id),
                ('state', '=', 'opened')
            ], limit=1)
            
            if not session:
                return {'error': 'No active POS session found'}
            
            # Get products using optimized loading
            products = session.get_products_for_cache(config_id, params)
            
            # Calculate performance metrics
            load_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Update cache metrics
            metrics = {
                'avg_load_time': load_time,
                'total_requests': 1,
                'total_products_cached': len(products) if isinstance(products, list) else 0,
            }
            
            if hasattr(session, 'update_cache_metrics'):
                session.update_cache_metrics(metrics)
            
            return {
                'products': products,
                'load_time': load_time,
                'cache_config': session.config_id.get_cache_config(config_id),
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error in get_cached_products: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/products/category', type='json', auth='user', csrf=False)
    def get_products_by_category(self, config_id, category_id=None, offset=0, limit=100):
        """Get products by category with caching"""
        start_time = time.time()
        
        try:
            config = request.env['pos.config'].browse(config_id)
            products_data = config.get_products_by_category(
                config_id, category_id, offset, limit
            )
            
            load_time = (time.time() - start_time) * 1000
            
            return {
                'products': products_data,
                'load_time': load_time,
                'category_id': category_id,
                'offset': offset,
                'limit': limit,
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error in get_products_by_category: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/products/search', type='json', auth='user', csrf=False)
    def search_products(self, config_id, search_term, limit=50):
        """Search products with caching"""
        start_time = time.time()
        
        try:
            session = request.env['pos.session'].search([
                ('config_id', '=', config_id),
                ('state', '=', 'opened')
            ], limit=1)
            
            if not session:
                return {'error': 'No active POS session found'}
            
            products = session._get_products_by_search(search_term, limit, 0)
            products_data = session._prepare_product_data(products, compress=True)
            
            load_time = (time.time() - start_time) * 1000
            
            return {
                'products': products_data,
                'search_term': search_term,
                'load_time': load_time,
                'results_count': len(products),
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error in search_products: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/products/images', type='json', auth='user', csrf=False)
    def get_product_images(self, product_ids):
        """Get product images for lazy loading"""
        start_time = time.time()
        
        try:
            products = request.env['product.product'].browse(product_ids)
            images_data = {}
            
            for product in products:
                if product.image_128:
                    images_data[product.id] = product.image_128
            
            load_time = (time.time() - start_time) * 1000
            
            return {
                'images': images_data,
                'load_time': load_time,
                'products_count': len(product_ids),
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error in get_product_images: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/analytics/update', type='json', auth='user', csrf=False)
    def update_cache_analytics(self, session_id, metrics):
        """Update cache analytics metrics"""
        try:
            session = request.env['pos.session'].browse(session_id)
            
            if session and session.cache_analytics_id:
                session.update_cache_metrics(metrics)
                
                return {
                    'success': True,
                    'analytics_id': session.cache_analytics_id.id
                }
            
            return {'error': 'Session or analytics not found', 'success': False}
            
        except Exception as e:
            _logger.error(f"Error updating cache analytics: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/config', type='json', auth='user', csrf=False)
    def get_cache_config(self, config_id):
        """Get cache configuration for POS"""
        try:
            config = request.env['pos.config'].browse(config_id)
            cache_config = config.get_cache_config(config_id)
            
            # Add performance statistics
            stats = config.get_cache_statistics()
            cache_config.update(stats)
            
            return {
                'config': cache_config,
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error getting cache config: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/clear', type='json', auth='user', csrf=False)
    def clear_cache(self, config_id=None, session_id=None):
        """Clear cache data"""
        try:
            # This endpoint would typically clear server-side cache
            # For now, it returns success to allow client-side cache clearing
            
            return {
                'success': True,
                'message': 'Cache cleared successfully',
                'timestamp': time.time()
            }
            
        except Exception as e:
            _logger.error(f"Error clearing cache: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/warmup', type='json', auth='user', csrf=False)
    def warmup_cache(self, config_id):
        """Warmup cache with priority products"""
        start_time = time.time()
        
        try:
            config = request.env['pos.config'].browse(config_id)
            
            # Get priority products for warmup
            priority_products = config.get_prioritized_products()
            
            # Get session for data preparation
            session = request.env['pos.session'].search([
                ('config_id', '=', config_id),
                ('state', '=', 'opened')
            ], limit=1)
            
            if session:
                products_data = session._prepare_product_data(priority_products, compress=True)
            else:
                products_data = []
            
            warmup_time = (time.time() - start_time) * 1000
            
            return {
                'products': products_data,
                'products_count': len(priority_products),
                'warmup_time': warmup_time,
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error in cache warmup: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/stats', type='json', auth='user', csrf=False)
    def get_cache_stats(self, config_id, days=7):
        """Get cache performance statistics"""
        try:
            analytics_model = request.env['pos.cache.analytics']
            stats = analytics_model.get_analytics_summary(config_id, days)
            
            return {
                'stats': stats,
                'period_days': days,
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e), 'success': False}

    @http.route('/pos_cache/decompress', type='json', auth='user', csrf=False)
    def decompress_data(self, compressed_data):
        """Decompress cached data"""
        try:
            if not isinstance(compressed_data, dict) or not compressed_data.get('compressed'):
                return compressed_data
            
            # Decode and decompress
            encoded_data = compressed_data.get('data', '')
            compressed_bytes = base64.b64decode(encoded_data.encode('utf-8'))
            decompressed_bytes = gzip.decompress(compressed_bytes)
            json_data = decompressed_bytes.decode('utf-8')
            
            return {
                'data': json.loads(json_data),
                'decompressed': True,
                'original_size': compressed_data.get('original_size', 0),
                'compressed_size': compressed_data.get('compressed_size', 0),
                'success': True
            }
            
        except Exception as e:
            _logger.error(f"Error decompressing data: {e}")
            return {'error': str(e), 'success': False}
