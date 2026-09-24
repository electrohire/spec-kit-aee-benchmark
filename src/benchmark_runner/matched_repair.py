"""Cloud port of the matched-repair protocol (scripts/matched_repair.py).

Runs the paired identical-start repair design on the cloud runner's
OpenAIProvider: one shared read-only diagnostic per fixture pair, then two
repair arms (ordinary vs AEE-guided) from the same pristine fixture snapshot.
Hidden grading happens after all runs; hidden outcomes are never fed back.

Arms: ``diagnose``, ``repair_ordinary``, ``repair_guided``, ``repair_workflow``.

``repair_workflow`` is the full Spec-Kit+AEE workflow treatment for Claim A
(v9 design section 1, ratified 2026-09-21): the exact frozen six-phase
workflow from benchmark_runner.workflow (constitution, specify, plan, tasks,
implement, converge) with the frozen skill prompts, grounded claims, and the
AEE assess() gate at each AEE phase with bounded recovery rounds. It runs on
the matched-repair fixture sandbox with the same shared diagnostic and
public-test feedback as the repair arms, so the only treatment difference is
the repair method.

The v3 structural diagnostic-termination fix from scripts/repeated_local.py
(Session.phase) is ported here verbatim in spirit: claim-bearing phases get a
done-only final step and a mid-phase draft-claims checkpoint, and a
non-terminating phase records an honest terminal done (adopting a valid
mid-phase draft, or a single explicit DIAG-NONTERMINATION-01 claim) instead of
executing a coerced action.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import random
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from .accounting import TOKEN_FIELDS, attempt_token_usage, request_prices
from .experiment import frozen_paths, source_hash
from .isolation import docker_args
from .store import Store, canonical, read_json, sha, utc, write_json
from .workflow import AEE_PHASES, assess, grounded_claims, phase_prompt, phases

ROOT = Path(__file__).resolve().parents[2]

MATCHED_ARMS = ("diagnose", "repair_ordinary", "repair_guided", "repair_workflow")

# (before, after, seeded_requirements) — ported from scripts/matched_repair.py.
#
# Hard-pair track (freeze v7): `before` may also be a list of
# (before, after) edit pairs (with `after=None`) for multi-edit variants
# such as coupled defects; variant_files applies them in order.
# Phase-2 track (freeze v8): edits may be (path, before, after) triples for
# cross-file multi-edit variants; see VARIANT_FILES.
VARIANTS = {
    "tinydb": {
        "bool_id": ("type(ident) is not int", "not isinstance(ident, int)", ["R04"]),
        "token_alias": ("self.tokens[token] = (deepcopy(operations), deepcopy(inserted))",
                        "self.tokens[token] = (deepcopy(operations), inserted)", ["R08"]),
        "partial_commit": ("docs[next_id] = deepcopy(op['document'])",
                           "docs[next_id] = deepcopy(op['document']); self.db.storage.write({'_default':docs})",
                           ["R02", "R05"]),
        # H2: eager idempotency-key reservation; failed batches consume the
        # token, violating R07 ("Failed batches do not consume a token").
        "token_reserve": ("        storage, next_id, inserted = self._simulate(operations)\n",
                          "        if token is not None:\n"
                          "            self.tokens[token] = (deepcopy(operations), [])\n"
                          "        storage, next_id, inserted = self._simulate(operations)\n",
                          ["R07"]),
        # H4: _simulate aliases live storage; preview() (R05 side-effect-free)
        # poisons the database, symptom surfaces two hops away at db.insert.
        "storage_alias": ("        storage = deepcopy(self.db.storage.read() or {})\n",
                          "        storage = self.db.storage.read() or {}\n",
                          ["R05"]),
        # token_ops_alias: R07 requires that repeating an already successful identical batch/token returns a detached copy of t
        "token_ops_alias": ('            self.tokens[token] = (deepcopy(operations), deepcopy(inserted))',
                       '            self.tokens[token] = (operations, deepcopy(inserted))',
                       ["R07", "R03"]),
        # empty_batch_token: R01 states 'Empty input returns []': an empty batch is a successful batch, not a malformed one. R07 
        "empty_batch_token": ("        if token is not None and (not isinstance(token, str) or not token):\n            raise ValueError('invalid token')\n",
                       "        if token is not None and (not isinstance(token, str) or not token):\n            raise ValueError('invalid token')\n        if token is not None and not operations:\n            raise ValueError('empty operations cannot use a token')\n",
                       ["R01", "R07"]),
        # token_conflict_shallow: R07: 'Reusing a token with different operations raises ValueError without changing data.' 'Different
        "token_conflict_shallow": ("            if previous != operations:\n                raise ValueError('token conflict')\n",
                       "            if len(previous) != len(operations):\n                raise ValueError('token conflict')\n",
                       ["R07"]),
        # preview_cache_alias: R05 defines preview as returning 'the inserted IDs that apply would produce' while leaving data and 
        "preview_cache_alias": ([('    def __init__(self, db):\n        self.db = db\n        self.tokens = {}\n', '    def __init__(self, db):\n        self.db = db\n        self.tokens = {}\n        self._preview_cache = {}\n'),
                      ('    def preview(self, operations):\n        return self._simulate(operations)[2]\n', '    def preview(self, operations):\n        key = repr(operations)\n        if key not in self._preview_cache:\n            self._preview_cache[key] = self._simulate(operations)[2]\n        return self._preview_cache[key]\n')],
                       None,
                       ["R05", "R03"]),
        # token_conflict_repr: R07's replay rule keys on an 'identical batch'. For operation dicts, identity is value equality (==)
        "token_conflict_repr": ("            if previous != operations:\n                raise ValueError('token conflict')\n",
                       "            if repr(previous) != repr(operations):\n                raise ValueError('token conflict')\n",
                       ["R07"]),
        # stale_snapshot: R06: 'direct db.insert operations between calls must be seen by the wrapper. Do not cache a stale in
        "stale_snapshot": ([('        storage = deepcopy(self.db.storage.read() or {})\n', "        if not hasattr(self, '_snap'):\n            self._snap = self.db.storage.read() or {}\n        storage = deepcopy(self._snap)\n"),
                      ('        self.db.storage.write(storage)\n', '        self.db.storage.write(storage)\n        self._snap = deepcopy(storage)\n')],
                       None,
                       ["R06"]),
        # compact_id_reuse: R05 names 'the next insertion ID' as stable state that preview and failed applies must not disturb, 
        "compact_id_reuse": ('        next_id = table._next_id if table._next_id is not None else max(docs, default=0) + 1\n',
                       '        used = set(docs)\n        next_id = 1\n        while next_id in used:\n            next_id += 1\n',
                       ["R05", "R03"]),
        # next_id_rewind: Same requirements as compact_id_reuse: R05's stable 'next insertion ID' plus R03's preservation of T
        "next_id_rewind": ('        next_id = table._next_id if table._next_id is not None else max(docs, default=0) + 1\n',
                       '        next_id = max(docs, default=0) + 1\n',
                       ["R05", "R03"]),
        # token_validate_late: R07: 'invalid tokens raise ValueError.' R02 makes batch application atomic ('on any error restore th
        "token_validate_late": ([("    def apply(self, operations, token=None):\n        if token is not None and (not isinstance(token, str) or not token):\n            raise ValueError('invalid token')\n        if token is not None and token in self.tokens:\n", '    def apply(self, operations, token=None):\n        if token is not None and token in self.tokens:\n'),
                      ("        self.db.table('_default')._next_id = next_id\n        if token is not None:\n", "        self.db.table('_default')._next_id = next_id\n        if token is not None and (not isinstance(token, str) or not token):\n            raise ValueError('invalid token')\n        if token is not None:\n")],
                       None,
                       ["R07", "R02"]),
        # conflict_mutates_before_raise: R07: 'Reusing a token with different operations raises ValueError without changing
        # data.' The conflict check must run BEFORE the batch is written; moving it after the write raises but leaves the
        # conflicting batch's mutations in the database. Identical replays still short-circuit (public idempotency holds).
        "conflict_mutates_before_raise": ([("        if token is not None and token in self.tokens:\n            previous, result = self.tokens[token]\n            if previous != operations:\n                raise ValueError('token conflict')\n            return deepcopy(result)\n",
                       "        previous, result = None, None\n        if token is not None and token in self.tokens:\n            previous, result = self.tokens[token]\n            if previous == operations:\n                return deepcopy(result)\n"),
                      ("        self.db.table('_default')._next_id = next_id\n        if token is not None:\n",
                       "        self.db.table('_default')._next_id = next_id\n        if token is not None and token in self.tokens and previous != operations:\n            raise ValueError('token conflict')\n        if token is not None:\n")],
                       None,
                       ["R07", "R02"]),
        # stale_table_cache: R02: 'Previously acquired db.table('_default') handles must reflect both success and rollback.'
        # Dropping the clear_cache() after a write leaves previously acquired handles serving stale query results.
        "stale_table_cache": ("        self.db.storage.write(storage)\n        for table in self.db._tables.values():\n            table.clear_cache()\n        self.db.table('_default')._next_id = next_id\n",
                       "        self.db.storage.write(storage)\n        self.db.table('_default')._next_id = next_id\n",
                       ["R02"]),
        # tokens_shared_across_instances: R08: 'Token bookkeeping belongs to this BatchWriter instance'. A class-level
        # tokens dict is shared across writers, so a fresh writer replays another writer's tokens instead of applying.
        # NOTE: in the full hidden suite this fails 10 tests, but 9 of the 10 fail only via cross-test pollution
        # through the shared class dict (same token strings reused across tests); only
        # test_R08_tokens_belong_to_instance is order-independent. The signature is deterministic in fixed file
        # order (what calibration and grading use); do not reorder tinydb hidden tests without re-running calibration.
        "tokens_shared_across_instances": ("class BatchWriter:\n    def __init__(self, db):\n        self.db = db\n        self.tokens = {}\n",
                       "class BatchWriter:\n    tokens = {}\n\n    def __init__(self, db):\n        self.db = db\n",
                       ["R08"]),
        # next_id_not_written_back: R05 names 'the next insertion ID' as stable wrapper state. _simulate computes it, but
        # without writing it back to table._next_id a later remove+insert sequence rewinds and reuses IDs.
        "next_id_not_written_back": ("        self.db.table('_default')._next_id = next_id\n",
                       "",
                       ["R05", "R03"]),
        "clean": (None, None, []),
    },
    "cachetools": {
        "expiry_boundary": ("now >= entry[2]", "now > entry[2]", ["R07", "R08"]),
        "value_alias": ("return deepcopy(self._cache[key][0])", "return self._cache[key][0]", ["R01", "R06"]),
        "boolean_ttl": ("isinstance(ttl, bool) or not isinstance(ttl, (int,float))",
                        "not isinstance(ttl, (int,float))", ["R07"]),
        # H1: deleting the empty-tags guard makes invalidate_many([], 'all')
        # remove everything. The stage-2 spec's conflicting evidence packet
        # (old note: "empty all-tags matches every key", superseded by R04)
        # asserts exactly this buggy behavior.
        "empty_tags": ("        if not tags:\n            return 0\n",
                       "",
                       ["R04"]),
        # H3: overwrite without ttl retains the prior expiry, violating R08
        # ("Overwriting an entry replaces its prior expiry").
        "expiry_retain": ("        expiry = None if ttl is None else self._timer() + ttl\n",
                          "        if ttl is None:\n"
                          "            try:\n"
                          "                expiry = Cache.__getitem__(self._cache, key)[2]\n"
                          "            except KeyError:\n"
                          "                expiry = None\n"
                          "        else:\n"
                          "            expiry = self._timer() + ttl\n",
                          ["R08"]),
        # H6: coupled defects; diagnosis must be complete (fixing only the
        # obvious boundary defect still fails hidden acceptance).
        "coupled": ([("now >= entry[2]", "now > entry[2]"),
                     ("        if not tags:\n            return 0\n", "")],
                    None,
                    ["R07", "R08", "R04"]),
        # resize_order_trap: R05 (stage2.md) requires resize to preserve 'surviving entries and their LRU order' and states 'Shri
        "resize_order_trap": ('        keys = list(old._LRUCache__order)',
                       '        keys = list(old)',
                       ["R05"]),
        # invalidate_many_no_expire: R08 (stage3.md) requires 'Expired entries must be removed before get, put, len, resize and invalidat
        "invalidate_many_no_expire": ("        if mode not in ('any','all'):\n            raise ValueError('invalid mode')\n        self._expire()\n        if not tags:",
                       "        if mode not in ('any','all'):\n            raise ValueError('invalid mode')\n        if not tags:",
                       ["R08"]),
        # put_no_recency_refresh: The reference put() refreshes LRU recency on overwrite via LRUCache.__setitem__ (move_to_end); the d
        "put_no_recency_refresh": ('        self._cache[key] = (value, tags, expiry)',
                       '        if key in self._cache:\n            Cache.__setitem__(self._cache, key, (value, tags, expiry))\n        else:\n            self._cache[key] = (value, tags, expiry)',
                       ["R02"]),
        # ttl_validation_after_mutation: R07 (stage3.md) requires 'Invalid TTL raises ValueError before any mutation'. Moving the TTL validit
        "ttl_validation_after_mutation": ("        tags = self._tags(tags)\n        if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, (int,float)) or not isfinite(ttl) or ttl < 0):\n            raise ValueError('invalid ttl')\n        value = deepcopy(value)\n        hash(key)\n        self._expire()\n        expiry = None if ttl is None else self._timer() + ttl\n        self._cache[key] = (value, tags, expiry)\n        self._expire()",
                       "        tags = self._tags(tags)\n        value = deepcopy(value)\n        hash(key)\n        self._expire()\n        expiry = None if ttl is None else self._timer() + ttl\n        self._cache[key] = (value, tags, expiry)\n        if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, (int,float)) or not isfinite(ttl) or ttl < 0):\n            raise ValueError('invalid ttl')\n        self._expire()",
                       ["R07"]),
        # generator_tags_reconsumed: R06 (stage2.md) requires 'Tags may be passed as generators and must be consumed only once'. The defe
        "generator_tags_reconsumed": ('        return set(items)',
                       '        return set(list(tags))',
                       ["R06"]),
        # maxsize_bool: R03 (stage1.md) and R05 (stage2.md) both require maxsize to be 'a positive integer, excluding bool'.
        "maxsize_bool": ('        if type(size) is not int or size <= 0:',
                       '        if not isinstance(size, int) or size <= 0:',
                       ["R03", "R05"]),
        # invalid_mode_silent: R04 (stage2.md) requires 'Reject invalid mode or tags before mutation'. Deleting the mode guard make
        "invalid_mode_silent": ("        if mode not in ('any','all'):\n            raise ValueError('invalid mode')\n",
                       "",
                       ["R04"]),
        # resize_no_expire: R08 (stage3.md) requires 'Expired entries must be removed before ... resize'. Skipping the purge in 
        "resize_no_expire": ('        self._validate_size(maxsize)\n        self._expire()\n        old = self._cache',
                       '        self._validate_size(maxsize)\n        old = self._cache',
                       ["R08", "R05"]),
        # put_no_pre_expire: R08 (stage3.md) requires 'Expired entries must be removed before ... put'. Without the pre-assignmen
        "put_no_pre_expire": ('        value = deepcopy(value)\n        hash(key)\n        self._expire()\n        expiry = None if ttl is None else self._timer() + ttl',
                       '        value = deepcopy(value)\n        hash(key)\n        expiry = None if ttl is None else self._timer() + ttl',
                       ["R08", "R02"]),
        # all_subset_flip: R04 (stage2.md): mode='all' 'removes entries containing every supplied tag', i.e. the entry's tag se
        "all_subset_flip": ("if (bool(current & tags) if mode == 'any' else tags <= current):",
                       "if (bool(current & tags) if mode == 'any' else current <= tags):",
                       ["R04"]),
        # expiry_recency_touch: R08 (stage3.md) requires expired entries to be removed 'without touching the recency of surviving en
        "expiry_recency_touch": ('            entry = Cache.__getitem__(self._cache, key)',
                       '            entry = self._cache[key]',
                       ["R08", "R02"]),
        # resize_drops_expiry: R05 (stage2.md) requires resize to preserve 'surviving entries'; an entry's absolute expiry is
        # part of the entry (R07/R08). Rebuilding entries with expiry None silently makes them immortal.
        "resize_drops_expiry": ('            new[key] = Cache.__getitem__(old,key)',
                       '            v, t, e = Cache.__getitem__(old,key)\n            new[key] = (v, t, None)',
                       ["R05", "R07", "R08"]),
        # len_no_expire: R08 (stage3.md) requires 'Expired entries must be removed before get, put, len, resize and
        # invalidation' and R02 counts live entries. len without the purge counts the dead.
        "len_no_expire": ("    def __len__(self):\n        self._expire()\n        return len(self._cache)",
                       "    def __len__(self):\n        return len(self._cache)",
                       ["R08", "R02"]),
        # get_no_recency_refresh: R02 (stage1.md) requires 'get refreshes LRU recency'. The passive Cache.__getitem__
        # reads without touching recency, unlike the LRUCache __getitem__ the reference get goes through.
        "get_no_recency_refresh": ("    def get(self, key):\n        self._expire()\n        return deepcopy(self._cache[key][0])",
                       "    def get(self, key):\n        self._expire()\n        return deepcopy(Cache.__getitem__(self._cache, key)[0])",
                       ["R02"]),
        "clean": (None, None, []),
    },
    "minisched": {
        # Phase-2 cross-file pairs (freeze v8): the symptom surfaces in
        # scheduler.py but the defect lives in another module, and a
        # plausible wrong-layer fix in scheduler.py passes every public test
        # while failing hidden tests that pin the contract at the true layer.
        # P1: wrong default in config.py; trap is `or 3` coercion in the
        # scheduler, which breaks the explicit max_retries=0 requirement.
        "config_default": ("DEFAULT_MAX_RETRIES = 3", "DEFAULT_MAX_RETRIES = 0",
                            ["R04", "R07"]),
        # P2: store.add aliases the caller's payload; trap is a defensive
        # copy in scheduler.enqueue, which leaves the store contract broken.
        "store_add_alias": ('"payload": deepcopy(payload)', '"payload": payload',
                             ["R05"]),
        # P3: coupled cross-file defects; diagnosis must be complete (fixing
        # only one still fails hidden acceptance). Edits carry explicit
        # paths; see variant_files.
        "coupled_xfile": ([("minisched/config.py", "DEFAULT_MAX_RETRIES = 3",
                              "DEFAULT_MAX_RETRIES = 0"),
                             ("minisched/store.py", '"payload": deepcopy(payload)',
                              '"payload": payload')],
                            None,
                            ["R04", "R05", "R07"]),
        # or_default_trap: R07: 'An explicit max_retries=0 is honored: the first failure marks the job failed immediately.' The
        "or_default_trap": ('self.max_retries = self.DEFAULT_MAX_RETRIES if max_retries is None else max_retries',
                       'self.max_retries = max_retries or self.DEFAULT_MAX_RETRIES',
                       ["R06", "R07"]),
        # retry_off_by_one: R04: 'if attempts > config.max_retries the job becomes failed, otherwise it stays pending' and 'The 
        "retry_off_by_one": ([("minisched/scheduler.py", 'if attempts > self.config.max_retries:', 'if attempts >= self.config.max_retries:')],
                       None,
                       ["R04"]),
        # failed_stays_listed: R08: 'Terminal jobs are never re-run: run_next skips failed and done jobs and returns None when no j
        "failed_stays_listed": ([("minisched/store.py", 'if record["status"] == "pending"', 'if record["status"] in ("pending", "failed")')],
                       None,
                       ["R04", "R08"]),
        # lifo_order: R02: 'jobs run in FIFO order.' Reversing list_pending runs the newest job first: test_R02_fifo_order
        "lifo_order": ([("minisched/store.py", 'for record in self._jobs.values()', 'for record in reversed(list(self._jobs.values()))')],
                       None,
                       ["R02", "R08"]),
        # default_retries_value: R04: 'The default configuration retries up to 3 times (4 total executions)' and R07: 'The default ma
        "default_retries_value": ('DEFAULT_MAX_RETRIES = 3',
                       'DEFAULT_MAX_RETRIES = 4',
                       ["R04", "R07"]),
        # get_live_record: R05: 'JobStore.add/get must not alias caller data: ... mutating a record returned by get ... must no
        "get_live_record": ([("minisched/store.py", 'return deepcopy(record) if record is not None else None', 'return record if record is not None else None')],
                       None,
                       ["R05"]),
        # attempts_not_stored: R04: 'on job-function exception, increment the job's attempts; if attempts > config.max_retries the 
        "attempts_not_stored": ([("minisched/scheduler.py", 'self.store.update(job_id, attempts=attempts)', 'self.store.update(job_id)')],
                       None,
                       ["R04", "R08"]),
        # hardcoded_retries: R04: 'if attempts > config.max_retries the job becomes failed' -- the threshold is the configured va
        "hardcoded_retries": ([("minisched/scheduler.py", 'if attempts > self.config.max_retries:', 'if attempts > 3:')],
                       None,
                       ["R04", "R07"]),
        # update_reinserts_reorders: R02: 'jobs run in FIFO order' -- FIFO is by enqueue order and must survive updates; R04's retry path
        "update_reinserts_reorders": ([("minisched/store.py", '        self._jobs[job_id].update(deepcopy(fields))', '        record = self._jobs.pop(job_id)\n        record.update(deepcopy(fields))\n        self._jobs[job_id] = record')],
                       None,
                       ["R02", "R04"]),
        # failed_status_mismatch: R04: 'if attempts > config.max_retries the job becomes failed' and R08: 'run_next skips failed and d
        "failed_status_mismatch": ([("minisched/scheduler.py", 'self.store.update(job_id, status="failed", attempts=attempts)', 'self.store.update(job_id, status="fail", attempts=attempts)')],
                       None,
                       ["R04", "R08"]),
        # add_shallow_copy: R05: 'JobStore.add/get must not alias caller data: mutating a payload after add ... must not affect 
        "add_shallow_copy": ([("minisched/store.py", 'from copy import deepcopy', 'from copy import copy, deepcopy'),
                      ("minisched/store.py", '"payload": deepcopy(payload)', '"payload": copy(payload)')],
                       None,
                       ["R05"]),
        # enqueue_eager_validation: R01: 'A payload without a callable fn is a job failure, not a caller error: ... never raising to the
        "enqueue_eager_validation": ([("minisched/scheduler.py", '    def enqueue(self, payload):\n        return self.store.add(payload)', '    def enqueue(self, payload):\n        if not isinstance(payload, dict) or not callable(payload.get("fn")):\n            raise ValueError("payload must be a dict carrying a callable \'fn\'")\n        return self.store.add(payload)')],
                       None,
                       ["R01", "R04"]),
        # config_snapshot_stale: R04: 'if attempts > config.max_retries the job becomes failed' -- the decision reads the live
        # config object on each run_next; snapshotting max_retries at construction ignores post-construction config changes.
        "config_snapshot_stale": ([("minisched/scheduler.py", '        self.config = config if config is not None else SchedulerConfig()',
                       '        self.config = config if config is not None else SchedulerConfig()\n        self._max_retries = self.config.max_retries'),
                      ("minisched/scheduler.py", 'if attempts > self.config.max_retries:', 'if attempts > self._max_retries:')],
                       None,
                       ["R04"]),
        # done_status_mismatch: R08 clarification -- the stored status token on completion is exactly 'done'; a distinct
        # stored token ('Done') breaks terminality keyed off the stored record even though run_next reports 'done'.
        "done_status_mismatch": ([("minisched/scheduler.py", 'self.store.update(job_id, status="done")', 'self.store.update(job_id, status="Done")')],
                       None,
                       ["R08"]),
        # list_pending_returns_live: R05 extension -- records returned by list_pending are detached copies; returning live
        # records lets callers corrupt the store through the listing.
        "list_pending_returns_live": ('        return [deepcopy(record) for record in self._jobs.values()\n                if record["status"] == "pending"]',
                       '        return [record for record in self._jobs.values()\n                if record["status"] == "pending"]',
                       ["R05"]),
        # update_unknown_silent: R02 -- updating an unknown id raises KeyError; silently returning hides caller bugs.
        "update_unknown_silent": ('    def update(self, job_id, **fields):\n        if job_id not in self._jobs:\n            raise KeyError(job_id)',
                       '    def update(self, job_id, **fields):\n        if job_id not in self._jobs:\n            return',
                       ["R02"]),
        "clean": (None, None, []),
    },
}

# Synthetic benchmark module placed into the real upstream package, mirroring
# scripts/repeated_local.py PROJECTS (module = synthetic file under test).
# Phase-2 project "minisched" is fully synthetic (no upstream checkout): the
# package ships in benchmarks/repeated_local/minisched/reference/ and
# variants may seed defects in any of its files (see VARIANT_FILES).
PROJECTS = {
    "tinydb": {"upstream": "/tmp/upstreams/tinydb", "package": "tinydb",
               "module": "tinydb/journal.py", "revision": "19066e03139e904c24410e23901e4b069d715a2e"},
    "cachetools": {"upstream": "/tmp/upstreams/cachetools", "package": "src/cachetools",
                   "module": "src/cachetools/tagged.py", "revision": "c403f9f4185e58090b904c1915345b9ba46d5a08"},
    "minisched": {"synthetic": True, "package": "minisched",
                  "module": "minisched/config.py"},
}

# For variants whose seeded defect lives in a file other than the project's
# default module (phase-2 cross-file pairs). (project, variant) -> relpath.
# Multi-edit variants may instead carry an explicit path per edit.
VARIANT_FILES = {
    ("minisched", "store_add_alias"): "minisched/store.py",
    ("minisched", "retry_off_by_one"): "minisched/scheduler.py",
    ("minisched", "failed_stays_listed"): "minisched/store.py",
    ("minisched", "lifo_order"): "minisched/store.py",
    ("minisched", "get_live_record"): "minisched/store.py",
    ("minisched", "attempts_not_stored"): "minisched/scheduler.py",
    ("minisched", "hardcoded_retries"): "minisched/scheduler.py",
    ("minisched", "update_reinserts_reorders"): "minisched/store.py",
    ("minisched", "failed_status_mismatch"): "minisched/scheduler.py",
    ("minisched", "add_shallow_copy"): "minisched/store.py",
    ("minisched", "enqueue_eager_validation"): "minisched/scheduler.py",
    ("minisched", "list_pending_returns_live"): "minisched/store.py",
    ("minisched", "update_unknown_silent"): "minisched/store.py",
}

SEEDS = [20260918, 20260919]

DIAGNOSTIC_CALLS = 8
REPAIR_ROUNDS = 2
CALLS_PER_ROUND = 8
# Per-phase action budget for the repair_workflow arm: six frozen workflow
# phases x 8 actions = 48, mirroring the 8-action diagnostic and repair
# rounds. The attempt-level max_calls for the local workflow manifest adds
# headroom for bounded AEE recovery rounds (see claim_a.main_config_local).
WORKFLOW_CALLS_PER_PHASE = 8

COMMON = """You are a capable software engineering agent in an isolated real repository.
Return exactly one JSON action: {"action":"shell","command":"..."} or
{"action":"done","summary":"..."}.
Use shell to inspect/edit source and run tests. No internet or human assistance.
Do not modify upstream tests or acceptance_public.py. You may add your own tests.
All shell commands run in /testbed. Use PYTHONPATH=src:. for repository imports.
Do not fabricate test evidence. Hidden acceptance is unavailable. Inspect concise
outputs; full tool outputs are retained as evidence.
"""

CLAIMS = """At phase completion, include a claims object in your done JSON. Extract actual
observations, not generic assertions. Example shape (replace example values):
"claims":{"schema_version":"1.0","claims":[{"id":"D01","text":"bounded claim",
"kind":"hypothesis","status":"unsupported","boundary":["diagnose"],
"depends_on":[],"conflicts_with":[],"falsification_tests":["specific counterexample"],
"source_ref":"phase transcript","uncertainty":"high","evidence":[]}]}
Inside its evidence array, for actual shell evidence use kind="observed",
ref=<evidence_ref returned by shell>, source_id=<source_id returned by shell>,
direction="supports" and a scoped description. Unverified prose stays asserted.
"""

PAIR_RE = re.compile(r"^mr-([a-z]+)-([a-z_]+)-(\d+)$")


def pair_of(instance_id):
    m = PAIR_RE.fullmatch(instance_id)
    if not m:
        raise ValueError(f"not a matched-repair instance id: {instance_id}")
    project, variant, seed = m.group(1), m.group(2), int(m.group(3))
    if project not in PROJECTS or variant not in VARIANTS[project]:
        raise ValueError(f"unknown matched-repair pair: {instance_id}")
    return project, variant, seed


def variant_files(project, variant):
    """{relative_path: bytes} for the fixture: reference files with the
    variant's seeded edits applied. Single-file projects return one entry
    (the module); synthetic multi-file projects return one entry per package
    file. Edits are (before, after) pairs applied to the variant's file, or
    (path, before, after) triples carrying an explicit path for cross-file
    multi-edit variants; each anchor must be unique in its file."""
    meta = PROJECTS[project]
    if meta.get("synthetic"):
        refdir = ROOT / "benchmarks/repeated_local" / project / "reference"
        prefix = meta["package"] + "/"
        files = {prefix + p.relative_to(refdir).as_posix(): p.read_bytes()
                 for p in sorted(refdir.rglob("*.py"))}
    else:
        ref = ROOT / "benchmarks/repeated_local" / project / "reference.py"
        files = {meta["module"]: ref.read_bytes()}
    before, after, _ = VARIANTS[project][variant]
    default_path = VARIANT_FILES.get((project, variant), meta["module"])
    edits = before if isinstance(before, list) else [(before, after)]
    for edit in edits:
        if len(edit) == 3:
            path, b, a = edit
        else:
            b, a = edit
            path = default_path
        if b:
            text = files[path].decode()
            assert text.count(b) == 1, f"variant anchor not unique: {project}/{variant} {path}"
            files[path] = text.replace(b, a).encode()
    return files


def variant_source(project, variant):
    files = variant_files(project, variant)
    if len(files) != 1:
        raise ValueError(f"variant_source is single-file only: {project}/{variant}")
    return next(iter(files.values()))


def spec_text(project):
    task = ROOT / "benchmarks/repeated_local" / project
    return "\n\n".join((task / f"stage{i}.md").read_text() for i in (1, 2, 3))


def compact_assessment(value):
    return {k: value.get(k) for k in ("outcome", "findings", "next_action", "confidence", "uncertainty") if k in value}


def tests_for(project, stage, public):
    source = (ROOT / "benchmarks/repeated_local" / project / "tests.py").read_text()
    parts = source.split("# STAGE2")
    first = parts[0]
    second, third = parts[1].split("# STAGE3")
    chosen = first + (second if stage >= 2 else "") + (third if stage >= 3 else "")
    if not public:
        return chosen.encode()
    tree = ast.parse(chosen)
    keep = [node for node in tree.body
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            or not node.name.startswith("test_") or node.name.startswith("test_public_")]
    tree.body = keep
    return ast.unparse(tree).encode()


# ---------------------------------------------------------------------------
# v3 structural termination port (from scripts/repeated_local.py Session.phase)
# ---------------------------------------------------------------------------

from .runner import LimitHit, MiniEnvironment, MiniModel, remaining  # noqa: E402


class MatchedModel(MiniModel):
    """MiniModel that also accepts a draft claims action in claim-bearing phases."""

    def begin_phase(self, claims, limit):
        self.claims_phase = claims
        self.limit = limit

    def query(self, messages):
        cleaned = [{"role": m["role"], "content": m["content"]} for m in messages]
        text = self.provider.query(cleaned, self.phase, min(remaining(self.deadline), 120))
        try:
            action = json.loads(text)
            allowed = ("shell", "done") + (("draft",) if self.claims_phase else ())
            if not isinstance(action, dict) or action.get("action") not in allowed:
                raise ValueError("expected shell, done" + (", or draft" if self.claims_phase else ""))
            if action["action"] == "shell" and not isinstance(action.get("command"), str):
                raise ValueError("shell command must be string")
            self.last = action
        except (ValueError, TypeError):
            self.last = {"action": "invalid"}
            action = self.last
        return {"role": "assistant", "content": text,
                "extra": {"actions": [action] if action["action"] == "shell" else []}}


def _terminal_done(phase, limit, draft_claims):
    """Honest terminal done for a claim-bearing phase that exhausts its action
    budget without the model returning done. Ported from Session._terminal_done:
    never invents grounded claims."""
    from aee.model import Claim
    if draft_claims is not None:
        bundle = draft_claims
        summary = ("Phase %s ended without an explicit done: the model did not terminate within its %d allocated actions. "
                   "The recorded mid-phase draft claims are reported as the terminal claims; treat them as unrefined." % (phase, limit))
    else:
        bundle = {"schema_version": "1.0", "claims": [{
            "id": "DIAG-NONTERMINATION-01",
            "text": ("The %s phase exhausted its %d allocated actions without the model returning done. "
                     "No grounded defect claims were established; every defect claim remains unsupported." % (phase, limit)),
            "kind": "hypothesis", "status": "unsupported", "boundary": [phase],
            "depends_on": [], "conflicts_with": [],
            "falsification_tests": ["Re-run the phase and observe whether done is returned within the action budget"],
            "source_ref": "phase transcript", "uncertainty": "high", "evidence": []}]}
        summary = ("Phase %s exhausted its %d allocated actions without the model returning done. "
                   "No grounded claims were produced; the terminal claim records this non-termination honestly." % (phase, limit))
    for c in bundle["claims"]:
        Claim.from_dict(c)
    return {"action": "done", "summary": summary, "claims": bundle, "terminal_synthesized": True}


def _validate_claims_bundle(bundle, draft=False):
    from aee.model import Claim
    if not isinstance(bundle, dict) or not bundle.get("claims"):
        raise ValueError("Nonempty %s claims required" % ("draft" if draft else ""))
    for c in bundle["claims"]:
        Claim.from_dict(c)
    return bundle


def run_matched_phase(agent, model, store, identity, cfg, phase, instructions, spec, limit, deadline, claims):
    """One phase with the v3 structural termination discipline. Returns a
    summary dict mirroring Session.phase: {phase, done, completed, errors, calls}."""
    model.phase = phase
    model.begin_phase(claims, limit)
    agent.add_messages(
        {"role": "system", "content": COMMON + "\nCURRENT PHASE: " + phase + "\n" + instructions + ("\n" + CLAIMS if claims else "")},
        {"role": "user", "content": spec})
    agent.add_messages({"role": "user", "content": (
        f"Begin the current {phase} phase now. You have at most {limit} actions in this phase, including done. "
        "Complete its requested deliverable, then return done.")})
    done, errors = None, []
    draft_step = limit // 2 if (claims and limit >= 6) else None
    draft_claims = None
    start_calls = agent.n_calls
    for step in range(limit):
        if (store.root / "CANCEL").exists():
            raise KeyboardInterrupt("cancelled")
        if step == limit - 1 and claims:
            agent.add_messages({"role": "user", "content": (
                'FINAL STEP: this is the last allocated action for this phase. Only a done action is accepted now. '
                'Return {"action":"done","summary":"...","claims":{"schema_version":"1.0","claims":[...]}} with your best current claims object'
                + (' (finalize your recorded mid-phase draft)' if draft_claims else '')
                + '. Shell actions are no longer available: any other action ends the phase and the harness records an honest terminal done.')})
        elif step == limit - 1:
            agent.add_messages({"role": "user", "content": (
                "This is the last allocated action for this phase. Return done now with an honest summary of completed and unresolved work. "
                "Do not perform another shell action.")})
        elif draft_step is not None and step == draft_step:
            agent.add_messages({"role": "user", "content": (
                'MID-PHASE CHECKPOINT (action %d of %d). Return a draft claims object now: '
                '{"action":"draft","claims":{"schema_version":"1.0","claims":[...]}} with your current best hypothesis claims; '
                "they may be refined later, and you may also return done if finished. Shell exploration may continue afterwards, "
                "but this step does not accept shell actions." % (step + 1, limit))})
        elif step == limit - 2:
            agent.add_messages({"role": "user", "content": (
                "Two actions remain in this phase. Finish the requested artifact/check now and use done to report its actual state; "
                "preserve unresolved issues.")})
        calls = [c for c in store.events("calls") if c["attempt_id"] == identity["attempt_id"]]
        # Unknown-usage calls (failed physical requests) are charged their
        # full reservation, so the ceiling stays enforceable; a transient
        # provider failure never kills the attempt here.
        used = attempt_token_usage(calls, cfg)
        if used + cfg["max_input_tokens"] + cfg["max_output_tokens"] > cfg["token_cap"]:
            raise LimitHit("next request token reservation exceeds attempt cap")
        if agent.n_calls >= cfg["max_calls"]:
            raise LimitHit("call limit")
        try:
            message = agent.query()
            action = model.last
            if claims and step == limit - 1 and action.get("action") != "done":
                # Structural termination: a non-done final action is not
                # executed. A draft returned on the final step is adopted as
                # the terminal claims; otherwise an honest terminal done is
                # synthesized (never inventing grounded claims).
                if action.get("action") == "draft":
                    try:
                        draft_claims = _validate_claims_bundle(action.get("claims"), draft=True)
                    except (ValueError, TypeError) as exc:
                        errors.append("FinalDraftInvalid: " + str(exc)[:200])
                done = _terminal_done(phase, limit, draft_claims)
                errors.append("TerminalActionCoerced: non-done action on the final step was not executed; recorded honest terminal done")
                break
            if draft_step is not None and step == draft_step and action.get("action") not in ("draft", "done"):
                raise ValueError("Mid-phase draft claims required on this step: return {\"action\":\"draft\",\"claims\":{...}} or done")
            if claims and action.get("action") == "draft":
                draft_claims = _validate_claims_bundle(action.get("claims"), draft=True)
                agent.add_messages({"role": "user", "content": (
                    "Draft claims recorded (%d claim(s)). Continue exploration or refinement; "
                    "your final done must still include the complete claims object." % len(draft_claims["claims"]))})
                continue
            if action.get("action") == "done":
                if claims:
                    _validate_claims_bundle(action.get("claims"))
                done = action
                break
            # shell actions execute; invalid actions yield the model's own
            # correction prompt via format_observation_messages (no execution).
            agent.execute_actions(message)
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc)[:500])
            if isinstance(exc, (LimitHit, KeyboardInterrupt)):
                raise
            agent.add_messages({"role": "user", "content": "Last action/request failed: " + errors[-1] + ". Correct the action; do not invent evidence."})
    artifact = store.artifact(canonical({"phase": phase, "done": done, "errors": errors}))
    store.append("phases", {**identity, "phase": phase, "timestamp": utc(), "artifact": artifact,
                            "completed": done is not None, "calls": agent.n_calls - start_calls})
    return {"phase": phase, "done": done, "completed": done is not None, "errors": errors,
            "calls": agent.n_calls - start_calls}


# ---------------------------------------------------------------------------
# Sandbox helpers: public tests, package snapshots, git state
# ---------------------------------------------------------------------------

# PYTHONDONTWRITEBYTECODE=1 keeps run_public_tests from dirtying the clean fixture
# worktree: without it, pytest writes untracked __pycache__/ dirs under /testbed and
# git_clean() (git status --porcelain) reports the tree dirty before the agent acts,
# which silently discards all diagnostic claims. Real agent edits are still detected.
PYTEST_CMD = ("PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -c /dev/null "
              "-q /testbed/acceptance_public.py --junitxml=/tmp/grade.xml")


def parse_junit(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    cases = []
    for n in root.iter("testcase"):
        failed = any(n.find(k) is not None for k in ("failure", "error", "skipped"))
        cases.append({"name": n.attrib.get("name"), "file": n.attrib.get("classname"), "passed": not failed,
                      "failures": [{"kind": c.tag, "message": c.attrib.get("message"), "text": c.text}
                                   for c in n if c.tag in ("failure", "error", "skipped")]})
    return cases


def run_public_tests(sandbox):
    result = sandbox.execute(PYTEST_CMD, 180)
    xml = sandbox.execute("cat /tmp/grade.xml")["stdout"]
    cases = parse_junit(xml)
    return {"passed": result["exit_code"] == 0 and bool(cases) and all(c["passed"] for c in cases),
            "test_count": len(cases), "cases": cases,
            "output": result["stdout"] + result["stderr"]}


def git_clean(sandbox):
    """True when the fixture worktree has no *source* changes.

    Interpreter and test-runner artifacts are not source changes: the agent
    may run python/pytest inside the sandbox without PYTHONDONTWRITEBYTECODE=1,
    writing untracked __pycache__/ dirs, .pyc files, or .pytest_cache/. Counting
    those as "changed source" silently discards valid diagnostics (the v6
    tinydb/clean recurrence of the diagnostic_changed_source false positive)
    and inflates source_changed in adjudication. Real edits -- tracked-file
    modifications, new source files -- are still detected.
    """
    check = sandbox.execute("git status --porcelain -uall", 30)
    if check["exit_code"] != 0 or not check["stdout"].strip():
        return check["exit_code"] == 0
    for line in check["stdout"].splitlines():
        path = line[3:].strip().strip('"')
        # Renames/copies report "old -> new"; judge by the new path.
        path = path.split(" -> ")[-1]
        lowered = path.lower()
        if ("__pycache__" in lowered or lowered.endswith((".pyc", ".pyo"))
                or "/.pytest_cache/" in lowered or lowered.startswith(".pytest_cache/")):
            continue
        return False
    return True


def snapshot_package(sandbox, package_dir):
    """Tar only the package .py files for grading — solver tests/config/hooks
    never cross into grading (mirrors ProjectSandbox.snapshot)."""
    command = ("import io,tarfile,pathlib,sys; b=io.BytesIO(); t=tarfile.open(fileobj=b,mode='w'); "
               f"files=sorted(pathlib.Path({package_dir!r}).rglob('*.py')); "
               "assert files and all(not p.is_symlink() for p in files); "
               "[t.add(p,arcname=str(p)) for p in files]; t.close(); sys.stdout.buffer.write(b.getvalue())")
    out = subprocess.run(["docker", "exec", sandbox.name, "python", "-c", command],
                         capture_output=True, timeout=60)
    if out.returncode:
        raise RuntimeError("package snapshot failed: " + out.stderr.decode(errors="replace")[:500])
    return out.stdout


# ---------------------------------------------------------------------------
# Attempt drivers
# ---------------------------------------------------------------------------

def _new_agent(provider, deadline):
    import os
    import shutil
    import tempfile
    from minisweagent.agents.default import DefaultAgent
    global_config = Path(tempfile.mkdtemp(prefix="mini-clean-config-"))
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(global_config)
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    try:
        agent = DefaultAgent(MatchedModel(provider, deadline), None,
                             system_template="", instance_template="", cost_limit=0)
    finally:
        shutil.rmtree(global_config, ignore_errors=True)
    return agent


def run_diagnostic(root, task, provider, sandbox, store, identity, cfg):
    project, variant, seed = pair_of(task["instance_id"])
    deadline = time.monotonic() + cfg["timeout_seconds"]
    agent = _new_agent(provider, deadline)
    agent.env = MiniEnvironment(sandbox, deadline, store, identity)
    model = agent.model

    public = run_public_tests(sandbox)
    store.append("public_feedback", {**identity, "stage": "diagnostic", "timestamp": utc(),
                                     "passed": public["passed"], "test_count": public["test_count"],
                                     "output_tail": public["output"][-4000:]})
    instruction = ("Read-only review of the implementation and public test feedback. It may be correct or contain defects. "
                   "Do not edit source. Inspect relevant code/tests, then return grounded requirement claims, explicit "
                   "uncertainty and concrete suspected defects if any. Do not invent observations.\nPublic feedback:\n"
                   + public["output"][-10000:])
    summary = run_matched_phase(agent, model, store, identity, cfg, "diagnose", instruction,
                                spec_text(project), DIAGNOSTIC_CALLS, deadline, claims=True)
    diagnostic_changed = not git_clean(sandbox)
    claims, evaluation, assessment_seconds = None, None, 0
    if summary["done"] and not diagnostic_changed:
        claims = grounded_claims(summary["done"]["claims"], store, identity["attempt_id"])
        begin = time.monotonic()
        evaluation = assess(root, claims, "implement", store, identity["attempt_id"])
        assessment_seconds = time.monotonic() - begin
    event = {**identity, "project": project, "variant": variant, "seed": seed,
             "summary": summary, "diagnostic_changed_source": diagnostic_changed,
             "claims": claims, "evaluation": evaluation,
             "assessment_seconds": assessment_seconds, "timestamp": utc()}
    store.append("diagnostics", event)
    return {"diagnostic_valid": claims is not None, "diagnostic_changed_source": diagnostic_changed,
            "tool_calls": agent.env.tool_calls,
            "package_snapshot": store.artifact(snapshot_package(sandbox, PROJECTS[project]["package"]))}


class DiagnosticUnavailable(Exception):
    """A dependent repair arm cannot run: the task's diagnose attempt was
    scheduled but produced no diagnostic evidence (it never completed --
    e.g. it stopped at `limit` after a provider error with unknown usage).

    This is a per-task dependency failure, not an infrastructure failure: the
    run loop pre-skips the repair attempt before any attempt-start event
    (status "skipped", no inference issued) and continues the schedule
    instead of fail-stopping the run. The exception remains as a backstop for
    direct execute_attempt callers. Downstream band selection fails closed on
    the missing attempts."""


# Repair arms that require the task's diagnostic evidence before they may run.
REPAIR_DEPENDENT_ARMS = ("repair_ordinary", "repair_guided", "repair_workflow")


def diagnostic_available(store, manifest, task):
    """True when a diagnostic evidence event exists for the task's diagnose
    attempt. Used to pre-skip dependent repair arms before an attempt-start
    event instead of recording started-then-error."""
    pair = task["instance_id"]
    diag_id = next((e["attempt_id"] for e in manifest["schedule"]
                    if e["task_id"] == pair and e["arm"] == "diagnose"), None)
    if diag_id is None:
        return False
    return any(e["attempt_id"] == diag_id for e in store.events("diagnostics"))


def _diagnostic_for(store, manifest, task):
    pair = task["instance_id"]
    diag_id = next((e["attempt_id"] for e in manifest["schedule"]
                    if e["task_id"] == pair and e["arm"] == "diagnose"), None)
    if diag_id is None:
        raise RuntimeError("no diagnostic attempt scheduled for " + pair)
    for event in store.events("diagnostics"):
        if event["attempt_id"] == diag_id:
            return event
    raise DiagnosticUnavailable("diagnostic evidence not recorded for " + diag_id)


def run_repair(root, task, arm, provider, sandbox, store, identity, cfg, manifest):
    project, variant, seed = pair_of(task["instance_id"])
    deadline = time.monotonic() + cfg["timeout_seconds"]
    agent = _new_agent(provider, deadline)
    agent.env = MiniEnvironment(sandbox, deadline, store, identity)
    model = agent.model

    diag = _diagnostic_for(store, manifest, task)
    public = run_public_tests(sandbox)
    spec = spec_text(project)
    guided = arm == "repair_guided"
    evaluation = diag.get("evaluation")
    assessment_note = (json.dumps(compact_assessment(evaluation))
                       if evaluation else "{'error': 'Shared diagnostic incomplete; no valid assessment'}")
    rounds = []
    current_output = public["output"]
    for iteration in (1, 2):
        instruction = ("Review and repair if necessary using requirements, source and public feedback. "
                       "This may be a clean negative control: do not change correct code without a concrete reason. "
                       "Preserve existing APIs and tests.\nShared diagnostic (assertions are not proof):\n"
                       + json.dumps(diag["summary"].get("done")) + "\nPublic feedback:\n" + current_output[-10000:])
        if guided:
            instruction += ("\nActual AEE/Evaluator findings (not hidden test results):\n" + assessment_note)
        phase = run_matched_phase(agent, model, store, identity, cfg, f"repair_round{iteration}",
                                  instruction, spec, CALLS_PER_ROUND, deadline, claims=False)
        snap = store.artifact(snapshot_package(sandbox, PROJECTS[project]["package"]))
        current = run_public_tests(sandbox)
        current_output = current["output"]
        rounds.append({"round": iteration, "phase": phase, "public": current,
                       "snapshot": snap, "source_changed": not git_clean(sandbox)})
        store.append("repair_rounds", {**identity, "round": iteration, "timestamp": utc(),
                                       "public_passed": current["passed"], "snapshot": snap})
    final_snapshot = store.artifact(snapshot_package(sandbox, PROJECTS[project]["package"]))
    patch = sandbox.execute("git add -N . && git diff --binary HEAD", 60)
    return {"patch": store.artifact(patch["stdout"].encode()),
            "package_snapshot": final_snapshot,
            "diagnostic_valid": diag["summary"].get("done") is not None and not diag["diagnostic_changed_source"],
            "guided_with_assessment": guided and evaluation is not None,
            "repair_rounds": rounds, "tool_calls": agent.env.tool_calls}


def execute_matched_attempt(root, task, arm, provider, sandbox, store, identity, cfg, manifest):
    if arm == "diagnose":
        return run_diagnostic(root, task, provider, sandbox, store, identity, cfg)
    if arm in ("repair_ordinary", "repair_guided"):
        return run_repair(root, task, arm, provider, sandbox, store, identity, cfg, manifest)
    if arm == "repair_workflow":
        return run_workflow_repair(root, task, provider, sandbox, store, identity, cfg, manifest)
    raise ValueError("unknown matched-repair arm: " + arm)


def _workflow_brief(task, project, diag, public):
    """Shared task brief for the workflow arm: identical start/feedback to the
    repair arms. The diagnostic summary is a matched covariate, explicitly
    labeled assertions-not-proof, exactly as in run_repair."""
    return (
        f"Matched-repair pair {task['instance_id']}: the /testbed repository may contain a seeded defect "
        f"in the {project} package -- possibly spanning modules, with the symptom surfacing in a "
        f"different file than the cause (or it may be a clean negative control: do not change correct "
        f"code without a concrete reason). Preserve existing APIs and tests.\n\n"
        f"Requirements under test:\n{spec_text(project)}\n\n"
        f"Shared diagnostic (assertions are not proof):\n{json.dumps(diag['summary'].get('done'))}\n\n"
        f"Public test feedback:\n{public['output'][-10000:]}")


def run_workflow_repair(root, task, provider, sandbox, store, identity, cfg, manifest):
    """Full Spec-Kit+AEE workflow repair treatment (Claim A local arm, v9 section 1).

    Treatment fidelity: the exact frozen workflow from benchmark_runner.workflow --
    the six phases from phases("spec_kit_aee"), the frozen skill prompts from
    phase_prompt(root, "spec_kit_aee", phase), grounded claims and the AEE assess()
    gate at each AEE phase with bounded recovery rounds (mirroring the proven
    spec_kit_aee arm in runner.execute_attempt). It runs on the matched-repair
    fixture sandbox (/testbed) with the same shared diagnostic and public-test
    feedback as the repair arms, so the only treatment difference is the repair
    method: phased workflow with per-phase AEE gating vs direct repair rounds.
    """
    project, variant, seed = pair_of(task["instance_id"])
    deadline = time.monotonic() + cfg["timeout_seconds"]
    agent = _new_agent(provider, deadline)
    agent.env = MiniEnvironment(sandbox, deadline, store, identity)
    model = agent.model

    diag = _diagnostic_for(store, manifest, task)
    public = run_public_tests(sandbox)
    store.append("public_feedback", {**identity, "stage": "workflow_repair", "timestamp": utc(),
                                     "passed": public["passed"], "test_count": public["test_count"],
                                     "output_tail": public["output"][-4000:]})
    sandbox.stage_workflow(root)
    brief = _workflow_brief(task, project, diag, public)
    claims_schema = (Path(root)/".specify/extensions/aee/templates/aee-claims.json").read_text()

    phase_summaries, assessment_outcome, recoveries, blocked = [], None, 0, False
    for phase in phases("spec_kit_aee"):
        in_aee = phase in AEE_PHASES
        instructions = (
            f"You are executing phase '{phase}' of the frozen Spec-Kit+AEE workflow on this repair task. "
            f"Apply the frozen skill phase below. Write workflow artifacts under /workflow/specs; "
            f"implement the fix in /testbed. Run the public tests yourself to verify; "
            f"hidden acceptance is unavailable.\n\n" + phase_prompt(root, "spec_kit_aee", phase))
        if in_aee:
            instructions += ("\nAt phase completion include claims using this schema example "
                             "(replace all example content):\n" + claims_schema)
        summary = run_matched_phase(agent, model, store, identity, cfg, f"workflow_{phase}",
                                    instructions, brief, WORKFLOW_CALLS_PER_PHASE, deadline,
                                    claims=in_aee)
        if in_aee and summary["done"]:
            claims = grounded_claims(summary["done"].get("claims") or {}, store, identity["attempt_id"])
            result = assess(root, claims, phase, store, identity["attempt_id"])
            assessment_outcome = result["outcome"]
            agent.add_messages({"role": "user", "content": "AEE/Evaluator result: " + json.dumps(result)})
            recovery = 0
            while result["outcome"] == "block" and recovery < cfg["max_recovery_rounds"]:
                recovery += 1
                recoveries += 1
                agent.add_messages({"role": "user", "content": (
                    "Address the AEE/Evaluator result within this phase. Use only task-provided facts; "
                    "no human assistance. Do not change model. Submit revised claims and evidence, "
                    "or retain gaps.")})
                summary = run_matched_phase(agent, model, store, identity, cfg,
                                            f"workflow_{phase}_recovery{recovery}",
                                            instructions, brief, WORKFLOW_CALLS_PER_PHASE,
                                            deadline, claims=True)
                if not summary["done"]:
                    break
                claims = grounded_claims(summary["done"].get("claims") or {}, store,
                                         identity["attempt_id"])
                result = assess(root, claims, phase, store, identity["attempt_id"])
                assessment_outcome = result["outcome"]
                agent.add_messages({"role": "user", "content": "AEE/Evaluator result: " + json.dumps(result)})
            if result["outcome"] == "block":
                blocked = True
                phase_summaries.append(summary)
                break
        phase_summaries.append(summary)

    # Final harness-measured state, in the same shape the grader and the
    # outcome classifier expect from the repair arms.
    final_public = run_public_tests(sandbox)
    final_snapshot = store.artifact(snapshot_package(sandbox, PROJECTS[project]["package"]))
    store.append("repair_rounds", {**identity, "round": "workflow", "timestamp": utc(),
                                   "public_passed": final_public["passed"], "snapshot": final_snapshot})
    patch = sandbox.execute("git add -N . && git diff --binary HEAD", 60)
    return {"patch": store.artifact(patch["stdout"].encode()),
            "package_snapshot": final_snapshot,
            "diagnostic_valid": diag["summary"].get("done") is not None and not diag["diagnostic_changed_source"],
            "workflow_phases": [s["phase"] for s in phase_summaries],
            "workflow_completed": all(s["completed"] for s in phase_summaries),
            "assessment_outcome": assessment_outcome,
            "workflow_recoveries": recoveries,
            "workflow_blocked": blocked,
            "repair_rounds": [{"round": "workflow", "phase": [s["phase"] for s in phase_summaries],
                               "public": final_public, "snapshot": final_snapshot,
                               "source_changed": not git_clean(sandbox)}],
            "tool_calls": agent.env.tool_calls}


# ---------------------------------------------------------------------------
# Fixture Docker images (offline; no model calls)
# ---------------------------------------------------------------------------

REGISTRY = "localhost:5000"
IMAGE_PREFIX = "mr-fixture"


def image_name(project, variant):
    return f"{REGISTRY}/{IMAGE_PREFIX}-{project}-{variant}"


def _copy_package_into(context, project):
    meta = PROJECTS[project]
    import shutil
    if meta.get("synthetic"):
        # Phase-2 synthetic project: the package ships in the repo; there is
        # no upstream checkout to pin. variant_files applies the seeded edits
        # on top of the reference tree after this copy.
        src = ROOT / "benchmarks/repeated_local" / project / "reference"
        package_dst = context / meta["package"]
        shutil.copytree(src, package_dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return meta
    upstream = Path(meta["upstream"])
    actual = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if actual != meta["revision"]:
        raise ValueError(f"upstream {project} not at pinned revision {meta['revision']}: {actual}")
    if subprocess.check_output(["git", "-C", str(upstream), "status", "--porcelain"], text=True).strip():
        raise ValueError(f"upstream {project} checkout is dirty")
    package_src = upstream / meta["package"]
    package_dst = context / meta["package"]
    package_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_src, package_dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
    return meta


def build_fixture_image(project, variant, push=True):
    """Build the fixture image: upstream package + synthetic variant module +
    public acceptance tests, committed as a clean git repo at /testbed.
    Returns (pinned_image_ref, base_commit)."""
    meta = PROJECTS[project]
    with tempfile.TemporaryDirectory(prefix="mr-fixture-") as tmp:
        context = Path(tmp)
        _copy_package_into(context, project)
        for relpath, data in variant_files(project, variant).items():
            (context / relpath).write_bytes(data)
        (context / "acceptance_public.py").write_bytes(tests_for(project, 3, True))
        (context / "Dockerfile").write_text(
            "FROM python:3.12-slim\n"
            "RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git "
            "&& rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pytest\n"
            "WORKDIR /testbed\n"
            "COPY . /testbed/\n"
            "RUN git init -q && git add -A && "
            "git -c user.name=Benchmark -c user.email=benchmark@example.invalid commit -qm fixture\n")
        tag = image_name(project, variant) + ":build"
        subprocess.run(["docker", "build", "-q", "-t", tag, str(context)],
                       check=True, capture_output=True, timeout=600)
        base_commit = subprocess.check_output(
            ["docker", "run", "--rm", tag, "git", "rev-parse", "HEAD"], text=True, timeout=60).strip()
        if push:
            subprocess.run(["docker", "tag", tag, image_name(project, variant) + ":smoke"],
                           check=True, capture_output=True, timeout=60)
            # Surface the daemon's stderr on failure: a bare CalledProcessError
            # hides the real cause (refused/denied/500) behind exit status 1.
            pr = subprocess.run(["docker", "push", image_name(project, variant) + ":smoke"],
                                capture_output=True, text=True, timeout=600)
            if pr.returncode != 0:
                detail = (pr.stderr or pr.stdout or "").strip()
                raise RuntimeError(
                    f"docker push failed for {image_name(project, variant)}:smoke "
                    f"(exit {pr.returncode}):\n{detail}")
            digests = json.loads(subprocess.check_output(
                ["docker", "inspect", image_name(project, variant) + ":smoke"], timeout=60))
            repo_digests = digests[0].get("RepoDigests") or []
            pinned = next((d for d in repo_digests if d.startswith(image_name(project, variant) + "@sha256:")), None)
            if pinned is None:
                raise RuntimeError("no registry digest after push for " + image_name(project, variant))
            return pinned, base_commit
        return tag, base_commit


def ensure_registry():
    probe = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", "mr-registry"],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        if probe.stdout.strip() == "true":
            return
        # Container exists but is stopped (e.g. after a host reboot): start it
        # rather than failing on the name conflict a fresh `docker run` would hit.
        subprocess.run(["docker", "start", "mr-registry"],
                       check=True, capture_output=True, timeout=60)
    else:
        subprocess.run(["docker", "run", "-d", "--restart=always", "--name", "mr-registry",
                        "-p", "5000:5000", "registry:2"], check=True, capture_output=True, timeout=300)
    # Wait for the registry HTTP API itself, not just the container: the
    # registry server takes a few seconds to listen after the container
    # reports running, and pushing before that fails with connection refused.
    import urllib.request
    for _ in range(60):
        time.sleep(2)
        try:
            with urllib.request.urlopen("http://localhost:5000/v2/", timeout=5) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
    raise RuntimeError("local registry did not start")


# ---------------------------------------------------------------------------
# Hidden grading (offline; runs in clean fixture containers)
# ---------------------------------------------------------------------------

def grade_snapshot(pinned_image, snapshot_bytes, project, expected_test_count=None):
    """Apply a package snapshot to a pristine fixture container and run the
    hidden acceptance tests. Hidden tests never enter solver images."""
    name = "mr-grade-" + sha(snapshot_bytes)[:12]
    hidden = tests_for(project, 3, False)
    with tempfile.TemporaryDirectory(prefix="mr-grade-") as tmp:
        snap_path = Path(tmp) / "snapshot.tar"
        snap_path.write_bytes(snapshot_bytes)
        hidden_path = Path(tmp) / "test_acceptance.py"
        hidden_path.write_bytes(hidden)
        try:
            subprocess.run(docker_args(pinned_image, name), check=True, capture_output=True, timeout=120)
            # Fixture images do not ship /grade; this Docker's `cp` will not
            # create missing parent dirs, so create it before copying in.
            subprocess.run(["docker", "exec", name, "mkdir", "-p", "/grade"],
                           check=True, capture_output=True, timeout=60)
            subprocess.run(["docker", "cp", str(snap_path), name + ":/tmp/snapshot.tar"],
                           check=True, capture_output=True, timeout=60)
            subprocess.run(["docker", "cp", str(hidden_path), name + ":/grade/test_acceptance.py"],
                           check=True, capture_output=True, timeout=60)
            setup = subprocess.run(
                ["docker", "exec", name, "bash", "-lc",
                 "mkdir -p /grade && tar -xf /tmp/snapshot.tar -C /testbed && "
                 "PYTHONPATH=src:. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -c /dev/null "
                 "-q /grade/test_acceptance.py --junitxml=/tmp/grade.xml; echo EXIT=$?"],
                capture_output=True, timeout=300)
            xml = subprocess.run(["docker", "exec", name, "cat", "/tmp/grade.xml"],
                                 capture_output=True, timeout=30).stdout.decode(errors="replace")
            cases = parse_junit(xml)
            passed = ("EXIT=0" in setup.stdout.decode(errors="replace") and bool(cases)
                      and all(c["passed"] for c in cases)
                      and (expected_test_count is None or len(cases) == expected_test_count))
            failed = [c["name"] for c in cases if not c["passed"]]
            return {"passed": passed, "test_count": len(cases), "expected": expected_test_count,
                    "failed_cases": failed, "cases": cases,
                    "output": setup.stdout.decode(errors="replace")[-4000:] + setup.stderr.decode(errors="replace")[-2000:]}
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)


def calibrate_fixtures(out, pairs):
    """Offline fixture calibration: seeded variants must fail hidden grading,
    clean controls must pass. Mirrors scripts/matched_repair.py calibration."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for project, variant in pairs:
        pinned, base_commit = build_fixture_image(project, variant)
        name = "mr-calib-" + sha(f"{project}-{variant}".encode())[:12]
        try:
            subprocess.run(docker_args(pinned, name), check=True, capture_output=True, timeout=120)
            snap = snapshot_package(_NamedSandbox(name), PROJECTS[project]["package"])
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        result = grade_snapshot(pinned, snap, project)
        ok = result["passed"] == (variant == "clean")
        rows.append({"project": project, "variant": variant, "image": pinned, "base_commit": base_commit,
                     "grade": result, "calibrated": ok,
                     "seeded_requirements": VARIANTS[project][variant][2]})
        if not ok:
            raise RuntimeError(f"fixture calibration FAILED: {project}/{variant}: {result}")
        print(f"CALIBRATION {project}/{variant}: passed={result['passed']} tests={result['test_count']}", flush=True)
    write_json(out / "calibration.json", {"passed": True, "fixtures": rows, "timestamp": utc()}, exclusive=True)
    return rows


