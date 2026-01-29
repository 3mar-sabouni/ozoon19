import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Numpad } from "@point_of_sale/app/components/numpad/numpad";
import { patch } from "@web/core/utils/patch";
import { Chrome } from "@point_of_sale/app/pos_app";

patch(Numpad.prototype, {
    setup() {
        this.pos = usePos();
        super.setup();
    }
});


/**
 * Blocks only Backspace and Minus keys in POS.
 */
patch(Chrome.prototype, {
    setup() {
        super.setup();

        if (window.__POS_KEYBOARD_BLOCKED__) return;
        window.__POS_KEYBOARD_BLOCKED__ = true;

        const blockKeyboard = (ev) => {
            const key = ev.key;

            const isBackspace = key === "Backspace";
            const isMinus =
                key === "-" ||
                key === "Subtract" ||       // some browsers
                ev.code === "NumpadSubtract";

            if (!isBackspace && !isMinus) {
                return; // allow everything else
            }

            ev.preventDefault();
            ev.stopImmediatePropagation();
            console.warn("⌨️ Blocked key:", key);
        };

        document.addEventListener("keydown", blockKeyboard, true);
        document.addEventListener("keyup", blockKeyboard, true);

        console.warn("✅ POS Backspace and Minus blocked");
    },
});