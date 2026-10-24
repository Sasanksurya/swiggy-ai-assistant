"""Read-only check of the real Swiggy connection.   python -m app.platform.swiggy.doctor [search words]

What it does, in order:
  1. shows whether your Swiggy account is connected
  2. lists Swiggy's real tools with their input schemas (this answers "what parameters does X take?")
  3. calls ONLY these read-only tools: get_addresses, search_restaurants, get_restaurant_menu, get_food_cart
  4. prints each response with the structure intact but personal data removed

It can never change a cart or place an order: any other tool name is refused by ReadOnlyTools, and the
refusal is covered by a test. Check the output once before you paste it anywhere.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Any

from ...config import get_settings
from .mcp_http import McpError, McpHttpClient, McpToolError
from .runtime import food_mcp_url, get_oauth

# Read-only by name and by Swiggy's docs: they look things up and never change a cart, address or order.
# Every other tool (update_food_cart, place_food_order, flush_food_cart, apply_food_coupon, create_address,
# delete_address, ...) is refused by ReadOnlyTools, whatever the caller asks for.
READ_ONLY_TOOLS = frozenset({"get_addresses", "search_restaurants", "get_restaurant_menu", "get_food_cart",
                             "search_menu", "get_food_orders", "fetch_food_coupons"})
MAX_DESCRIPTION = 300

_SENSITIVE_WORDS = frozenset({
    "phone", "mobile", "email", "lat", "lng", "lon", "latitude", "longitude", "address", "landmark", "pin",
    "pincode", "zip", "user", "customer", "token", "secret", "password", "otp", "session", "house", "flat",
    "street", "tid", "sid", "device", "deviceid"})
MAX_LIST_ITEMS = 3
MAX_STRING = 160


class ReadOnlyTools:
    """The only way the doctor reaches Swiggy: a small allow-list of tools that cannot change anything."""

    def __init__(self, client: McpHttpClient):
        self._client = client

    async def call(self, name: str, arguments: dict | None = None) -> Any:
        if name not in READ_ONLY_TOOLS:
            raise PermissionError(f"The doctor only calls read-only tools; refused '{name}'")
        return await self._client.call_tool(name, arguments)


def _is_sensitive_key(key: str) -> bool:
    """Matches whole words inside camelCase or snake_case keys, so `related` is fine but `userPhone` is not."""
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", key)
    return any(w.lower() in _SENSITIVE_WORDS for w in words)


def redact(value: Any, *, strict: bool = False, _sensitive: bool = False) -> Any:
    """Keeps keys, types and list lengths; removes personal values. Everything nested under a sensitive key
    is blanked too. `strict` blanks every string."""
    if isinstance(value, dict):
        return {k: redact(v, strict=strict, _sensitive=_sensitive or _is_sensitive_key(str(k)))
                for k, v in value.items()}
    if isinstance(value, list):
        shown = [redact(v, strict=strict, _sensitive=_sensitive) for v in value[:MAX_LIST_ITEMS]]
        if len(value) > MAX_LIST_ITEMS:
            shown.append(f"<{len(value) - MAX_LIST_ITEMS} more items of the same shape>")
        return shown
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        if strict or _sensitive:
            return "<redacted>"
        value = re.sub(r"\d{6,}", "<digits>", value)  # long digit runs: phone numbers, pincodes, ids
        return value if len(value) <= MAX_STRING else value[:MAX_STRING] + "..."
    if isinstance(value, (int, float)) and _sensitive:
        return "<redacted>"
    return value


def find_first(value: Any, keys: tuple[str, ...]) -> Any:
    """First value stored under any of `keys`, searching nested data. Used only to chain read-only calls."""
    if isinstance(value, dict):
        for k in keys:
            if k in value and value[k] not in (None, ""):
                return value[k]
        for v in value.values():
            found = find_first(v, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for v in value:
            found = find_first(v, keys)
            if found is not None:
                return found
    return None


def describe_tools(listing: list[dict]) -> str:
    """Plain-text summary of Swiggy's tools. Schemas describe inputs only, so nothing here is personal."""
    lines = []
    for t in listing:
        schema = t.get("inputSchema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        lines.append(f"\n* {t.get('name')}")
        desc = " ".join(str(t.get("description", "")).split())
        if desc:
            lines.append(f"    {desc[:MAX_DESCRIPTION]}")
        for name, spec in props.items():
            kind = spec.get("type", "?")
            if "enum" in spec:
                kind += " one of " + "/".join(map(str, spec["enum"]))
            mark = "REQUIRED" if name in required else "optional"
            lines.append(f"    - {name} ({kind}, {mark})")
    return "\n".join(lines)


def schema_args(schema: dict, known: dict[str, Any]) -> tuple[dict, list[str]]:
    """Builds call arguments from a tool's own input schema. Returns (arguments, missing required names).
    Only values we already hold are filled in (addressId, restaurantId, query), nothing is invented."""
    props = (schema or {}).get("properties") or {}
    args = {k: known[k] for k in props if k in known and known[k] is not None}
    missing = [r for r in (schema or {}).get("required") or [] if r not in args]
    return args, missing


def first_open_restaurant_id(value: Any) -> Any:
    """Id of the first restaurant whose availabilityStatus is OPEN (else the first restaurant id)."""
    if isinstance(value, dict):
        if value.get("availabilityStatus") == "OPEN" and value.get("id") not in (None, ""):
            return value["id"]
        for v in value.values():
            found = first_open_restaurant_id(v)
            if found is not None:
                return found
    elif isinstance(value, list):
        for v in value:
            found = first_open_restaurant_id(v)
            if found is not None:
                return found
    return None


def _show(title: str, data: Any, *, strict: bool = False) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(redact(data, strict=strict), indent=2, ensure_ascii=False))


