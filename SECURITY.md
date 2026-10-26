# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately, through GitHub's private vulnerability
reporting on this repository (Security → Report a vulnerability) or by contacting the
maintainer, [@Ashin-06](https://github.com/Ashin-06), directly. Do not open a public issue.

Include what you found, how to reproduce it and what an attacker could do with it. You should
get an acknowledgement within 5 working days. Please give us 90 days to fix an issue before
disclosing it, and don't test against anyone else's deployment.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | yes |
| < 1.0 | no (prototype releases) |

## Scope

In scope: the screening API, the transliteration and matching code, the SDN loader, the
screening log, the container image and the CI configuration in this repository. A systematic
way to get a listed name past the matcher (a spelling pattern, a script, a company form) is in
scope too: report it privately, since it helps evaders. Known misses are listed in
`docs/model-card.md`.

Out of scope: the accuracy of OFAC's list itself, and findings that need an already-compromised
host or a leaked API key with the matching role.

This project has **not** had an independent security review or penetration test.
