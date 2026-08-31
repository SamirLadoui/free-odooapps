odoo.define('pos_cache_optimizer.SearchCache', function (require) {
"use strict";

var core = require('web.core');
var rpc = require('web.rpc');

var _t = core._t;

/**
 * Search Cache for POS Products
 * Implements intelligent search caching with fuzzy matching and suggestions
 */
var PosSearchCache = core.Class.extend({

    init: function(pos, options) {
        this.pos = pos;
        this.options = _.extend({
            maxCacheSize: 100,
            minSearchLength: 2,
            searchDelay: 300,
            fuzzyThreshold: 0.8,
            enableSuggestions: true,
            enableFuzzySearch: true,
            cacheExpiry: 30 * 60 * 1000 // 30 minutes
        }, options);
        
        this.searchCache = new Map();
        this.suggestionCache = new Map();
        this.searchHistory = [];
        this.popularSearches = new Map();
        this.searchStats = {
            totalSearches: 0,
            cacheHits: 0,
            cacheMisses: 0
        };
        
        this.searchTimeout = null;
        this.lastSearchTerm = '';
        this.isEnabled = true;
        
        this._setupSearchOptimizations();
    },

    /**
     * Setup search optimizations
     */
    _setupSearchOptimizations: function() {
        // Precompile common search patterns
        this.searchPatterns = {
            barcode: /^\d{8,14}$/,
            sku: /^[A-Z0-9\-_]+$/i,
            price: /^\$?\d+(\.\d{2})?$/,
        };
        
        // Setup fuzzy search if enabled
        if (this.options.enableFuzzySearch) {
            this._initializeFuzzySearch();
        }
    },

    /**
     * Search products with caching
     */
    searchProducts: function(searchTerm, options) {
        options = options || {};
        
        if (!this.isEnabled || !searchTerm || searchTerm.length < this.options.minSearchLength) {
            return Promise.resolve([]);
        }

        // Normalize search term
        const normalizedTerm = this._normalizeSearchTerm(searchTerm);
        const cacheKey = this._generateSearchCacheKey(normalizedTerm, options);
        
        // Check cache first
        if (this.searchCache.has(cacheKey) && !this._isCacheExpired(cacheKey)) {
            this.searchStats.cacheHits++;
            this.searchStats.totalSearches++;
            
            const cachedResult = this.searchCache.get(cacheKey);
            this._updateSearchHistory(normalizedTerm, cachedResult.results.length);
            
            return Promise.resolve(cachedResult.results);
        }

        // Cache miss - perform search
        this.searchStats.cacheMisses++;
        this.searchStats.totalSearches++;

        return this._performSearch(normalizedTerm, options).then((results) => {
            // Cache the results
            this._cacheSearchResults(cacheKey, results);
            
            // Update search history and stats
            this._updateSearchHistory(normalizedTerm, results.length);
            this._updatePopularSearches(normalizedTerm);
            
            return results;
        });
    },

    /**
     * Get search suggestions
     */
    getSearchSuggestions: function(searchTerm, maxSuggestions) {
        if (!this.options.enableSuggestions || !searchTerm) {
            return [];
        }

        maxSuggestions = maxSuggestions || 5;
        const normalizedTerm = this._normalizeSearchTerm(searchTerm);
        
        // Check suggestion cache
        const cacheKey = `suggestions_${normalizedTerm}`;
        if (this.suggestionCache.has(cacheKey)) {
            return this.suggestionCache.get(cacheKey);
        }

        const suggestions = this._generateSuggestions(normalizedTerm, maxSuggestions);
        
        // Cache suggestions
        this.suggestionCache.set(cacheKey, suggestions);
        
        // Limit suggestion cache size
        if (this.suggestionCache.size > this.options.maxCacheSize) {
            const firstKey = this.suggestionCache.keys().next().value;
            this.suggestionCache.delete(firstKey);
        }
        
        return suggestions;
    },

    /**
     * Search with debouncing
     */
    searchWithDelay: function(searchTerm, callback, options) {
        // Clear previous timeout
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }

        // Set new timeout
        this.searchTimeout = setTimeout(() => {
            this.searchProducts(searchTerm, options).then(callback);
        }, this.options.searchDelay);
    },

    /**
     * Get popular searches
     */
    getPopularSearches: function(limit) {
        limit = limit || 10;
        
        const popular = Array.from(this.popularSearches.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, limit)
            .map(entry => entry[0]);
            
        return popular;
    },

    /**
     * Get recent searches
     */
    getRecentSearches: function(limit) {
        limit = limit || 10;
        return this.searchHistory.slice(-limit).reverse();
    },

    /**
     * Clear search cache
     */
    clearCache: function() {
        this.searchCache.clear();
        this.suggestionCache.clear();
        console.log('[POS Search Cache] Cache cleared');
    },

    /**
     * Clear search history
     */
    clearHistory: function() {
        this.searchHistory = [];
        this.popularSearches.clear();
        console.log('[POS Search Cache] History cleared');
    },

    /**
     * Get search statistics
     */
    getSearchStats: function() {
        const totalSearches = this.searchStats.totalSearches;
        const hitRatio = totalSearches > 0 ? (this.searchStats.cacheHits / totalSearches) * 100 : 0;
        
        return {
            totalSearches: totalSearches,
            cacheHits: this.searchStats.cacheHits,
            cacheMisses: this.searchStats.cacheMisses,
            hitRatio: hitRatio.toFixed(2),
            cacheSize: this.searchCache.size,
            historySize: this.searchHistory.length,
            popularSearches: this.popularSearches.size
        };
    },

    /**
     * Enable/disable search cache
     */
    setEnabled: function(enabled) {
        this.isEnabled = enabled;
        console.log(`[POS Search Cache] ${enabled ? 'Enabled' : 'Disabled'}`);
    },

    // Private methods

    /**
     * Perform actual search
     */
    _performSearch: function(searchTerm, options) {
        // First try pattern-based search for better performance
        const searchType = this._detectSearchType(searchTerm);
        
        if (this.pos.cacheManager) {
            return this.pos.cacheManager.searchProducts(searchTerm, options.limit);
        }
        
        // Fallback to legacy search
        return this.pos.search_products(searchTerm, options.limit);
    },

    /**
     * Detect search type based on pattern
     */
    _detectSearchType: function(searchTerm) {
        if (this.searchPatterns.barcode.test(searchTerm)) {
            return 'barcode';
        } else if (this.searchPatterns.sku.test(searchTerm)) {
            return 'sku';
        } else if (this.searchPatterns.price.test(searchTerm)) {
            return 'price';
        }
        return 'general';
    },

    /**
     * Normalize search term
     */
    _normalizeSearchTerm: function(searchTerm) {
        return searchTerm.toLowerCase().trim().replace(/\s+/g, ' ');
    },

    /**
     * Generate cache key for search
     */
    _generateSearchCacheKey: function(searchTerm, options) {
        const optionsKey = JSON.stringify(options || {});
        return `search_${searchTerm}_${optionsKey}`;
    },

    /**
     * Check if cache entry is expired
     */
    _isCacheExpired: function(cacheKey) {
        const entry = this.searchCache.get(cacheKey);
        if (!entry) return true;
        
        return (Date.now() - entry.timestamp) > this.options.cacheExpiry;
    },

    /**
     * Cache search results
     */
    _cacheSearchResults: function(cacheKey, results) {
        const entry = {
            results: results,
            timestamp: Date.now()
        };
        
        this.searchCache.set(cacheKey, entry);
        
        // Maintain cache size limit
        if (this.searchCache.size > this.options.maxCacheSize) {
            const firstKey = this.searchCache.keys().next().value;
            this.searchCache.delete(firstKey);
        }
    },

    /**
     * Update search history
     */
    _updateSearchHistory: function(searchTerm, resultCount) {
        const historyEntry = {
            term: searchTerm,
            timestamp: Date.now(),
            resultCount: resultCount
        };
        
        this.searchHistory.push(historyEntry);
        
        // Limit history size
        if (this.searchHistory.length > 100) {
            this.searchHistory.shift();
        }
    },

    /**
     * Update popular searches
     */
    _updatePopularSearches: function(searchTerm) {
        const currentCount = this.popularSearches.get(searchTerm) || 0;
        this.popularSearches.set(searchTerm, currentCount + 1);
    },

    /**
     * Generate search suggestions
     */
    _generateSuggestions: function(searchTerm, maxSuggestions) {
        const suggestions = [];
        
        // Get suggestions from search history
        const historySuggestions = this.searchHistory
            .filter(entry => entry.term.includes(searchTerm) && entry.term !== searchTerm)
            .map(entry => entry.term)
            .slice(-maxSuggestions);
        
        suggestions.push(...historySuggestions);
        
        // Get suggestions from popular searches
        const popularSuggestions = this.getPopularSearches()
            .filter(term => term.includes(searchTerm) && term !== searchTerm && !suggestions.includes(term))
            .slice(0, maxSuggestions - suggestions.length);
        
        suggestions.push(...popularSuggestions);
        
        return suggestions.slice(0, maxSuggestions);
    },

    /**
     * Initialize fuzzy search
     */
    _initializeFuzzySearch: function() {
        // Simple fuzzy search implementation
        this.fuzzySearch = function(needle, haystack) {
            const needleLength = needle.length;
            const haystackLength = haystack.length;
            
            if (needleLength === 0) return haystackLength;
            if (haystackLength === 0) return needleLength;
            
            const matrix = [];
            
            for (let i = 0; i <= haystackLength; i++) {
                matrix[i] = [i];
            }
            
            for (let j = 0; j <= needleLength; j++) {
                matrix[0][j] = j;
            }
            
            for (let i = 1; i <= haystackLength; i++) {
                for (let j = 1; j <= needleLength; j++) {
                    if (haystack.charAt(i - 1) === needle.charAt(j - 1)) {
                        matrix[i][j] = matrix[i - 1][j - 1];
                    } else {
                        matrix[i][j] = Math.min(
                            matrix[i - 1][j - 1] + 1,
                            matrix[i][j - 1] + 1,
                            matrix[i - 1][j] + 1
                        );
                    }
                }
            }
            
            return matrix[haystackLength][needleLength];
        };
    },

    /**
     * Get search recommendations based on current context
     */
    getContextualRecommendations: function(currentCategory, limit) {
        limit = limit || 5;
        const recommendations = [];
        
        // Add category-specific popular searches
        if (currentCategory) {
            // This would be enhanced with actual category-specific data
            recommendations.push(`${currentCategory.name} products`);
        }
        
        // Add time-based suggestions (e.g., seasonal items)
        const now = new Date();
        const season = this._getCurrentSeason(now);
        if (season) {
            recommendations.push(`${season} items`);
        }
        
        // Add trending searches
        const trending = this.getPopularSearches(3);
        recommendations.push(...trending);
        
        return recommendations.slice(0, limit);
    },

    /**
     * Get current season for seasonal suggestions
     */
    _getCurrentSeason: function(date) {
        const month = date.getMonth();
        if (month >= 2 && month <= 4) return 'spring';
        if (month >= 5 && month <= 7) return 'summer';
        if (month >= 8 && month <= 10) return 'fall';
        return 'winter';
    }

});

return PosSearchCache;

});
