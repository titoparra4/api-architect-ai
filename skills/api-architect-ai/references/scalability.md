# Mode D — Scalability & Resilience Review

Use this reference to evaluate whether an API can scale and degrade gracefully. **Never invent
benchmark results.** Without metrics, every bottleneck is a hypothesis with a measurement plan.

## Contents
1. Evidence rules
2. Golden signals and objectives
3. Scalability checklist
4. Resilience patterns
5. Bottleneck hypothesis format
6. Capacity planning
7. Observability

---

## 1. Evidence rules

| Evidence available | What you may say |
|---|---|
| Production metrics, load-test reports, traces | Quantified findings, citing the source and time window |
| Code/config only | "Likely bottleneck" + mechanism + measurement needed (status `Requires validation`) |
| Requirements only | Design recommendations and proposed SLOs, labeled as recommendations |

Never write "handles 10k RPS" or "p99 is 200 ms" unless the user supplied that data.

## 2. Golden signals and objectives

Analyze **latency** (p50/p95/p99 per operation, success vs error separately), **throughput**
(requests/s per operation and tenant), **error rate** (5xx and relevant 4xx such as 429), **saturation**
(CPU, memory, connection pools, thread pools, queue depth, DB connections) and **availability**.

Derive SLOs from business requirements, not habit. Template:

| Operation | Business driver | SLI | Proposed SLO | Measurement source |
|---|---|---|---|---|
| `GET /v1/policies/{id}` | Agent desktop must feel instant | Latency of successful requests | p95 < 300 ms over 28 days (proposal — validate) | Gateway access logs / APM |
| `POST /v1/quotes` | Quote abandonment rises with wait time | Success rate | 99.5 % non-5xx over 28 days | Gateway metrics |

Mark all proposed numbers as proposals until the business confirms them.

## 3. Scalability checklist

- **Statelessness:** no in-memory sessions or sticky-session dependence; state in DB/cache/token.
- **Horizontal scalability:** instances interchangeable; no local file storage for shared data;
  singleton jobs coordinated (leader election/locks).
- **Caching:** HTTP caching (`Cache-Control`, `ETag`, `304`) for cacheable reads; application cache
  with explicit TTL and invalidation; cache keys include tenant and authorization context; stampede
  protection (request coalescing, jittered TTL). Never cache personalized responses in shared caches
  without `private`/`Vary`.
- **Database efficiency:** N+1 queries (loops issuing queries per item), missing indexes for filters
  and sort keys, `SELECT *`, unbounded queries, deep `OFFSET`, long transactions, lock contention.
  Verification: query logs / `EXPLAIN` in a non-production environment.
- **Pagination:** enforced max page size; cursor/keyset for large collections.
- **Rate limiting and quotas:** per client and tenant; distributed counters if multi-instance;
  fairness between tenants (noisy-neighbor protection).
- **Asynchronous processing:** long-running or bursty work moved to queues with `202 Accepted`;
  consumers idempotent; dead-letter queues; back-pressure.
- **Connection management:** pooled HTTP/DB clients with bounded pool sizes; keep-alive; pool size
  consistent with DB max connections × instances.
- **Payload size:** compression, field selection only if justified, bounded arrays.

## 4. Resilience patterns

| Pattern | Check | Common defects |
|---|---|---|
| Timeouts | Every outbound call (HTTP, DB, cache, queue) has connect + read timeouts; total budget < caller's timeout | Library defaults (often infinite or very long) |
| Retries + exponential backoff + jitter | Only idempotent operations or with idempotency keys; retry budget; honor `Retry-After` | Retry storms; retrying non-idempotent POSTs; retries at every layer (multiplicative) |
| Circuit breaker | Opens on failure rate/slow calls; fallback defined; metrics exposed | Fallback hides data errors; no half-open probing |
| Bulkheads | Separate pools/limits per dependency or tenant | One slow dependency exhausts the shared thread pool |
| Idempotency | `Idempotency-Key`, natural keys, dedup in consumers | Duplicate payments/claims on client retry |
| Concurrency control | ETag/`If-Match`, DB constraints, optimistic locking | Lost updates |
| Graceful degradation | Non-critical features disabled under load; cached/stale responses where acceptable | Whole request fails when an optional enrichment fails |
| Load shedding | Reject early (`503` + `Retry-After`) when saturated | Queues grow unbounded; latency explodes |
| Health checks | Separate liveness and readiness; readiness reflects critical dependencies only | Liveness checking DB → restart loops |
| Failure isolation | Per-tenant limits; async boundaries; separate deployments only if justified | Cascading failures across synchronous chains |

Timeout budget rule: if the gateway timeout is 30 s and the call chain is A → B → C, each hop's
timeout plus retries must fit inside the caller's remaining budget.

## 5. Bottleneck hypothesis format

```text
Hypothesis ID:  SCL-H-001
Suspected bottleneck: N+1 queries when listing policies with coverages
Evidence: src/policies/service.py:88 loops over policies and calls coverage_repo.find_by_policy()
Mechanism: 1 + N queries per page; with pageSize=100 → 101 round trips
Expected symptom: list latency grows linearly with page size; DB connection saturation under load
Measurement: enable SQL logging in staging; run k6 scenario with pageSize 10/50/100 at 20 RPS;
             compare query count and p95 latency
Confirmation criterion: query count per request > pageSize, or p95 grows > 2x from 10 to 100
Fix options: eager loading / join; batch query with IN (...); dedicated read model
Status: Requires validation
```

## 6. Capacity planning

Inputs needed (ask or assume explicitly): peak RPS per operation, growth rate, payload sizes,
dependency limits (DB connections, third-party rate limits), latency SLOs, availability target.
Method: measure per-instance throughput at target latency in a load test → required instances =
peak RPS / safe per-instance RPS (at ~60–70 % utilization) + N+1 redundancy. Re-check dependency
limits (e.g. total DB connections = instances × pool size). Treat every number as an estimate until
load-tested.

Load tests (k6, Gatling, JMeter, Locust) only in approved non-production environments.

## 7. Observability

- Structured logs with correlation/trace ID, tenant, operation, status, latency; no secrets/PII
  beyond policy.
- Metrics: RED (rate, errors, duration) per operation; USE (utilization, saturation, errors) per
  resource; pool and queue metrics.
- Distributed tracing with W3C Trace Context (`traceparent`, `tracestate`); OpenTelemetry
  instrumentation; propagate across async boundaries (message headers).
- Alerts on SLO burn rate, not raw thresholds alone.
- Dashboards per API and per critical dependency.
