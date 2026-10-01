## AI analyst

Customers ask plain-English questions about their own usage. The model has no SQL
access and never sees an org id: it calls five fixed tools (daily usage, feature
usage, MRR, digest, definitions), each running through Postgres RLS under the
caller's token. Every call is logged to `ai.calls` (tokens, cost, latency, tool
trace). There is a per-org kill switch, a per-org daily budget and a global switch.

**Evaluation** (37 questions: metrics checked against raw-table SQL, cited
definitions, canceled-org edge cases, out-of-scope, and 11 attack prompts):
- First run 26/30. The eval caught three real bugs: the model guessed dates
  (fixed by passing today's date), added numbers wrongly (fixed by precomputing
  totals in the tools), and skipped a citation.
- After fixes: 37/37, including 7 questions added after tuning. 0 cross-tenant
  leaks, 0 false refusals.
- Cost about $0.0004 per question; median latency 5.9 s (p95 8.9 s).

**Limits:** the eval set is small and uses two test orgs, answers can vary
between runs, and the budget check can overshoot by one question.