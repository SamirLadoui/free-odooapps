odoo.define("pos_stock_enhancements.models", function (require) {
  "use strict";

  var models = require("point_of_sale.models");
  const { Gui } = require("point_of_sale.Gui");

  var _super_PosModel = models.PosModel.prototype;
  models.PosModel = models.PosModel.extend({
    async getProductStock(product) {
      if (!this.config.enforce_pos_stock_check) {
        return Infinity;
      }

      if (!product) {
        return 0;
      }

      const result = await this.rpc({
        model: "product.product",
        method: "get_product_stock_for_pos",
        args: [[product.id], this.config.available_stock_location_ids],
      });
      return result[product.id] || 0;
    },

    async after_load_server_data() {
      await _super_PosModel.after_load_server_data.apply(this, arguments);

      if (
        this.config.enforce_pos_stock_check &&
        (!this.config.available_stock_location_ids ||
          this.config.available_stock_location_ids.length === 0)
      ) {
        await Gui.showPopup("ErrorTracebackPopup", {
          title: this.env._t("POS Configuration Error"),
          body: this.env._t(
            "Stock checking is enforced, but no stock locations have been configured for this Point of Sale. Please configure them in the POS settings. The POS will not start."
          ),
          exitButtonIsShown: true,
        });
      }
    },
  });
});
