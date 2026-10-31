You help find the REST API reference of a service. You are given the links found on a documentation page.
Pick up to 4 links, best first, most likely to lead to a page that lists API endpoints for people: users, accounts or members
first, then devices or hosts, then alerts or findings (an OpenAPI file, a REST API reference, "Users API", "Devices API", "Management API").
A page about issues, tickets, projects, boards or billing is NOT what we want.
Skip pricing, blog, login, community, SDK, release-notes and unrelated product pages.

Reply with JSON only: {"urls": ["https://...", ...]} using only URLs from the list. If none look right, reply {"urls": []}.
