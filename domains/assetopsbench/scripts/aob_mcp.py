"""Talk to AssetOpsBench MCP servers directly over stdio. No LLM, no agent runner.

Run inside AssetOpsBench's venv (it provides the `mcp` SDK); the checkout is never modified:

    uv run --project "${AOB_DIR:-../AssetOpsBench}" python domains/assetopsbench/scripts/aob_mcp.py explore
    uv run --project "${AOB_DIR:-../AssetOpsBench}" python domains/assetopsbench/scripts/aob_mcp.py dump

`explore` starts servers with AOB_READONLY=1, so write tools are not even registered.
`dump` only calls list_tools and saves the raw response, one JSON file per server.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
MANIFESTS = HERE.parent / "manifests"
SERVERS = ["wo", "iot"]
WRITE_VERBS = ("generate", "create", "update", "approve", "assign", "close", "cancel", "delete")
# CouchDB settings from the checkout's .env.public plus the docker-compose credentials, passed via the
# environment instead of creating a .env inside the checkout. Values already in the environment win.
COUCH_ENV = {"COUCHDB_URL": "http://localhost:5984", "COUCHDB_USERNAME": "admin", "COUCHDB_PASSWORD": "password",
             "IOT_DBNAME": "iot", "ASSET_DBNAME": "asset", "WO_DBNAME": "workorder",
             "FAILURE_CODE_DBNAME": "failure_code"}


def aob_dir() -> Path:
    """The AssetOpsBench checkout, from $AOB_DIR or ../AssetOpsBench."""
    path = Path(os.environ.get("AOB_DIR", HERE.parents[3] / "AssetOpsBench")).resolve()
    if not (path / "src" / "servers").is_dir():
        raise SystemExit(f"AOB_DIR does not look like an AssetOpsBench checkout: {path}")
    return path


@asynccontextmanager
async def session(server: str, readonly: bool):
    """An initialised MCP client session to one server spawned as `uv run <server>-mcp-server`."""
    env = {**COUCH_ENV, **os.environ, "AOB_READONLY": "1" if readonly else "0"}
    params = StdioServerParameters(command="uv", args=["run", f"{server}-mcp-server"], cwd=str(aob_dir()), env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        await s.initialize()
        yield s


async def call(s: ClientSession, tool: str, **args) -> dict:
    """Call a read tool and return its structured result; refuse anything that looks like a write."""
    if set(tool.split("_")) & set(WRITE_VERBS):
        raise SystemExit(f"refusing to call write-like tool {tool!r}")
    res = await s.call_tool(tool, args)
    if res.isError:
        raise SystemExit(f"{tool} failed: {res.content}")
    out = res.structuredContent or json.loads(res.content[0].text)
    if set(out) == {"result"}:  # FastMCP wraps Union return types as {"result": ...}
        out = out["result"]
    # AOB servers report many failures as a normal result carrying an `error` field (isError=False).
    if "error" in out:
        raise SystemExit(f"{tool} returned an error payload: {out}")
    return out


async def tool_names(server: str, readonly: bool) -> list[str]:
    """Names of the tools a server registers in the given mode."""
    async with session(server, readonly) as s:
        return sorted(t.name for t in (await s.list_tools()).tools)


async def explore() -> None:
    """Print sites, work-order sample and status counts, and each tool marked read or write."""
    for server in SERVERS:
        full, ro = await tool_names(server, False), await tool_names(server, True)
        print(f"\n## {server}: {len(full)} tools ({len(ro)} registered under AOB_READONLY=1)")
        for name in full:
            print(f"  {'read ' if name in ro else 'WRITE'}  {name}")
    async with session("iot", readonly=True) as s:
        print("\n## iot.sites ->", json.dumps(await call(s, "sites")))
    async with session("wo", readonly=True) as s:
        res = await call(s, "list_workorders", page_size=0)
        wos = res["work_orders"]
        print(f"\n## wo.list_workorders(page_size=0): total={res['total']}")
        print("siteid counts:", dict(Counter(w.get("siteid") for w in wos)))
        print("status counts:", dict(Counter(w.get("status") for w in wos).most_common()))
        print("item keys:", sorted(wos[0]))
        for status in sorted({w.get("status") for w in wos}, key=str):
            for w in [w for w in wos if w.get("status") == status][:2]:
                print(f"  sample {status:6}: wonum={w.get('wonum')!r} siteid={w.get('siteid')!r} "
                      f"assetnum={w.get('assetnum')!r} description={str(w.get('description'))[:50]!r}")


async def dump(out: Path = MANIFESTS) -> None:
    """Save the list_tools response of each server (full tool set) to `out` and print its SHA-256."""
    out.mkdir(parents=True, exist_ok=True)
    for server in SERVERS:
        async with session(server, readonly=False) as s:
            raw = (await s.list_tools()).model_dump(mode="json", by_alias=True, exclude_none=True)
        path = out / f"{server}.tools.json"
        if path.exists():
            raise SystemExit(f"{path} exists; pinned manifests are never overwritten")
        path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
        print(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cmd", choices=["explore", "dump"])
    parser.add_argument("--out", type=Path, default=MANIFESTS, help="dump: output directory (default: pinned manifests/)")
    args = parser.parse_args()
    asyncio.run(explore() if args.cmd == "explore" else dump(args.out))
