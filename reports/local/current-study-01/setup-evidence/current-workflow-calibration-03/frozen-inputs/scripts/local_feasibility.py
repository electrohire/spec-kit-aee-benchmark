"""One free, capped localhost request; feasibility evidence, not scored results."""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from benchmark_runner.store import write_json, utc, canonical


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("loopback probe refuses redirects")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--url", default="http://127.0.0.1:8081/v1")
    p.add_argument("--model", required=True)
    args = p.parse_args()
    if urlparse(args.url).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("free feasibility probe permits loopback only")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(args.url+"/models", timeout=10) as handle:
        models = json.loads(handle.read())
    if args.model not in {r["id"] for r in models.get("data", [])}:
        raise ValueError("selected model is not advertised")
    payload = dict(model=args.model, temperature=0, seed=20261016,
                   max_completion_tokens=32,
                   messages=[dict(role="user", content="Return only the word READY.")])
    freeze = dict(schema="local-feasibility-v1", created_at=utc(),
                  purpose="One readiness call; not workflow efficacy or cost evidence",
                  url=args.url, model=args.model, request=payload, max_calls=1,
                  timeout_seconds=60, retries=0, paid_calls_permitted=False,
                  models_sha256=hashlib.sha256(canonical(models)).hexdigest())
    write_json(args.output/"freeze.json", freeze, exclusive=True)
    result = dict(started_at=utc(), api_spend_usd="0", physical_calls=1)
    tick = time.monotonic()
    try:
        request = urllib.request.Request(args.url+"/chat/completions", canonical(payload),
                                         {"Content-Type":"application/json"})
        with opener.open(request, timeout=60) as handle:
            raw = handle.read()
        response = json.loads(raw)
        result.update(response_sha256=hashlib.sha256(raw).hexdigest(),
                      response_model=response.get("model"), usage=response.get("usage"),
                      finish_reason=response.get("choices", [{}])[0].get("finish_reason"),
                      identity_verified=response.get("model") == args.model,
                      ready=response.get("choices", [{}])[0].get("message", {}).get("content", "").strip() == "READY")
    except Exception as exc:
        result.update(error=type(exc).__name__, usage=None, ready=False)
    result["seconds"] = time.monotonic()-tick
    write_json(args.output/"result.json", result, exclusive=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
