"""Repository layer - the only place in the SDR module that touches `db`.

Services and domain code never issue a Mongo query directly. That rule buys
one specific thing: when tenancy is eventually added to AgencyOS (see
TENANT_SECURITY.md and ADR 0002), the scope filter goes into `scope()` in
base.py and every SDR query inherits it, rather than being retrofitted into
several dozen call sites.
"""
