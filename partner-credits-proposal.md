# Partner Credits: Zero-Registration Free Tier for last30days Users

**Type:** Partnership proposal for ScrapeCreators
**Date:** 2026-03-05
**Status:** Draft proposal

---

## The Pitch

Every last30days user gets 100 free ScrapeCreators credits — Reddit, TikTok, Instagram — without ever visiting scrapecreators.com or creating an account. When they run out, the skill tells them where to upgrade. ScrapeCreators gets a distribution channel. last30days gets a killer default experience.

## The Problem

Right now, new last30days users hit a wall:

1. Install the skill (30 seconds)
2. Try `/last30days AI video tools`
3. Get told they need a `SCRAPECREATORS_API_KEY`
4. Have to go to scrapecreators.com, register, get a key, paste it into `.env`
5. Many never come back

The best Reddit experience requires a key. The friction kills adoption.

## The Proposal: Machine-Bound Partner Tokens

### How It Works

**ScrapeCreators side:**
1. Issue last30days a **partner ID** (e.g., `partner_last30days`)
2. Accept a new header: `X-Partner-Device: <device_hash>`
3. On first request per device hash: allocate 100 credits, no registration needed
4. Track usage: `(partner_id, device_hash) → credits_remaining`
5. When credits hit 0: return `402` with upgrade URL in response body

**last30days side:**
1. On first run, generate a **device fingerprint** and cache it locally
2. If user has no `SCRAPECREATORS_API_KEY`, send requests with partner headers instead
3. When 402 comes back, show a friendly "upgrade" message

That's it. No accounts, no OAuth, no registration flow.

### The Device Fingerprint

```python
import hashlib, platform, uuid, os

def get_device_id():
    """Generate a stable, hard-to-forge device fingerprint."""
    # Use the OS-level machine ID (persists across reinstalls on most systems)
    machine_id = _get_machine_id()

    # Salt with the partner ID so the hash is useless outside this context
    raw = f"last30days:{machine_id}"
    return hashlib.sha256(raw.encode()).hexdigest()

def _get_machine_id():
    """Get the OS hardware/machine ID."""
    if platform.system() == "Darwin":
        # macOS: IOPlatformUUID (hardware-bound, survives OS reinstall)
        import subprocess
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if "IOPlatformUUID" in line:
                return line.split('"')[-2]

    elif platform.system() == "Linux":
        # Linux: /etc/machine-id (set at install time)
        try:
            return open("/etc/machine-id").read().strip()
        except FileNotFoundError:
            pass

    # Fallback: MAC address + hostname (less stable but reasonable)
    return f"{uuid.getnode()}:{platform.node()}"
```

**Why this works:**
- macOS `IOPlatformUUID` is hardware-bound — can't change it without a new motherboard
- Linux `/etc/machine-id` is set at OS install — persists across reboots
- Hashed with `last30days:` prefix so the raw ID is never sent to ScrapeCreators
- Cached locally in `~/.config/last30days/.device_id` after first generation

### API Request Format

```
# Without partner credits (existing flow — user has their own key)
GET /v1/reddit/search?query=AI+tools
x-api-key: sc_user_abc123

# With partner credits (new — no registration needed)
GET /v1/reddit/search?query=AI+tools
x-api-key: sc_partner_last30days
X-Partner-Device: a1b2c3d4e5f6...  (sha256 hex)
```

ScrapeCreators treats `sc_partner_last30days` as a special key class:
- Requires `X-Partner-Device` header
- Credits tracked per device hash, not per API key
- Rate limited per device (e.g., 10 requests/minute)
- 100 credits per unique device, lifetime

### What Counts as a Credit

One API call = one credit. A typical `/last30days` run uses roughly:
- 2-4 Reddit searches (global + subreddit drilldowns)
- 1-2 TikTok searches + 2-3 transcript fetches
- 1-2 Instagram searches + 2-3 transcript fetches

So ~10-15 credits per run. 100 credits ≈ **7-10 full research runs** before upgrade.

That's enough to get hooked.

## Abuse Prevention

### What we're defending against

| Threat | Likelihood | Impact |
|--------|-----------|--------|
| User spoofs device ID to get infinite credits | Low | Medium |
| Script generates thousands of fake device IDs | Medium | High |
| User shares partner key for non-last30days use | Low | Low |

### Defenses (simplest first)

**1. Hardware-bound device ID (primary defense)**
- macOS IOPlatformUUID can't be changed without hardware swap
- Linux machine-id requires root to change and breaks other software
- Not a cookie or config file — it's the machine itself