class _NamedSandbox:
    """Minimal adapter so snapshot_package can target an already-running container."""
    def __init__(self, name):
        self.name = name


# ---------------------------------------------------------------------------
# Solver image audit (offline): no hidden grader material in solver images
# ---------------------------------------------------------------------------

def audit_solver_image(pinned_image, project):
    """Verify the solver image contains no hidden tests or grader material:
    only the package, the synthetic module, acceptance_public.py, and git metadata."""
    name = "mr-audit-" + sha(pinned_image.encode())[:12]
    try:
        subprocess.run(docker_args(pinned_image, name), check=True, capture_output=True, timeout=120)
        listing = subprocess.run(["docker", "exec", name, "bash", "-lc",
                                  "find /testbed -type f | sort"],
                                 capture_output=True, timeout=60).stdout.decode()
        files = [l for l in listing.splitlines() if l]
        hidden_markers = [f for f in files
                          if "test_acceptance" in f and "acceptance_public" not in f
                          or "hidden" in f.lower() or "/grade/" in f]
        git_check = subprocess.run(["docker", "exec", name, "bash", "-lc",
                                    "git -C /testbed rev-parse HEAD && git -C /testbed status --porcelain"],
                                   capture_output=True, timeout=60).stdout.decode().strip().splitlines()
        base_commit = git_check[0].strip() if git_check else None
        clean = len(git_check) == 1
        return {"image": pinned_image, "files": files, "hidden_markers": hidden_markers,
                "base_commit": base_commit, "git_clean": clean,
                "audit_pass": not hidden_markers and clean and base_commit is not None}
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)


