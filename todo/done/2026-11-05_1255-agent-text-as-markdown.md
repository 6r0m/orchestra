# Agent text read as the Markdown it is written in

**Status:** DONE 2026-11-05 — the goal met: reviewed with no blocking issue; green in `make demo` and in the
full suite on both hosts; rechecked on the live Workbench; closed on the operator's word.
**Scope:** how the Workbench page draws what agents write: a decision's evidence, what a turn produced, and
the parts a turn received ([run.js](../../app/interfaces/workbench/static/run.js), a new `markdown.js`, a vendored
markdown-it, [style.css](../../app/interfaces/workbench/static/style.css),
[server.py](../../app/interfaces/workbench/server.py)'s list of served files), and its scripted proof
([demo.py](../../tools/demo.py), [demo_press.py](../../tools/demo_press.py)). The workflow and what is copied do not
change.
**Stable documentation owner:** the invariant on agent text in
[interfaces' structure](../../app/interfaces/docs/architecture/structure.md) and the
[architecture](../../docs/architecture/structure.md); [using.md](../../docs/using.md) for what the operator sees.

## Goal

What an agent writes in Markdown — tables, lists, emphasis, code, links — reads on the page as Markdown, from
a parser off the shelf, while agent text still never reaches the page as markup.

## Authority register

### Operator decisions

- **D1** Agents' answers are shown as rendered Markdown, tables included, by an out-of-the-box parser.
  - 2026-11-05, operator: *"could we here in answer proper md preview tables and ect? full markdown preview?
    out of box"*

## Verified evidence

- **What the page does now.** A decision's evidence is a `div.prose` with `white-space: pre-wrap`, what a turn
  produced and its prompt's parts a `div.turn-prose`, all set with `textContent`: a research brief's table
  reads as rows of pipes and `|---|---|---|`, its `**bold**` as asterisks.
- **The invariant it keeps:** agent text reaches the page as terminal bytes or as text, never as markup.
  That is what keeps an agent's words from running on the page.
- **The parser.** markdown-it 15.0.3 (MIT, 2026-10-16) ships a self-contained browser ES module, so the page
  stays native modules with no build step. Probed: with `html: false` raw HTML stays text; its link check
  turns a `javascript:` link back into text; tables carry their column alignment; `linkify` makes bare URLs
  links. A path an agent links to — `C:/path/to/repo/File.h:35` — comes as a link token like any
  other.

## What changed

- **Parse only.** markdown-it parses the text into tokens; the page builds from them only the elements it
  knows — paragraphs, headings, lists, quotes, tables, code, emphasis, rules, breaks — every word and code
  block set as text. No HTML string of the parser's or the agent's is ever inserted.
- **Links.** One over http(s) opens in a tab of its own, with no referrer and no opener. Any other — a path
  on the agent's host — is its words, its target shown on hover. An image is its words: nothing the text
  names is loaded.
- **Where.** A decision's evidence, what a turn produced, and the parts a turn received; a history row's and a
  turn's one-line summary drawn inline — emphasis and code, its links as words, since a click on that line
  opens what it summarises. Kept as written:
  a failure, the exact prompt, the raw record, the operator's own notes, and everything a Copy copies.
- **Vendored as xterm is:** `vendor/markdown-it/` holds the browser build and its licence, unmodified, the
  licences of the five packages its source map shows it bundles (entities, BSD-2-Clause; linkify-it, mdurl,
  punycode.js, uc.micro, MIT), and its version, source and integrity. The server serves it and
  `markdown.js` by name, as every file the page loads.
- **Proof.** The demo's architect writes its verification — which is also what its second assessment says —
  with a table and bold, and the run's plan approval must show a table; the page's renderer, given hostile
  Markdown — raw HTML, a script, an event attribute, a `javascript:` link, an image, a path — must make no
  element outside its own set, no link off the web and nothing that loads.
- **Docs.** The invariant in interfaces' structure and in the architecture, the vendored dependencies'
  risk, the operator's side in using.md, and the demo's and its driver's rows in tools/README.md.

## Considered and not taken

- **The parser's HTML with a sanitiser** (markdown-it's `render`, or marked, with DOMPurify): a second
  library, and agent text would then reach the page as markup, cleaned — the invariant would have to give.
- **A parser of our own:** the operator asked for one off the shelf, and Markdown's edge cases are the
  parser's to own.

## Review record

- **External reviewer, 2026-11-05:** read with the live change's first review — *markdown-it parses the text,
  while the Workbench constructs permitted DOM elements using text rather than inserting agent-generated HTML…
  I found no blocking Markdown issue* — and not reopened at its final PASS.

## Verification

- **Red:** `make demo` with the page as it was: the plan approval's evidence read *The change is the approved
  plan. | file | change | |---|---| | greeting.txt | \*\*new\*\* |* — no table, its rule row left as pipes, its
  bold as asterisks. The renderer's check, run against the live Workbench: `/markdown.js` could not be
  imported. (A first red run read the wrong turn's words: the fake architect's second assessment takes its
  verification's branch, which then held no table; the table moved there.)
- **Green:** `make demo` on the final code, the summary's line included, DEMO PASSED, 111 checks: the evidence's table drawn — cells `file`, `change`,
  `greeting.txt`, `new` — its bold drawn, no table left as pipes; the hostile sample drawn as `a, blockquote,
  code, div, h2, li, p, pre, span, strong, table, tbody, td, th, thead, tr, ul` and nothing else, its only links
  the two over https, each `_blank` with `noopener noreferrer`, the path its words with its target on hover,
  the raw HTML, the script, the `javascript:` link and the image their words.
- **Mutation control:** with every link taken as a web link, the renderer's check failed — the path became a
  link — and the page file was then restored byte for byte.
- **On the live Workbench,** restarted on this code: the renderer's check, with the summary's line — bold
  drawn, its link and raw HTML its words — passed; the operator's run's history reads *through a selective
  extraction of audio* where it read `**selective extraction**`. Again at the close, with both workers on the
  final code: the same elements and nothing else, the two web links only, the path on hover.
- **Unit tests on WSL:** `tests.interfaces.test_workbench` — every file the page loads served as its type —
  `tests.test_architecture` and `tests.test_demo`: 22 classes, 127 tests, OK. `make public-check` passed; the
  new vendored files are untracked until staged, so its scan of them comes with the commit and its push.
- **The full suite, after the final PASS:** on WSL 150 classes, 744 tests, OK; on Windows 102 classes, 517
  tests, OK.
