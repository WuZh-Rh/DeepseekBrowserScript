/**
 * 获取页面 DOM 树压缩快照（在浏览器上下文中执行）
 * 文本仅保留在叶子节点或交互元素上，避免重复。
 *
 * @param {Object} params - 配置参数
 * @param {number} params.maxDepth - 最大遍历深度（默认 6）
 * @param {number} params.maxChildren - 每层最大子节点数（默认 30）
 * @param {number} params.maxNodesLimit - 总节点数上限（默认 300）
 * @returns {Object} 包含 title, url, total_nodes, tree 的快照对象
 */
((params) => {
    const maxDepth = params.maxDepth || 6;
    const maxChildren = params.maxChildren || 30;
    const maxNodesLimit = params.maxNodesLimit || 300;

    const maxNodes = { count: 0, limit: maxNodesLimit };
    const refCounter = { count: 1 };

    function getAttr(el, name) {
        const val = el.getAttribute(name);
        return val !== null ? val : undefined;
    }

    // 获取直接文本节点（排除子元素）
    function getDirectText(el) {
        let text = '';
        for (const child of el.childNodes) {
            if (child.nodeType === 3) { // 文本节点
                text += child.textContent;
            }
        }
        return text.trim();
    }

    function isInteractive(el) {
        const tag = el.tagName.toLowerCase();
        if (['a','button','input','textarea','select'].includes(tag)) return true;
        const role = el.getAttribute('role');
        if (role && ['button','link','textbox','menuitem','checkbox','radio'].includes(role)) return true;
        if (el.hasAttribute('onclick')) return true;
        const tabindex = el.getAttribute('tabindex');
        if (tabindex && parseInt(tabindex) >= 0) return true;
        return false;
    }

    function buildTree(node, depth) {
        if (!node || node.nodeType !== 1) return null;
        if (depth > maxDepth) return null;
        if (maxNodes.count >= maxNodes.limit) return null;

        const tag = node.tagName.toLowerCase();
        const ignored = ['script','style','noscript','meta','link','head','title','template'];
        if (ignored.includes(tag)) return null;

        const el = { tag };

        const cls = getAttr(node, 'class');
        if (cls) el.class = cls;
        const id = getAttr(node, 'id');
        if (id) el.id = id;

        if (tag === 'a') {
            const href = getAttr(node, 'href');
            if (href) el.href = href;
        }
        if (tag === 'img') {
            const src = getAttr(node, 'src');
            if (src) el.src = src;
            const alt = getAttr(node, 'alt');
            if (alt) el.alt = alt;
        }
        if (['input','textarea','select'].includes(tag)) {
            const type = getAttr(node, 'type');
            if (type) el.type = type;
            const value = node.value;
            if (value !== undefined && value !== null && value !== '') {
                el.value = String(value).slice(0, 60);
            }
            const placeholder = getAttr(node, 'placeholder');
            if (placeholder) el.placeholder = placeholder;
        }

        // ----- 文本提取（避免重复） -----
        const directText = getDirectText(node);
        if (directText) {
            // 有直接文本：直接使用，不取 innerText
            el.text = directText.slice(0, 300);
        } else {
            // 无直接文本：仅当叶子或交互元素时取 innerText
            const isLeaf = node.children.length === 0;
            const isInteractiveNode = isInteractive(node);
            if (isLeaf || isInteractiveNode) {
                let t = node.innerText;
                if (t && typeof t === 'string') {
                    t = t.trim();
                    if (t) el.text = t.slice(0, 300);
                }
            }
        }

        // 分配 ref（仅交互元素）
        if (isInteractive(node)) {
            const ref = 'E' + (refCounter.count++);
            el.ref = ref;
            node.setAttribute('data-ds-ref', ref);
        }

        maxNodes.count += 1;

        const children = [];
        let childCount = 0;
        const childNodes = node.children;
        for (let i = 0; i < childNodes.length && childCount < maxChildren; i++) {
            const sub = buildTree(childNodes[i], depth + 1);
            if (sub) {
                children.push(sub);
                childCount++;
            }
        }
        if (children.length) {
            el.children = children;
        }

        return el;
    }

    const root = buildTree(document.body, 1);
    return {
        title: document.title,
        url: location.href,
        total_nodes: maxNodes.count,
        tree: root
    };
})