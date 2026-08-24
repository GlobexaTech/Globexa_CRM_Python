"""
AI services package init.
"""
from app.services.ai.router import AIRouter, get_ai_router, AIResponse, AIProvider, OllamaProvider, NVIDIAProvider, OpenAIProvider, AnthropicProvider
from app.services.ai.lead_scoring import LeadScoringService, LeadScoreResult, ScoringFactor
from app.services.ai.auto_assignment import AutoAssignmentService, AssignmentResult, AssignmentFactor
from app.services.ai.next_best_action import NextBestActionService, NextActionRecommendation, NextActionType
from app.services.ai.reply_analysis import ReplyAnalysisService, ReplyAnalysis, ReplyResponse, ReplyIntent, ReplySentiment
from app.services.ai.lead_miner import LeadMinerService, LeadMinerResult, DiscoveredProspect, ICPDefinition
from app.services.ai.proposal_generator import ProposalGeneratorService, GeneratedProposal, ProposalTemplate
from app.services.ai.assistant import AIAssistantService, AssistantResponse, ToolDefinition, ToolCall, ToolResult, AssistantMessage

__all__ = [
    "AIRouter",
    "get_ai_router",
    "AIResponse",
    "AIProvider",
    "OllamaProvider",
    "NVIDIAProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "LeadScoringService",
    "LeadScoreResult",
    "ScoringFactor",
    "AutoAssignmentService",
    "AssignmentResult",
    "AssignmentFactor",
    "NextBestActionService",
    "NextActionRecommendation",
    "NextActionType",
    "ReplyAnalysisService",
    "ReplyAnalysis",
    "ReplyResponse",
    "ReplyIntent",
    "ReplySentiment",
    "LeadMinerService",
    "LeadMinerResult",
    "DiscoveredProspect",
    "ICPDefinition",
    "ProposalGeneratorService",
    "GeneratedProposal",
    "ProposalTemplate",
    "AIAssistantService",
    "AssistantResponse",
    "ToolDefinition",
    "ToolCall",
    "ToolResult",
    "AssistantMessage",
]