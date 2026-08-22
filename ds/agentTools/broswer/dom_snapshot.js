/**
 * 获取页面 DOM 树压缩快照（在浏览器上下文中执行）
 * 文本仅保留在叶子节点或交互元素上，避免重复。
 *
 * @param {Object} params - 配置参数
 * @param {number} params.maxDepth - 最大遍历深度（默认 10）
 * @param {number} params.maxChildren - 每层最大子节点数（默认 200）
 * @param {number} params.maxNodesLimit - 总节点数上限（默认 500）
 * @param {array} params.includeAttrs - 白名单属性列表（支持通配符 *）
 * @param {array} params.excludeAttrs - 黑名单属性列表（支持通配符 *）
 * @returns {Object} 包含 title, url, total_nodes, tree 的快照对象
 */
((params) => {
    const maxDepth = params.maxDepth || 10;
    const maxChildren = params.maxChildren || 200;
    const maxNodesLimit = params.maxNodesLimit || 500;
    const includeList = params.includeAttrs || [];
    const excludeList = params.excludeAttrs || [];

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

    // ----- 属性匹配（支持通配符 *） -----
    function matchPattern(name, pattern) {
        if (pattern === '*') return true;
        if (pattern.endsWith('*')) {
            const prefix = pattern.slice(0, -1);
            return name.startsWith(prefix);
        }
        if (pattern.startsWith('*')) {
            const suffix = pattern.slice(1);
            return name.endsWith(suffix);
        }
        return name === pattern;
    }

    function buildTree(node, depth) {
        if (!node || node.nodeType !== 1) return null;
        if (depth > maxDepth) return null;
        if (maxNodes.count >= maxNodes.limit) return null;

        const tag = node.tagName.toLowerCase();
        const ignored = ['script','style','noscript','meta','link','head','title','template'];
        if (ignored.includes(tag)) return null;

        const el = { tag };

        // class 和 id 始终提取
        const cls = getAttr(node, 'class');
        if (cls) el.class = cls;
        const id = getAttr(node, 'id');
        if (id) el.id = id;

        // 特定标签的固定属性（仍保留，但不影响通用过滤）
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

        // ----- 通用属性过滤（白名单优先） -----
        const attrs = node.attributes;
        for (let i = 0; i < attrs.length; i++) {
            const attr = attrs[i];
            const name = attr.name;
            const value = attr.value;

            // 跳过 class 和 id（已单独提取）
            if (name === 'class' || name === 'id') continue;

            // 白名单模式：只保留匹配的属性
            if (includeList.length > 0) {
                let matched = false;
                for (const pat of includeList) {
                    if (matchPattern(name, pat)) {
                        matched = true;
                        break;
                    }
                }
                if (matched) {
                    el[name] = value;
                }
                continue;
            }

            // 黑名单模式：排除匹配的属性
            let excluded = false;
            for (const pat of excludeList) {
                if (matchPattern(name, pat)) {
                    excluded = true;
                    break;
                }
            }
            if (excluded) continue;

            el[name] = value;
        }

        // ----- 添加位置信息 -----
        const rect = node.getBoundingClientRect();
        el._rect = {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height)
        };

        // ----- 文本提取（避免重复） -----
        const directText = getDirectText(node);
        if (directText) {
            el.text = directText.slice(0, 300);
        } else {
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