# ---------------------------------------------------------------------------
# Reservation-bound verification (operator gate before freezing)
# ---------------------------------------------------------------------------

# GPT-6 Astra documented limits (developers.openai.com/api/docs/models, checked 2026-09-20).
# OpenRouter serves the identical model as "openai/gpt-6-astra" (live catalog
# 2026-09-22: context 1,050,000, pricing identical to OpenAI list on every
# tier): same weights, same context window, same documented limits. The gate
# is therefore keyed on the model family, not the API endpoint -- and the
# reservation math reads prices from the frozen cfg snapshot, so a different
# endpoint cannot weaken the bound without failing this check.
ASTRA_MODEL_IDS = frozenset({"gpt-6-astra", "openai/gpt-6-astra"})
ASTRA_MAX_INPUT_TOKENS = 922000
ASTRA_MAX_OUTPUT_TOKENS = 128000


def verify_reservation_bounds(cfg):
    """Verify the model-specific reservation bound the provider enforces.
    Returns the verified numbers; raises on any inconsistency.

    The reservation uses the conservative maximum of the short and long
    price tiers, exactly as provider.query() reserves via request_prices().
    The long-context tier (272K+ input tokens) is provably unreachable
    because max_input_tokens (32,768) is a hard ceiling well below the
    threshold, so the short-tier prices would suffice — but the bound is
    checked against the same conservative reservation the budget enforces,
    never a weaker one.

    Local backend: there is no marginal dollar cost, so every bound is zero
    by construction and there is nothing provider-specific to verify."""
    if cfg.get("provider_backend") == "local":
        return {"per_call_usd": "0", "diagnostic_attempt_usd": "0", "repair_attempt_usd": "0"}
    if cfg["model"] not in ASTRA_MODEL_IDS:
        raise ValueError("reservation bounds verified only for the GPT-6 Astra "
                         "model family (gpt-6-astra, openai/gpt-6-astra)")
    if cfg["max_input_tokens"] > ASTRA_MAX_INPUT_TOKENS:
        raise ValueError("max_input_tokens exceeds Astra documented max input")
    if cfg["max_output_tokens"] > ASTRA_MAX_OUTPUT_TOKENS:
        raise ValueError("max_output_tokens exceeds Astra documented max output")
    if cfg["max_input_tokens"] >= cfg["long_context_threshold"]:
        raise ValueError("max_input_tokens reaches long-context tier; "
                         "long-tier prices would require official verification")
    # Conservative maximum rates, exactly as the provider reserves
    # (request_prices with no usage returns the max of short/long tiers).
    tier = request_prices(cfg)
    per_call = ((Decimal(cfg["max_input_tokens"]) * Decimal(str(tier["input"]))
                 + Decimal(cfg["max_output_tokens"]) * Decimal(str(tier["output"]))) / Decimal(1_000_000))
    worst = {
        "per_call_usd": str(per_call),
        "diagnostic_attempt_usd": str(per_call * DIAGNOSTIC_CALLS),
        "repair_attempt_usd": str(per_call * REPAIR_ROUNDS * CALLS_PER_ROUND),
    }
    if Decimal(worst["repair_attempt_usd"]) > Decimal(str(cfg["attempt_cap_usd"])):
        raise ValueError("worst-case repair reservation exceeds attempt cap")
    if Decimal(worst["diagnostic_attempt_usd"]) > Decimal(str(cfg["attempt_cap_usd"])):
        raise ValueError("worst-case diagnostic reservation exceeds attempt cap")
    return worst


