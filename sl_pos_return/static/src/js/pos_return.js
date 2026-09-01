/** @odoo-module **/
/**
 * Returning products in the Point of Sale (18.0).
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
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";

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

        const order = this.get_order();
        // The till only holds part of the catalogue, so a product sold weeks
        // ago is very often not loaded. Fetch the ones that are missing before
        // building the lines: skipping them silently returns nothing and looks
        // to the cashier like the button did not work.
        const missing = payload.lines
            .map((line) => line.product_id)
            .filter((id) => !this.models["product.product"].get(id));
        if (missing.length) {
            try {
                await this.data.read("product.product", missing);
            } catch {
                // Fall through: whatever could not be fetched is reported below.
            }
        }

        const absent = [];
        for (const line of payload.lines) {
            const product = this.models["product.product"].get(line.product_id);
            if (!product) {
                // Genuinely gone - archived, or no longer sold here.
                absent.push(line.product_name);
                continue;
            }
            // 19.0 builds the line from the template - it reads taxes off it
            // and picks the variant itself - so the template has to be given.
            // The variant is passed as well so a product with several of them
            // comes back as the one that was actually sold.
            await this.addLineToCurrentOrder(
                {
                    product_tmpl_id: product.product_tmpl_id,
                    product_id: product,
                    qty: -line.qty_returnable,
                    price_unit: line.price_unit,
                    discount: line.discount,
                },
                {}
            );
        }
        // An integer, not the relation: a many2one to pos.order shipped to
        // the client makes it build a half-made order and crash. The server
        // turns this back into the link.
        if (absent.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Return"),
                body: _t(
                    "These are no longer available in this point of sale and " +
                    "were not put back: %s",
                    absent.join(", ")
                ),
            });
        }
        order.sl_return_of_order_ref = payload.order_id;
        if (payload.partner_id && !order.get_partner()) {
            const partner = this.models["res.partner"].get(payload.partner_id);
            if (partner) {
                order.set_partner(partner);
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
