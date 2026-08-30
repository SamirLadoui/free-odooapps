/** @odoo-module **/
/**
 * Returning products in the Point of Sale (18.0 / 19.0).
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
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(PosStore.prototype, {
    /**
     * Look a receipt up and put what is left of it on the current order.
     */
    async slLoadReturn(reference) {
        let payload;
        try {
            payload = await this.data.call(
                "pos.order", "sl_find_returnable", [reference]
            );
        } catch (error) {
            // The server phrases these for the cashier: unknown receipt,
            // nothing paid under that number. Show it as it is written.
            this.dialog.add(AlertDialog, {
                title: _t("Return"),
                body: error.data && error.data.message
                    ? error.data.message
                    : _t("That receipt could not be found."),
            });
            return false;
        }

        if (!payload.lines.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Return"),
                body: _t("Everything on that receipt has already been returned."),
            });
            return false;
        }

        const order = this.getOrder();
        for (const line of payload.lines) {
            const product = this.models["product.product"].get(line.product_id);
            if (!product) {
                // The product was taken out of the point of sale since the
                // sale. Skip it rather than failing the whole return.
                continue;
            }
            await this.addLineToCurrentOrder(
                {
                    product_id: product,
                    qty: -line.qty_returnable,
                    price_unit: line.price_unit,
                    discount: line.discount,
                },
                {}
            );
        }
        order.sl_return_of_order_id = payload.order_id;
        if (payload.partner_id && !order.getPartner()) {
            const partner = this.models["res.partner"].get(payload.partner_id);
            if (partner) {
                order.setPartner(partner);
            }
        }
        return true;
    },
});

/**
 * The button the cashier presses. It asks for the receipt number and hands it
 * to the store; everything else - what is returnable, what is refused - is
 * decided on the server.
 */
patch(ControlButtons.prototype, {
    async slReturn() {
        const reference = await makeAwaitable(this.dialog, TextInputPopup, {
            title: _t("Return"),
            placeholder: _t("Receipt number"),
        });
        if (!reference) {
            return;
        }
        await this.pos.slLoadReturn(reference);
    },
});