# ---------------------------------------------------------------------------
# Post-run hidden acceptance grading (offline; Docker only, no model calls)
# ---------------------------------------------------------------------------

def grade_run(run_dir, grade_fn=None):
    """Grade a completed scored run's repair snapshots with the hidden
    acceptance tests. Runs after ALL attempts are done: hidden outcomes are
    recorded in the `hidden_grades` event stream and never fed back to any
    attempt. Offline (Docker only, no model calls) and idempotent: attempts
    already graded are skipped. Fails closed on missing snapshots or hash
    mismatches."""
    grade_fn = grade_fn or grade_snapshot
    run_dir = Path(run_dir)
    manifest = read_json(run_dir / "freeze.json")
    tasks = {t["instance_id"]: t for t in manifest["tasks"]["tasks"]}
    store = Store(run_dir)
    graded = {e["attempt_id"] for e in store.events("hidden_grades")}
    latest = {}
    for e in store.events("attempts"):
        latest[e["attempt_id"]] = e
    results = []
    for attempt_id in sorted(latest):
        attempt = latest[attempt_id]
        if attempt_id in graded:
            continue
        if attempt.get("arm") not in ("repair_ordinary", "repair_guided", "repair_workflow"):
            continue
        identity = {"attempt_id": attempt_id, "task_id": attempt["task_id"], "arm": attempt["arm"],
                    "experiment_id": manifest["freeze_id"], "run_id": manifest["freeze_id"][:16],
                    "purpose": manifest["config"]["purpose"]}
        if attempt.get("status") != "completed":
            store.append("hidden_grades", {**identity, "graded": False,
                                           "reason": "attempt status %s; no final snapshot to grade"
                                                     % attempt.get("status"),
                                           "timestamp": utc()})
            results.append((attempt_id, "skipped"))
            print(f"GRADE {attempt_id}: skipped ({attempt.get('status')})", flush=True)
            continue
        snap_ref = attempt.get("package_snapshot")
        if not snap_ref:
            raise ValueError(f"completed repair attempt {attempt_id} has no package_snapshot")
        snap_path = store.root / snap_ref["path"]
        data = snap_path.read_bytes()
        if sha(data) != snap_ref["sha256"]:
            raise ValueError(f"package snapshot changed for {attempt_id}")
        project, _, _ = pair_of(attempt["task_id"])
        task = tasks[attempt["task_id"]]
        grade = grade_fn(task["image"], data, project, task.get("hidden_test_count"))
        store.append("hidden_grades", {**identity, "graded": True,
                                       "hidden_passed": grade["passed"],
                                       "test_count": grade["test_count"],
                                       "expected_test_count": grade["expected"],
                                       "failed_cases": grade["failed_cases"],
                                       "grade_artifact": store.artifact(canonical(grade)),
                                       "timestamp": utc()})
        results.append((attempt_id, grade["passed"]))
        print(f"GRADE {attempt_id}: hidden_passed={grade['passed']} "
              f"tests={grade['test_count']} failed={grade['failed_cases']}", flush=True)
    return results


