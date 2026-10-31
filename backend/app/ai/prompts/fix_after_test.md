Your config was tried against the real service (first page only, nothing saved). Here is what happened:

{result}

Fix the config. If mapped fields found nothing, correct `records_path` and the paths under `map` to match the real record.
If a note says the paging is wrong, fix `pagination` using the documentation: services that page by number need type `page_number` (the page parameter, start 1),
those that page by record count need type `offset`, and many give a link to the next page (`next_link`, for example GitHub's `Link` header).
A note that a variable is still an example value is for the person to fix: leave the variables as they are.
If the service refused the request (400, 404 or 422), read its message in the notes and fix the path, query or body it complains about
(for example a search that needs a restriction, or a required parameter).
If the service refused the login (401 or 403), fix only how the secret is sent (`auth`), as the documentation says.
If the endpoint is gone (410) or the method is not allowed (405), use a current endpoint from the documentation instead.
Never hide a field that found nothing by replacing its path with a constant `default`: if the real record lacks the field, the request
probably has to ask for it (many services need a `fields` or `expand` query parameter), so fix the request instead.
Change nothing else.
The sample record is masked (names look like ***, emails like ***@example.com): that is expected.

Reply with the full corrected YAML only. No explanation, no markdown fences.
