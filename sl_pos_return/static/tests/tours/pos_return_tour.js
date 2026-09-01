/** @odoo-module **/
/**
 * Returning products at the till, driven through the real interface (17-19).
 *
 * The rest of this module is covered by ordinary server-side tests. This is
 * the part they cannot reach: that the Return button is on the screen, that
 * pressing it asks for a receipt number, and that what comes back is a refund
 * line for the right product at a negative quantity.
 *
 * The point of sale's own tour helpers move between versions - 17.0 keeps them
 * under tests/tours/helpers, 18.0 under tests/tours/utils, 19.0 under
 * tests/pos/tours/utils - so this uses the selectors those helpers build
 * instead, which have been the same across all three.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("sl_pos_return_tour", {
    steps: () => [
        {
            content: "wait for the point of sale to load",
            trigger: ".pos",
        },
        {
            content: "open the register",
            trigger: ".screen-login .btn.open-register-btn",
            run: "click",
        },
        {
            // Opening the register raises a dialog. Nothing behind it can be
            // clicked until it is gone, which is what made every later step
            // look like a missing button.
            content: "confirm the opening of the register",
            trigger: ".modal:not(.o_inactive_modal) .modal-footer .btn-primary",
            run: "click",
        },
        {
            content: "the opening dialog is gone",
            trigger: "body:not(:has(.modal:not(.o_inactive_modal)))",
        },
        {
            content: "wait for the product screen",
            trigger: ".pos .product-screen",
        },
        {
            content: "open the More actions",
            trigger: ".control-buttons button.more-btn",
            run: "click",
        },
        {
            content: "the Return button is offered",
            trigger: ".control-buttons-modal button.o_sl_return_button",
            run: "click",
        },
        {
            content: "type the receipt number from the customer's receipt",
            trigger: ".modal textarea, .modal input[type='text']",
            run: "edit SLRET-0001",
        },
        {
            content: "confirm the receipt number",
            trigger: ".modal .btn-primary",
            run: "click",
        },
        {
            content: "the product comes back as a refund line",
            trigger: ".order-container .orderline:has(.product-name:contains('Returnable Thing'))",
        },
        {
            content: "and the quantity on it is negative",
            trigger: ".order-container .orderline:has(.qty:contains('-2'))",
        },
    ],
});
