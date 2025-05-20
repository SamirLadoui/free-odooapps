odoo.define("pos_stock_enhancements.ProductScreen", function (require) {
  "use strict";

  const ProductScreen = require("point_of_sale.ProductScreen");
  const Registries = require("point_of_sale.Registries");
  const NumberBuffer = require("point_of_sale.NumberBuffer");

  const PosStockProductScreen = (ProductScreen) =>
    class extends ProductScreen {
      async _clickProduct(event) {
        const product = event.detail;

        if (this.env.pos.config.enforce_pos_stock_check && product) {
          const availableStock = await this.env.pos.getProductStock(product);

          if (availableStock <= 0) {
            await this.showPopup("ErrorPopup", {
              title: this.env._t("Out of Stock"),
              body: _.str.sprintf(
                this.env._t("Product '%s' is completely out of stock."),
                product.display_name
              ),
            });
            return;
          }
        }
        await super._clickProduct(event);
      }

      async _setValue(val) {
        if (this.state.numpadMode === "quantity") {
          const orderline = this.currentOrder.get_selected_orderline();
          if (
            this.env.pos.config.enforce_pos_stock_check &&
            orderline &&
            orderline.get_product()
          ) {
            const product = orderline.get_product();
            let newQuantity = parseFloat(val);

            if (isNaN(newQuantity)) {
              await super._setValue(val);
              return;
            }

            const availableStock = await this.env.pos.getProductStock(product);

            let otherLinesQuantity = 0;
            this.currentOrder.get_orderlines().forEach((line) => {
              if (
                line.get_product().id === product.id &&
                line.cid !== orderline.cid
              ) {
                otherLinesQuantity += line.get_quantity();
              }
            });
            const effectiveAvailableStock = availableStock - otherLinesQuantity;

            if (newQuantity > effectiveAvailableStock) {
              await this.showPopup("ErrorPopup", {
                title: this.env._t("Insufficient Stock"),
                body: _.str.sprintf(
                  this.env._t(
                    "Cannot set quantity to %s. Only %s unit(s) of '%s' effectively available (total %s, %s in other lines)."
                  ),
                  newQuantity,
                  parseFloat(effectiveAvailableStock.toFixed(2)),
                  product.display_name,
                  parseFloat(availableStock.toFixed(2)),
                  parseFloat(otherLinesQuantity.toFixed(2))
                ),
              });
              if (effectiveAvailableStock > 0) {
                super._setValue(effectiveAvailableStock.toString());
              } else {
                super._setValue("0");
              }
              NumberBuffer.reset();
              return;
            }
          }
        }
        await super._setValue(val);
      }
    };

  Registries.Component.extend(ProductScreen, PosStockProductScreen);

  return ProductScreen;
});
