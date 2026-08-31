# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class PosCacheAnalytics(models.Model):
    _name = 'pos.cache.analytics'
    _description = 'POS Cache Analytics'
    _order = 'create_date desc'
    _rec_name = 'pos_config_id'

    pos_config_id = fields.Many2one(
        'pos.config',
        string='POS Configuration',
        required=True,
        ondelete='cascade'
    )
    
    pos_session_id = fields.Many2one(
        'pos.session',
        string='POS Session',
        ondelete='cascade'
    )
    
    # Performance Metrics
    cache_hit_ratio = fields.Float(
        string='Cache Hit Ratio (%)',
        help='Percentage of requests served from cache'
    )
    
    cache_miss_ratio = fields.Float(
        string='Cache Miss Ratio (%)',
        compute='_compute_cache_miss_ratio',
        store=True
    )
    
    avg_load_time = fields.Float(
        string='Average Load Time (ms)',
        help='Average time to load products'
    )
    
    total_requests = fields.Integer(
        string='Total Requests',
        help='Total number of product requests'
    )
    
    cache_hits = fields.Integer(
        string='Cache Hits',
        help='Number of requests served from cache'
    )
    
    cache_misses = fields.Integer(
        string='Cache Misses',
        help='Number of requests requiring database query'
    )
    
    # Cache Size Metrics
    total_products_cached = fields.Integer(
        string='Total Products Cached',
        help='Number of products currently in cache'
    )
    
    cache_size_mb = fields.Float(
        string='Cache Size (MB)',
        help='Current cache size in megabytes'
    )
    
    max_cache_size_mb = fields.Float(
        string='Max Cache Size (MB)',
        help='Maximum cache size reached'
    )
    
    # Loading Performance
    initial_load_time = fields.Float(
        string='Initial Load Time (s)',
        help='Time taken for initial POS load'
    )
    
    product_search_time = fields.Float(
        string='Product Search Time (ms)',
        help='Average time for product search'
    )
    
    category_load_time = fields.Float(
        string='Category Load Time (ms)',
        help='Average time to load products by category'
    )
    
    # Cache Strategy Performance
    strategy_used = fields.Selection([
        ('lazy', 'Lazy Loading'),
        ('category', 'Category Based'),
        ('priority', 'Priority Based'),
        ('hybrid', 'Hybrid')
    ], string='Strategy Used')
    
    preloaded_products = fields.Integer(
        string='Preloaded Products',
        help='Number of products preloaded initially'
    )
    
    lazy_loaded_products = fields.Integer(
        string='Lazy Loaded Products',
        help='Number of products loaded on demand'
    )
    
    # Memory Usage
    browser_memory_usage = fields.Float(
        string='Browser Memory Usage (MB)',
        help='Memory usage in browser'
    )
    
    compression_ratio = fields.Float(
        string='Compression Ratio (%)',
        help='Data compression efficiency'
    )
    
    # Date/Time fields
    session_start_time = fields.Datetime(
        string='Session Start Time',
        default=fields.Datetime.now
    )
    
    session_end_time = fields.Datetime(
        string='Session End Time'
    )
    
    session_duration = fields.Float(
        string='Session Duration (hours)',
        compute='_compute_session_duration',
        store=True
    )

    @api.depends('cache_hit_ratio')
    def _compute_cache_miss_ratio(self):
        for record in self:
            record.cache_miss_ratio = 100 - record.cache_hit_ratio

    @api.depends('session_start_time', 'session_end_time')
    def _compute_session_duration(self):
        for record in self:
            if record.session_start_time and record.session_end_time:
                duration = record.session_end_time - record.session_start_time
                record.session_duration = duration.total_seconds() / 3600
            else:
                record.session_duration = 0

    @api.model
    def create_analytics_record(self, pos_config_id, pos_session_id=None, metrics=None):
        """Create analytics record with performance metrics"""
        if not metrics:
            metrics = {}
            
        vals = {
            'pos_config_id': pos_config_id,
            'pos_session_id': pos_session_id,
            'cache_hit_ratio': metrics.get('cache_hit_ratio', 0),
            'avg_load_time': metrics.get('avg_load_time', 0),
            'total_requests': metrics.get('total_requests', 0),
            'cache_hits': metrics.get('cache_hits', 0),
            'cache_misses': metrics.get('cache_misses', 0),
            'total_products_cached': metrics.get('total_products_cached', 0),
            'cache_size_mb': metrics.get('cache_size_mb', 0),
            'max_cache_size_mb': metrics.get('max_cache_size_mb', 0),
            'initial_load_time': metrics.get('initial_load_time', 0),
            'product_search_time': metrics.get('product_search_time', 0),
            'category_load_time': metrics.get('category_load_time', 0),
            'strategy_used': metrics.get('strategy_used', 'hybrid'),
            'preloaded_products': metrics.get('preloaded_products', 0),
            'lazy_loaded_products': metrics.get('lazy_loaded_products', 0),
            'browser_memory_usage': metrics.get('browser_memory_usage', 0),
            'compression_ratio': metrics.get('compression_ratio', 0),
        }
        
        return self.create(vals)

    @api.model
    def update_session_metrics(self, pos_session_id, metrics):
        """Update metrics for an existing session"""
        analytics = self.search([
            ('pos_session_id', '=', pos_session_id)
        ], limit=1)
        
        if analytics:
            analytics.write(metrics)
        
        return analytics

    def get_performance_summary(self):
        """Get performance summary for dashboard"""
        self.ensure_one()
        
        return {
            'cache_efficiency': self.cache_hit_ratio,
            'load_performance': self.avg_load_time,
            'memory_usage': self.cache_size_mb,
            'products_cached': self.total_products_cached,
            'strategy': self.strategy_used,
            'session_duration': self.session_duration,
        }

    @api.model
    def get_analytics_summary(self, pos_config_id, days=7):
        """Get analytics summary for the last N days"""
        date_from = datetime.now() - timedelta(days=days)
        
        analytics = self.search([
            ('pos_config_id', '=', pos_config_id),
            ('create_date', '>=', date_from)
        ])
        
        if not analytics:
            return {
                'avg_cache_hit_ratio': 0,
                'avg_load_time': 0,
                'total_sessions': 0,
                'avg_products_cached': 0,
                'avg_cache_size': 0,
            }
        
        return {
            'avg_cache_hit_ratio': sum(analytics.mapped('cache_hit_ratio')) / len(analytics),
            'avg_load_time': sum(analytics.mapped('avg_load_time')) / len(analytics),
            'total_sessions': len(analytics),
            'avg_products_cached': sum(analytics.mapped('total_products_cached')) / len(analytics),
            'avg_cache_size': sum(analytics.mapped('cache_size_mb')) / len(analytics),
        }

    @api.model
    def cleanup_old_analytics(self, days=30):
        """Clean up analytics older than specified days"""
        date_limit = datetime.now() - timedelta(days=days)
        old_analytics = self.search([
            ('create_date', '<', date_limit)
        ])
        old_analytics.unlink()
        _logger.info(f"Cleaned up {len(old_analytics)} old analytics records")
