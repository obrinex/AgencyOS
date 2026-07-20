"""Service layer - orchestration and side effects.

Services compose the domain layer with repositories and providers. They own
the "what happens when", transactional ordering, and the audit trail. They
contain no HTTP concepts and no React, and they never issue a Mongo query
directly - that is the repository layer's job.
"""
