# Token accounting
Provider-native per-call prompt/completion counts are measured when supplied.
cached_input_tokens is a subset of input; reasoning_tokens is a subset of output.
Cost = ((input-cached)*input_rate + cached*cache_rate + output*output_rate)/1e6.
No additional reasoning charge. No tool fees apply to the plain chat requests.
All prices must come from a dated official snapshot, default tier, USD; report
list-price estimates separately from invoices. No subscription-to-API conversion.

Missing usage is null with a reason. Missing cache categories cannot silently
become zero. Unknown costs propagate into aggregate totals. Cumulative telemetry
adapters must difference snapshots; this HTTP adapter receives per-call values.
Request/call IDs deduplicate exact records, but distinct billable retries remain.
No automatic retries are issued. A retry is a new request with its own reservation.

Before each call, reserve the documented model input ceiling at uncached price
plus maximum completion tokens. This deliberately over-reserves; only measured
cost releases the difference. Unknown calls retain full reservation. Persist
reservations before HTTP; resumption retains even requests interrupted before
logging. An experiment advisory lock serializes mutation. A bound violation stops
the campaign and retains observed cost. Provider-side project limits are useful
as an additional ceiling, not a substitute for this accounting.

Token cap similarly reserves max input+output before a call. Context is never
priced by transcript length. Each phase, repair and finalization counts.
Setup, per-task execution, infrastructure and human time are distinct.
Cold-start = known setup + execution. Amortized = setup/reuse_count + execution.
Without measured setup and a declared reuse count, both remain unknown.