def graded_comparison(run_dir):
    """Per-pair ordinary-vs-guided hidden outcomes from the hidden_grades
    stream. Only graded attempts appear; pairs with a missing arm are honest
    about it (no imputation). hidden_pass_rate is the primary comparison
    metric for hard pairs where partial passes are expected."""
    grades = {}
    for e in Store(Path(run_dir)).events("hidden_grades"):
        grades[e["attempt_id"]] = e
    pairs = {}
    for g in grades.values():
        row = pairs.setdefault(g["task_id"], {})
        if g.get("graded"):
            failed = g["failed_cases"] or []
            total = g["test_count"]
            rate = (total - len(failed)) / total if total else None
            row[g["arm"]] = {"hidden_passed": g["hidden_passed"],
                             "test_count": total,
                             "failed_cases": failed,
                             "hidden_pass_rate": rate}
        else:
            row[g["arm"]] = {"hidden_passed": None, "reason": g.get("reason")}
    return pairs


# ---------------------------------------------------------------------------
# Smoke freeze builder (freeze v4)
# ---------------------------------------------------------------------------

SMOKE_PAIR = ("tinydb", "bool_id", 20260918)

# First scored pair: the smoke pair above is excluded from every scored freeze,
# so the pilot starts on the next tinydb variant with the same scored seed.
SCORED_PAIR = ("tinydb", "token_alias", 20260918)

BUDGET_AUTHORIZATION = (
    "On 2026-09-20 Tristen authorized a 3-attempt development smoke with attempt_cap_usd=25 and global_cap_usd=100."
)

SCORED_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized a fresh 3-attempt scored matched-repair comparison "
    "(freeze v5, pair tinydb/token_alias, seed 20260918, model gpt-6-astra) with attempt_cap_usd=25 "
    "and global_cap_usd=100. Prior measured spend: $1.4831 (smoke v4, 2026-09-21). The 2026-09-20 "
    "failed run's unmeasured charge was discounted by Tristen on 2026-09-21 as unverifiable."
)

