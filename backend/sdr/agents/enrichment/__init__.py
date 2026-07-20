"""Lead enrichment - the reference agent.

Every later agent copies this file's structure: schema.py (typed contract),
prompts.py (versioned, never inline), agent.py (thin execute over services).
"""

from sdr.agents.enrichment.agent import EnrichmentAgent

__all__ = ["EnrichmentAgent"]
