# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
import json
import logging

_logger = logging.getLogger(__name__)


class PosCacheConfig(models.Model):
    _name = 'pos.cache.config'
    _description = 'POS Cache Configuration'
    _rec_name = 'name'

    name = fields.Char(
        string='Configuration Name',
        required=True,
        help='Name for this cache configuration'
    )
    
    pos_config_ids = fields.Many2many(
        'pos.config',
        string='POS Configurations',
        help='POS configurations using this cache setup'
    )
    
    # Cache Strategy Settings
    cache_strategy = fields.Selection([
        ('lazy', 'Lazy Loading'),
        ('category', 'Category Based'),
        ('priority', 'Priority Based'),
        ('hybrid', 'Hybrid')
    ], string='Cache Strategy', default='hybrid', required=True)
    
    # Performance Settings
    cache_size_limit_mb = fields.Integer(
        string='Cache Size Limit (MB)',
        default=50,
        help='Maximum memory usage for cache'
    )
    
    preload_products_count = fields.Integer(
        string='Preload Products Count',
        default=500,
        help='Number of products to preload'
    )
    
    lazy_load_batch_size = fields.Integer(
        string='Lazy Load Batch Size',
        default=100,
        help='Number of products to load per batch'
    )
    
    # Compression Settings
    enable_compression = fields.Boolean(
        string='Enable Compression',
        default=True,
        help='Compress cached data'
    )
    
    compression_level = fields.Selection([
        ('1', 'Fast (Level 1)'),
        ('6', 'Balanced (Level 6)'),
        ('9', 'Best (Level 9)')
    ], string='Compression Level', default='6')
    
    # Image Settings
    enable_image_lazy_loading = fields.Boolean(
        string='Enable Image Lazy Loading',
        default=True
    )
    
    image_quality = fields.Selection([
        ('low', 'Low (64x64)'),
        ('medium', 'Medium (128x128)'),
        ('high', 'High (256x256)')
    ], string='Image Quality', default='medium')
    
    # Cache Expiry Settings
    cache_expiry_hours = fields.Integer(
        string='Cache Expiry (hours)',
        default=24,
        help='Cache expiration time'
    )
    
    auto_refresh_enabled = fields.Boolean(
        string='Auto Refresh Cache',
        default=True,
        help='Automatically refresh expired cache'
    )
    
    # Background Sync Settings
    enable_background_sync = fields.Boolean(
        string='Enable Background Sync',
        default=True
    )
    
    sync_interval_minutes = fields.Integer(
        string='Sync Interval (minutes)',
        default=5,
        help='Background sync frequency'
    )
    
    # Priority Categories
    priority_category_ids = fields.Many2many(
        'pos.category',
        'pos_cache_config_priority_category_rel',
        'cache_config_id',
        'category_id',
        string='Priority Categories',
        help='Categories to prioritize in cache'
    )
    
    # Advanced Settings
    enable_indexeddb = fields.Boolean(
        string='Enable IndexedDB',
        default=True,
        help='Use IndexedDB for persistent storage'
    )
    
    enable_service_worker = fields.Boolean(
        string='Enable Service Worker',
        default=False,
        help='Use service worker for offline caching'
    )
    
    max_concurrent_requests = fields.Integer(
        string='Max Concurrent Requests',
        default=5,
        help='Maximum concurrent cache requests'
    )
    
    # Analytics Settings
    enable_analytics = fields.Boolean(
        string='Enable Analytics',
        default=True,
        help='Track cache performance metrics'
    )
    
    detailed_logging = fields.Boolean(
        string='Detailed Logging',
        default=False,
        help='Enable detailed cache logging'
    )
    
    # Performance Thresholds
    performance_warning_threshold = fields.Float(
        string='Performance Warning Threshold (ms)',
        default=1000.0,
        help='Warn if load time exceeds this threshold'
    )
    
    cache_hit_ratio_target = fields.Float(
        string='Cache Hit Ratio Target (%)',
        default=80.0,
        help='Target cache hit ratio'
    )
    
    # Configuration Status
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    description = fields.Text(
        string='Description',
        help='Description of this cache configuration'
    )

    def get_config_dict(self):
        """Get configuration as dictionary"""
        self.ensure_one()
        
        return {
            'name': self.name,
            'cache_strategy': self.cache_strategy,
            'cache_size_limit_mb': self.cache_size_limit_mb,
            'preload_products_count': self.preload_products_count,
            'lazy_load_batch_size': self.lazy_load_batch_size,
            'enable_compression': self.enable_compression,
            'compression_level': int(self.compression_level),
            'enable_image_lazy_loading': self.enable_image_lazy_loading,
            'image_quality': self.image_quality,
            'cache_expiry_hours': self.cache_expiry_hours,
            'auto_refresh_enabled': self.auto_refresh_enabled,
            'enable_background_sync': self.enable_background_sync,
            'sync_interval_minutes': self.sync_interval_minutes,
            'priority_category_ids': self.priority_category_ids.ids,
            'enable_indexeddb': self.enable_indexeddb,
            'enable_service_worker': self.enable_service_worker,
            'max_concurrent_requests': self.max_concurrent_requests,
            'enable_analytics': self.enable_analytics,
            'detailed_logging': self.detailed_logging,
            'performance_warning_threshold': self.performance_warning_threshold,
            'cache_hit_ratio_target': self.cache_hit_ratio_target,
        }

    @api.model
    def create_default_config(self, name='Default Cache Config'):
        """Create a default cache configuration"""
        default_config = self.create({
            'name': name,
            'cache_strategy': 'hybrid',
            'cache_size_limit_mb': 50,
            'preload_products_count': 500,
            'lazy_load_batch_size': 100,
            'enable_compression': True,
            'compression_level': '6',
            'enable_image_lazy_loading': True,
            'image_quality': 'medium',
            'cache_expiry_hours': 24,
            'auto_refresh_enabled': True,
            'enable_background_sync': True,
            'sync_interval_minutes': 5,
            'enable_indexeddb': True,
            'enable_service_worker': False,
            'max_concurrent_requests': 5,
            'enable_analytics': True,
            'detailed_logging': False,
            'performance_warning_threshold': 1000.0,
            'cache_hit_ratio_target': 80.0,
            'active': True,
            'description': 'Default cache configuration with balanced performance settings',
        })
        
        return default_config

    def action_apply_to_pos_configs(self):
        """Apply this configuration to selected POS configs"""
        self.ensure_one()
        
        config_dict = self.get_config_dict()
        
        # Update POS configurations
        for pos_config in self.pos_config_ids:
            pos_config.write({
                'cache_strategy': config_dict['cache_strategy'],
                'cache_size_limit': config_dict['cache_size_limit_mb'],
                'preload_products_count': config_dict['preload_products_count'],
                'cache_compression': config_dict['enable_compression'],
                'enable_image_lazy_loading': config_dict['enable_image_lazy_loading'],
                'cache_expiry_hours': config_dict['cache_expiry_hours'],
                'enable_background_sync': config_dict['enable_background_sync'],
                'priority_categories': [(6, 0, config_dict['priority_category_ids'])],
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Configuration applied to {len(self.pos_config_ids)} POS configurations.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_test_configuration(self):
        """Test this cache configuration"""
        self.ensure_one()
        
        # Simulate cache performance with this configuration
        test_results = self._simulate_cache_performance()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Test completed! Estimated performance: {test_results["estimated_cache_hit_ratio"]:.1f}% hit ratio, {test_results["estimated_initial_load_time"]:.0f}ms load time',
                'type': 'success',
                'sticky': False,
            }
        }

    def _simulate_cache_performance(self):
        """Simulate cache performance for this configuration"""
        # Get sample product data
        sample_products = self.env['product.product'].search([
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True)
        ], limit=1000)
        
        total_products = len(sample_products)
        preload_count = min(self.preload_products_count, total_products)
        remaining_products = total_products - preload_count
        
        # Estimate performance metrics
        estimated_initial_load_time = self._estimate_load_time(preload_count)
        estimated_lazy_load_time = self._estimate_load_time(self.lazy_load_batch_size)
        estimated_cache_hit_ratio = self._estimate_cache_hit_ratio()
        estimated_memory_usage = self._estimate_memory_usage(preload_count)
        
        return {
            'total_products': total_products,
            'preload_count': preload_count,
            'remaining_products': remaining_products,
            'estimated_initial_load_time': estimated_initial_load_time,
            'estimated_lazy_load_time': estimated_lazy_load_time,
            'estimated_cache_hit_ratio': estimated_cache_hit_ratio,
            'estimated_memory_usage': estimated_memory_usage,
            'batch_count': (remaining_products // self.lazy_load_batch_size) + 1,
        }

    def _estimate_load_time(self, product_count):
        """Estimate load time based on product count and configuration"""
        base_time = product_count * 0.5  # 0.5ms per product base time
        
        if self.enable_compression:
            base_time *= 0.8  # 20% faster with compression
        
        if self.enable_image_lazy_loading:
            base_time *= 0.7  # 30% faster without images
        
        return base_time

    def _estimate_cache_hit_ratio(self):
        """Estimate cache hit ratio based on strategy"""
        strategy_ratios = {
            'lazy': 60,
            'category': 75,
            'priority': 85,
            'hybrid': 90
        }
        
        base_ratio = strategy_ratios.get(self.cache_strategy, 75)
        
        if self.enable_background_sync:
            base_ratio += 5
        
        if self.cache_expiry_hours > 12:
            base_ratio += 5
        
        return min(95, base_ratio)

    def _estimate_memory_usage(self, product_count):
        """Estimate memory usage in MB"""
        base_size_per_product = 2048  # 2KB per product
        
        total_size = product_count * base_size_per_product
        
        if self.enable_compression:
            compression_ratios = {'1': 0.8, '6': 0.6, '9': 0.5}
            total_size *= compression_ratios.get(self.compression_level, 0.6)
        
        if not self.enable_image_lazy_loading:
            total_size *= 2  # Images double the size
        
        return total_size / (1024 * 1024)  # Convert to MB

    @api.model
    def get_recommended_config(self, product_count, device_type='desktop'):
        """Get recommended configuration based on product count and device"""
        if product_count < 1000:
            strategy = 'priority'
            cache_size = 20
            preload_count = product_count
        elif product_count < 5000:
            strategy = 'hybrid'
            cache_size = 50
            preload_count = 1000
        else:
            strategy = 'lazy'
            cache_size = 100
            preload_count = 500
        
        if device_type == 'mobile':
            cache_size = int(cache_size * 0.5)
            preload_count = int(preload_count * 0.5)
        
        return {
            'cache_strategy': strategy,
            'cache_size_limit_mb': cache_size,
            'preload_products_count': preload_count,
            'enable_compression': True,
            'enable_image_lazy_loading': True,
        }