REAL_SMOKE_EVIDENCE = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC: 3/3 attempts completed "
    "(diagnose $0.3728, repair_ordinary $0.4815, repair_guided $0.6287), 32 model calls, "
    "$1.4831 measured spend. Validated in production: provider telemetry-identity check "
    "before the HTTP request (fail fast before spending) and budget settlement in a finally "
    "block. real_smoke_verified=True is grounded on this completed smoke run."
)

PRICE_SOURCE = (
    "https://openai.com/fr-CA/api/pricing/ and https://developers.openai.com/api/docs/models "
    "(checked 2026-09-20): GPT-6 Astra list $10/1M input, $1/1M cached input, $50/1M output; "
    "requests above 272,000 input tokens bill $20/1M input, $2/1M cached input, $75/1M output "
    "for the full request. Model id gpt-6-astra is the only published snapshot/alias. "
    "Cross-checked 2026-09-20 against multiple outlets citing OpenAI's pricing page "
    "(cloudzero.com, laozhang.ai, devtoollab.com, kingy.ai): $10/$1/$50 standard; "
    "$20/$2/$75 above 272K input tokens for the entire request; API model string gpt-6-astra; "
    "~1.1M token context window."
)

# OpenRouter catalog pricing for openai/gpt-6-astra, checked 2026-09-22
# against the live https://openrouter.ai/api/v1/models catalog
# (context_length 1,050,000; per-token USD: prompt 0.00001, completion
# 0.00005, input_cache_read 0.000001; above 272,000 prompt tokens the
# override tier bills prompt 0.00002, completion 0.000075,
# input_cache_read 0.000002). Per 1M tokens: $10/$1/$50 standard,
# $20/$2/$75 long-context -- identical to the OpenAI list prices above.
# The OpenAI <-> OpenRouter price delta for GPT-6 Astra is $0 on every
# tier; moving the frontier arm between providers changes no dollar amount
# in the reservation or the spend accounting.
OPENROUTER_PRICE_SOURCE = (
    "https://openrouter.ai/api/v1/models (checked 2026-09-22): openai/gpt-6-astra "
    "(OpenAI: GPT-6 Astra), context 1,050,000, list $10/1M input, $1/1M cached input, "
    "$50/1M output; requests above 272,000 input tokens bill $20/1M input, $2/1M cached "
    "input, $75/1M output for the full request. API model string openai/gpt-6-astra. "
    "Identical to the OpenAI list prices on every tier: the provider switch changes "
    "no dollar amount in the reservation or spend accounting."
)

# Price snapshot for the OpenRouter-served frontier arm, in the same schema
# as smoke_config(). Historical freezes keep their own snapshots untouched.
OPENROUTER_PRICE_SNAPSHOT_ID = "openrouter-list-2026-09-22"
OPENROUTER_PRICES = {"input": 10.0, "cached_input": 1.0, "output": 50.0}
OPENROUTER_LONG_CONTEXT_PRICES = {"input": 20.0, "cached_input": 2.0, "output": 75.0}


def smoke_config():
    return {
        "schema_version": 1,
        "purpose": "development_smoke",
        "seed": 20260920,
        "repeats": 1,
        "runner": "mini-swe-agent-2.4.6-instrumented",
        "model": "gpt-6-astra",
        "reasoning_effort": "medium",
        "temperature": None,
        "max_input_tokens": 32768,
        "max_output_tokens": 4096,
        "token_cap": 1000000,
        "global_cap_usd": 100,
        "attempt_cap_usd": 25,
        "timeout_seconds": 1800,
        "max_calls": 24,
        "max_recovery_rounds": 2,
        "price_snapshot_id": "openai-list-2026-09-20",
        "price_source": PRICE_SOURCE,
        "prices": {"input": 10.0, "cached_input": 1.0, "output": 50.0},
        "long_context_prices": {"input": 20.0, "cached_input": 2.0, "output": 75.0},
        "long_context_threshold": 272000,
        "currency": "USD",
        "service_tier": "default",
        "budget_authorization": BUDGET_AUTHORIZATION,
        # Frozen transport policy (pacing/retry bounds): part of the
        # campaign-frozen config, validated by validate_live before any
        # spend. 1s process-wide minimum gap between physical provider
        # requests; retries only on 429/5xx (never on ambiguous transport
        # failures or timeouts); at most 6 physical attempts per query with
        # 300s total backoff budget.
        "transport": {
            "min_request_gap_seconds": 1.0,
            "max_http_attempts": 6,
            "base_backoff_seconds": 2.0,
            "max_backoff_seconds": 120.0,
            "max_total_backoff_seconds": 300.0,
        },
        "reservation_bound_verified": False,
        "grader_smoke_verified": False,
        "real_smoke_verified": False,
        "solver_image_audit_verified": False,
    }


def scored_config():
    """Frozen config for the first scored matched-repair comparison (freeze v5).

    Same model, caps, and token bounds as the smoke. real_smoke_verified=True is
    grounded on the completed freeze-v4 smoke (see REAL_SMOKE_EVIDENCE); the scored
    seed is 20260918 per the standing benchmark plan."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": 20260918,
        "budget_authorization": SCORED_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE,
    })
    return cfg


def run_grade_smoke(calibration):
    """Independent grader smoke (gate): per project, a seeded-bug snapshot
    must fail hidden grading and a clean snapshot must pass — exercises the
    full snapshot -> grade path on both outcomes. Raises on failure."""
    results = {}
    projects = sorted({f["project"] for f in calibration["fixtures"]})
    for project in projects:
        bad = next(f for f in calibration["fixtures"] if f["project"] == project and f["variant"] != "clean")
        good = next(f for f in calibration["fixtures"] if f["project"] == project and f["variant"] == "clean")
        project_results = {}
        for fixture, key in ((bad, "bad"), (good, "good")):
            name = f"mr-gsmoke-{project}-{key}"
            try:
                subprocess.run(docker_args(fixture["image"], name), check=True,
                               capture_output=True, timeout=120)
                snap = snapshot_package(_NamedSandbox(name), PROJECTS[project]["package"])
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            project_results[key] = grade_snapshot(fixture["image"], snap, project)
        print(f"GRADER SMOKE {project}: bad_passed={project_results['bad']['passed']} "
              f"good_passed={project_results['good']['passed']} "
              f"tests={project_results['good']['test_count']}", flush=True)
        if project_results["bad"]["passed"] or not project_results["good"]["passed"]:
            raise ValueError(f"grader smoke failed for {project}")
        results[project] = {k: {"passed": v["passed"], "test_count": v["test_count"],
                                "failed_cases": v["failed_cases"]}
                            for k, v in project_results.items()}
    print("GRADER SMOKE PASS", flush=True)
    return results


def build_smoke_freeze(output, calibration):
    """Build freeze v4 for the 3-attempt development smoke. `calibration` is the
    fixture calibration record (image refs + base commits). Runs every offline
    gate itself — reservation bounds, solver image audit, grader smoke — and
    sets the verification flags True only when each gate genuinely passes.
    Fails closed otherwise."""
    project, variant, seed = SMOKE_PAIR
    pair_id = f"mr-{project}-{variant}-{seed}"
    fixture = next(f for f in calibration["fixtures"]
                   if (f["project"], f["variant"]) == (project, variant))
    cfg = smoke_config()
    reservation = verify_reservation_bounds(cfg)
    audit = audit_solver_image(fixture["image"], project)
    if not audit["audit_pass"]:
        raise ValueError("solver image audit failed: " + json.dumps(audit["hidden_markers"]))
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True
    problem_statement = (
        f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
        f"in {PROJECTS[project]['module']} (or may be a clean negative control). "
        "Protocol: (1) a shared read-only diagnostic attempt reviews the implementation and public test "
        "feedback and returns grounded requirement claims with explicit uncertainty; (2) two repair attempts "
        "(ordinary and AEE-guided) start from the same pristine snapshot and each get two repair rounds. "
        "The guided arm additionally receives the actual AEE/Evaluator findings from the shared diagnostic. "
        "Hidden acceptance tests grade the final package snapshots after all runs; hidden outcomes are never "
        "fed back to any attempt.")
    tasks = {"schema_version": 1, "seed": cfg["seed"],
             "selection": "matched-repair development smoke: single excluded pair",
             "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                  if (p, v, s) != SMOKE_PAIR),
             "tasks": [{"instance_id": pair_id, "repo": "matched-repair-fixture",
                        "base_commit": fixture["base_commit"], "problem_statement": problem_statement,
                        "image": fixture["image"], "language": "python"}]}
    arms = ["repair_ordinary", "repair_guided"]
    random.Random(seed + len(variant)).shuffle(arms)
    ordered_arms = ["diagnose"] + arms
    schedule = [dict(task_id=pair_id, arm=arm, repeat=1, attempt_id=f"{pair_id}--{arm}")
                for arm in ordered_arms]
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": tasks,
        "schedule": schedule,
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden outcomes never feed back. The smoke pair "
                    "is excluded from any future scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audit": audit,
        "grade_smoke": grade_smoke,
        "fixture": {"project": project, "variant": variant, "seed": seed,
                    "image": fixture["image"], "base_commit": fixture["base_commit"],
                    "hidden_test_count": fixture["grade"]["test_count"]},
        "notes": ("Freeze v4: development smoke only. Real smoke is an integration and spend-measurement check, "
                  "not a performance comparison. Historical freezes v2/v3 and all prior evidence are untouched."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v4-smoke.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# Scored freeze builder (freeze v5)
# ---------------------------------------------------------------------------

def build_scored_freeze(output, calibration):
    """Build freeze v5: the first scored matched-repair comparison. Same three
    arms and the same offline gates as the smoke; runs scored (hidden grading
    after the run), so real_smoke_verified must be True — grounded on the
    completed freeze-v4 smoke (see REAL_SMOKE_EVIDENCE). The smoke pair
    (tinydb/bool_id) is excluded by construction. Fails closed otherwise."""
    project, variant, seed = SCORED_PAIR
    pair_id = f"mr-{project}-{variant}-{seed}"
    fixture = next(f for f in calibration["fixtures"]
                   if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config()
    reservation = verify_reservation_bounds(cfg)
    audit = audit_solver_image(fixture["image"], project)
    if not audit["audit_pass"]:
        raise ValueError("solver image audit failed: " + json.dumps(audit["hidden_markers"]))
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True
    problem_statement = (
        f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
        f"in {PROJECTS[project]['module']} (or may be a clean negative control). "
        "Protocol: (1) a shared read-only diagnostic attempt reviews the implementation and public test "
        "feedback and returns grounded requirement claims with explicit uncertainty; (2) two repair attempts "
        "(ordinary and AEE-guided) start from the same pristine snapshot and each get two repair rounds. "
        "The guided arm additionally receives the actual AEE/Evaluator findings from the shared diagnostic. "
        "Hidden acceptance tests grade the final package snapshots after all runs; hidden outcomes are never "
        "fed back to any attempt.")
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    tasks = {"schema_version": 1, "seed": cfg["seed"],
             "selection": "matched-repair scored comparison: single pair (smoke pair excluded)",
             "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                  if (p, v, s) != SCORED_PAIR),
             "tasks": [{"instance_id": pair_id, "repo": "matched-repair-fixture",
                        "base_commit": fixture["base_commit"], "problem_statement": problem_statement,
                        "image": fixture["image"], "language": "python"}]}
    arms = ["repair_ordinary", "repair_guided"]
    random.Random(seed + len(variant)).shuffle(arms)
    ordered_arms = ["diagnose"] + arms
    schedule = [dict(task_id=pair_id, arm=arm, repeat=1, attempt_id=f"{pair_id}--{arm}")
                for arm in ordered_arms]
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": tasks,
        "schedule": schedule,
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden outcomes never feed back. The smoke pair "
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audit": audit,
        "grade_smoke": grade_smoke,
        "fixture": {"project": project, "variant": variant, "seed": seed,
                    "image": fixture["image"], "base_commit": fixture["base_commit"],
                    "hidden_test_count": fixture["grade"]["test_count"]},
        "notes": ("Freeze v5: first scored matched-repair comparison. Scored seed 20260918, model gpt-6-astra. "
                  "Freeze v4 (development smoke) and all prior evidence are untouched; negative and partial "
                  "outcomes are preserved in the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v5-scored.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# Scored freeze builder (freeze v6): full scored set with hidden grading
# ---------------------------------------------------------------------------

# Every variant at the scored seed except the smoke pair
# (tinydb/bool_id/20260918), which is excluded from every scored freeze.
# Clean variants are negative controls: the agent must not change correct
# code without a concrete reason; hidden grading expects them to pass.
#
# Pinned explicitly (not derived from VARIANTS): the v7 hard-pair variants
# added to VARIANTS must not leak into the frozen v6 set.
SCORED_SEED_V6 = 20260918
SCORED_PAIRS_V6 = (
    ("tinydb", "token_alias", SCORED_SEED_V6),
    ("tinydb", "partial_commit", SCORED_SEED_V6),
    ("tinydb", "clean", SCORED_SEED_V6),
    ("cachetools", "expiry_boundary", SCORED_SEED_V6),
    ("cachetools", "value_alias", SCORED_SEED_V6),
    ("cachetools", "boolean_ttl", SCORED_SEED_V6),
    ("cachetools", "clean", SCORED_SEED_V6),
)

SCORED_V6_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized a scored matched-repair campaign with attempt_cap_usd=25 and "
    "global_cap_usd=100 (freeze v5: 3 attempts on tinydb/token_alias, seed 20260918, model gpt-6-astra), "
    "and on 2026-09-21 further authorized rerunning the full scored set with hidden acceptance grading "
    "in the mix (freeze v6: all 7 scored pairs at seed 20260918, 21 attempts) under the same $25/attempt "
    "and $100 global caps. Prior measured spend: $1.4831 (smoke v4) + $1.5029 (scored v5) = $2.9860; "
    "$97.0140 of the global cap remains. Expected v6 spend ~$10.50 at v5's $1.50/pair rate. "
    "The 2026-09-20 failed run's unmeasured charge was discounted by Tristen on 2026-09-21 as unverifiable. "
    "Spend settles to measured usage; unknown usage is never released."
)

REAL_SMOKE_EVIDENCE_V6 = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC (3/3 attempts, $1.4831 measured) and "
    "freeze v5 scored comparison completed 2026-09-21 ~12:23 UTC (3/3 attempts on tinydb/token_alias, "
    "$1.5029 measured, diagnostic_valid=true, guided_with_assessment=true). "
    "real_smoke_verified=True is grounded on both completed runs."
)


def scored_config_v6():
    """Frozen config for the full scored campaign (freeze v6).

    Same model, caps, and token bounds as v5. real_smoke_verified=True is
    grounded on the completed v4 smoke AND the completed v5 scored run
    (see REAL_SMOKE_EVIDENCE_V6)."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": SCORED_SEED_V6,
        "budget_authorization": SCORED_V6_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE_V6,
    })
    return cfg


