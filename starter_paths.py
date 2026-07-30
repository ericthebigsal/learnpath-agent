from dataclasses import dataclass, field


@dataclass
class StarterPathStep:
    item_id: str
    rationale: str


@dataclass
class StarterPath:
    id: str
    title: str
    description: str
    steps: list[StarterPathStep] = field(default_factory=list)


STARTER_PATHS: list[StarterPath] = [
    StarterPath(
        id="product-manager",
        title="Product Manager",
        description="A breadth-first tour for PMs who need to speak credibly about AI systems without writing the code.",
        steps=[
            StarterPathStep("llmf-what-is-an-llm-really", "Grounds every later conversation in what the model actually is."),
            StarterPathStep("llmf-tokens-and-context-windows", "The vocabulary you'll need to read a token bill or a context limit."),
            StarterPathStep("llmf-prompting-basics", "The lowest-cost lever product teams reach for first."),
            StarterPathStep("llmf-choosing-the-right-model", "Model choice is a product tradeoff, not just an engineering one."),
            StarterPathStep("rag-fundamentals", "The most common pattern behind 'our AI knows our data.'"),
            StarterPathStep("ctx-what-is-context-engineering", "Explains why the same model behaves differently across products."),
            StarterPathStep("mas-what-is-a-multi-agent-system", "What 'agentic' actually means when a vendor pitches it to you."),
            StarterPathStep("eval-why-eval-llm-apps", "How teams know an AI feature is actually working before shipping it."),
            StarterPathStep("bill-how-token-pricing-works", "The unit economics question you'll get asked about in every review."),
        ],
    ),
    StarterPath(
        id="engineer",
        title="Engineer",
        description="Practical, build-oriented depth for engineers shipping AI features.",
        steps=[
            StarterPathStep("llmf-how-llms-generate-text", "The mechanics behind every downstream architecture decision."),
            StarterPathStep("llmf-embeddings-explained", "The primitive that RAG, search, and clustering all sit on top of."),
            StarterPathStep("rag-fundamentals", "The core pattern you'll implement first."),
            StarterPathStep("rag-chunking-strategies", "The single highest-leverage lever for RAG quality."),
            StarterPathStep("rag-vector-databases", "What's actually happening when you call a similarity search."),
            StarterPathStep("tools-function-calling-basics", "How a model goes from text to real side effects."),
            StarterPathStep("tools-designing-good-tool-schemas", "Bad schemas are the most common source of tool-calling bugs."),
            StarterPathStep("ctx-context-window-budgeting", "You'll hit this limit in production before you hit any other."),
            StarterPathStep("eval-golden-datasets-and-test-sets", "Without this, you can't tell a regression from noise."),
            StarterPathStep("bill-input-vs-output-token-costs", "Cost shows up in your design decisions, not just your invoice."),
        ],
    ),
    StarterPath(
        id="product-builder-fd",
        title="Product Builder (Forward-Deployed)",
        description="Agents, tools, and cost tradeoffs for builders deploying agentic systems directly with clients.",
        steps=[
            StarterPathStep("mas-what-is-a-multi-agent-system", "The architecture you'll be standing up on-site."),
            StarterPathStep("mas-orchestrator-vs-swarm-patterns", "The first design decision for any client deployment."),
            StarterPathStep("tools-what-are-agent-tools", "What actually connects an agent to a client's real systems."),
            StarterPathStep("mas-task-decomposition-and-delegation", "How work actually gets split across agents in practice."),
            StarterPathStep("tools-tool-selection-at-scale", "Client environments rarely have just one or two tools."),
            StarterPathStep("mas-handling-agent-failures-and-loops", "The failure mode that will page you at a client site."),
            StarterPathStep("rag-fundamentals", "How agents ground answers in a client's own data."),
            StarterPathStep("ctx-memory-and-state-management", "What survives between turns in a long-running client session."),
            StarterPathStep("eval-llm-as-judge", "How you'll demonstrate the system is working without a human reviewing every output."),
            StarterPathStep("bill-choosing-models-for-cost-efficiency", "Client budgets make model routing a real design constraint, not an afterthought."),
        ],
    ),
]


def get_starter_path(starter_id: str) -> StarterPath:
    for path in STARTER_PATHS:
        if path.id == starter_id:
            return path
    raise KeyError(f"No starter path with id {starter_id!r}")
