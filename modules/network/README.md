# Network inventory

`collect.py` is a read-only Linux collector. Follow [the egress worksheet](../../docs/debian-egress-hardening.md). It does not install firewall rules or approve observed destinations.

Captures contain private network metadata. Choose an output directory outside tracked paths, keep it private and inspect collection errors before interpreting the results. Never publish captured traffic or automatically generate allowances from it.
