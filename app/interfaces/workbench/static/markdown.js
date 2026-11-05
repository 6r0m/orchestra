// Agent text drawn as the Markdown it is written in: headings, lists, quotes, tables, code, emphasis and links.
// The vendored markdown-it only parses it. From its tokens this module makes only the elements it knows, every
// word and every block of code set as text, so agent text still never reaches the page as markup: raw HTML in it
// stays its words. A link opens only over http(s), in a tab of its own; any other — a path on the agent's host —
// stays its words, its target shown on hover. An image is its words too: nothing the text names is loaded.

import markdownit from "./vendor/markdown-it.js";
import { el } from "./ui.js";

// Raw HTML off; bare web addresses made links; a line break kept where the agent broke the line; quotes and
// dashes left as written.
const parser = markdownit({ html: false, linkify: true, breaks: true, typographer: false });

// The elements drawn as themselves, by the tag the parser names; any other is a plain box of its kind.
const TAGS = new Set(["p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "thead", "tbody",
  "tr", "th", "td", "strong", "em", "s"]);
const WEB = /^https?:\/\//i;
const ALIGNED = /^text-align:(left|right|center)$/;

// `text` drawn as Markdown, in a new block of `className` beside `md`.
export function markdown(text, className) {
  const box = el("div", null, className ? "md " + className : "md");
  draw(box, parser.parse(text, {}));
  return box;
}

// One line of `text` drawn as inline Markdown — emphasis and code — in a new span of `className`. It sits in a
// summary a click opens, so its links are their words: a click on the line opens what it summarises.
export function markdownLine(text, className) {
  const line = el("span", null, className);
  for (const token of parser.parseInline(text, {})) {
    draw(line, (token.children || []).filter((part) => part.type !== "link_open" && part.type !== "link_close"));
  }
  return line;
}

// Tokens into `parent`: an opening token's element takes what follows until its closing token.
function draw(parent, tokens) {
  const open = [parent];
  for (const token of tokens) {
    const at = open[open.length - 1];
    if (token.nesting === -1) {
      if (open.length > 1) open.pop();
    } else if (token.nesting === 1) {
      // A tight list's paragraphs are hidden: their words sit in the item itself.
      if (token.hidden) {
        open.push(at);
        continue;
      }
      const [outer, inner] = opened(token);
      at.appendChild(outer);
      open.push(inner);
    } else {
      at.appendChild(single(token));
    }
  }
}

// The element an opening token starts, and the one its contents go into: a table sits in a box that scrolls.
function opened(token) {
  if (token.type === "table_open") {
    const box = el("div", null, "md-table");
    const table = el("table");
    box.appendChild(table);
    return [box, table];
  }
  if (token.type === "link_open") {
    const href = token.attrGet("href") || "";
    if (WEB.test(href)) {
      const link = el("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return [link, link];
    }
    const named = el("span", null, "md-link");
    named.title = href;
    return [named, named];
  }
  const node = el(TAGS.has(token.tag) ? token.tag : token.block ? "div" : "span");
  if (token.type === "ordered_list_open" && /^\d+$/.test(token.attrGet("start") || "")) {
    node.start = Number(token.attrGet("start"));
  }
  const aligned = ALIGNED.exec(token.attrGet("style") || "");
  if (aligned && (token.tag === "th" || token.tag === "td")) node.style.textAlign = aligned[1];
  return [node, node];
}

// What a token that holds no other draws: words, a break, a rule, or code — always as text.
function single(token) {
  switch (token.type) {
    case "inline": {
      const words = document.createDocumentFragment();
      draw(words, token.children || []);
      return words;
    }
    case "softbreak":
    case "hardbreak":
      return el("br");
    case "hr":
      return el("hr");
    case "code_inline":
      return verbatim(el("code", token.content));
    case "fence":
    case "code_block": {
      const block = el("pre");
      block.appendChild(verbatim(el("code", token.content.replace(/\n$/, ""))));
      return block;
    }
    default:
      // Words, an image's words, and anything else the parser holds as text.
      return document.createTextNode(token.content || "");
  }
}

function verbatim(node) {
  node.translate = false;
  return node;
}
