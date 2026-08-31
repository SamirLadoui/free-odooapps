odoo.define('pos_cache_optimizer.LazyLoader', function (require) {
"use strict";

var core = require('web.core');
var rpc = require('web.rpc');

var _t = core._t;

/**
 * Lazy Loader for POS Products
 * Implements smart lazy loading with intersection observer
 */
var PosLazyLoader = core.Class.extend({

    init: function(pos, options) {
        this.pos = pos;
        this.options = _.extend({
            threshold: 0.1,
            rootMargin: '50px',
            batchSize: 100,
            maxConcurrentRequests: 3,
            preloadDistance: 200
        }, options);
        
        this.observer = null;
        this.loadingQueue = [];
        this.activeRequests = 0;
        this.loadedBatches = new Set();
        this.totalProducts = 0;
        this.currentOffset = 0;
        this.isEnabled = false;
        
        this._setupIntersectionObserver();
    },

    /**
     * Enable lazy loading
     */
    enable: function() {
        this.isEnabled = true;
        console.log('[POS Lazy Loader] Enabled');
    },

    /**
     * Disable lazy loading
     */
    disable: function() {
        this.isEnabled = false;
        if (this.observer) {
            this.observer.disconnect();
        }
        console.log('[POS Lazy Loader] Disabled');
    },

    /**
     * Setup intersection observer for lazy loading
     */
    _setupIntersectionObserver: function() {
        if (!window.IntersectionObserver) {
            console.warn('[POS Lazy Loader] IntersectionObserver not supported');
            return;
        }

        this.observer = new IntersectionObserver((entries) => {
            if (!this.isEnabled) return;
            
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this._handleIntersection(entry.target);
                }
            });
        }, {
            threshold: this.options.threshold,
            rootMargin: this.options.rootMargin
        });
    },

    /**
     * Handle intersection event
     */
    _handleIntersection: function(target) {
        const batchId = target.dataset.batchId;
        if (!batchId || this.loadedBatches.has(batchId)) {
            return;
        }

        // Add to loading queue
        this.loadingQueue.push({
            batchId: batchId,
            element: target,
            offset: parseInt(target.dataset.offset) || 0,
            limit: parseInt(target.dataset.limit) || this.options.batchSize
        });

        this._processLoadingQueue();
    },

    /**
     * Process the loading queue
     */
    _processLoadingQueue: function() {
        while (this.loadingQueue.length > 0 && this.activeRequests < this.options.maxConcurrentRequests) {
            const batch = this.loadingQueue.shift();
            this._loadBatch(batch);
        }
    },

    /**
     * Load a batch of products
     */
    _loadBatch: function(batch) {
        if (this.loadedBatches.has(batch.batchId)) {
            return Promise.resolve([]);
        }

        this.activeRequests++;
        this.loadedBatches.add(batch.batchId);

        // Show loading indicator
        this._showLoadingIndicator(batch.element);

        const params = {
            limit: batch.limit,
            offset: batch.offset
        };

        // Add category filter if specified
        if (batch.element.dataset.categoryId) {
            params.category_id = parseInt(batch.element.dataset.categoryId);
        }

        return this.pos.cacheManager.loadProducts(params).then((products) => {
            this.activeRequests--;
            
            // Hide loading indicator
            this._hideLoadingIndicator(batch.element);
            
            // Render products
            this._renderProducts(products, batch.element);
            
            // Continue processing queue
            this._processLoadingQueue();
            
            return products;
        }).catch((error) => {
            this.activeRequests--;
            this.loadedBatches.delete(batch.batchId);
            
            console.error('[POS Lazy Loader] Error loading batch:', error);
            this._showErrorIndicator(batch.element);
            
            // Continue processing queue
            this._processLoadingQueue();
        });
    },

    /**
     * Observe element for lazy loading
     */
    observe: function(element, options) {
        if (!this.observer || !element) return;

        options = options || {};
        
        // Set data attributes
        element.dataset.batchId = options.batchId || this._generateBatchId();
        element.dataset.offset = options.offset || this.currentOffset;
        element.dataset.limit = options.limit || this.options.batchSize;
        
        if (options.categoryId) {
            element.dataset.categoryId = options.categoryId;
        }

        this.observer.observe(element);
        
        // Update current offset
        this.currentOffset += options.limit || this.options.batchSize;
    },

    /**
     * Unobserve element
     */
    unobserve: function(element) {
        if (this.observer && element) {
            this.observer.unobserve(element);
        }
    },

    /**
     * Create lazy loading sentinel element
     */
    createSentinel: function(options) {
        options = options || {};
        
        const sentinel = document.createElement('div');
        sentinel.className = 'pos-lazy-loading-sentinel';
        sentinel.style.height = '1px';
        sentinel.style.width = '100%';
        sentinel.style.clear = 'both';
        
        // Set up for observation
        const batchId = this._generateBatchId();
        sentinel.dataset.batchId = batchId;
        sentinel.dataset.offset = options.offset || this.currentOffset;
        sentinel.dataset.limit = options.limit || this.options.batchSize;
        
        if (options.categoryId) {
            sentinel.dataset.categoryId = options.categoryId;
        }

        return sentinel;
    },

    /**
     * Setup lazy loading for product list
     */
    setupProductList: function(container, options) {
        options = options || {};
        
        // Create initial sentinels for batches
        const batchCount = Math.ceil((options.totalProducts || 1000) / this.options.batchSize);
        
        for (let i = 1; i < batchCount; i++) {
            const sentinel = this.createSentinel({
                offset: i * this.options.batchSize,
                limit: this.options.batchSize,
                categoryId: options.categoryId
            });
            
            container.appendChild(sentinel);
            this.observe(sentinel);
        }
    },

    /**
     * Setup lazy loading for category view
     */
    setupCategoryView: function(container, category) {
        const sentinel = this.createSentinel({
            offset: 0,
            limit: this.options.batchSize,
            categoryId: category ? category.id : null
        });
        
        container.appendChild(sentinel);
        this.observe(sentinel);
    },

    /**
     * Preload next batch
     */
    preloadNext: function(currentPosition) {
        const nextOffset = Math.ceil(currentPosition / this.options.batchSize) * this.options.batchSize;
        
        if (!this.loadedBatches.has('preload_' + nextOffset)) {
            this._loadBatch({
                batchId: 'preload_' + nextOffset,
                element: null,
                offset: nextOffset,
                limit: this.options.batchSize
            });
        }
    },

    /**
     * Clear all loaded batches
     */
    clearBatches: function() {
        this.loadedBatches.clear();
        this.loadingQueue = [];
        this.currentOffset = 0;
        
        if (this.observer) {
            this.observer.disconnect();
            this._setupIntersectionObserver();
        }
    },

    /**
     * Get loading statistics
     */
    getStats: function() {
        return {
            loadedBatches: this.loadedBatches.size,
            queueLength: this.loadingQueue.length,
            activeRequests: this.activeRequests,
            currentOffset: this.currentOffset,
            isEnabled: this.isEnabled
        };
    },

    // Utility methods

    _generateBatchId: function() {
        return 'batch_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    },

    _showLoadingIndicator: function(element) {
        if (!element) return;
        
        element.classList.add('pos-lazy-loading');
        
        const indicator = document.createElement('div');
        indicator.className = 'pos-cache-loading';
        indicator.style.margin = '10px auto';
        indicator.style.display = 'block';
        
        element.appendChild(indicator);
    },

    _hideLoadingIndicator: function(element) {
        if (!element) return;
        
        element.classList.remove('pos-lazy-loading');
        
        const indicator = element.querySelector('.pos-cache-loading');
        if (indicator) {
            indicator.remove();
        }
    },

    _showErrorIndicator: function(element) {
        if (!element) return;
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-warning';
        errorDiv.style.margin = '10px';
        errorDiv.innerHTML = `
            <small>
                <i class="fa fa-exclamation-triangle"></i>
                Failed to load products. 
                <a href="#" onclick="this.parentElement.parentElement.remove(); return false;">
                    Click to retry
                </a>
            </small>
        `;
        
        element.appendChild(errorDiv);
    },

    _renderProducts: function(products, container) {
        if (!container || !products || products.length === 0) return;
        
        // This would integrate with the actual product rendering logic
        // For now, just log the products
        console.log(`[POS Lazy Loader] Rendered ${products.length} products`);
        
        // Trigger custom event for product rendering
        const event = new CustomEvent('pos:products_loaded', {
            detail: {
                products: products,
                container: container
            }
        });
        
        document.dispatchEvent(event);
    }

});

return PosLazyLoader;

});
