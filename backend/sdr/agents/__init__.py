"""Agent layer - LLM orchestration.

Every agent implements the same contract (`base/agent.py`) and is executed by
the same runner, which is what makes 21 agents tractable rather than 21
bespoke scripts. The runner - not the agent - owns run recording, output
validation, cost ceilings, timeouts and guardrails, so an agent author cannot
accidentally skip them.

Agents are invoked by the job runner (`sdr/services/jobs.py`), never directly
from a request handler: an LLM call plus provider I/O does not reliably fit
inside the 60-second serverless ceiling.
"""
