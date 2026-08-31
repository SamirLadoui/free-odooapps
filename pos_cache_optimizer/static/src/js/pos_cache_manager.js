odoo.define('pos_cache_optimizer.CacheManager', function (require) {
"use strict";

var core = require('web.core');
var rpc = require('web.rpc');
var Session = require('web.session');

var _t = core._t;

/**
 * POS Cache Manager
 * Handles intelligent caching of products for POS performance optimization
 */
var PosCacheManager = core.Class.extend({

    init: function(pos) {
        this.pos = pos;
        this.config = null;
        this.cache = new Map();
        this.imageCache = new Map();
        this.searchCache = new Map();
        this.cacheStats = {
            hits: 0,
            misses: 0,
            totalRequests: 0,
            totalSize: 0,
            startTime: Date.now()
        };
        this.compressionSupported = this._checkCompressionSupport();
        this.indexedDBSupported = this._checkIndexedDBSupport();
        this.maxCacheSize = 50 * 1024 * 1024; // 50MB default
        this.isInitialized = false;
    },

    /**
     * Initialize cache manager with POS config
     */
    initialize: function() {
        if (this.isInitialized) return Promise.resolve();
        
        console.log('[POS Cache] Initializing cache manager...');
        
        return this._loadCacheConfig().then(() => {
            this._setupCacheStrategy();
            this._initializeStorage();
            this._startBackgroundSync();
            this.isInitialized = true;
            console.log('[POS Cache] Cache manager initialized successfully');
        });
    },

    /**
     * Load cache configuration from server
     */
    _loadCacheConfig: function() {
        return rpc.query({
            route: '/pos_cache/config',
            params: {
                config_id: this.pos.config.id
            }
        }).then((result) => {
            if (result.success) {
                this.config = result.config;
                this.maxCacheSize = (this.config.cache_size_limit || 50) * 1024 * 1024;
                console.log('[POS Cache] Configuration loaded:', this.config);
            } else {
                console.error('[POS Cache] Failed to load configuration:', result.error);
                this._setDefaultConfig();
            }
        }).catch((error) => {
            console.error('[POS Cache] Error loading configuration:', error);
            this._setDefaultConfig();
        });
    },

    _setDefaultConfig: function() {
        this.config = {
            enable_product_cache: true,
            cache_strategy: 'hybrid',
            cache_size_limit: 50,
            preload_products_count: 500,
            enable_image_lazy_loading: true,
            cache_compression: true,
            cache_expiry_hours: 24,
            enable_background_sync: true
        };
    },

    /**
     * Setup cache strategy based on configuration
     */
    _setupCacheStrategy: function() {
        this.strategy = this.config.cache_strategy || 'hybrid';
        console.log(`[POS Cache] Using strategy: ${this.strategy}`);
        
        switch (this.strategy) {
            case 'lazy':
                this.loadProducts = this._lazyLoadProducts.bind(this);
                break;
            case 'category':
                this.loadProducts = this._categoryBasedLoad.bind(this);
                break;
            case 'priority':
                this.loadProducts = this._priorityBasedLoad.bind(this);
                break;
            default: // hybrid
                this.loadProducts = this._hybridLoad.bind(this);
        }
    },

    /**
     * Initialize storage based on browser capabilities
     */
    _initializeStorage: function() {
        if (this.indexedDBSupported) {
            this._initIndexedDB();
        } else {
            this._initLocalStorage();
        }
    },

    /**
     * Load products using configured strategy
     */
    loadProducts: function(params) {
        // This will be replaced by strategy-specific method
        return this._hybridLoad(params);
    },

    /**
     * Hybrid loading strategy (recommended)
     */
    _hybridLoad: function(params = {}) {
        const cacheKey = this._generateCacheKey('products', params);
        
        // Check cache first
        if (this.cache.has(cacheKey) && !this._isCacheExpired(cacheKey)) {
            this.cacheStats.hits++;
            this.cacheStats.totalRequests++;
            return Promise.resolve(this.cache.get(cacheKey).data);
        }

        // Cache miss - load from server
        this.cacheStats.misses++;
        this.cacheStats.totalRequests++;

        return rpc.query({
            route: '/pos_cache/products',
            params: {
                config_id: this.pos.config.id,
                ...params
            }
        }).then((result) => {
            if (result.success) {
                let products = result.products;
                
                // Handle compressed data
                if (this._isCompressedData(products)) {
                    products = this._decompressData(products);
                }
                
                // Cache the results
                this._cacheProducts(cacheKey, products);
                
                // Update performance metrics
                this._updatePerformanceMetrics(result.load_time);
                
                return products;
            } else {
                console.error('[POS Cache] Error loading products:', result.error);
                return [];
            }
        });
    },

    /**
     * Lazy loading strategy
     */
    _lazyLoadProducts: function(params = {}) {
        const limit = params.limit || 100;
        const offset = params.offset || 0;
        
        return this.loadProducts({
            ...params,
            limit: limit,
            offset: offset
        });
    },

    /**
     * Category-based loading strategy
     */
    _categoryBasedLoad: function(params = {}) {
        const categoryId = params.category_id;
        
        if (categoryId) {
            return rpc.query({
                route: '/pos_cache/products/category',
                params: {
                    config_id: this.pos.config.id,
                    category_id: categoryId,
                    offset: params.offset || 0,
                    limit: params.limit || 100
                }
            }).then((result) => {
                if (result.success) {
                    return result.products;
                }
                return [];
            });
        }
        
        return this.loadProducts(params);
    },

    /**
     * Priority-based loading strategy
     */
    _priorityBasedLoad: function(params = {}) {
        // Load priority products first
        return this.loadProducts({
            ...params,
            priority_first: true
        });
    },

    /**
     * Search products with caching
     */
    searchProducts: function(searchTerm, limit = 50) {
        if (!searchTerm || searchTerm.length < 2) {
            return Promise.resolve([]);
        }

        const cacheKey = `search_${searchTerm.toLowerCase()}_${limit}`;
        
        // Check search cache
        if (this.searchCache.has(cacheKey)) {
            this.cacheStats.hits++;
            return Promise.resolve(this.searchCache.get(cacheKey));
        }

        this.cacheStats.misses++;

        return rpc.query({
            route: '/pos_cache/products/search',
            params: {
                config_id: this.pos.config.id,
                search_term: searchTerm,
                limit: limit
            }
        }).then((result) => {
            if (result.success) {
                let products = result.products;
                
                if (this._isCompressedData(products)) {
                    products = this._decompressData(products);
                }
                
                // Cache search results
                this.searchCache.set(cacheKey, products);
                
                // Limit search cache size
                if (this.searchCache.size > 100) {
                    const firstKey = this.searchCache.keys().next().value;
                    this.searchCache.delete(firstKey);
                }
                
                return products;
            }
            return [];
        });
    },

    /**
     * Load product images lazily
     */
    loadProductImages: function(productIds) {
        const uncachedIds = productIds.filter(id => !this.imageCache.has(id));
        
        if (uncachedIds.length === 0) {
            const images = {};
            productIds.forEach(id => {
                if (this.imageCache.has(id)) {
                    images[id] = this.imageCache.get(id);
                }
            });
            return Promise.resolve(images);
        }

        return rpc.query({
            route: '/pos_cache/products/images',
            params: {
                product_ids: uncachedIds
            }
        }).then((result) => {
            if (result.success) {
                // Cache images
                Object.entries(result.images).forEach(([id, image]) => {
                    this.imageCache.set(parseInt(id), image);
                });
                
                // Return all requested images
                const images = {};
                productIds.forEach(id => {
                    if (this.imageCache.has(id)) {
                        images[id] = this.imageCache.get(id);
                    }
                });
                
                return images;
            }
            return {};
        });
    },

    /**
     * Warmup cache with priority products
     */
    warmupCache: function() {
        console.log('[POS Cache] Starting cache warmup...');
        
        return rpc.query({
            route: '/pos_cache/warmup',
            params: {
                config_id: this.pos.config.id
            }
        }).then((result) => {
            if (result.success) {
                let products = result.products;
                
                if (this._isCompressedData(products)) {
                    products = this._decompressData(products);
                }
                
                // Cache warmup products
                this._cacheProducts('warmup_products', products);
                
                console.log(`[POS Cache] Cache warmed up with ${result.products_count} products in ${result.warmup_time}ms`);
                return products;
            }
            return [];
        });
    },

    /**
     * Clear all caches
     */
    clearCache: function() {
        console.log('[POS Cache] Clearing all caches...');
        
        this.cache.clear();
        this.imageCache.clear();
        this.searchCache.clear();
        
        // Clear localStorage
        if (typeof Storage !== 'undefined') {
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith('pos_cache_')) {
                    localStorage.removeItem(key);
                }
            });
        }
        
        // Clear IndexedDB if supported
        if (this.indexedDBSupported) {
            this._clearIndexedDB();
        }
        
        // Reset stats
        this.cacheStats = {
            hits: 0,
            misses: 0,
            totalRequests: 0,
            totalSize: 0,
            startTime: Date.now()
        };
        
        return rpc.query({
            route: '/pos_cache/clear',
            params: {
                config_id: this.pos.config.id
            }
        });
    },

    /**
     * Get cache statistics
     */
    getCacheStats: function() {
        const totalRequests = this.cacheStats.hits + this.cacheStats.misses;
        const hitRatio = totalRequests > 0 ? (this.cacheStats.hits / totalRequests) * 100 : 0;
        const uptime = (Date.now() - this.cacheStats.startTime) / 1000 / 60; // minutes

        return {
            hitRatio: hitRatio.toFixed(2),
            totalRequests: totalRequests,
            cacheHits: this.cacheStats.hits,
            cacheMisses: this.cacheStats.misses,
            cacheSize: this._getCacheSizeFormatted(),
            uptimeMinutes: uptime.toFixed(1),
            strategy: this.strategy
        };
    },

    // Utility methods

    _generateCacheKey: function(type, params) {
        const key = `${type}_${JSON.stringify(params)}`;
        return key;
    },

    _isCacheExpired: function(cacheKey) {
        const item = this.cache.get(cacheKey);
        if (!item) return true;
        
        const expiryTime = this.config.cache_expiry_hours * 60 * 60 * 1000;
        return (Date.now() - item.timestamp) > expiryTime;
    },

    _cacheProducts: function(key, products) {
        const data = {
            data: products,
            timestamp: Date.now(),
            size: this._calculateDataSize(products)
        };
        
        // Check cache size limits
        if (this._getTotalCacheSize() + data.size > this.maxCacheSize) {
            this._evictOldestItems();
        }
        
        this.cache.set(key, data);
        this.cacheStats.totalSize += data.size;
    },

    _isCompressedData: function(data) {
        return data && typeof data === 'object' && data.compressed === true;
    },

    _decompressData: function(compressedData) {
        // This would typically be handled by the server
        // For now, return the data as-is if it's not compressed
        if (compressedData.data) {
            try {
                // In a real implementation, you'd decompress here
                return JSON.parse(atob(compressedData.data));
            } catch (e) {
                console.error('[POS Cache] Error decompressing data:', e);
                return [];
            }
        }
        return compressedData;
    },

    _calculateDataSize: function(data) {
        return JSON.stringify(data).length;
    },

    _getTotalCacheSize: function() {
        let total = 0;
        this.cache.forEach(item => {
            total += item.size;
        });
        return total;
    },

    _getCacheSizeFormatted: function() {
        const size = this._getTotalCacheSize();
        if (size < 1024) return size + ' B';
        if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
        return (size / (1024 * 1024)).toFixed(1) + ' MB';
    },

    _evictOldestItems: function() {
        // Simple LRU eviction
        const entries = Array.from(this.cache.entries());
        entries.sort((a, b) => a[1].timestamp - b[1].timestamp);
        
        // Remove oldest 25% of items
        const removeCount = Math.floor(entries.length * 0.25);
        for (let i = 0; i < removeCount; i++) {
            this.cache.delete(entries[i][0]);
        }
    },

    _updatePerformanceMetrics: function(loadTime) {
        // Update analytics on server
        if (this.pos.pos_session && this.pos.pos_session.id) {
            const stats = this.getCacheStats();
            rpc.query({
                route: '/pos_cache/analytics/update',
                params: {
                    session_id: this.pos.pos_session.id,
                    metrics: {
                        cache_hit_ratio: parseFloat(stats.hitRatio),
                        avg_load_time: loadTime,
                        total_requests: stats.totalRequests,
                        cache_hits: stats.cacheHits,
                        cache_misses: stats.cacheMisses,
                        total_products_cached: this.cache.size,
                        cache_size_mb: this._getTotalCacheSize() / (1024 * 1024)
                    }
                }
            }).catch(error => {
                console.error('[POS Cache] Error updating analytics:', error);
            });
        }
    },

    _startBackgroundSync: function() {
        if (!this.config.enable_background_sync) return;
        
        // Sync cache every 5 minutes
        setInterval(() => {
            this._backgroundCacheUpdate();
        }, 5 * 60 * 1000);
    },

    _backgroundCacheUpdate: function() {
        // Update cache with new/modified products
        console.log('[POS Cache] Running background cache update...');
        // Implementation would check for updated products and refresh cache
    },

    _checkCompressionSupport: function() {
        return typeof TextEncoder !== 'undefined' && typeof TextDecoder !== 'undefined';
    },

    _checkIndexedDBSupport: function() {
        return typeof indexedDB !== 'undefined';
    },

    _initIndexedDB: function() {
        // Initialize IndexedDB for persistent caching
        console.log('[POS Cache] IndexedDB supported - enabling persistent cache');
    },

    _initLocalStorage: function() {
        // Fallback to localStorage
        console.log('[POS Cache] Using localStorage for caching');
    },

    _clearIndexedDB: function() {
        // Clear IndexedDB cache
        console.log('[POS Cache] Clearing IndexedDB cache');
    }

});

return PosCacheManager;

});