# (tool, show strictly?) in the order they are tried; each call is built from that tool's own schema
_PLAN = (("search_restaurants", False), ("get_restaurant_menu", False), ("search_menu", False),
         ("get_food_cart", False), ("fetch_food_coupons", False), ("get_food_orders", True))


async def run(query: str = "biryani") -> int:
    settings = get_settings()
    oauth = get_oauth()
    print(f"Swiggy server: {settings.swiggy_base_url}")
    print(f"Redirect URI : {settings.swiggy_redirect_uri}")
    if not oauth.is_connected():
        print("\nNot connected. Open http://localhost:8000/api/swiggy/connect in your browser, sign in with your\n"
              "Swiggy phone number and OTP, then run this command again.")
        return 1
    client = McpHttpClient(food_mcp_url(settings), oauth.get_access_token, oauth.refresh)
    tools = ReadOnlyTools(client)
    try:
        listing = await client.list_tools()
        print(f"\n=== {len(listing)} tools Swiggy offers (inputs only, no personal data) ===")
        print(describe_tools(listing))
        schemas = {t.get("name"): t.get("inputSchema") or {} for t in listing}

        addresses = await tools.call("get_addresses")
        _show("get_addresses (all text blanked)", addresses, strict=True)
        known: dict[str, Any] = {
            "addressId": find_first(addresses, ("defaultAddressId",)) or find_first(addresses, ("id",)),
            "query": query}
        for tool, strict in _PLAN:
            if tool not in schemas:
                print(f"\n--- {tool}: not offered by this server, skipped")
                continue
            args, missing = schema_args(schemas[tool], known)
            if missing:
                print(f"\n--- {tool}: skipped, still missing required {missing}")
                continue
            try:
                result = await tools.call(tool, args)
            except McpToolError as e:  # one refused call must not hide the others
                print(f"\n--- {tool}: Swiggy refused the call ({e.message[:200]})")
                continue
            _show(f"{tool} args={sorted(args)}", result, strict=strict)
            if tool == "search_restaurants":
                known["restaurantId"] = first_open_restaurant_id(result)
    except McpError as e:
        print(f"\nSwiggy call failed: {type(e).__name__}: {e}")
        return 2
    print("\nDone. Nothing was added to a cart and nothing was ordered.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run(" ".join(sys.argv[1:]) or "biryani")))
