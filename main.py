import os
import json
import requests
from urllib.parse import urlencode

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
if not DISCORD_WEBHOOK:
    raise RuntimeError("Missing DISCORD_WEBHOOK secret")

USERNAME = "kch123"
STATE_FILE = "state.json"

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

def post_discord(msg: str):
    requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=15)

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_proxy_wallet(username: str) -> str:
    params = {"q": username, "search_profiles": "true", "limit_per_type": 5}
    url = f"{GAMMA_BASE}/public-search?{urlencode(params)}"
    data = requests.get(url, timeout=15).json()
    profiles = data.get("profiles") or []

    for p in profiles:
        if p.get("proxyWallet"):
            # best-effort match
            for field in ("username", "userName", "name", "pseudonym"):
                v = p.get(field)
                if v and username.lower() in str(v).lower():
                    return p["proxyWallet"]

    for p in profiles:
        if p.get("proxyWallet"):
            return p["proxyWallet"]

    raise RuntimeError(f"Could not find proxyWallet for @{username}")

def fetch_positions(proxy_wallet: str):
    params = {"user": proxy_wallet, "sizeThreshold": 0}
    url = f"{DATA_BASE}/positions?{urlencode(params)}"
    return requests.get(url, timeout=15).json()

def normalize(raw_positions):
    out = {}
    for p in raw_positions:
        key = f"{p.get('conditionId','')}:{p.get('outcomeIndex')}:{p.get('asset','')}"
        out[key] = {
            "title": p.get("title", ""),
            "outcome": p.get("outcome", ""),
            "size": float(p.get("size", 0) or 0),
            "slug": p.get("slug", ""),
        }
    return out

def main():
    state = load_state()
    proxy = state.get("proxyWallet") or get_proxy_wallet(USERNAME)

    curr = normalize(fetch_positions(proxy))
    prev = state.get("positions", {})

    # First run: store state, don't spam
    if not prev:
        state["proxyWallet"] = proxy
        state["positions"] = curr
        save_state(state)
        print("Initialized (no alerts).")
        return

    added = [k for k in curr.keys() if k not in prev]
    removed = [k for k in prev.keys() if k not in curr]
    changed = [k for k in curr.keys() & prev.keys() if abs(curr[k]["size"] - prev[k]["size"]) > 1e-6]

    if added or removed or changed:
        lines = [f"📌 Position change for @{USERNAME}"]
        for k in added:
            p = curr[k]
            link = f"https://polymarket.com/market/{p['slug']}" if p["slug"] else f"https://polymarket.com/@{USERNAME}?tab=positions"
            lines.append(f"🟢 OPENED: {p['title']} — {p['outcome']} | size={p['size']:.4f} | {link}")
        for k in changed:
            before = prev[k]["size"]
            after = curr[k]["size"]
            p = curr[k]
            link = f"https://polymarket.com/market/{p['slug']}" if p["slug"] else f"https://polymarket.com/@{USERNAME}?tab=positions"
            lines.append(f"🟡 UPDATED: {p['title']} — {p['outcome']} | {before:.4f} → {after:.4f} | {link}")
        for k in removed:
            p = prev[k]
            lines.append(f"🔴 CLOSED: {p.get('title','')} — {p.get('outcome','')}")
        post_discord("\n".join(lines))

    state["proxyWallet"] = proxy
    state["positions"] = curr
    save_state(state)
    print("Done.")

if __name__ == "__main__":
    main()
