# pgi: policy-generation injection

Research prototype. What the project asks, its vocabulary and its invariants are in `CLAUDE.md`; dated
decisions are in `docs/decisions.md`; results, each traced to a `runs/<id>/` folder, are in `docs/findings.md`;
where the local surrogate and AWS AgentCore Policy differ is in `docs/transfer-fidelity.md`.

## Setup

- Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/). `uv sync` installs the project; the schema generator is
  in the `schemagen` dependency group (`uv run --group schemagen ...`; the lock file already carries it).
- **Cedar CLI with symcc**: `cedar` built with the `analyze` feature (Cedar 4.14.1 at the time of writing), and
  **cvc5** 1.3.1. The tests and runners find them through `PATH` and `$CVC5`:

  ```sh
  export PATH="$HOME/tools/bin:$PATH"                              # where `cedar` lives on this machine
  export CVC5="$HOME/tools/cvc5/cvc5-macOS-arm64-static/bin/cvc5"  # the cvc5 binary symcc calls
  ```

  Put both lines in your shell profile. A shell that does not source it (an IDE task runner, an agent's shell)
  will not see them: without `cedar` the modules that validate policies skip with the reason
  "cedar CLI not on PATH" (`tests/conftest.py`), and without `$CVC5` the symcc tests skip.
- **Dogwood interpreter** (temporal track): the `pydogwood` wheel in the `dogwood` dependency group wraps the
  reference interpreter (`dogwood-language` 1.1.0); no Rust needed. `uv run --group dogwood pytest` runs the
  temporal tests; without the group they skip with the reason "pydogwood not installed".
- AssetOpsBench lives outside the repo at `$AOB_DIR` (default `../AssetOpsBench`) and is never modified.
- LLM calls need `ANTHROPIC_API_KEY`; every call goes through the on-disk cache in `cache/llm/`. Replays
  (`--replay`) and `--cache-only` runs make no API calls.

## Tests

```sh
uv run pytest                   # ~2 min with cedar and cvc5; symbolic tests skip without them
uv run --group dogwood pytest   # also the Dogwood temporal tests
```

## Runs

```sh
uv run python -m pgi.runs.clean --model M --n N --label L          # clean baseline
uv run python -m pgi.runs.probe --spec domains/assetopsbench/probes/<probe>.yaml --model M --n N   # channel probe
uv run python -m pgi.runs.probe --replay runs/<id>                  # zero API calls
uv run --group dogwood python -m pgi.runs.temporal_clean --model M --n N \
    --scenario domains/assetopsbench/scenarios/t01_close_after_approval --label L   # temporal (Dogwood) clean baseline
```

Every run writes a new `runs/<stamp>-<kind>[-label]/` folder with its config, input snapshots and per-sample
records; run folders are never overwritten.
