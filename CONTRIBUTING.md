# Contributing

Start at the [source map](app/README.md) to find the owner of the behavior you want to change.
Report bugs in [GitHub Issues](https://github.com/6r0m/orchestra/issues) with the expected result,
the actual result and reproducible steps. Check existing issues and [work in progress](todo/README.md)
before opening a change, and link the fix to the issue.

Follow the [repository rules](AGENTS.md) and [architecture](docs/architecture/README.md).
Use the [test guide](tests/README.md) to choose checks that prove the change. Include the commands
and results in the pull request, along with any host or behavior you could not verify.

Before sending a change, run `make public-check`. Use sanitized examples in GitHub issues and pull
requests.