def scored_v6_schedule():
    """Deterministic 21-attempt schedule for freeze v6: per pair, diagnose
    first, then the two repair arms in seeded-shuffled order. Pure function of
    SCORED_PAIRS_V6 (no Docker, no model calls)."""
    schedule = []
    for i, (project, variant, seed) in enumerate(SCORED_PAIRS_V6):
        pair_id = f"mr-{project}-{variant}-{seed}"
        arms = ["repair_ordinary", "repair_guided"]
        random.Random(seed + len(variant) + i).shuffle(arms)
        for arm in ["diagnose"] + arms:
            schedule.append(dict(task_id=pair_id, arm=arm, repeat=1,
                                 attempt_id=f"{pair_id}--{arm}"))
    return schedule


def build_scored_freeze_v6(output, calibration):
    """Build freeze v6: the full scored campaign with hidden acceptance
    grading in the mix. Seven pairs at the scored seed (smoke pair excluded),
    three arms each, 21 attempts. Same offline gates as v5 — reservation
    bounds, per-fixture solver image audit, grader smoke — plus
    real_smoke_verified grounded on the completed v4 and v5 runs. Fails
    closed otherwise."""
    fixtures = {}
    for project, variant, seed in SCORED_PAIRS_V6:
        fixtures[(project, variant)] = next(
            f for f in calibration["fixtures"]
            if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config_v6()
    reservation = verify_reservation_bounds(cfg)
    audits = {}
    for (project, variant), fixture in fixtures.items():
        audit = audit_solver_image(fixture["image"], project)
        if not audit["audit_pass"]:
            raise ValueError(f"solver image audit failed for {project}/{variant}: "
                             + json.dumps(audit["hidden_markers"]))
        audits[f"{project}/{variant}"] = audit
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True

    def problem_statement(pair_id, project):
        return (
            f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
            f"in {PROJECTS[project]['module']} (or may be a clean negative control). "
            "Protocol: (1) a shared read-only diagnostic attempt reviews the implementation and public test "
            "feedback and returns grounded requirement claims with explicit uncertainty; (2) two repair attempts "
            "(ordinary and AEE-guided) start from the same pristine snapshot and each get two repair rounds. "
            "The guided arm additionally receives the actual AEE/Evaluator findings from the shared diagnostic. "
            "After all runs, the final package snapshots are graded with hidden acceptance tests; "
            "hidden outcomes are never fed back to any attempt.")

    tasks = []
    for project, variant, seed in SCORED_PAIRS_V6:
        pair_id = f"mr-{project}-{variant}-{seed}"
        fixture = fixtures[(project, variant)]
        tasks.append({"instance_id": pair_id, "repo": "matched-repair-fixture",
                      "base_commit": fixture["base_commit"],
                      "problem_statement": problem_statement(pair_id, project),
                      "image": fixture["image"], "language": "python",
                      "hidden_test_count": fixture["grade"]["test_count"]})
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": {"schema_version": 1, "seed": cfg["seed"],
                  "selection": "matched-repair scored campaign: all pairs at the scored seed (smoke pair excluded)",
                  "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                       if (p, v, s) not in set(SCORED_PAIRS_V6)),
                  "tasks": tasks},
        "schedule": scored_v6_schedule(),
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden grading of final snapshots happens after "
                    "all runs and is never fed back. The smoke pair "
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audits": audits,
        "grade_smoke": grade_smoke,
        "pairs": [{"project": p, "variant": v, "seed": s,
                   "image": fixtures[(p, v)]["image"],
                   "base_commit": fixtures[(p, v)]["base_commit"],
                   "hidden_test_count": fixtures[(p, v)]["grade"]["test_count"]}
                  for p, v, s in SCORED_PAIRS_V6],
        "notes": ("Freeze v6: full scored campaign (7 pairs x 3 arms = 21 attempts) with post-run hidden "
                  "acceptance grading of every completed repair snapshot. Reruns the v5 pair (tinydb/token_alias) "
                  "so grading is in the mix for the whole set. Freezes v4/v5 and all prior evidence untouched; "
                  "negative and partial outcomes are preserved in the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v6-scored.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# Scored freeze builder (freeze v7): hard pairs designed to separate the arms
# ---------------------------------------------------------------------------

# After the v6 null result (all 14 repair snapshots 16/16 hidden, ordinary and
# guided identical), v7 keeps the tinydb/token_alias anchor and both clean
# negative controls, and adds five hard pairs. Every hard pair was verified
# offline 2026-09-21: all 4 public tests pass on the seeded defect, at least
# one hidden test fails, and the reference passes the full hidden set.
# v6-only single-defect variants (bool_id, partial_commit, value_alias,
# boolean_ttl, expiry_boundary) are excluded; the expiry_boundary defect
# returns inside the coupled pair.
SCORED_SEED_V7 = 20260918
SCORED_PAIRS_V7 = (
    ("tinydb", "token_alias", SCORED_SEED_V7),
    ("cachetools", "empty_tags", SCORED_SEED_V7),
    ("tinydb", "token_reserve", SCORED_SEED_V7),
    ("cachetools", "expiry_retain", SCORED_SEED_V7),
    ("tinydb", "storage_alias", SCORED_SEED_V7),
    ("cachetools", "coupled", SCORED_SEED_V7),
    ("tinydb", "clean", SCORED_SEED_V7),
    ("cachetools", "clean", SCORED_SEED_V7),
)

SCORED_V7_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized the freeze-v7 hard-pair scored campaign: "
    "24 attempts (8 pairs x diagnose/ordinary/guided) on gpt-6-astra with "
    "attempt_cap_usd=25 and global_cap_usd=100. Expected spend ~$14-19. "
    "Prior measured spend: $11.8730 against the $100 global cap ($88.1270 remaining). "
    "Spend settles to measured usage; unknown usage is never released."
)

REAL_SMOKE_EVIDENCE_V7 = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC (3/3 attempts, $1.4831 measured), "
    "freeze v5 scored comparison completed 2026-09-21 ~12:23 UTC (3/3 attempts on tinydb/token_alias, "
    "$1.5029 measured, diagnostic_valid=true, guided_with_assessment=true), and freeze v6 full scored "
    "campaign completed 2026-09-21 ~13:25 UTC (21/21 attempts, $8.8870 measured, hidden acceptance "
    "grading 14/14 PASS). real_smoke_verified=True is grounded on these completed runs: the paid model "
    "path is proven end to end."
)


def scored_config_v7():
    """Frozen config for the hard-pair scored campaign (freeze v7).

    Same model, caps, and token bounds as v6. real_smoke_verified=True is
    grounded on the completed v4/v5/v6 runs (see REAL_SMOKE_EVIDENCE_V7).
    Tristen authorized this campaign on 2026-09-21 (see
    SCORED_V7_BUDGET_AUTHORIZATION); the host RUN gate still takes his typed
    RUN as the fresh confirmation before any paid call."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": SCORED_SEED_V7,
        "budget_authorization": SCORED_V7_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE_V7,
    })
    return cfg


def scored_v7_schedule():
    """Deterministic 24-attempt schedule for freeze v7: per pair, diagnose
    first, then the two repair arms in seeded-shuffled order. Pure function of
    SCORED_PAIRS_V7 (no Docker, no model calls)."""
    schedule = []
    for i, (project, variant, seed) in enumerate(SCORED_PAIRS_V7):
        pair_id = f"mr-{project}-{variant}-{seed}"
        arms = ["repair_ordinary", "repair_guided"]
        random.Random(seed + len(variant) + i).shuffle(arms)
        for arm in ["diagnose"] + arms:
            schedule.append(dict(task_id=pair_id, arm=arm, repeat=1,
                                 attempt_id=f"{pair_id}--{arm}"))
    return schedule


def build_scored_freeze_v7(output, calibration):
    """Build freeze v7: the hard-pair scored campaign. Eight pairs at the
    scored seed (token_alias anchor, five hard pairs, both clean controls),
    three arms each, 24 attempts. Same offline gates as v6 — reservation
    bounds, per-fixture solver image audit, grader smoke. Fails closed
    otherwise. Offline only: no model calls, no spend."""
    fixtures = {}
    for project, variant, seed in SCORED_PAIRS_V7:
        fixtures[(project, variant)] = next(
            f for f in calibration["fixtures"]
            if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config_v7()
    reservation = verify_reservation_bounds(cfg)
    audits = {}
    for (project, variant), fixture in fixtures.items():
        audit = audit_solver_image(fixture["image"], project)
        if not audit["audit_pass"]:
            raise ValueError(f"solver image audit failed for {project}/{variant}: "
                             + json.dumps(audit["hidden_markers"]))
        audits[f"{project}/{variant}"] = audit
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True

    def problem_statement(pair_id, project):
        return (
            f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
            f"in {PROJECTS[project]['module']} (or may be a clean negative control). "
            "Protocol: (1) a shared read-only diagnostic attempt reviews the implementation and public test "
            "feedback and returns grounded requirement claims with explicit uncertainty; (2) two repair attempts "
            "(ordinary and AEE-guided) start from the same pristine snapshot and each get two repair rounds. "
            "The guided arm additionally receives the actual AEE/Evaluator findings from the shared diagnostic. "
            "After all runs, the final package snapshots are graded with hidden acceptance tests; "
            "hidden outcomes are never fed back to any attempt.")

    tasks = []
    for project, variant, seed in SCORED_PAIRS_V7:
        pair_id = f"mr-{project}-{variant}-{seed}"
        fixture = fixtures[(project, variant)]
        tasks.append({"instance_id": pair_id, "repo": "matched-repair-fixture",
                      "base_commit": fixture["base_commit"],
                      "problem_statement": problem_statement(pair_id, project),
                      "image": fixture["image"], "language": "python",
                      "hidden_test_count": fixture["grade"]["test_count"]})
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": {"schema_version": 1, "seed": cfg["seed"],
                  "selection": ("matched-repair scored campaign: hard pairs at the scored seed "
                                "(token_alias anchor, five hard pairs, both clean controls)"),
                  "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                       if (p, v, s) not in set(SCORED_PAIRS_V7)),
                  "tasks": tasks},
        "schedule": scored_v7_schedule(),
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden grading of final snapshots happens after "
                    "all runs and is never fed back. The smoke pair "
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audits": audits,
        "grade_smoke": grade_smoke,
        "pairs": [{"project": p, "variant": v, "seed": s,
                   "image": fixtures[(p, v)]["image"],
                   "base_commit": fixtures[(p, v)]["base_commit"],
                   "hidden_test_count": fixtures[(p, v)]["grade"]["test_count"]}
                  for p, v, s in SCORED_PAIRS_V7],
        "notes": ("Freeze v7: hard-pair scored campaign (8 pairs x 3 arms = 24 attempts) designed to separate "
                  "ordinary vs guided repair after the v6 null result (all 14 repair snapshots 16/16 hidden). "
                  "Five hard pairs (empty_tags, token_reserve, expiry_retain, storage_alias, coupled) target "
                  "diagnosis adjudication rather than defect visibility; the tinydb/token_alias anchor is kept "
                  "for longitudinal comparison and now carries the replay-detach trap test; both clean negative "
                  "controls are kept. Per-arm hidden pass-rate is the primary comparison metric. Freezes "
                  "v4/v5/v6 and all prior evidence untouched; negative and partial outcomes are preserved in "
                  "the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v7-scored.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# Scored freeze builder (freeze v8): phase-2 cross-file defect task class
# ---------------------------------------------------------------------------

# After the v7 null (second consecutive graded null on guided-vs-ordinary
# quality; ceiling effect at gpt-6-astra on single-module repair), v8 pilots
# the harder task class from the design doc: a synthetic three-module package
# (minisched) with defects whose symptom surfaces in scheduler.py while the
# cause lives in config.py or store.py, each with a plausible wrong-layer fix
# in scheduler.py that passes every public test but fails hidden tests pinned
# at the true layer. Every pair was verified offline 2026-09-21: all 4 public
# tests pass on each seeded defect, hidden tests fail exactly the expected
# requirement tests, the reference passes the full hidden set, and both
# wrong-layer trap repairs pass public while failing hidden.
SCORED_SEED_V8 = 20260918
SCORED_PAIRS_V8 = (
    ("minisched", "config_default", SCORED_SEED_V8),
    ("minisched", "store_add_alias", SCORED_SEED_V8),
    ("minisched", "coupled_xfile", SCORED_SEED_V8),
    ("minisched", "clean", SCORED_SEED_V8),
)

SCORED_V8_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized the freeze-v8 phase-2 cross-file scored campaign "
    "(\"design and execute phase-2 harder task class\"): 12 attempts (4 pairs x "
    "diagnose/ordinary/guided) on gpt-6-astra with attempt_cap_usd=25 and global_cap_usd=100. "
    "Expected spend ~$6-9. Prior measured spend: $22.8863 against the $100 global cap "
    "($77.1137 remaining). Spend settles to measured usage; unknown usage is never released."
)

REAL_SMOKE_EVIDENCE_V8 = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC (3/3 attempts, $1.4831 measured), "
    "freeze v5 scored comparison completed 2026-09-21 ~12:23 UTC (3/3 attempts on tinydb/token_alias, "
    "$1.5029 measured, diagnostic_valid=true, guided_with_assessment=true), freeze v6 full scored "
    "campaign completed 2026-09-21 ~13:25 UTC (21/21 attempts, $8.8870 measured, hidden acceptance "
    "grading 14/14 PASS), and freeze v7 hard-pair campaign completed 2026-09-21 (24/24 attempts, "
    "$11.0133 measured, hidden acceptance grading 16/16 PASS, second consecutive null on "
    "guided-vs-ordinary quality). real_smoke_verified=True is grounded on these completed runs: "
    "the paid model path is proven end to end."
)


def scored_config_v8():
    """Frozen config for the phase-2 cross-file scored campaign (freeze v8).

    Same model, caps, and token bounds as v6/v7. real_smoke_verified=True is
    grounded on the completed v4/v5/v6/v7 runs (see REAL_SMOKE_EVIDENCE_V8).
    Tristen authorized this campaign on 2026-09-21 (see
    SCORED_V8_BUDGET_AUTHORIZATION); the host RUN gate still takes his typed
    RUN as the fresh confirmation before any paid call."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": SCORED_SEED_V8,
        "budget_authorization": SCORED_V8_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE_V8,
    })
    return cfg


