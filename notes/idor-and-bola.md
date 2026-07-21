# IDOR and BOLA

Insecure Direct Object Reference (IDOR) is when an application exposes a reference to an
internal object (a database ID, a filename, a key) and lets a user manipulate that reference
to access data they shouldn't reach — most often because the server checks that the object
exists, but not that the *current user* is allowed to touch it.

BOLA (Broken Object Level Authorization) is the API-focused framing of the same root cause,
and sits at #1 on the OWASP API Security Top 10. In a REST API it usually shows up as
`GET /api/orders/1234` returning someone else's order just because the ID is guessable or
enumerable.

Common variants:
- Sequential numeric IDs that are trivial to enumerate.
- IDs exposed in URLs, hidden form fields, or API responses, with no server-side ownership check.
- Multi-step actions where only the *first* step checks authorization and subsequent steps trust
  the object reference blindly.

Fix pattern: check on every request that the authenticated identity actually owns (or is
otherwise entitled to) the specific object being referenced — never rely on the ID being
hard to guess as a security boundary.