**2. Rate limiting per device (ScrapeCreators side)**
- 10 requests/minute per device hash
- Prevents scripted rapid-fire abuse even with valid device IDs
- Normal usage never hits this — a full run takes 60-70 seconds with natural gaps

**3. IP rate limiting on new device registrations (ScrapeCreators side)**
- Max 3 new device hashes per IP per day
- Stops "generate 1000 device IDs from one server" attacks
- Legitimate users: one machine, one device ID, done

**4. Total partner pool cap (safety valve)**
- ScrapeCreators sets a monthly cap on total partner credits (e.g., 50,000/month)
- If last30days goes viral and blows the cap, both parties renegotiate
- Prevents runaway costs from unexpected growth

### What we're NOT doing (intentional simplicity)

- No CAPTCHAs
- No email verification
- No phone verification
- No browser fingerprinting
- No token signing or crypto
- No account creation whatsoever

The goal is zero friction. The device ID is "good enough" — it stops casual abuse and scripts. A determined attacker could maybe get 200-300 free credits by VM gymnastics, but that's not worth defending against when paid plans are cheap.

## User Experience

### First run (no key configured)

```
$ /last30days AI video tools

🔍 Searching Reddit, TikTok, Instagram...
ℹ️  Using 100 free partner credits from ScrapeCreators (93 remaining)
   Get your own key for unlimited use: scrapecreators.com/last30days

[... normal results ...]
```

### Credits running low

```
ℹ️  12 partner credits remaining. Get unlimited access: scrapecreators.com/last30days
```

### Credits exhausted

```
⚠️  Free partner credits used up!

Reddit, TikTok, and Instagram require a ScrapeCreators API key.
Get one at: scrapecreators.com/last30days (100 free credits on signup, then pay-as-you-go)

Continuing with X, YouTube, Hacker News, Polymarket, and web search...
```

Key detail: the skill **doesn't stop working** — it gracefully falls back to the sources that don't need a key. The user still gets value, but they see what they're missing.

### After upgrade

```
$ echo 'SCRAPECREATORS_API_KEY=sc_abc123' >> ~/.config/last30days/.env

# Next run — partner headers no longer sent, user's own key used
```

## What ScrapeCreators Gets

1. **Distribution channel** — every last30days install is a potential paying customer
2. **Zero support burden** — no accounts to manage for free tier users
3. **Qualified leads** — users who exhaust 100 credits are proven power users
4. **Co-marketing** — "Powered by ScrapeCreators" in every skill run
5. **Usage data** — anonymous device-level usage patterns across topics

## What last30days Gets

1. **Zero-config Reddit** — install and go, no registration anywhere
2. **TikTok and Instagram included** — three sources work out of the box
3. **Lower barrier to adoption** — the #1 friction point eliminated
4. **Upgrade path built in** — natural conversion funnel

## Implementation Effort

### ScrapeCreators side (their work)
- [ ] Create partner key class with per-device credit tracking
- [ ] Accept `X-Partner-Device` header on partner keys
- [ ] Return `402` with upgrade URL when credits exhausted
- [ ] Rate limit: 10 req/min per device, 3 new devices/day per IP
- [ ] Dashboard for last30days to see aggregate partner usage

### last30days side (our work)
- [ ] `scripts/lib/device_id.py` — generate and cache device fingerprint (~30 lines)
- [ ] Update `scripts/lib/env.py` — fall back to partner auth when no user key
- [ ] Update `_sc_headers()` in reddit.py, tiktok.py, instagram.py — add partner headers
- [ ] Handle 402 response — show upgrade message, continue with other sources
- [ ] Show credits remaining in run output (from response header)

### Suggested response headers from ScrapeCreators

```
X-Partner-Credits-Remaining: 87
X-Partner-Credits-Total: 100
X-Partner-Upgrade-URL: https://scrapecreators.com/last30days
```

## Open Questions

1. **Credit pool negotiation** — what monthly cap works for ScrapeCreators?
2. **Referral tracking** — should `scrapecreators.com/last30days` give a signup bonus or revenue share?
3. **Credit count per endpoint** — should transcript fetches cost the same as searches?
4. **Expiration** — do unused partner credits expire (e.g., 90 days)?

---

## Summary

One device ID. One partner key. One header. 100 free credits. Zero registration.

The entire abuse prevention is: your computer has a hardware ID that you can't easily change. That's it. Simple, clever, and good enough.
