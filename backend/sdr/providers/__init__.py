"""Provider layer - the only place third-party APIs are touched.

Everything above depends on the `DataProvider` port in `base.py`, never on a
vendor SDK, and vendor field names never escape an adapter's `_normalize`
method. Swapping Apollo for Clearbit is one registry entry.

A provider that cannot do something returns `unsupported` rather than
pretending. That rule is load-bearing for the LinkedIn case, where the only
technically-possible implementations violate the platform's terms - the
adapter reports the capability as unavailable and the UI explains why.
"""
