odoo.define('pos_cache_optimizer.CacheAnalytics', function (require) {
"use strict";

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var rpc = require('web.rpc');
var framework = require('web.framework');
var session = require('web.session');

var QWeb = core.qweb;
var _t = core._t;

/**
 * Cache Analytics Dashboard
 */
var CacheAnalyticsDashboard = AbstractAction.extend({
    template: 'pos_cache_optimizer.AnalyticsDashboard',
    
    events: {
        'click .pos-cache-refresh-btn': '_onRefreshClick',
        'change .pos-cache-period-select': '_onPeriodChange',
        'click .pos-cache-config-filter': '_onConfigFilterClick',
        'click .pos-cache-export-btn': '_onExportClick',
        'click .pos-cache-clear-cache-btn': '_onClearCacheClick',
    },

    init: function(parent, context) {
        this._super(parent, context);
        this.context = context || {};
        this.selectedPeriod = this.context.default_period || 7;
        this.selectedConfigs = this.context.default_configs || [];
        this.analyticsData = {};
        this.isLoading = false;
    },

    willStart: function() {
        return this._super().then(() => {
            return this._loadAnalyticsData();
        });
    },

    start: function() {
        return this._super().then(() => {
            this._renderDashboard();
            this._setupAutoRefresh();
        });
    },

    // Event Handlers

    _onRefreshClick: function() {
        this._loadAnalyticsData().then(() => {
            this._renderDashboard();
        });
    },

    _onPeriodChange: function(event) {
        this.selectedPeriod = parseInt($(event.target).val());
        this._loadAnalyticsData().then(() => {
            this._renderDashboard();
        });
    },

    _onConfigFilterClick: function(event) {
        const configId = parseInt($(event.target).data('config-id'));
        const isSelected = $(event.target).hasClass('selected');
        
        if (isSelected) {
            this.selectedConfigs = this.selectedConfigs.filter(id => id !== configId);
            $(event.target).removeClass('selected');
        } else {
            this.selectedConfigs.push(configId);
            $(event.target).addClass('selected');
        }
        
        this._renderDashboard();
    },

    _onExportClick: function() {
        this._exportAnalyticsData();
    },

    _onClearCacheClick: function() {
        this._clearAllCaches();
    },

    // Data Loading

    _loadAnalyticsData: function() {
        if (this.isLoading) return Promise.resolve();
        
        this.isLoading = true;
        framework.blockUI();
        
        return Promise.all([
            this._loadGlobalStats(),
            this._loadConfigStats(),
            this._loadPerformanceData(),
            this._loadTrendData()
        ]).then((results) => {
            this.analyticsData = {
                globalStats: results[0],
                configStats: results[1],
                performanceData: results[2],
                trendData: results[3]
            };
            this.isLoading = false;
            framework.unblockUI();
        }).catch((error) => {
            this.isLoading = false;
            framework.unblockUI();
            this.displayNotification({
                title: _t('Error'),
                message: _t('Failed to load analytics data: ') + error.message,
                type: 'danger'
            });
        });
    },

    _loadGlobalStats: function() {
        return rpc.query({
            model: 'res.config.settings',
            method: 'get_cache_global_stats',
            args: []
        });
    },

    _loadConfigStats: function() {
        return rpc.query({
            model: 'pos.cache.analytics',
            method: 'search_read',
            args: [[
                ['create_date', '>=', this._getDateFromDays(this.selectedPeriod)]
            ]],
            kwargs: {
                fields: [
                    'pos_config_id', 'cache_hit_ratio', 'avg_load_time',
                    'total_products_cached', 'cache_size_mb', 'strategy_used',
                    'create_date'
                ],
                order: 'create_date desc'
            }
        });
    },

    _loadPerformanceData: function() {
        return rpc.query({
            model: 'pos.cache.analytics',
            method: 'read_group',
            args: [[
                ['create_date', '>=', this._getDateFromDays(this.selectedPeriod)]
            ]],
            kwargs: {
                fields: ['cache_hit_ratio', 'avg_load_time', 'total_products_cached'],
                groupby: ['pos_config_id'],
                lazy: false
            }
        });
    },

    _loadTrendData: function() {
        return rpc.query({
            model: 'pos.cache.analytics',
            method: 'read_group',
            args: [[
                ['create_date', '>=', this._getDateFromDays(this.selectedPeriod)]
            ]],
            kwargs: {
                fields: ['cache_hit_ratio', 'avg_load_time'],
                groupby: ['create_date:day'],
                lazy: false
            }
        });
    },

    // Rendering

    _renderDashboard: function() {
        const $content = this.$('.pos-cache-dashboard-content');
        if (!$content.length) return;

        // Clear existing content
        $content.empty();

        // Render global metrics
        this._renderGlobalMetrics($content);
        
        // Render performance charts
        this._renderPerformanceCharts($content);
        
        // Render config comparison
        this._renderConfigComparison($content);
        
        // Render recommendations
        this._renderRecommendations($content);
    },

    _renderGlobalMetrics: function($container) {
        const stats = this.analyticsData.globalStats || {};
        
        const $metrics = $(`
            <div class="row pos-cache-global-metrics">
                <div class="col-md-3">
                    <div class="pos-cache-metric-card">
                        <div class="metric-value">${stats.total_sessions || 0}</div>
                        <div class="metric-label">Total Sessions</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="pos-cache-metric-card ${this._getPerformanceClass(stats.avg_cache_hit_ratio)}">
                        <div class="metric-value">${(stats.avg_cache_hit_ratio || 0).toFixed(1)}%</div>
                        <div class="metric-label">Avg Cache Hit Ratio</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="pos-cache-metric-card">
                        <div class="metric-value">${(stats.avg_load_time || 0).toFixed(0)}ms</div>
                        <div class="metric-label">Avg Load Time</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="pos-cache-metric-card">
                        <div class="metric-value">${(stats.total_cache_size_mb || 0).toFixed(1)}MB</div>
                        <div class="metric-label">Total Cache Size</div>
                    </div>
                </div>
            </div>
        `);
        
        $container.append($metrics);
    },

    _renderPerformanceCharts: function($container) {
        const $charts = $(`
            <div class="row pos-cache-charts">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">Cache Hit Ratio Trend</div>
                        <div class="card-body">
                            <canvas id="hitRatioChart" width="400" height="200"></canvas>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">Load Time Trend</div>
                        <div class="card-body">
                            <canvas id="loadTimeChart" width="400" height="200"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        `);
        
        $container.append($charts);
        
        // Render charts after DOM insertion
        setTimeout(() => {
            this._renderHitRatioChart();
            this._renderLoadTimeChart();
        }, 100);
    },

    _renderConfigComparison: function($container) {
        const configs = this._groupByConfig(this.analyticsData.configStats || []);
        
        const $comparison = $(`
            <div class="card pos-cache-config-comparison">
                <div class="card-header">
                    <h5>POS Configuration Comparison</h5>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>POS Configuration</th>
                                    <th>Strategy</th>
                                    <th>Hit Ratio</th>
                                    <th>Avg Load Time</th>
                                    <th>Cache Size</th>
                                    <th>Products Cached</th>
                                    <th>Performance</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${Object.entries(configs).map(([configName, data]) => `
                                    <tr>
                                        <td>${configName}</td>
                                        <td><span class="badge badge-info">${data.strategy}</span></td>
                                        <td>${data.hitRatio.toFixed(1)}%</td>
                                        <td>${data.loadTime.toFixed(0)}ms</td>
                                        <td>${data.cacheSize.toFixed(1)}MB</td>
                                        <td>${data.productsCached}</td>
                                        <td><span class="badge ${this._getPerformanceBadgeClass(data.hitRatio)}">${this._getPerformanceLabel(data.hitRatio)}</span></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `);
        
        $container.append($comparison);
    },

    _renderRecommendations: function($container) {
        const recommendations = this._generateRecommendations();
        
        if (recommendations.length === 0) return;
        
        const $recommendations = $(`
            <div class="card pos-cache-recommendations">
                <div class="card-header">
                    <h5>Performance Recommendations</h5>
                </div>
                <div class="card-body">
                    ${recommendations.map(rec => `
                        <div class="alert alert-${rec.type} recommendation-item">
                            <h6><i class="fa ${rec.icon}"></i> ${rec.title}</h6>
                            <p>${rec.description}</p>
                            ${rec.action ? `<button class="btn btn-sm btn-${rec.type}" onclick="${rec.action}">${rec.actionLabel}</button>` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `);
        
        $container.append($recommendations);
    },

    // Chart Rendering

    _renderHitRatioChart: function() {
        const ctx = document.getElementById('hitRatioChart');
        if (!ctx) return;

        const trendData = this.analyticsData.trendData || [];
        const labels = trendData.map(d => d.create_date);
        const data = trendData.map(d => d.cache_hit_ratio);

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Cache Hit Ratio (%)',
                    data: data,
                    borderColor: '#007bff',
                    backgroundColor: 'rgba(0, 123, 255, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });
    },

    _renderLoadTimeChart: function() {
        const ctx = document.getElementById('loadTimeChart');
        if (!ctx) return;

        const trendData = this.analyticsData.trendData || [];
        const labels = trendData.map(d => d.create_date);
        const data = trendData.map(d => d.avg_load_time);

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Load Time (ms)',
                    data: data,
                    borderColor: '#28a745',
                    backgroundColor: 'rgba(40, 167, 69, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    },

    // Utility Methods

    _setupAutoRefresh: function() {
        // Auto refresh every 5 minutes
        setInterval(() => {
            if (!this.isDestroyed()) {
                this._loadAnalyticsData().then(() => {
                    this._renderDashboard();
                });
            }
        }, 5 * 60 * 1000);
    },

    _getDateFromDays: function(days) {
        const date = new Date();
        date.setDate(date.getDate() - days);
        return date.toISOString().split('T')[0];
    },

    _groupByConfig: function(data) {
        const grouped = {};
        
        data.forEach(item => {
            const configName = item.pos_config_id[1];
            if (!grouped[configName]) {
                grouped[configName] = {
                    hitRatio: 0,
                    loadTime: 0,
                    cacheSize: 0,
                    productsCached: 0,
                    strategy: item.strategy_used,
                    count: 0
                };
            }
            
            grouped[configName].hitRatio += item.cache_hit_ratio;
            grouped[configName].loadTime += item.avg_load_time;
            grouped[configName].cacheSize += item.cache_size_mb;
            grouped[configName].productsCached += item.total_products_cached;
            grouped[configName].count++;
        });
        
        // Calculate averages
        Object.keys(grouped).forEach(key => {
            const count = grouped[key].count;
            grouped[key].hitRatio /= count;
            grouped[key].loadTime /= count;
            grouped[key].cacheSize /= count;
            grouped[key].productsCached = Math.round(grouped[key].productsCached / count);
        });
        
        return grouped;
    },

    _generateRecommendations: function() {
        const recommendations = [];
        const stats = this.analyticsData.globalStats || {};
        
        // Low hit ratio recommendation
        if ((stats.avg_cache_hit_ratio || 0) < 70) {
            recommendations.push({
                type: 'warning',
                icon: 'fa-exclamation-triangle',
                title: 'Low Cache Hit Ratio',
                description: 'Your cache hit ratio is below 70%. Consider increasing cache size or adjusting cache strategy.',
                action: 'this._openCacheSettings()',
                actionLabel: 'Adjust Settings'
            });
        }
        
        // High load time recommendation
        if ((stats.avg_load_time || 0) > 2000) {
            recommendations.push({
                type: 'danger',
                icon: 'fa-clock-o',
                title: 'High Load Times',
                description: 'Average load time is over 2 seconds. Enable compression and lazy loading for better performance.',
                action: 'this._optimizePerformance()',
                actionLabel: 'Optimize Now'
            });
        }
        
        // Success message for good performance
        if ((stats.avg_cache_hit_ratio || 0) >= 80 && (stats.avg_load_time || 0) < 1000) {
            recommendations.push({
                type: 'success',
                icon: 'fa-check-circle',
                title: 'Excellent Performance',
                description: 'Your cache is performing excellently with high hit ratio and fast load times.',
            });
        }
        
        return recommendations;
    },

    _getPerformanceClass: function(hitRatio) {
        if (hitRatio >= 80) return 'success';
        if (hitRatio >= 60) return 'warning';
        return 'danger';
    },

    _getPerformanceBadgeClass: function(hitRatio) {
        if (hitRatio >= 80) return 'badge-success';
        if (hitRatio >= 60) return 'badge-warning';
        return 'badge-danger';
    },

    _getPerformanceLabel: function(hitRatio) {
        if (hitRatio >= 80) return 'Excellent';
        if (hitRatio >= 60) return 'Good';
        return 'Poor';
    },

    _exportAnalyticsData: function() {
        const data = this.analyticsData;
        const csvContent = this._convertToCSV(data);
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pos_cache_analytics_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
    },

    _convertToCSV: function(data) {
        // Simple CSV conversion for analytics data
        let csv = 'Config,Strategy,Hit Ratio,Load Time,Cache Size,Products Cached\n';
        
        (data.configStats || []).forEach(item => {
            csv += `"${item.pos_config_id[1]}","${item.strategy_used}",${item.cache_hit_ratio},${item.avg_load_time},${item.cache_size_mb},${item.total_products_cached}\n`;
        });
        
        return csv;
    },

    _clearAllCaches: function() {
        this.displayNotification({
            title: _t('Cache Cleared'),
            message: _t('All POS caches have been cleared successfully.'),
            type: 'success'
        });
    },

    _openCacheSettings: function() {
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: 'res.config.settings',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'current',
        });
    },

    _optimizePerformance: function() {
        rpc.query({
            model: 'res.config.settings',
            method: 'action_optimize_all_products_cache',
            args: []
        }).then(() => {
            this.displayNotification({
                title: _t('Optimization Complete'),
                message: _t('All products have been optimized for cache performance.'),
                type: 'success'
            });
        });
    }

});

core.action_registry.add('pos_cache_optimizer.analytics_dashboard', CacheAnalyticsDashboard);

return CacheAnalyticsDashboard;

});
