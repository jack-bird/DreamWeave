"""Agent State and Story State definitions for the narrative generation agent."""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class StoryState:
    """Persistent story state stored in database."""
    current_world: str = "default_world"
    current_scene: str = ""
    story_stage: str = "opening"
    long_summary: str = ""
    characters: Dict[str, Any] = field(default_factory=dict)
    relationships: Dict[str, Any] = field(default_factory=dict)
    world_flags: Dict[str, Any] = field(default_factory=dict)
    inventory: List[Any] = field(default_factory=list)
    pending_events: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_world": self.current_world,
            "current_scene": self.current_scene,
            "story_stage": self.story_stage,
            "long_summary": self.long_summary,
            "characters": self.characters,
            "relationships": self.relationships,
            "world_flags": self.world_flags,
            "inventory": self.inventory,
            "pending_events": self.pending_events
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoryState':
        """Create from dictionary."""
        return cls(
            current_world=data.get("current_world", "default_world"),
            current_scene=data.get("current_scene", ""),
            story_stage=data.get("story_stage", "opening"),
            long_summary=data.get("long_summary", ""),
            characters=data.get("characters", {}),
            relationships=data.get("relationships", {}),
            world_flags=data.get("world_flags", {}),
            inventory=data.get("inventory", []),
            pending_events=data.get("pending_events", [])
        )


@dataclass
class AgentState:
    """Runtime state for agent workflow execution."""
    # Task identification
    task_id: str
    user_id: str
    story_id: str
    session_id: str
    model: str
    
    # Input data
    user_input: str
    story_state: StoryState
    recent_history: List[Dict[str, str]] = field(default_factory=list)
    
    # Context from server
    world_setting: str = ""
    character_setting: str = ""
    story_title: str = ""
    
    # Agent workflow data
    retrieved_lore: List[str] = field(default_factory=list)
    narrative_plan: str = ""
    character_reactions: str = ""
    draft_response: str = ""
    final_response: str = ""
    
    # Output data
    state_update: Dict[str, Any] = field(default_factory=dict)
    
    # Quality check
    quality_passed: bool = True
    quality_issues: List[str] = field(default_factory=list)
    
    # Metadata
    agent_trace: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "story_id": self.story_id,
            "session_id": self.session_id,
            "model": self.model,
            "user_input": self.user_input,
            "story_state": self.story_state.to_dict(),
            "recent_history": self.recent_history,
            "world_setting": self.world_setting,
            "character_setting": self.character_setting,
            "story_title": self.story_title,
            "retrieved_lore": self.retrieved_lore,
            "narrative_plan": self.narrative_plan,
            "character_reactions": self.character_reactions,
            "draft_response": self.draft_response,
            "final_response": self.final_response,
            "state_update": self.state_update,
            "quality_passed": self.quality_passed,
            "quality_issues": self.quality_issues,
            "agent_trace": self.agent_trace,
            "error_message": self.error_message
        }
    
    @classmethod
    def from_task(cls, task: Dict[str, Any]) -> 'AgentState':
        """Create AgentState from a task dictionary."""
        story_state_data = task.get("context", {}).get("story_state", {})
        story_state = StoryState.from_dict(story_state_data)
        
        recent_messages = task.get("context", {}).get("recent_messages", [])
        context = task.get("context", {})
        
        return cls(
            task_id=task.get("task_id", ""),
            user_id=task.get("user_id", ""),
            story_id=task.get("story_id", ""),
            session_id=task.get("session_id", ""),
            model=task.get("model", ""),
            user_input=task.get("input", ""),
            story_state=story_state,
            recent_history=recent_messages,
            world_setting=context.get("world_setting", ""),
            character_setting=context.get("character_setting", ""),
            story_title=context.get("story_title", "")
        )