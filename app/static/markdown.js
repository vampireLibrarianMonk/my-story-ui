'use strict';
// Minimal, safe Markdown -> DOM renderer for the subset the app produces:
// atx headings, blockquotes, unordered/ordered lists, horizontal rules, paragraphs,
// and inline **bold**, *italic*, `code`. It builds real nodes with createElement and
// textContent only. It never uses innerHTML, so untrusted document text cannot inject markup.
(function (global) {
  function inline(container, text) {
    // Tokenize **bold**, *italic* / _italic_, and `code`; everything else is literal text.
    const re = /(\*\*([^*]+)\*\*|\*([^*]+)\*|_([^_]+)_|`([^`]+)`)/g;
    let last = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) container.appendChild(document.createTextNode(text.slice(last, m.index)));
      if (m[2] !== undefined) {
        const b = document.createElement('strong'); b.textContent = m[2]; container.appendChild(b);
      } else if (m[3] !== undefined || m[4] !== undefined) {
        const i = document.createElement('em'); i.textContent = m[3] ?? m[4]; container.appendChild(i);
      } else if (m[5] !== undefined) {
        const c = document.createElement('code'); c.textContent = m[5]; container.appendChild(c);
      }
      last = re.lastIndex;
    }
    if (last < text.length) container.appendChild(document.createTextNode(text.slice(last)));
  }

  function renderMarkdown(src) {
    const root = document.createElement('div');
    root.className = 'markdown';
    const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
    let i = 0;
    let para = [];
    const flushPara = () => {
      if (!para.length) return;
      const p = document.createElement('p');
      // Each source line within a paragraph becomes its own visual line (soft break), so label
      // lines like "Role: ...\nStatus: ...\nVersion: ..." read as separate lines, matching author intent.
      para.forEach((lineText, idx) => {
        if (idx > 0) p.appendChild(document.createElement('br'));
        inline(p, lineText.trim());
      });
      root.appendChild(p);
      para = [];
    };
    const list = (ordered) => {
      flushPara();
      const el = document.createElement(ordered ? 'ol' : 'ul');
      while (i < lines.length) {
        const m = lines[i].match(ordered ? /^\s*\d+\.\s+(.*)$/ : /^\s*[-*]\s+(.*)$/);
        if (!m) break;
        const li = document.createElement('li');
        inline(li, m[1]);
        el.appendChild(li);
        i++;
      }
      root.appendChild(el);
    };
    while (i < lines.length) {
      const line = lines[i];
      const heading = line.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        flushPara();
        const h = document.createElement('h' + heading[1].length);
        inline(h, heading[2].trim());
        root.appendChild(h);
        i++;
      } else if (/^\s*>\s?/.test(line)) {
        flushPara();
        const q = document.createElement('blockquote');
        const buf = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, '')); i++; }
        inline(q, buf.join(' ').trim());
        root.appendChild(q);
      } else if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
        flushPara();
        root.appendChild(document.createElement('hr'));
        i++;
      } else if (/^\s*[-*]\s+/.test(line)) {
        list(false);
      } else if (/^\s*\d+\.\s+/.test(line)) {
        list(true);
      } else if (line.trim() === '') {
        flushPara();
        i++;
      } else {
        para.push(line.trim());
        i++;
      }
    }
    flushPara();
    return root;
  }

  global.renderMarkdown = renderMarkdown;
})(window);
