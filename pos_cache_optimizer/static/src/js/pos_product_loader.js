odoo.define('pos_cache_optimizer.ProductLoader', function (require) {
"use strict";

var models = require('point_of_sale.models');
var PosCacheManager = require('pos_cache_optimizer.CacheManager');
var core = require('web.core');

var _t = core._t;

// Extend PosModel to integrate cache manager
var PosModelParent = models.PosModel;
models.PosModel = models.PosModel.extend({

    initialize: function(session, attributes) {
        var self = this;
        
        // Initialize cache manager
        this.cacheManager = new PosCacheManager(this);
        
        // Call parent initialize
        PosModelParent.prototype.initialize.call(this, session, attributes);
    },

    // Override product loading to use cache
    load_server_data: function() {
        var self = this;
        
        return PosModelParent.prototype.load_server_data.call(this).then(function() {
            // Initialize cache manager after POS is loaded
            if (self.config.enable_product_cache) {
                return self.cacheManager.initialize().then(function() {
                    console.log('[POS Cache] Cache manager ready');
                    // Warmup cache if configured
                    if (self.config.cache_strategy === 'priority' || self.config.cache_strategy === 'hybrid') {
                        return self.cacheManager.warmupCache();
                    }
                });
            }
        });
    },

    // Enhanced product loading with cache
    load_products_with_cache: function(params) {
        if (!this.cacheManager || !this.config.enable_product_cache) {
            return this._load_products_legacy(params);
        }
        
        return this.cacheManager.loadProducts(params);
    },

    // Legacy product loading fallback
    _load_products_legacy: function(params) {
        var domain = this._get_product_domain();
        
        return this.rpc({
            model: 'product.product',
            method: 'search_read',
            args: [domain],
            kwargs: {
                limit: params.limit || 1000,
                offset: params.offset || 0,
                fields: this._get_product_fields()
            }
        });
    },

    // Get products by category with cache
    get_products_by_category: function(category, limit, offset) {
        if (!this.cacheManager || !this.config.enable_product_cache) {
            return this._get_products_by_category_legacy(category, limit, offset);
        }
        
        var categoryId = category ? category.id : null;
        return this.cacheManager.loadProducts({
            category_id: categoryId,
            limit: limit || 100,
            offset: offset || 0
        });
    },

    _get_products_by_category_legacy: function(category, limit, offset) {
        var domain = this._get_product_domain();
        if (category) {
            domain.push(['pos_categ_id', '=', category.id]);
        }
        
        return this.rpc({
            model: 'product.product',
            method: 'search_read',
            args: [domain],
            kwargs: {
                limit: limit || 100,
                offset: offset || 0,
                fields: this._get_product_fields()
            }
        });
    },

    // Enhanced product search with cache
    search_products: function(searchTerm, limit) {
        if (!this.cacheManager || !this.config.enable_product_cache) {
            return this._search_products_legacy(searchTerm, limit);
        }
        
        return this.cacheManager.searchProducts(searchTerm, limit);
    },

    _search_products_legacy: function(searchTerm, limit) {
        var domain = this._get_product_domain();
        
        if (searchTerm) {
            domain.push([
                '|', '|', '|',
                ['name', 'ilike', searchTerm],
                ['default_code', 'ilike', searchTerm],
                ['barcode', 'ilike', searchTerm],
                ['description_sale', 'ilike', searchTerm]
            ]);
        }
        
        return this.rpc({
            model: 'product.product',
            method: 'search_read',
            args: [domain],
            kwargs: {
                limit: limit || 50,
                fields: this._get_product_fields()
            }
        });
    },

    // Load product images lazily
    load_product_images: function(productIds) {
        if (!this.cacheManager || !this.config.enable_image_lazy_loading) {
            return Promise.resolve({});
        }
        
        return this.cacheManager.loadProductImages(productIds);
    },

    // Get cache statistics
    get_cache_stats: function() {
        if (!this.cacheManager) {
            return {
                hitRatio: 0,
                totalRequests: 0,
                cacheSize: '0 B',
                strategy: 'disabled'
            };
        }
        
        return this.cacheManager.getCacheStats();
    },

    // Clear cache
    clear_product_cache: function() {
        if (this.cacheManager) {
            return this.cacheManager.clearCache();
        }
        return Promise.resolve();
    },

    // Utility methods
    _get_product_domain: function() {
        var domain = [
            ['sale_ok', '=', true],
            ['available_in_pos', '=', true]
        ];
        
        if (this.config.iface_available_categ_ids && this.config.iface_available_categ_ids.length > 0) {
            domain.push(['pos_categ_id', 'in', this.config.iface_available_categ_ids]);
        }
        
        return domain;
    },

    _get_product_fields: function() {
        return [
            'id', 'display_name', 'lst_price', 'standard_price', 'categ_id',
            'pos_categ_id', 'taxes_id', 'barcode', 'default_code', 'to_weight',
            'uom_id', 'description_sale', 'description', 'product_tmpl_id',
            'tracking', 'available_in_pos', 'image_128'
        ];
    }

});

// Extend ProductScreen to use cached products
var screens = require('point_of_sale.screens');

if (screens.ProductScreenWidget) {
    screens.ProductScreenWidget.include({

        start: function() {
            var self = this;
            var result = this._super();
            
            // Set up cache-aware product loading
            if (this.pos.cacheManager) {
                this._setupCachedProductLoading();
            }
            
            return result;
        },

        _setupCachedProductLoading: function() {
            var self = this;
            
            // Override product list rendering to use lazy loading
            var originalRenderProductList = this.renderElement;
            this.renderElement = function() {
                if (self.pos.config.enable_product_cache) {
                    return self._renderProductListCached();
                }
                return originalRenderProductList.call(this);
            };
        },

        _renderProductListCached: function() {
            var self = this;
            
            // Load initial products with cache
            return this.pos.load_products_with_cache({
                limit: this.pos.config.preload_products_count || 500,
                offset: 0
            }).then(function(products) {
                self._displayProducts(products);
                
                // Set up lazy loading for remaining products
                self._setupLazyLoading();
            });
        },

        _displayProducts: function(products) {
            // Display products in the UI
            // This would integrate with the existing product list rendering
            console.log(`[POS Cache] Displaying ${products.length} products`);
        },

        _setupLazyLoading: function() {
            var self = this;
            
            // Set up intersection observer for lazy loading
            if ('IntersectionObserver' in window) {
                var observer = new IntersectionObserver(function(entries) {
                    entries.forEach(function(entry) {
                        if (entry.isIntersecting) {
                            self._loadMoreProducts();
                        }
                    });
                });
                
                // Observe the bottom of the product list
                var sentinel = this.$('.product-list-bottom')[0];
                if (sentinel) {
                    observer.observe(sentinel);
                }
            }
        },

        _loadMoreProducts: function() {
            // Load more products when scrolling to bottom
            var currentCount = this.$('.product').length;
            
            return this.pos.load_products_with_cache({
                limit: 100,
                offset: currentCount
            }).then((products) => {
                this._appendProducts(products);
            });
        },

        _appendProducts: function(products) {
            // Append new products to the list
            console.log(`[POS Cache] Loaded ${products.length} additional products`);
        },

        // Enhanced search with cache
        search_products: function(searchTerm) {
            if (!this.pos.cacheManager) {
                return this._super(searchTerm);
            }
            
            return this.pos.search_products(searchTerm).then((products) => {
                this._displaySearchResults(products);
                return products;
            });
        },

        _displaySearchResults: function(products) {
            // Display search results
            console.log(`[POS Cache] Search returned ${products.length} products`);
        }

    });
}

// Extend ProductListWidget for category-based loading
if (screens.ProductListWidget) {
    screens.ProductListWidget.include({

        set_category: function(category) {
            var self = this;
            
            if (this.pos.cacheManager && this.pos.config.enable_product_cache) {
                // Load products for this category with cache
                this.pos.get_products_by_category(category, 100, 0).then(function(products) {
                    self._displayCategoryProducts(products, category);
                });
            } else {
                this._super(category);
            }
        },

        _displayCategoryProducts: function(products, category) {
            // Display products for the selected category
            console.log(`[POS Cache] Loaded ${products.length} products for category:`, category);
        }

    });
}

});
