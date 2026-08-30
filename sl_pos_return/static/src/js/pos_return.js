/** @odoo-module **/
/**
 * Returning products in the Point of Sale (17.0).
 *
 * The cashier types the receipt number from the customer's receipt. What is
 * still returnable on that order is added to the current order as negative
 * quantities, and the order is marked as a return of the original.
 *
 * Quantities arrive as everything that is left; the cashier adjusts or removes
 * lines with the ordinary numpad and delete key rather than through a screen
 * of our own. The server is the one that decides what is returnable, so a
 * cashier cannot give back more than was bought however the lines are edited.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";

patch(PosStore.prototype, {
    /**
     * Look a receipt up and put what is left of it on the current order.
     */
    async slLoadReturn(reference) {
        let payload;
        try {
            payload = await this.orm.call(
                "pos.order", "sl_find_returnable", [reference]
            );
        } catch (error) {
            // The server phrases these for the cashier: unknown receipt,
            // nothing paid under that number. Show it as it is written.
            this.popup.add(ErrorPopup, {
                title: _t("Return"),
                body: error.data && error.data.message
                    ? error.data.message
                    : _t("That receipt could not be found."),
            });
            return false;
        }

        if (!payload.lines.length) {
            this.popup.add(ErrorPopup, {
                title: _t("Return"),
                body: _t("Everything on that receipt has already been returned."),
            });
            return false;
        }

        const order = this.get_order();
        for (const line of payload.lines) {
            const product = this.db.get_product_by_id(line.product_id);
            if (!product) {
                // The product was taken out of the point of sale since the
                // sale. Skip it rather than failing the whole return.
                continue;
            }
            // 17.0 takes the product and options, not a vals object.
            await this.addProductToCurrentOrder(product, {
                quantity: -line.qty_returnable,
                price: line.price_unit,
                discount: line.discount,
            });
        }
        order.sl_return_of_order_id = payload.order_id;
        if (payload.partner_id && !order.get_partner()) {
            const partner = this.db.get_partner_by_id(payload.partner_id);
            if (partner) {
                order.set_partner(partner);
            }
        }
        return true;
    },
});


/**
 * The button the cashier presses. 17.0 registers control buttons on the
 * product screen and its popups answer {confirmed, payload} rather than
 * returning the value itself.
 */
export class SlReturnButton extends Component {
    static template = "sl_pos_return.ReturnButton";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }

    async onClick() {
        const { confirmed, payload: reference } = await this.popup.add(
            TextInputPopup,
            { title: _t("Return"), placeholder: _t("Receipt number") }
        );
        if (!confirmed || !reference) {
            return;
        }
        await this.pos.slLoadReturn(reference);
    }
}

ProductScreen.addControlButton({
    component: SlReturnButton,
    condition: function () {
        return this.pos.config.sl_allow_returns;
    },
});
