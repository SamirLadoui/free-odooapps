/** @odoo-module **/
/**
 * Stock checking at the till, driven through the real interface (17-19).
 *
 * The server side is covered by ordinary tests. This is the part they cannot
 * reach: that clicking a product with nothing left actually refuses the sale
 * and tells the cashier why, rather than quietly adding the line.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("sl_pos_stock_tour", {
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
            // Opening the register raises a dialog and nothing behind it can
            // be clicked until it is gone.
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
            content: "try to sell something there is none of",
            trigger: ".product-list .product-name:contains('Sold Out Thing')",
            run: "click",
        },
        {
            content: "the till refuses and says why",
            trigger: ".modal:not(.o_inactive_modal):contains('Out of Stock')",
        },
        {
            content: "dismiss the warning",
            trigger: ".modal:not(.o_inactive_modal) .modal-footer .btn-primary",
            run: "click",
        },
        {
            content: "the warning is gone",
            trigger: "body:not(:has(.modal:not(.o_inactive_modal)))",
        },
        {
            // Anchored on body, not on the order container: an empty order may
            // not render a container at all, and then the assertion would pass
            // or fail for the wrong reason.
            content: "nothing was added to the order",
            trigger: "body:not(:has(.orderline:has(.product-name:contains('Sold Out Thing'))))",
        },
    ],
});