def scored_v8_schedule():
    """Deterministic 12-attempt schedule for freeze v8: per pair, diagnose
    first, then the two repair arms in seeded-shuffled order. Pure function of
    SCORED_PAIRS_V8 (no Docker, no model calls)."""
    schedule = []
    for i, (project, variant, seed) in enumerate(SCORED_PAIRS_V8):
        pair_id = f"mr-{project}-{variant}-{seed}"
        arms = ["repair_ordinary", "repair_guided"]
        random.Random(seed + len(variant) + i).shuffle(arms)
        for arm in ["diagnose"] + arms:
            schedule.append(dict(task_id=pair_id, arm=arm, repeat=1,
                                 attempt_id=f"{pair_id}--{arm}"))
    return schedule


def build_scored_freeze_v8(output, calibration):
    """Build freeze v8: the phase-2 cross-file scored campaign. Four minisched
    pairs at the scored seed, three arms each, 12 attempts. Same offline gates
    as v6/v7 — reservation bounds, per-fixture solver image audit, grader
    smoke. Fails closed otherwise. Offline only: no model calls, no spend."""
    fixtures = {}
    for project, variant, seed in SCORED_PAIRS_V8:
        fixtures[(project, variant)] = next(
            f for f in calibration["fixtures"]
            if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config_v8()
    reservation = verify_reservation_bounds(cfg)
    audits = {}
    for (project, variant), fixture in fixtures.items():
        audit = audit_solver_image(fixture["image"], project)
        if not audit["audit_pass"]:
            raise ValueError(f"solver image audit failed for {project}/{variant}: "
                             + json.dumps(audit["hidden_markers"]))
        audits[f"{project}/{variant}"] = audit
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True

    def problem_statement(pair_id, project):
        return (
            f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
            f"in the {PROJECTS[project]['package']} package — possibly spanning modules, with the "
            f"symptom surfacing in a different file than the cause (or it may be a clean negative "
            f"control). Protocol: (1) a shared read-only diagnostic attempt reviews the implementation "
            f"and public test feedback and returns grounded requirement claims with explicit "
            f"uncertainty; (2) two repair attempts (ordinary and AEE-guided) start from the same "
            f"pristine snapshot and each get two repair rounds. The guided arm additionally receives "
            f"the actual AEE/Evaluator findings from the shared diagnostic. After all runs, the final "
            f"package snapshots are graded with hidden acceptance tests; hidden outcomes are never "
            f"fed back to any attempt.")

    tasks = []
    for project, variant, seed in SCORED_PAIRS_V8:
        pair_id = f"mr-{project}-{variant}-{seed}"
        fixture = fixtures[(project, variant)]
        tasks.append({"instance_id": pair_id, "repo": "matched-repair-fixture",
                      "base_commit": fixture["base_commit"],
                      "problem_statement": problem_statement(pair_id, project),
                      "image": fixture["image"], "language": "python",
                      "hidden_test_count": fixture["grade"]["test_count"]})
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": {"schema_version": 1, "seed": cfg["seed"],
                  "selection": ("matched-repair scored campaign: phase-2 cross-file pairs at the scored seed "
                                "(config_default, store_add_alias, coupled_xfile, clean control)"),
                  "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                       if (p, v, s) not in set(SCORED_PAIRS_V8)),
                  "tasks": tasks},
        "schedule": scored_v8_schedule(),
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden grading of final snapshots happens after "
                    "all runs and is never fed back. The smoke pair "
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audits": audits,
        "grade_smoke": grade_smoke,
        "pairs": [{"project": p, "variant": v, "seed": s,
                   "image": fixtures[(p, v)]["image"],
                   "base_commit": fixtures[(p, v)]["base_commit"],
                   "hidden_test_count": fixtures[(p, v)]["grade"]["test_count"]}
                  for p, v, s in SCORED_PAIRS_V8],
        "notes": ("Freeze v8: phase-2 cross-file scored campaign (4 pairs x 3 arms = 12 attempts) piloting the "
                  "harder task class after the v7 null (second consecutive graded null on guided-vs-ordinary "
                  "quality). The synthetic minisched package (config/store/scheduler) seeds defects whose "
                  "symptom surfaces in scheduler.py while the cause lives in config.py or store.py; each "
                  "carries a plausible wrong-layer fix in scheduler.py that passes every public test but fails "
                  "hidden tests pinned at the true layer. Per-arm hidden pass-rate is the primary comparison "
                  "metric. Freezes v4/v5/v6/v7 and all prior evidence untouched; negative and partial outcomes "
                  "are preserved in the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v8-scored.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# Scored freeze builder (freeze v8.1): phase-2 cross-file pairs, R03 spec fix
# ---------------------------------------------------------------------------

# v8 completed 2026-09-21: 12/12 attempts, 94 model calls, $3.8762 measured,
# third consecutive guided-vs-ordinary quality null — but the graded metric was
# contaminated by a task-design validity defect: stage1.md said "A payload
# without a callable 'fn' raises ValueError when executed" while the hidden
# test pins the reference behavior (run_next treats a bad payload as a job
# failure under the retry rule, never raising to the caller). The diagnostic
# itself generated the phantom defect and all 8 repair arms, including both
# clean negative-control arms, hoisted validation out of the retry path. True-
# layer localization held (all seeded defects fixed at the true layer, no
# wrong-layer trap taken). v8.1 fixes the spec wording to match the hidden
# test exactly and reruns the same 4 pairs x 3 arms for a clean graded
# comparison on the cross-file question.
SCORED_SEED_V8_1 = 20260918
SCORED_PAIRS_V8_1 = (
    ("minisched", "config_default", SCORED_SEED_V8_1),
    ("minisched", "store_add_alias", SCORED_SEED_V8_1),
    ("minisched", "coupled_xfile", SCORED_SEED_V8_1),
    ("minisched", "clean", SCORED_SEED_V8_1),
)

SCORED_V8_1_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized the freeze-v8.1 rerun (\"make that fix so we can rerun it\"): "
    "the v8 R03 spec/grader contradiction is fixed in stage1.md and the same 12 attempts "
    "(4 minisched pairs x diagnose/ordinary/guided) rerun on gpt-6-astra with attempt_cap_usd=25 "
    "and global_cap_usd=100. Expected spend ~$4. Prior measured spend: $26.7625 against the $100 "
    "global cap ($73.2375 remaining). Spend settles to measured usage; unknown usage is never released."
)

REAL_SMOKE_EVIDENCE_V8_1 = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC (3/3 attempts, $1.4831 measured), "
    "freeze v5 scored comparison completed 2026-09-21 ~12:23 UTC (3/3 attempts on tinydb/token_alias, "
    "$1.5029 measured, diagnostic_valid=true, guided_with_assessment=true), freeze v6 full scored "
    "campaign completed 2026-09-21 ~13:25 UTC (21/21 attempts, $8.8870 measured, hidden acceptance "
    "grading 14/14 PASS), freeze v7 hard-pair campaign completed 2026-09-21 (24/24 attempts, "
    "$11.0133 measured, hidden acceptance grading 16/16 PASS, second consecutive null on "
    "guided-vs-ordinary quality), and freeze v8 phase-2 cross-file campaign completed 2026-09-21 "
    "(12/12 attempts, $3.8762 measured, all 8 repair snapshots 17/18 hidden with the same single "
    "R03_bad_payload failure caused by a spec/grader contradiction, fixed for v8.1): "
    "real_smoke_verified=True is grounded on these completed runs: "
    "the paid model path is proven end to end."
)


def scored_config_v8_1():
    """Frozen config for the v8.1 rerun: same pairs, seed, model, caps as v8.

    The only material change is the stage1.md R03 spec fix, which the host
    picks up from main when it checks out origin/main before building the
    freeze. Tristen authorized this rerun on 2026-09-21 (see
    SCORED_V8_1_BUDGET_AUTHORIZATION); the host RUN gate still takes his typed
    RUN as the fresh confirmation before any paid call."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": SCORED_SEED_V8_1,
        "budget_authorization": SCORED_V8_1_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE_V8_1,
    })
    return cfg


def scored_v8_1_schedule():
    """Deterministic 12-attempt schedule for freeze v8.1. Pure function of
    SCORED_PAIRS_V8_1 (no Docker, no model calls)."""
    schedule = []
    for i, (project, variant, seed) in enumerate(SCORED_PAIRS_V8_1):
        pair_id = f"mr-{project}-{variant}-{seed}"
        arms = ["repair_ordinary", "repair_guided"]
        random.Random(seed + len(variant) + i).shuffle(arms)
        for arm in ["diagnose"] + arms:
            schedule.append(dict(task_id=pair_id, arm=arm, repeat=1,
                                 attempt_id=f"{pair_id}--{arm}"))
    return schedule


def build_scored_freeze_v8_1(output, calibration):
    """Build freeze v8.1: rerun of the v8 phase-2 cross-file scored campaign
    with the R03 spec/grader contradiction fixed. Four minisched pairs at the
    scored seed, three arms each, 12 attempts. Same offline gates as v8 —
    reservation bounds, per-fixture solver image audit, grader smoke. Fails
    closed otherwise. Offline only: no model calls, no spend."""
    fixtures = {}
    for project, variant, seed in SCORED_PAIRS_V8_1:
        fixtures[(project, variant)] = next(
            f for f in calibration["fixtures"]
            if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config_v8_1()
    reservation = verify_reservation_bounds(cfg)
    audits = {}
    for (project, variant), fixture in fixtures.items():
        audit = audit_solver_image(fixture["image"], project)
        if not audit["audit_pass"]:
            raise ValueError(f"solver image audit failed for {project}/{variant}: "
                             + json.dumps(audit["hidden_markers"]))
        audits[f"{project}/{variant}"] = audit
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True

    def problem_statement(pair_id, project):
        return (
            f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
            f"in the {PROJECTS[project]['package']} package — possibly spanning modules, with the "
            f"symptom surfacing in a different file than the cause (or it may be a clean negative "
            f"control). Protocol: (1) a shared read-only diagnostic attempt reviews the implementation "
            f"and public test feedback and returns grounded requirement claims with explicit "
            f"uncertainty; (2) two repair attempts (ordinary and AEE-guided) start from the same "
            f"pristine snapshot and each get two repair rounds. The guided arm additionally receives "
            f"the actual AEE/Evaluator findings from the shared diagnostic. After all runs, the final "
            f"package snapshots are graded with hidden acceptance tests; hidden outcomes are never "
            f"fed back to any attempt.")

    tasks = []
    for project, variant, seed in SCORED_PAIRS_V8_1:
        pair_id = f"mr-{project}-{variant}-{seed}"
        fixture = fixtures[(project, variant)]
        tasks.append({"instance_id": pair_id, "repo": "matched-repair-fixture",
                      "base_commit": fixture["base_commit"],
                      "problem_statement": problem_statement(pair_id, project),
                      "image": fixture["image"], "language": "python",
                      "hidden_test_count": fixture["grade"]["test_count"]})
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": {"schema_version": 1, "seed": cfg["seed"],
                  "selection": ("matched-repair scored campaign rerun: phase-2 cross-file pairs at the scored seed "
                                "(config_default, store_add_alias, coupled_xfile, clean control), "
                                "R03 spec wording fixed to match the hidden test"),
                  "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                       if (p, v, s) not in set(SCORED_PAIRS_V8_1)),
                  "tasks": tasks},
        "schedule": scored_v8_1_schedule(),
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden grading of final snapshots happens after "
                    "all runs and is never fed back. The smoke pair "
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audits": audits,
        "grade_smoke": grade_smoke,
        "pairs": [{"project": p, "variant": v, "seed": s,
                   "image": fixtures[(p, v)]["image"],
                   "base_commit": fixtures[(p, v)]["base_commit"],
                   "hidden_test_count": fixtures[(p, v)]["grade"]["test_count"]}
                  for p, v, s in SCORED_PAIRS_V8_1],
        "notes": ("Freeze v8.1: rerun of the v8 phase-2 cross-file scored campaign (4 pairs x 3 arms = 12 attempts) "
                  "with the v8 validity defect fixed: stage1.md R01 now states that a payload without a callable "
                  "'fn' is a job failure handled under the retry rule, never raised to the caller — matching the "
                  "hidden test_R03_bad_payload exactly. Same pairs, seed, model, and caps as v8; per-arm hidden "
                  "pass-rate remains the primary comparison metric. Freezes v4/v5/v6/v7/v8 and all prior evidence "
                  "untouched; negative and partial outcomes are preserved in the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v8-1-scored.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Matched-repair cloud port")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-images").add_argument("--no-push", action="store_true")
    p = sub.add_parser("calibrate"); p.add_argument("out", type=Path)
    p = sub.add_parser("audit"); p.add_argument("image"); p.add_argument("project")
    p = sub.add_parser("freeze"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-scored"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-scored-v6"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-scored-v7"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-scored-v8"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-scored-v8-1"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("grade-run"); p.add_argument("--run", type=Path, required=True,
        help="completed run directory (reads freeze.json + attempts, appends hidden_grades)")
    p = sub.add_parser("grade-smoke"); p.add_argument("--calibration", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "build-images":
        ensure_registry()
        for project, variants in VARIANTS.items():
            for variant in variants:
                pinned, commit = build_fixture_image(project, variant, push=not args.no_push)
                print(f"BUILT {project}/{variant}: {pinned} commit={commit[:12]}", flush=True)
    elif args.command == "calibrate":
        ensure_registry()
        pairs = [(p, v) for p in VARIANTS for v in VARIANTS[p]]
        calibrate_fixtures(args.out, pairs)
    elif args.command == "audit":
        print(json.dumps(audit_solver_image(args.image, args.project), indent=2))
    elif args.command == "freeze":
        manifest = build_smoke_freeze(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
    elif args.command == "freeze-scored":
        manifest = build_scored_freeze(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
    elif args.command == "freeze-scored-v6":
        manifest = build_scored_freeze_v6(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
        print("pairs:", len(manifest["pairs"]), "attempts:", len(manifest["schedule"]))
    elif args.command == "freeze-scored-v7":
        manifest = build_scored_freeze_v7(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
        print("pairs:", len(manifest["pairs"]), "attempts:", len(manifest["schedule"]))
    elif args.command == "freeze-scored-v8":
        manifest = build_scored_freeze_v8(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
        print("pairs:", len(manifest["pairs"]), "attempts:", len(manifest["schedule"]))
    elif args.command == "freeze-scored-v8-1":
        manifest = build_scored_freeze_v8_1(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
        print("pairs:", len(manifest["pairs"]), "attempts:", len(manifest["schedule"]))
    elif args.command == "grade-run":
        results = grade_run(args.run)
        print("GRADED", len(results))
        for attempt_id, outcome in results:
            print(f"  {attempt_id}: {outcome}")
    elif args.command == "grade-smoke":
        # Independent grader smoke (gate): a seeded-bug snapshot must fail hidden
        # grading and a clean snapshot must pass — exercises the full
        # snapshot -> grade path on both outcomes.
        run_grade_smoke(read_json(args.calibration))


if __name__ == "__main__":
    main()
