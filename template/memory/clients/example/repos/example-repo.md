# acme-shop (Acme, fictional example)

## What this repo does
The Acme web shop: product pages, cart and checkout.

## How to navigate it
- `app/` the web app, one folder per page
- `lib/payments/` the payment provider client
- Run `make test` before every push. Deploys run only from the pipeline.

## How it connects
- Pipeline: GitHub Actions, deploys to staging on every merge to main.
- Reads product data from the `acme-catalog` service.

## Current state
- 2026-01-12: New checkout live on staging, card payments still behind a feature flag.

## Gotchas and decisions
- Prices are stored in cents as integers. Never use floats for money.
- The search index rebuilds nightly; changes to products show up the next morning.

## Questions for the owner
- none
