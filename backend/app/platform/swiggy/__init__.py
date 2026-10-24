"""Connection layer for the authorized Swiggy MCP (Builders Club).

oauth.py       OAuth 2.1 + PKCE login with dynamic client registration and refresh-token rotation
token_store.py where the credentials live (a 0600 file, or memory in tests)
mcp_http.py    JSON-RPC over streamable HTTP, with retry rules that never blindly retry an order
doctor.py      read-only command that prints Swiggy's real tool schemas and response shapes (redacted)

Source of truth: https://mcp.swiggy.com/builders/docs/ . Nothing here guesses at Swiggy's response data;
mapping Swiggy's data to this app's models is a separate step that uses recorded real responses.
"""
