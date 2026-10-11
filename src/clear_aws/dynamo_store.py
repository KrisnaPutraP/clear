"""The data store on DynamoDB (docs/PLAN.md §4c).

Same interface as clear_tools.store.JsonStore, so the tools, the case log,
and the UI run unchanged on it. One item per file of data/seed/, keyed by
the file's path ("records/cases.json", "documents/SHP-1001/packing_list.txt")
with the file's text in `body`. The largest item, the exception history, is
about 60 KB of DynamoDB's 400 KB item limit.

Reads are strongly consistent, so a tool sees a record that another Lambda
invocation wrote a moment earlier. Every item carries a version, and a
write fails if the item changed after this thread read it: two writers can
never silently overwrite each other's records.

A UI far from the region reads through snapshot(): one Scan of the whole
table instead of one round trip per item.
"""

import contextlib
import csv
import io
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from clear_aws import settings

KEY, BODY, VERSION = "name", "body", "version"


class ConcurrentWriteError(RuntimeError):
    """An item changed between this writer's read and its write."""


class DynamoStore:
    """Items of one DynamoDB table, addressed by the names JsonStore uses for files."""

    def __init__(self, table: str, client=None):
        self.table = table
        self.client = client or boto3.client("dynamodb", region_name=settings.region())
        self._local = threading.local()  # Per thread: versions read, active snapshot.

    @classmethod
    def from_env(cls) -> "DynamoStore":
        return cls(settings.table())

    def read(self, name: str) -> Any:
        return json.loads(self.read_text(f"{name}.json"))

    def write(self, name: str, data: Any) -> None:
        self._put(f"{name}.json", json.dumps(data, indent=2, ensure_ascii=False) + "\n", check=True)

    def read_text(self, name: str) -> str:
        snapshot = self._snapshot()
        if snapshot is not None:
            if name not in snapshot:
                raise FileNotFoundError(f"{name} not found in DynamoDB table {self.table}")
            return snapshot[name]
        item = self.client.get_item(TableName=self.table, Key=_key(name), ConsistentRead=True).get("Item")
        if item is None:
            raise FileNotFoundError(f"{name} not found in DynamoDB table {self.table}")
        self._versions()[name] = item[VERSION]["N"]
        return item[BODY]["S"]

    def read_csv(self, name: str) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(self.read_text(name), newline="")))

    def exists(self, name: str) -> bool:
        snapshot = self._snapshot()
        if snapshot is not None:
            return name in snapshot
        response = self.client.get_item(TableName=self.table, Key=_key(name), ConsistentRead=True,
                                        ProjectionExpression="#k", ExpressionAttributeNames={"#k": KEY})
        return "Item" in response

    @contextlib.contextmanager
    def snapshot(self) -> Iterator[None]:
        """Serve this thread's reads from one consistent Scan of the table. Writes fail meanwhile."""
        if self._snapshot() is not None:  # Already inside one: keep it.
            yield
            return
        self._local.snapshot = {item[KEY]["S"]: item[BODY]["S"] for item in self._scan(KEY, BODY)}
        try:
            yield
        finally:
            self._local.snapshot = None

    def names(self) -> set[str]:
        return {item[KEY]["S"] for item in self._scan(KEY)}

    def put_text(self, name: str, text: str) -> None:
        """Write an item whatever its version, as a reset does."""
        self._put(name, text, check=False)

    def delete(self, name: str) -> None:
        self.client.delete_item(TableName=self.table, Key=_key(name))
        self._versions().pop(name, None)

    def _put(self, name: str, text: str, check: bool) -> None:
        if self._snapshot() is not None:
            raise RuntimeError(f"Cannot write {name} while reading from a snapshot")
        values = {":b": {"S": text}, ":zero": {"N": "0"}, ":one": {"N": "1"}}
        request = {
            "TableName": self.table,
            "Key": _key(name),
            "UpdateExpression": "SET #b = :b, #v = if_not_exists(#v, :zero) + :one",
            "ExpressionAttributeNames": {"#b": BODY, "#v": VERSION},
            "ExpressionAttributeValues": values,
            "ReturnValues": "UPDATED_NEW",
        }
        seen = self._versions().get(name) if check else None
        if seen is not None:
            request["ConditionExpression"] = "#v = :seen"
            values[":seen"] = {"N": seen}
        try:
            response = self.client.update_item(**request)
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConcurrentWriteError(f"{name} changed after it was read; another writer is active") from None
            raise
        self._versions()[name] = response["Attributes"][VERSION]["N"]

    def _scan(self, *attributes: str) -> Iterator[dict]:
        names = {f"#a{i}": attribute for i, attribute in enumerate(attributes)}
        request = {"TableName": self.table, "ConsistentRead": True,
                   "ProjectionExpression": ", ".join(names), "ExpressionAttributeNames": names}
        while True:
            page = self.client.scan(**request)
            yield from page.get("Items", [])
            if "LastEvaluatedKey" not in page:
                return
            request["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def _versions(self) -> dict[str, str]:
        if not hasattr(self._local, "versions"):
            self._local.versions = {}
        return self._local.versions

    def _snapshot(self) -> dict[str, str] | None:
        return getattr(self._local, "snapshot", None)


def reset_table(seed_dir: Path, store: DynamoStore) -> None:
    """Replace every item with the files of seed_dir: the DynamoDB counterpart of reset_runtime."""
    seed_dir = Path(seed_dir).resolve()
    if not seed_dir.is_dir():
        raise FileNotFoundError(f"Seed directory not found: {seed_dir}")
    files = {path.relative_to(seed_dir).as_posix(): path for path in sorted(seed_dir.rglob("*")) if path.is_file()}
    for name in sorted(store.names() - files.keys()):
        store.delete(name)
    for name, path in files.items():
        store.put_text(name, path.read_text(encoding="utf-8"))


def _key(name: str) -> dict:
    return {KEY: {"S": name}}
