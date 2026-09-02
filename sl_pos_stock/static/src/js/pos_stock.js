/** @odoo-module **/
/**
 * Stock checking in the Point of Sale (18.0 / 19.0).
 *
 * Every line added to an order is checked against the stock in the locations
 * configured on the POS. A product with none is refused; a quantity beyond
 * what is left is clamped to what is actually available.
 *
 * The check happens in addLineToCurrentOrder, which is the single point every
 * route into an order passes through - clicking a product, scanning a barcode
 * or typing a quantity - so none of them can slip past it.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

patch(PosStore.prototype, {
    /** Available stock for one product, cached for the life of the order. */
    async slGetProductStock(product) {
        if (!this.config.enforce_pos_stock_check || !product) {
            return Infinity;
        }
        this._slStockCache = this._slStockCache || {};
        if (product.id in this._slStockCache) {
            return this._slStockCache[product.id];
        }
        const result = await this.data.call(
            "product.product",
            "get_product_stock_for_pos",
            [[product.id], this.config.available_stock_location_ids.map((l) => l.id ?? l)]
        );
        const available = result[product.id] || 0;
        this._slStockCache[product.id] = available;
        return available;
    },

    /** How much of this product is already on the order. */
    slQuantityOnOrder(product, exceptLine) {
        const order = this.get_order();
        if (!order) {
            return 0;
        }
        return order
            .get_orderlines()
            .filter((line) => line.get_product().id === product.id && line !== exceptLine)
            .reduce((total, line) => total + line.get_quantity(), 0);
    },

    async addLineToCurrentOrder(vals, opts = {}, configure = true) {
        const product = vals.product_id || vals.product_tmpl_id;
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

            const wanted = vals.qty ?? 1;
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
                vals = { ...vals, qty: remaining };
            }
        }
        return await super.addLineToCurrentOrder(vals, opts, configure);
    },
});
