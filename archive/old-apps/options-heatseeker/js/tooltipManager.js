// ===== Tooltip Manager =====

const TooltipManager = {
    tooltip: null,

    init() {
        this.tooltip = document.getElementById('tooltip');
    },

    show(content, x, y) {
        if (!this.tooltip) this.init();

        this.tooltip.innerHTML = content;
        this.tooltip.style.left = `${x + CONFIG.UI.TOOLTIP_OFFSET.x}px`;
        this.tooltip.style.top = `${y + CONFIG.UI.TOOLTIP_OFFSET.y}px`;
        this.tooltip.classList.remove('hidden');
    },

    hide() {
        if (!this.tooltip) return;
        this.tooltip.classList.add('hidden');
    }
};

Object.freeze(TooltipManager);
