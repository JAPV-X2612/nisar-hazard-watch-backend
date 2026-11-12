import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from nisar_bench.cases import CaseSpec
from nisar_bench.catalog import search_catalog
from nisar_bench.reader import apply_reader, load_lab
from nisar_bench.run_case import CatalogSearch, run_case

KEYCHAIN_ITEM = "nisac-earthdata-token"
LOCAL_RUNTIME = "local"


class KeychainError(RuntimeError):
    pass


def read_keychain_token() -> str:
    command = [
        "security",
        "find-generic-password",
        "-a",
        os.environ.get("USER", ""),
        "-s",
        KEYCHAIN_ITEM,
        "-w",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise KeychainError(f"cannot read the Keychain item {KEYCHAIN_ITEM!r}") from None
    return result.stdout.strip()


def run_local(
    specs: list[CaseSpec],
    run_id: str,
    token_provider: Callable[[], str] = read_keychain_token,
    lab_loader: Callable[[], Any] = load_lab,
    reader_applier: Callable[[Any, str], None] = apply_reader,
    catalog_search: CatalogSearch = search_catalog,
) -> list[dict[str, Any]]:
    token = token_provider()
    lab = lab_loader()
    records = []
    for position, spec in enumerate(specs, start=1):
        print(f"[local {position}/{len(specs)}] {spec}", file=sys.stderr, flush=True)
        reader_applier(lab, spec.reader)
        records.append(
            run_case(
                spec=spec,
                token=token,
                lab=lab,
                runtime=LOCAL_RUNTIME,
                run_id=run_id,
                catalog_search=catalog_search,
            )
        )
    return records
