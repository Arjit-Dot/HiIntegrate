# NVD CVE API 2.0: reference for AI drafting

Why this file exists: nvd.nist.gov is now a JavaScript app (`<app-root>`), so the AI's documentation reader gets an empty
page, and NVD publishes no OpenAPI file to fall back on (found in end-to-end testing, 1 Nov). This is the part of NVD's developer
documentation (https://nvd.nist.gov/developers/vulnerabilities) the platform needs, checked against the live API on 1 Nov.
Attach this file (and `sample-cves.json`) in AI mode, or paste it.

## Endpoint

```
GET https://services.nvd.nist.gov/rest/json/cves/2.0
```

## Authentication

Optional API key in the request header `apiKey: <key>` (no prefix). Request one free at
https://nvd.nist.gov/developers/request-an-api-key. Without a key the limit is 5 requests in a rolling 30 seconds,
with a key 50. **An invalid key is refused with HTTP 404 and the header `message: Invalid apiKey.`**

## Paging (offset)

- `resultsPerPage`: page size, at most 2000 (default 2000)
- `startIndex`: zero-based index of the first result
- The response says `totalResults`, `resultsPerPage` and `startIndex`. Stop when `startIndex` reaches `totalResults`.

## Useful filters

- `lastModStartDate` and `lastModEndDate` (ISO 8601, both together, at most 120 days apart): CVEs changed in the window
- `pubStartDate` and `pubEndDate`: CVEs published in the window (same rules)
- `cvssV3Severity`: `LOW`, `MEDIUM`, `HIGH` or `CRITICAL`
- `keywordSearch`: words in the description
- `cveId`: one CVE, for example `CVE-2021-44228` (a lookup)

## Response

```
{ "resultsPerPage": 2, "startIndex": 0, "totalResults": 417595, "format": "NVD_CVE", "version": "2.0", "timestamp": "...",
  "vulnerabilities": [ { "cve": { ... } } ] }
```

Each record is `vulnerabilities[].cve`:

| Field | Path in the record (relative to each item of `vulnerabilities`) |
|---|---|
| id | `cve.id` (for example `CVE-2024-12345`) |
| published | `cve.published` (ISO 8601, no time zone) |
| last modified | `cve.lastModified` |
| status | `cve.vulnStatus` (`Analyzed`, `Awaiting Analysis`, `Modified`, `Rejected`, ...) |
| description (English) | `cve.descriptions[?lang=='en'].value \| [0]` |
| severity (CVSS 3.1) | `cve.metrics.cvssMetricV31[0].cvssData.baseSeverity` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`); older CVEs may have only `cvssMetricV30`, `cvssMetricV2` or no metrics at all |
| score | `cve.metrics.cvssMetricV31[0].cvssData.baseScore` |

`sample-cves.json` in this folder is a real response (two CVEs, trimmed: `configurations` removed, lists cut to the first item).
