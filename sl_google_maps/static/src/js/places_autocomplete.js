/** @odoo-module **/
/**
 * Google Places autocomplete on an address field.
 *
 * Put widget="sl_places_autocomplete" on a Char field and typing in it offers
 * Google's address suggestions; picking one fills the rest of the address and
 * the coordinates on the same record.
 *
 * With no API key configured the widget degrades to a plain text input, so the
 * form still works exactly as it did before the module was installed.
 */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useInputField } from "@web/views/fields/input_field_hook";
import { Component, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";

const MAPS_SCRIPT_ID = "sl_google_maps_places";

/** Load the Places library once per page, whoever asks first. */
function loadPlaces(apiKey) {
    if (window.google && window.google.maps && window.google.maps.places) {
        return Promise.resolve(true);
    }
    if (!apiKey) {
        return Promise.resolve(false);
    }
    let pending = document.getElementById(MAPS_SCRIPT_ID);
    if (!pending) {
        pending = document.createElement("script");
        pending.id = MAPS_SCRIPT_ID;
        pending.async = true;
        pending.src =
            "https://maps.googleapis.com/maps/api/js?libraries=places&key=" +
            encodeURIComponent(apiKey);
        document.head.appendChild(pending);
    }
    return new Promise((resolve) => {
        if (pending.dataset.loaded === "1") {
            resolve(true);
            return;
        }
        pending.addEventListener("load", () => {
            pending.dataset.loaded = "1";
            resolve(true);
        });
        pending.addEventListener("error", () => resolve(false));
    });
}

/** Google returns address parts as a flat list; pull out the ones we store. */
function readComponents(place) {
    const parts = {};
    for (const component of place.address_components || []) {
        for (const type of component.types) {
            parts[type] = {
                long: component.long_name,
                short: component.short_name,
            };
        }
    }
    const number = parts.street_number ? parts.street_number.long : "";
    const route = parts.route ? parts.route.long : "";
    return {
        street: [number, route].filter(Boolean).join(" "),
        city: (parts.locality || parts.postal_town || {}).long || "",
        zip: (parts.postal_code || {}).long || "",
        stateCode: (parts.administrative_area_level_1 || {}).short || "",
        countryCode: (parts.country || {}).short || "",
    };
}

export class PlacesAutocompleteField extends Component {
    static template = "sl_google_maps.PlacesAutocompleteField";
    static props = { ...standardFieldProps };

    setup() {
        this.input = useRef("input");
        this.autocomplete = null;
        useInputField({ getValue: () => this.props.record.data[this.props.name] || "" });

        onWillStart(async () => {
            this.available = await loadPlaces(this.apiKey);
        });
        onMounted(() => this.attach());
        onWillUnmount(() => this.detach());
    }

    get apiKey() {
        // Injected server-side; absent means "no key configured".
        return (window.odoo && window.odoo.sl_google_maps_key) || "";
    }

    attach() {
        if (!this.available || !this.input.el) {
            return;
        }
        this.autocomplete = new window.google.maps.places.Autocomplete(this.input.el, {
            fields: ["address_components", "geometry", "formatted_address"],
        });
        this.listener = this.autocomplete.addListener("place_changed", () =>
            this.onPlaceChanged()
        );
    }

    detach() {
        if (this.listener && window.google) {
            window.google.maps.event.removeListener(this.listener);
        }
        this.listener = null;
        this.autocomplete = null;
    }

    async onPlaceChanged() {
        const place = this.autocomplete.getPlace();
        if (!place || !place.address_components) {
            return;
        }
        const parts = readComponents(place);
        const values = { [this.props.name]: parts.street };

        const record = this.props.record;
        const has = (name) => name in record.fields;
        if (has("city")) {
            values.city = parts.city;
        }
        if (has("zip")) {
            values.zip = parts.zip;
        }
        if (place.geometry && place.geometry.location) {
            if (has("partner_latitude")) {
                values.partner_latitude = place.geometry.location.lat();
            }
            if (has("partner_longitude")) {
                values.partner_longitude = place.geometry.location.lng();
            }
        }
        await record.update(values);

        // Country and state are relations, so they are resolved server-side
        // from the ISO codes Google gives us.
        if (parts.countryCode && has("country_id")) {
            const resolved = await this.env.services.orm.call(
                "res.partner",
                "sl_resolve_place_location",
                [parts.countryCode, parts.stateCode]
            );
            const relations = {};
            if (resolved.country_id && has("country_id")) {
                relations.country_id = resolved.country_id;
            }
            if (resolved.state_id && has("state_id")) {
                relations.state_id = resolved.state_id;
            }
            if (Object.keys(relations).length) {
                await record.update(relations);
            }
        }
    }
}

export const placesAutocompleteField = {
    component: PlacesAutocompleteField,
    displayName: "Address Autocomplete",
    supportedTypes: ["char"],
};

// 17.0 introduced the descriptor form; 16.0 registers the component class
// itself. The 16.0 build overrides this file.
registry.category("fields").add("sl_places_autocomplete", placesAutocompleteField);
