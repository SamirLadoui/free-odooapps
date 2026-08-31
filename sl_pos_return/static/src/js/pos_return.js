odoo.define("sl_pos_return.pos_return", function (require) {
    "use strict";
    /**
     * Returning products in the Point of Sale (15.0 / 16.0, legacy POS).
     *
     * 17.0 rewrote the Point of Sale, so this is the legacy implementation:
     * odoo.define modules, PosComponent, Registries and showPopup.
     *
     * The cashier types the receipt number from the customer's receipt. What
     * is still returnable on that order is added to the current order as
     * negative quantities, and the order is marked as a return of the
     * original. The server decides what is returnable, so a cashier cannot
     * give back more than was bought however the lines are edited.
     */
    const PosComponent = require("point_of_sale.PosComponent");
    const ProductScreen = require("point_of_sale.ProductScreen");
    const Registries = require("point_of_sale.Registries");
    const { useListener } = require("@web/core/utils/hooks");
    const models = require("point_of_sale.models");

    // Carry the link back to the server when the order is saved.
    const _super_order = models.Order.prototype;
    models.Order = models.Order.extend({
        export_as_JSON: function () {
            const json = _super_order.export_as_JSON.apply(this, arguments);
            if (this.sl_return_of_order_id) {
                json.sl_return_of_order_id = this.sl_return_of_order_id;
            }
            return json;
        },
        init_from_JSON: function (json) {
            _super_order.init_from_JSON.apply(this, arguments);
            this.sl_return_of_order_id = json.sl_return_of_order_id || false;
        },
    });

    class SlReturnButton extends PosComponent {
        setup() {
            super.setup();
            useListener("click", this.onClick);
        }

        async onClick() {
            const { confirmed, payload: reference } = await this.showPopup(
                "TextInputPopup",
                {
                    title: this.env._t("Return"),
                    placeholder: this.env._t("Receipt number"),
                }
            );
            if (!confirmed || !reference) {
                return;
            }

            let payload;
            try {
                payload = await this.rpc({
                    model: "pos.order",
                    method: "sl_find_returnable",
                    args: [reference],
                });
            } catch (error) {
                // The server phrases these for the cashier: unknown receipt,
                // nothing paid under that number. Show it as it is written.
                await this.showPopup("ErrorPopup", {
                    title: this.env._t("Return"),
                    body:
                        error.message && error.message.data
                            ? error.message.data.message
                            : this.env._t("That receipt could not be found."),
                });
                return;
            }

            if (!payload.lines.length) {
                await this.showPopup("ErrorPopup", {
                    title: this.env._t("Return"),
                    body: this.env._t(
                        "Everything on that receipt has already been returned."
                    ),
                });
                return;
            }

            const order = this.env.pos.get_order();
            for (const line of payload.lines) {
                const product = this.env.pos.db.get_product_by_id(line.product_id);
                if (!product) {
                    // Taken out of the point of sale since the sale. Skip it
                    // rather than failing the whole return.
                    continue;
                }
                order.add_product(product, {
                    quantity: -line.qty_returnable,
                    price: line.price_unit,
                    discount: line.discount,
                });
            }
            order.sl_return_of_order_id = payload.order_id;
            if (payload.partner_id && !order.get_partner()) {
                const partner = this.env.pos.db.get_partner_by_id(payload.partner_id);
                if (partner) {
                    order.set_partner(partner);
                }
            }
        }
    }
    SlReturnButton.template = "SlReturnButton";

    ProductScreen.addControlButton({
        component: SlReturnButton,
        condition: function () {
            return this.env.pos.config.sl_allow_returns;
        },
    });

    Registries.Component.add(SlReturnButton);

    return SlReturnButton;
});
