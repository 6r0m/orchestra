# Done

Plans whose change was merged, or whose defined scope the operator explicitly closed. A run moves
its todo here at the final gate, with a finished status line; a manually authored todo may move on
explicit operator closure before a commit. The file keeps the reasoning behind that change reachable.

A repository may say it deletes a finished plan instead, by setting `todo_done_dir` to `null` in
its `repos.json` entry. This repository keeps them.
