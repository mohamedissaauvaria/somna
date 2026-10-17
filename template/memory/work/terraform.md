# Terraform conventions (example)

## Layout
- One root module per environment.
- Remote state with locking, one state file per root module.

## Providers
- Pin providers with a pessimistic constraint, for example "~> 5.0".
- Keep the same major version across root and child modules.

## Known pitfalls
- terraform init fails when root and child modules pin incompatible provider versions.
  Fix the root pin first, then re-run init.
