#!/usr/bin/env python3
"""Rebuild blog post HTML from the markdown drafts in _drafts/.

Usage:
    python3 _scripts/build_blog.py                 # every _drafts/*.md with a matching blog/*.html
    python3 _scripts/build_blog.py _drafts/foo.md  # just one post

Only the title, subtitle, and post body are regenerated; everything else in the
existing blog/<name>.html (head, analytics, byline, scripts) is left alone.

Markdown supported (one paragraph per line, blank lines optional):
    # Title                   first line; the italic line right after it is the subtitle
    ## Section                h2, listed in the table of contents
    ### Sub / #### Subsub     h3 / h4, not in the table of contents
    > text                    pull-quote
    1. item                   numbered list (consecutive lines)
    - item                    bulleted list (consecutive lines)
    - *3. Goal title*         numbered goal list; following plain lines are the goal's body
    [^name] / [^name]: text   footnote, rendered as a sidenote next to its paragraph
    ***x***, **x**, *x*, [text](url)
"""

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BODY_START = '<div class="blog-post-content">\n'
BODY_END = '      </div>\n    </article>'


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower().replace("'", '')).strip('-')


class Converter:
    def __init__(self, md):
        self.lines = [l.rstrip() for l in md.split('\n')]
        self.footnotes = {}  # name -> text
        self.footnote_order = []  # names, numbered by first reference
        self.toc = []
        self.title = self.subtitle = None

    def inline(self, text):
        text = html.escape(text, quote=False)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(\S(?:.*?\S)?)\*', r'<em>\1</em>', text)
        return text

    def footnote_refs(self, text):
        """Replace [^name] with markers; return (text, names referenced)."""
        names = []

        def marker(m):
            name = m.group(1)
            if name not in self.footnotes:
                sys.exit(f'footnote [^{name}] has no definition')
            if name not in self.footnote_order:
                self.footnote_order.append(name)
            n = self.footnote_order.index(name) + 1
            names.append(name)
            return (f'<sup class="footnote-marker"><a class="footnote-ref" id="{name}-ref" '
                    f'href="#{name}-note" aria-label="Footnote {n}">{n}</a></sup>')

        text = re.sub(r'\[\^([\w-]+)\]', marker, text)
        return text, names

    def paragraph(self, text):
        text, notes = self.footnote_refs(self.inline(text))
        if not notes:
            return [f'        <p>\n          {text}\n        </p>']
        out = ['        <div class="with-sidenote">', f'          <p>\n            {text}\n          </p>']
        for name in notes:
            n = self.footnote_order.index(name) + 1
            out += [f'          <aside class="sidenote" id="{name}-note" role="note">',
                    f'            <a class="sidenote-number" href="#{name}-ref" aria-label="Back to text">{n}</a>',
                    f'            {self.inline(self.footnotes[name])}',
                    '          </aside>']
        out.append('        </div>')
        return out

    def convert(self):
        lines = []
        for l in self.lines:
            m = re.match(r'\[\^([\w-]+)\]:\s*(.*)', l)
            if m:
                self.footnotes[m.group(1)] = m.group(2)
            else:
                lines.append(l)

        out = []
        i = 0
        while i < len(lines):
            l = lines[i]
            if not l.strip():
                i += 1
            elif l.startswith('# ') and self.title is None:
                self.title = l[2:].strip()
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                m = re.fullmatch(r'\*([^*].*?)\*', lines[i].strip()) if i < len(lines) else None
                if m:
                    self.subtitle = m.group(1)
                    i += 1
            elif m := re.match(r'(#{2,4}) (.+)', l):
                level, text = len(m.group(1)), m.group(2).strip()
                if level == 2:
                    slug = slugify(text)
                    self.toc.append((slug, text))
                    out.append(f'\n        <h2 id="{slug}">{self.inline(text)}</h2>')
                else:
                    out.append(f'\n        <h{level}>{self.inline(text)}</h{level}>')
                i += 1
            elif l.startswith('> '):
                out.append(f'\n        <p class="pull-quote">{self.inline(l[2:].strip())}</p>\n')
                i += 1
            elif re.match(r'- \*\d+\. ', l):
                start = re.match(r'- \*(\d+)\.', l).group(1)
                attr = '' if start == '1' else f' start="{start}"'
                out.append(f'        <ol class="goal-list"{attr}>')
                while i < len(lines) and (m := re.fullmatch(r'- \*\d+\. (.+)\*', lines[i])):
                    out += ['          <li>', f'            <p class="goal-title">{self.inline(m.group(1))}</p>']
                    i += 1
                    while i < len(lines) and lines[i].strip() and not lines[i].startswith(('-', '#', '>')):
                        out.append(f'            <p>{self.inline(lines[i])}</p>')
                        i += 1
                    out.append('          </li>')
                out.append('        </ol>')
            elif re.match(r'(\d+\.|-) ', l):
                tag = 'ol' if l[0].isdigit() else 'ul'
                pattern = r'\d+\. ' if tag == 'ol' else r'- '
                out.append(f'        <{tag}>')
                while i < len(lines) and re.match(pattern, lines[i]):
                    text = re.sub(pattern, '', lines[i], count=1)
                    out.append(f'          <li>{self.inline(text)}</li>')
                    i += 1
                out.append(f'        </{tag}>')
            else:
                out += self.paragraph(l)
                i += 1

        toc = ['        <nav class="post-toc" aria-label="Table of contents">',
               '          <div class="post-toc-inner">',
               '            <ol>']
        toc += [f'              <li><a href="#{slug}">{self.inline(text)}</a></li>' for slug, text in self.toc]
        toc += ['            </ol>', '          </div>', '        </nav>', '']
        body = '\n'.join(toc + out).replace('\n\n\n', '\n\n')
        return body.rstrip() + '\n'


def build(md_path, html_path):
    conv = Converter(md_path.read_text())
    body = conv.convert()
    page = html_path.read_text()

    start = page.index(BODY_START) + len(BODY_START)
    end = page.index(BODY_END)
    page = page[:start] + body + page[end:]

    title = html.escape(conv.title, quote=False)
    page = re.sub(r'<title>.*?( - Justin Kerr)?</title>', lambda m: f'<title>{title}{m.group(1) or ""}</title>', page)
    page = re.sub(r'(<header class="blog-post-header">\s*<h1>).*?(</h1>)', lambda m: m.group(1) + title + m.group(2), page)
    if conv.subtitle:
        sub = conv.inline(conv.subtitle)
        plain = html.escape(re.sub(r'<[^>]+>', '', sub), quote=True)
        page = re.sub(r'(<p class="blog-subtitle">).*?(</p>)', lambda m: m.group(1) + sub + m.group(2), page)
        page = re.sub(r'(<meta name="description" content=").*?(">)', lambda m: m.group(1) + plain + m.group(2), page)

    html_path.write_text(page)
    print(f'{md_path.relative_to(ROOT)} -> {html_path.relative_to(ROOT)}')


def main():
    if len(sys.argv) > 1:
        drafts = [Path(p).resolve() for p in sys.argv[1:]]
    else:
        drafts = sorted((ROOT / '_drafts').glob('*.md'))
    for md_path in drafts:
        html_path = ROOT / 'blog' / (md_path.stem + '.html')
        if not html_path.exists():
            print(f'skipping {md_path.name}: create {html_path.relative_to(ROOT)} first (copy an existing post)')
            continue
        build(md_path, html_path)


if __name__ == '__main__':
    main()
