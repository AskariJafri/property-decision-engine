# Accounts, credits, billing and the admin console

How the paid product works, what is and is not wired up, and how to operate it.

---

## Tiers

| Tier | How someone gets it | What it includes (defaults — all editable in Admin → Pricing) |
|---|---|---|
| **Free** | Sign up | 5 analyses in total, offer scenarios, comparison, ads shown |
| **Paid** | Any active subscription or any completed purchase | Ads hidden; Deep Dive for purchased analyses |
| **Property Watch** — $29 CAD/mo | Stripe subscription | 30 analyses/month, 10 watches, no ads |
| **Professional** — $49 CAD/mo | Stripe subscription, or role `professional` set by an admin | 200 analyses/month, every Deep Dive, 50 watches, no ads |
| **Deep Dive** — $9.99 CAD one-time | Stripe payment for one analysis | The full report for that analysis |
| **Admin** | `grant-role` CLI or `PDE_BOOTSTRAP_ADMIN_EMAILS` | Unlimited everything, no ads, the admin console |

When a subscriber exhausts the month's allowance, remaining free credits are used next.

## How the limit is enforced

- Credits are an append-only ledger (`usage_events`). The remaining allowance is derived from
  it on every request; nothing is stored in the browser.
- `POST /api/v1/properties/analyze` checks the entitlement before any work, runs the analysis,
  then re-checks **under a row lock** and writes the analysis and the ledger row in one
  transaction. Two tabs racing for the last credit get one analysis.
- A refused analysis (422) consumes nothing. The same inputs within 24 hours return the saved
  result for free (`duplicate: true`).
- Viewing, listing, comparing, offer scenarios, Deep Dive views and watch recalculations never
  consume a credit; they are rate-limited instead (120/hour per kind).
- Other limits: 10 analyses/hour (`PDE_ANALYSIS_RATE_LIMIT_PER_HOUR`), 20 listing reads/day,
  6 MB request bodies, 5 MB uploads, 20 PDF pages, 10 failed sign-ins per 15 minutes, and a
  daily AI budget (`PDE_AI_DAILY_BUDGET_CENTS`). Admins bypass the analysis limits.

## Roles and the admin console

The role lives on `users.role` and is read from the database on every request. No header,
body field or cookie other than the opaque session token can make a request an admin's.

**Make the first admin** (either works; both are server-side):

```bash
# 1. Sign up normally in the app, then:
cd backend && python -m app.cli grant-role you@example.com admin

# or 2. set before the account signs up / signs in:
PDE_BOOTSTRAP_ADMIN_EMAILS=you@example.com
```

Admins can then change other users' roles in Admin → Users (audited; an admin cannot demote
themselves). The console covers pricing, promotions, ads, feature switches, cost assumptions,
Deep Dive projection assumptions, the funnel, errors, API usage and the audit log.

## Unit economics

Admin → Overview shows, for the last 30 days:

```
revenue (verified payments)
− AI/API cost      (estimated from the per-token / per-call prices you enter)
− payment fees     (actual from Stripe's balance transaction, else estimated at 2.9% + 30¢)
− other costs      (infrastructure + other monthly costs you enter)
= contribution margin      — also per user and per paying user
```

Every figure is counted from rows that exist. Ad impressions and ad revenue show "Not
available" because no ad network reports to the product.

## Payments (Stripe)

Status: **built, not configured.** With no keys, checkout returns 503 "Payments are not set
up yet … No charge was made" and the pricing page says so.

To turn it on:

1. Stripe dashboard → Developers → API keys → set `PDE_STRIPE_SECRET_KEY` (start with `sk_test_`).
2. Developers → Webhooks → add endpoint `https://<api>/api/v1/billing/webhook` with events
   `checkout.session.completed`, `invoice.paid`, `customer.subscription.updated`,
   `customer.subscription.deleted`. Set its signing secret as `PDE_STRIPE_WEBHOOK_SECRET`.
3. Set `PDE_PUBLIC_APP_URL` to the web app's URL.
4. Enable the Customer Portal in Stripe (Settings → Billing → Customer portal) so users can cancel.
5. Locally: `stripe listen --forward-to localhost:8000/api/v1/billing/webhook` and use the
   secret it prints.

Prices come from Admin → Pricing and are sent as inline `price_data`, so changing a price needs
no Stripe dashboard change. Card details go to Stripe's hosted page only. Entitlements are
granted **only** by signature-verified webhooks; returning to `/billing/success` grants nothing.
Percent-off promotions become a one-time Stripe coupon; "extra analyses" promotions are
redeemed on the Account page.

**Refunds** are not yet reflected automatically (a `charge.refunded` handler is a TODO).

## Advertising

Status: **framework only; no network connected.** Slots: `AD_SLOT_TOP_BANNER` (analyze page),
`AD_SLOT_RESULTS_SIDEBAR`, `AD_SLOT_BETWEEN_SECTIONS` (between the factors and the
explanation — never inside figures), `AD_SLOT_DASHBOARD`. Each is labelled "Advertisement",
boxed apart from the analysis, hidden when printing, and shown only when the server says
`show_ads` (free users by default; paid, professional and admin never unless you change the
audience in Admin → Ads).

With provider `none`, production renders nothing and development renders a labelled
placeholder. To use AdSense: get approved, then in Admin → Ads set provider `adsense` and your
`ca-pub-…` client ID. Review Google's policies for financial-services content first.

## Property Watch

Updates come from the user (price, status, days on market). A price change re-runs the full
analysis at the new price as a new analysis linked to the old one and shows the difference.
There is **no automatic monitoring**: listing portals prohibit automated collection (ADR 0002),
and the product says this on the page. `app/providers/watch.py` defines the provider protocol
for a future licensed feed; `POST /api/v1/internal/watch/refresh` (bearer `PDE_CRON_SECRET`)
is the scheduler hook and currently reports that no automated provider exists.

## Analytics

A first-party `product_events` table, visible in Admin → Activity → Funnel. Event names only
(plus small labels such as which product); values ending in `_cents` or naming income or price
are dropped. Server events: `signup_completed`, `analysis_completed`, `free_analysis_used`,
`free_limit_reached`, `deep_dive_checkout_started`, `subscription_checkout_started`,
`payment_succeeded`, `property_watch_created`, `comparison_created`, `offer_scenarios_run`.
Client events (whitelisted): `landing_viewed`, `analysis_started`, `deep_dive_viewed`,
`subscription_viewed`, `pricing_viewed`, `upgrade_clicked`.

## Data protection

- Passwords: argon2id. Sessions: 256-bit tokens, only the sha256 stored, httpOnly + SameSite=Lax
  cookies, `Secure` when deployed; CSRF double-submit on every signed-in write.
- A household's submitted inputs and full results are encrypted at rest with Fernet
  (`PDE_DATA_ENCRYPTION_KEY`). Summary columns (price, monthly cost, cash required) stay
  plain for list views; income, debts and savings never are.
- Throttling keys and IPs are stored as keyed hashes. Error events store path and exception
  class, never request bodies. The logging redaction filter is unchanged.
- Not yet built: email verification and password reset (need an email provider), account
  deletion endpoint (the `users.deleted_at` queue exists in the schema).
