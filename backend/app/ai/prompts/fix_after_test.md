Your config was tried against the real service (first page only, nothing saved). Here is what happened:

{result}

Fix the config. If mapped fields found nothing, correct `records_path` and the paths under `map` to match the real record.
If the endpoint is gone (410) or the method is not allowed (405), use a current endpoint from the documentation instead.
Change nothing else.
The sample record is masked (names look like ***, emails like ***@example.com): that is expected.

Reply with the full corrected YAML only. No explanation, no markdown fences.
