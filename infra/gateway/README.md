# infra/gateway

`nftables.conf` in this directory is copied from the gateway VM's
`/etc/nftables.conf` — it's an export of the live ruleset for reference and
rebuildability, not applied automatically from here. See `docs/build-environment.md`
and `BUILD_ENV_HARDENING.md` (Layer 4) for how it's built, applied, and verified.
