/** @odoo-module **/
/**
 * Stock checking in the Point of Sale (17.0).
 *
 * 17.0 adds products through addProductToCurrentOrder(product, options);
 * 18.0 replaced it with addLineToCurrentOrder(vals, ...), and 19.0 moved the
 * store from app/store to app/services. Hence one file per generation.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

patch(PosStore.prototype, {
    async slGetProductStock(product) {
        if (!this.config.enforce_pos_stock_check || !product) {
            return Infinity;
        }
        this._slStockCache = this._slStockCache || {};
        if (product.id in this._slStockCache) {
            return this._slStockCache[product.id];
        }
        const result = await this.orm.call(
            "product.product",
            "get_product_stock_for_pos",
            [[product.id], this.config.available_stock_location_ids]
        );
        const available = result[product.id] || 0;
        this._slStockCache[product.id] = available;
        return available;
    },

    slQuantityOnOrder(product) {
        const order = this.get_order();
        if (!order) {
            return 0;
        }
        return order
            .get_orderlines()
            .filter((line) => line.get_product().id === product.id)
            .reduce((total, line) => total + line.get_quantity(), 0);
    },

    async addProductToCurrentOrder(product, options = {}) {
        if (this.config.enforce_pos_stock_check && product) {
            const available = await this.slGetProductStock(product);

            if (available <= 0) {
                this.dialog.add(AlertDialog, {
                    title: _t("Out of Stock"),
                    body: _t(
                        "%s has no stock in the locations this Point of Sale checks.",
                        product.display_name
                    ),
                });
                return;
            }

            const wanted = options.quantity ?? 1;
            const alreadyOn = this.slQuantityOnOrder(product);
            if (alreadyOn + wanted > available) {
                const remaining = available - alreadyOn;
                if (remaining <= 0) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Insufficient Stock"),
                        body: _t(
                            "All %(available)s available unit(s) of %(product)s are already on this order.",
                            { available, product: product.display_name }
                        ),
                    });
                    return;
                }
                this.dialog.add(AlertDialog, {
                    title: _t("Insufficient Stock"),
                    body: _t(
                        "Only %(remaining)s unit(s) of %(product)s left, so the quantity was reduced.",
                        { remaining, product: product.display_name }
                    ),
                });
                options = { ...options, quantity: remaining };
            }
        }
        return await super.addProductToCurrentOrder(product, options);
    },
});
