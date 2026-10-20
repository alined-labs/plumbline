# The edge's rate limit (Lane P)

Cloudflare's Free plan allows one rate-limiting rule, matching on the path only, counting
per IP over 10 seconds, blocking for 10 seconds. Plumbline's rule covers the two routes
that start model calls; the result and event routes of a lease check are not counted.
The daily quotas (`api/quota.py`) and the spend caps sit behind it: this rule stops bursts,
the quotas stop a patient visitor, and the caps stop everyone.

Dashboard: the zone `alinedlabs.co`, **Security**, **WAF**, **Rate limiting rules**,
**Create rule**:

| Field | Value |
| --- | --- |
| Rule name | `plumbline: model routes` |
| If incoming requests match | custom expression, below |
| With the same characteristics | IP |
| When rate exceeds | 5 requests per 10 seconds |
| Then take action | Block, with the default response |
| For duration | 10 seconds |

```text
(http.request.uri.path eq "/api/ask") or (http.request.uri.path eq "/api/check-lease")
```

The paths are matched zone-wide (the Free plan cannot match the host); nothing else in the
zone serves them. Check it with `bash deploy/edge-check.sh`, which sends invalid questions
(which the API refuses with 422 and does not count against the quota) until Cloudflare
answers 429. Terraform takes this rule over on Friday (P7b).
