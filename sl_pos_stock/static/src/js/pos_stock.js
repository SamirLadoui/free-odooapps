odoo.define("sl_pos_stock.pos_stock", function (require) {
    "use strict";
    /**
     * Stock checking in the Point of Sale (15.0 / 16.0, legacy POS).
     *
     * 17.0 rewrote the Point of Sale entirely, so this file is the legacy
     * implementation: odoo.define modules, Registries.Component.extend and the
     * _clickProduct / _setValue hooks on ProductScreen.
     */
    const ProductScreen = require("point_of_sale.ProductScreen");
    const Registries = require("point_of_sale.Registries");
    const NumberBuffer = require("point_of_sale.NumberBuffer");
    const models = require("point_of_sale.models");

    const _superPosModel = models.PosModel.prototype;
    models.PosModel = models.PosModel.extend({
        async slGetProductStock(product) {
            if (!this.config.enforce_pos_stock_check || !product) {
                return Infinity;
            }
            this._slStockCache = this._slStockCache || {};
            if (product.id in this._slStockCache) {
                return this._slStockCache[product.id];
            }
            const result = await this.rpc({
                model: "product.product",
                method: "get_product_stock_for_pos",
                args: [[product.id], this.config.available_stock_location_ids],
            });
            const available = result[product.id] || 0;
            this._slStockCache[product.id] = available;
            return available;
        },
    });

    const PosStockProductScreen = (ProductScreen) =>
        class extends ProductScreen {
            /** Everything of this product already on the order. */
            _slQuantityOnOrder(product, exceptLine) {
                return this.currentOrder
                    .get_orderlines()
                    .filter(
                        (line) =>
                            line.get_product().id === product.id &&
                            (!exceptLine || line.cid !== exceptLine.cid)
                    )
                    .reduce((total, line) => total + line.get_quantity(), 0);
            }

            async _clickProduct(event) {
                const product = event.detail;
                if (this.env.pos.config.enforce_pos_stock_check && product) {
                    const available = await this.env.pos.slGetProductStock(product);
                    if (available <= 0) {
                        await this.showPopup("ErrorPopup", {
                            title: this.env._t("Out of Stock"),
                            body: _.str.sprintf(
                                this.env._t(
                                    "%s has no stock in the locations this Point of Sale checks."
                                ),
                                product.display_name
                            ),
                        });
                        return;
                    }
                    if (this._slQuantityOnOrder(product) >= available) {
                        await this.showPopup("ErrorPopup", {
                            title: this.env._t("Insufficient Stock"),
                            body: _.str.sprintf(
                                this.env._t(
                                    "All %s available unit(s) of %s are already on this order."
                                ),
                                available,
                                product.display_name
                            ),
                        });
                        return;
                    }
                }
                await super._clickProduct(event);
            }

            async _setValue(val) {
                if (this.state.numpadMode !== "quantity") {
                    return await super._setValue(val);
                }
                const orderline = this.currentOrder.get_selected_orderline();
                if (
                    !this.env.pos.config.enforce_pos_stock_check ||
                    !orderline ||
                    !orderline.get_product()
                ) {
                    return await super._setValue(val);
                }

                const product = orderline.get_product();
                const wanted = parseFloat(val);
                if (isNaN(wanted)) {
                    return await super._setValue(val);
                }

                const available = await this.env.pos.slGetProductStock(product);
                const onOtherLines = this._slQuantityOnOrder(product, orderline);
                const remaining = available - onOtherLines;

                if (wanted > remaining) {
                    await this.showPopup("ErrorPopup", {
                        title: this.env._t("Insufficient Stock"),
                        body: _.str.sprintf(
                            this.env._t(
                                "Only %s unit(s) of %s left, so the quantity was reduced."
                            ),
                            parseFloat(remaining.toFixed(2)),
                            product.display_name
                        ),
                    });
                    // Clamp rather than refuse: the cashier still wants the line,
                    // just not more of it than exists.
                    await super._setValue(Math.max(0, remaining).toString());
                    NumberBuffer.reset();
                    return;
                }
                await super._setValue(val);
            }
        };

    Registries.Component.extend(ProductScreen, PosStockProductScreen);
    return ProductScreen;
});
