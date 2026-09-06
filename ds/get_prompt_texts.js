(() => {
    const results = [];

    document.querySelectorAll('.ds-flex').forEach(flex => {
        const parent = flex.parentElement;
        if (!parent) return;

        if (parent.closest && parent.closest('.ds-message')) {
            return;
        }

        const siblings = [parent.previousElementSibling, parent.nextElementSibling];

        for (const sib of siblings) {
            if (!sib) continue;

            const span = sib.matches && sib.matches('span')
                ? sib
                : sib.querySelector('span');

            if (span) {
                const text = span.textContent.trim();
                if (text.length > 0 && !results.includes(text)) {
                    results.push(text);
                }
            }
        }

        const spanInParent = parent.querySelector('span');
        if (spanInParent) {
            const text = spanInParent.textContent.trim();
            if (text.length > 0 && !results.includes(text)) {
                results.push(text);
            }
        }
    });

    return results;
})()