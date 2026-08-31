# -*- coding: utf-8 -*-

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # POS Cache Global Settings
    pos_cache_global_enable = fields.Boolean(
        string='Enable POS Cache Globally',
        config_parameter='pos_cache_optimizer.global_enable',
        default=True,
        help='Enable POS cache optimization globally for all POS configurations'
    )
    
    pos_cache_default_strategy = fields.Selection([
        ('lazy', 'Lazy Loading'),
        ('category', 'Category Based'),
        ('priority', 'Priority Based'),
        ('hybrid', 'Hybrid (Recommended)')
    ], string='Default Cache Strategy',
       config_parameter='pos_cache_optimizer.default_strategy',
       default='hybrid',
       help='Default cache strategy for new POS configurations')
    
    pos_cache_default_size_limit = fields.Integer(
        string='Default Cache Size Limit (MB)',
        config_parameter='pos_cache_optimizer.default_size_limit',
        default=50,
        help='Default maximum memory usage for product cache in browser'
    )
    
    pos_cache_default_preload_count = fields.Integer(
        string='Default Preload Products Count',
        config_parameter='pos_cache_optimizer.default_preload_count',
        default=500,
        help='Default number of products to preload immediately'
    )
    
    pos_cache_compression_enable = fields.Boolean(
        string='Enable Cache Compression by Default',
        config_parameter='pos_cache_optimizer.compression_enable',
        default=True,
        help='Enable data compression by default for new POS configurations'
    )
    
    pos_cache_image_lazy_loading = fields.Boolean(
        string='Enable Image Lazy Loading by Default',
        config_parameter='pos_cache_optimizer.image_lazy_loading',
        default=True,
        help='Enable image lazy loading by default for new POS configurations'
    )
    
    pos_cache_analytics_retention_days = fields.Integer(
        string='Analytics Retention (Days)',
        config_parameter='pos_cache_optimizer.analytics_retention_days',
        default=30,
        help='Number of days to keep cache analytics data'
    )
    
    pos_cache_background_sync_enable = fields.Boolean(
        string='Enable Background Sync by Default',
        config_parameter='pos_cache_optimizer.background_sync_enable',
        default=True,
        help='Enable background cache updates by default'
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        
        # Load POS cache settings
        ICPSudo = self.env['ir.config_parameter'].sudo()
        
        res.update({
            'pos_cache_global_enable': ICPSudo.get_param('pos_cache_optimizer.global_enable', True),
            'pos_cache_default_strategy': ICPSudo.get_param('pos_cache_optimizer.default_strategy', 'hybrid'),
            'pos_cache_default_size_limit': int(ICPSudo.get_param('pos_cache_optimizer.default_size_limit', 50)),
            'pos_cache_default_preload_count': int(ICPSudo.get_param('pos_cache_optimizer.default_preload_count', 500)),
            'pos_cache_compression_enable': ICPSudo.get_param('pos_cache_optimizer.compression_enable', True),
            'pos_cache_image_lazy_loading': ICPSudo.get_param('pos_cache_optimizer.image_lazy_loading', True),
            'pos_cache_analytics_retention_days': int(ICPSudo.get_param('pos_cache_optimizer.analytics_retention_days', 30)),
            'pos_cache_background_sync_enable': ICPSudo.get_param('pos_cache_optimizer.background_sync_enable', True),
        })
        
        return res

    def set_values(self):
        super().set_values()
        
        # Save POS cache settings
        ICPSudo = self.env['ir.config_parameter'].sudo()
        
        ICPSudo.set_param('pos_cache_optimizer.global_enable', self.pos_cache_global_enable)
        ICPSudo.set_param('pos_cache_optimizer.default_strategy', self.pos_cache_default_strategy)
        ICPSudo.set_param('pos_cache_optimizer.default_size_limit', self.pos_cache_default_size_limit)
        ICPSudo.set_param('pos_cache_optimizer.default_preload_count', self.pos_cache_default_preload_count)
        ICPSudo.set_param('pos_cache_optimizer.compression_enable', self.pos_cache_compression_enable)
        ICPSudo.set_param('pos_cache_optimizer.image_lazy_loading', self.pos_cache_image_lazy_loading)
        ICPSudo.set_param('pos_cache_optimizer.analytics_retention_days', self.pos_cache_analytics_retention_days)
        ICPSudo.set_param('pos_cache_optimizer.background_sync_enable', self.pos_cache_background_sync_enable)

    def action_apply_default_cache_settings(self):
        """Apply default cache settings to all POS configurations"""
        pos_configs = self.env['pos.config'].search([])
        
        default_values = {
            'enable_product_cache': self.pos_cache_global_enable,
            'cache_strategy': self.pos_cache_default_strategy,
            'cache_size_limit': self.pos_cache_default_size_limit,
            'preload_products_count': self.pos_cache_default_preload_count,
            'cache_compression': self.pos_cache_compression_enable,
            'enable_image_lazy_loading': self.pos_cache_image_lazy_loading,
            'enable_background_sync': self.pos_cache_background_sync_enable,
        }
        
        pos_configs.write(default_values)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Default cache settings applied to {len(pos_configs)} POS configurations.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_optimize_all_products_cache(self):
        """Optimize all products for cache performance"""
        products = self.env['product.template'].search([
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True)
        ])
        
        products.action_optimize_for_cache()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Cache optimization applied to {len(products)} products.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cleanup_old_analytics(self):
        """Clean up old analytics data"""
        analytics_model = self.env['pos.cache.analytics']
        analytics_model.cleanup_old_analytics(self.pos_cache_analytics_retention_days)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Old analytics data cleaned up successfully.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_cache_analytics(self):
        """View cache analytics dashboard"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'POS Cache Analytics',
            'res_model': 'pos.cache.analytics',
            'view_mode': 'tree,form,pivot,graph',
            'domain': [],
            'context': {'search_default_group_by_config': 1},
        }

    @api.model
    def get_cache_global_stats(self):
        """Get global cache statistics"""
        # Get analytics for all POS configurations
        analytics = self.env['pos.cache.analytics'].search([])
        
        if not analytics:
            return {
                'total_sessions': 0,
                'avg_cache_hit_ratio': 0,
                'avg_load_time': 0,
                'total_products_cached': 0,
                'total_cache_size_mb': 0,
            }
        
        return {
            'total_sessions': len(analytics),
            'avg_cache_hit_ratio': sum(analytics.mapped('cache_hit_ratio')) / len(analytics),
            'avg_load_time': sum(analytics.mapped('avg_load_time')) / len(analytics),
            'total_products_cached': sum(analytics.mapped('total_products_cached')),
            'total_cache_size_mb': sum(analytics.mapped('cache_size_mb')),
        }
