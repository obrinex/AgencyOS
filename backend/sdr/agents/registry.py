"""Agent registry.

Explicit registration, like the provider registry: an agent should never
become runnable as a side effect of an import. The job runner resolves
`agent_key` through here, so an unregistered key dead-letters with a clear
message rather than failing obscurely.
"""

from sdr.agents.base.agent import Agent
from sdr.agents.enrichment import EnrichmentAgent
from sdr.agents.inbound import InboundClassifierAgent
from sdr.agents.meetings import MeetingProposalAgent
from sdr.agents.outreach import OutreachSendAgent, PersonalizationAgent
from sdr.agents.research import CompanyResearchAgent
from sdr.agents.scoring import LeadScoringAgent, QualificationAgent
from sdr.agents.website_audit import WebsiteAuditAgent

_AGENTS: dict = {}


def register(agent: Agent) -> None:
    _AGENTS[agent.key] = agent


register(EnrichmentAgent())
register(WebsiteAuditAgent())
register(CompanyResearchAgent())
register(LeadScoringAgent())
register(QualificationAgent())
register(PersonalizationAgent())
register(OutreachSendAgent())
register(InboundClassifierAgent())
register(MeetingProposalAgent())


def get_agent(key: str) -> Agent | None:
    return _AGENTS.get(key)


def all_agents() -> list:
    return list(_AGENTS.values())


def describe() -> list:
    """Static metadata for the Agents page."""
    return [
        {
            "key": agent.key,
            "version": agent.version,
            "description": agent.description,
            "category": agent.category,
            "surface": agent.surface,
            "queue": agent.queue,
            "cost_ceiling_usd": agent.cost_ceiling_usd,
            "timeout_ms": agent.timeout_ms,
        }
        for agent in sorted(_AGENTS.values(), key=lambda a: a.key)
    ]
