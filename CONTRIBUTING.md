# contributing

## setup

1. fork and clone
2. `pip install -e ".[dev]"`
3. copy `.env.example` to `.env`, add keys for any adapters you're testing
4. `pytest tests/` to verify everything works

## making changes

- tests pass before you open a PR. `pytest tests/ -v`
- don't add dependencies unless you really need them
- if your change affects user-facing behavior, update the README
- one logical change per commit

## code style

- PEP 8
- descriptive names over comments
- keep functions short

## reporting issues

include: what you expected, what happened, steps to reproduce, python version and OS.

## security

if you find a security issue, don't open a public issue. email the maintainer directly.
