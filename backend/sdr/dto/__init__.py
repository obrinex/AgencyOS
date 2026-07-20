"""Boundary schemas.

One Pydantic model per boundary - HTTP request, provider response, job
payload. The host app declares its DTOs inline at the top of each router; SDR
DTOs that cross more than one boundary live here instead so the router, the
provider registry and the job runner all validate against the same definition.
"""
