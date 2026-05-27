"""Agent nodes for the narrative generation workflow."""

import asyncio
import json
import re
from typing import Dict, Any, List
from datetime import datetime

from .agent_state import AgentState, StoryState
from .lore import LoreSystem, SimpleLoreRetriever


class AgentNode:
    """Base class for agent workflow nodes."""
    
    def __call__(self, state: AgentState) -> AgentState:
        """Execute the node logic."""
        raise NotImplementedError


class LoadContextNode(AgentNode):
    """Load and prepare context from task and story state."""
    
    def __call__(self, state: AgentState) -> AgentState:
        """Load context from the task and prepare it for generation."""
        # Prepare recent history context
        history_context = []
        for msg in state.recent_history[-10:]:  # Last 10 messages
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if role == 'user':
                history_context.append(f"玩家: {content}")
            elif role == 'assistant':
                history_context.append(f"叙述: {content}")
        
        state.agent_trace['history_loaded'] = len(state.recent_history)
        state.agent_trace['context_prepared'] = True
        
        return state


class RetrieveLoreNode(AgentNode):
    """Retrieve relevant lore based on context."""
    
    def __init__(self, worlds_path: str = None):
        self.lore_system = LoreSystem(worlds_path)
        self.retriever = SimpleLoreRetriever(self.lore_system)
    
    def __call__(self, state: AgentState) -> AgentState:
        """Retrieve relevant lore for the current situation."""
        try:
            # Get world name from story state
            world_name = state.story_state.current_world
            
            # Set current world in lore system
            self.lore_system.current_world = world_name
            
            # Retrieve relevant context
            lore_context = self.retriever.retrieve_context_for_generation(
                user_input=state.user_input,
                current_scene=state.story_state.current_scene,
                story_state=state.story_state.to_dict(),
                world_name=world_name
            )
            
            state.retrieved_lore = [lore_context]
            state.agent_trace['lore_retrieved'] = True
            state.agent_trace['world_name'] = world_name
            
        except Exception as e:
            state.agent_trace['lore_error'] = str(e)
            # Fallback to minimal context
            state.retrieved_lore = ["World: Fantasy setting with magic and adventure"]
        
        return state


class PlanNarrativeNode(AgentNode):
    """Plan the narrative direction (simple rule-based for MVP)."""
    
    def __call__(self, state: AgentState) -> AgentState:
        """Create a simple narrative plan based on context."""
        
        # Analyze user input intent
        user_input_lower = state.user_input.lower()
        
        # Determine narrative focus
        if any(word in user_input_lower for word in ['攻击', '战斗', '打击', '伤害']):
            narrative_focus = "action_combat"
        elif any(word in user_input_lower for word in ['说话', '对话', '询问', '交谈']):
            narrative_focus = "dialogue_social"
        elif any(word in user_input_lower for word in ['观察', '查看', '检查', '寻找']):
            narrative_focus = "exploration_discovery"
        elif any(word in user_input_lower for word in ['移动', '走', '跑', '离开']):
            narrative_focus = "movement_transition"
        else:
            narrative_focus = "general_response"
        
        # Update story stage if needed
        current_stage = state.story_state.story_stage
        if current_stage == "opening" and narrative_focus in ["movement_transition", "exploration_discovery"]:
            state.state_update['story_stage'] = "inciting_incident"
        elif current_stage == "inciting_incident" and narrative_focus == "action_combat":
            state.state_update['story_stage'] = "rising_action"
        
        # Create simple narrative plan
        plan = f"""
NARRATIVE PLAN:
- Focus: {narrative_focus}
- Current Stage: {state.story_state.story_stage}
- User Intent: {state.user_input[:100]}
- Scene: {state.story_state.current_scene or 'Unknown'}

Approach:
1. Acknowledge player action
2. Describe immediate consequences
3. Maintain atmosphere and tension
4. Provide new options or information
5. Update world state as needed
"""
        
        state.narrative_plan = plan.strip()
        state.agent_trace['narrative_focus'] = narrative_focus
        state.agent_trace['plan_created'] = True
        
        return state


class GenerateStoryNode(AgentNode):
    """Generate the main story content using LLM."""
    
    def __init__(self, ollama_client=None):
        self.ollama_client = ollama_client
    
    def __call__(self, state: AgentState) -> AgentState:
        """Generate story content using the LLM."""
        if not self.ollama_client:
            state.error_message = "Ollama client not available"
            state.quality_passed = False
            return state
        
        try:
            # Build the generation prompt
            prompt = self._build_generation_prompt(state)
            
            # Generate content
            response = asyncio.run(
                self.ollama_client.generate(
                    prompt,
                    model=state.model,
                    generation_options={
                    'num_predict': 500,
                    'temperature': 0.7,
                    'top_p': 0.9,
                    }
                )
            )
            
            if response:
                state.final_response = response.strip()
                state.agent_trace['generation_success'] = True
                state.agent_trace['tokens_generated'] = len(state.final_response)
            else:
                state.error_message = "Empty response from LLM"
                state.quality_passed = False
                
        except Exception as e:
            state.error_message = f"Generation failed: {str(e)}"
            state.quality_passed = False
            state.agent_trace['generation_error'] = str(e)
        
        return state
    
    def _build_generation_prompt(self, state: AgentState) -> str:
        """Build the complete generation prompt."""
        
        # Start with recent history
        history_text = ""
        if state.recent_history:
            history_text = "RECENT CONVERSATION:\\n" + "\\n".join([
                f"{msg['role']}: {msg['content']}" 
                for msg in state.recent_history[-6:]
            ])
        
        # Add retrieved lore
        lore_text = ""
        if state.retrieved_lore:
            lore_text = "\\n".join(state.retrieved_lore)
        
        # Add narrative plan
        plan_text = state.narrative_plan if state.narrative_plan else "Continue the story naturally."
        
        # Build the complete prompt
        prompt = f"""You are a narrator for an interactive fiction story. The player has just taken an action, and you need to describe what happens next.

{lore_text}

{history_text}

CURRENT SITUATION:
- Player Action: {state.user_input}
- Current Location: {state.story_state.current_scene or 'Unknown location'}
- Story Stage: {state.story_state.story_stage}

{plan_text}

WORLD SETTING:
{state.world_setting}

CHARACTER SETTING:
{state.character_setting}

IMPORTANT RULES:
1. Use second-person perspective ("你") to address the player
2. Never describe the player's thoughts or feelings
3. Never make decisions for the player
4. Describe what happens as a result of their action
5. Maintain atmosphere and world consistency
6. Keep responses engaging but not too long (200-400 characters)
7. End with an open situation that invites further action

Generate the next part of the story:"""

        return prompt


class QualityCheckAndUpdateStateNode(AgentNode):
    """Check quality and update story state."""
    
    def __call__(self, state: AgentState) -> AgentState:
        """Perform quality checks and update state."""
        
        if not state.final_response:
            state.quality_passed = False
            state.quality_issues.append("Empty response")
            return state
        
        # Perform quality checks
        issues = []
        
        # Check for forbidden patterns
        forbidden_patterns = [
            (r'你决定', "Making decisions for player"),
            (r'你感到', "Describing player feelings"),
            (r'你认为', "Describing player thoughts"),
            (r'你想要', "Describing player desires"),
        ]
        
        for pattern, issue in forbidden_patterns:
            if re.search(pattern, state.final_response):
                issues.append(issue)
        
        # Check response length
        response_length = len(state.final_response)
        if response_length < 50:
            issues.append("Response too short")
        elif response_length > 800:
            issues.append("Response too long")
        
        # Check for modern terms
        modern_terms = ['手机', '电脑', '网络', '电视', '汽车']
        for term in modern_terms:
            if term in state.final_response:
                issues.append(f"Modern term: {term}")
        
        # Update quality status
        state.quality_issues = issues
        state.quality_passed = len(issues) == 0
        
        # Generate state updates based on content
        self._generate_state_updates(state)
        
        state.agent_trace['quality_checked'] = True
        state.agent_trace['quality_issues'] = issues
        
        return state
    
    def _generate_state_updates(self, state: AgentState):
        """Generate state updates based on the generated content."""
        
        # Extract potential scene changes
        scene_keywords = ['进入', '来到', '走出', '到达', '穿越到']
        for keyword in scene_keywords:
            if keyword in state.final_response:
                # Try to extract location name
                match = re.search(f'{keyword}([^，。]+?)(?:，|。|$)', state.final_response)
                if match:
                    new_scene = match.group(1).strip()
                    if len(new_scene) < 20 and len(new_scene) > 2:
                        state.state_update['current_scene'] = new_scene
                        break
        
        # Update world flags based on actions
        if any(word in state.user_input for word in ['打开', '启动', '激活']):
            # Extract what was opened/activated
            match = re.search(r'(打开|启动|激活)([^，。]+?)(?:，|。|$)', state.user_input)
            if match:
                item = match.group(2).strip()
                flag_key = f"{item}_opened".lower().replace(" ", "_")
                state.state_update['world_flags'] = state.state_update.get('world_flags', {})
                state.state_update['world_flags'][flag_key] = True
        
        # Add pending events if interesting things happened
        interest_keywords = ['听到', '看到', '发现', '感觉', '注意到']
        for keyword in interest_keywords:
            if keyword in state.final_response:
                # Extract what was noticed
                match = re.search(f'{keyword}([^，。]+?)(?:，|。|$)', state.final_response)
                if match:
                    event = match.group(1).strip()
                    if len(event) < 50:
                        pending_events = state.state_update.get('pending_events', [])
                        pending_events.append(event)
                        state.state_update['pending_events'] = pending_events[-3:]  # Keep last 3
                        break
        
        # Update long summary periodically
        if len(state.final_response) > 200:
            summary_snippet = state.final_response[:200] + "..."
            current_summary = state.story_state.long_summary
            if len(current_summary) < 1000:  # Keep summary under 1000 chars
                state.state_update['long_summary'] = current_summary + "\\n" + summary_snippet
            else:
                state.state_update['long_summary'] = summary_snippet  # Replace if too long


class ReturnResponseNode(AgentNode):
    """Prepare the final response for return to server."""
    
    def __call__(self, state: AgentState) -> AgentState:
        """Prepare final response payload."""
        
        # Prepare trace information
        state.agent_trace['completed_at'] = datetime.now().isoformat()
        state.agent_trace['total_nodes'] = 5
        state.agent_trace['quality_passed'] = state.quality_passed
        
        # Ensure we have content to return
        if not state.final_response and state.error_message:
            state.final_response = f"[系统错误: {state.error_message}]"
        
        return state


def create_agent_workflow(ollama_client=None, worlds_path: str = None):
    """Create a simple agent workflow with all nodes."""
    
    return [
        LoadContextNode(),
        RetrieveLoreNode(worlds_path),
        PlanNarrativeNode(),
        GenerateStoryNode(ollama_client),
        QualityCheckAndUpdateStateNode(),
        ReturnResponseNode()
    ]


def execute_agent_workflow(task: Dict[str, Any], ollama_client=None, worlds_path: str = None) -> Dict[str, Any]:
    """Execute the complete agent workflow and return the result."""
    
    # Create agent state from task
    agent_state = AgentState.from_task(task)
    
    # Create workflow nodes
    workflow = create_agent_workflow(ollama_client, worlds_path)
    
    # Execute workflow
    for node in workflow:
        try:
            agent_state = node(agent_state)
            if not agent_state.quality_passed and agent_state.error_message:
                # Stop workflow if there's a critical error
                break
        except Exception as e:
            agent_state.error_message = f"Node execution failed: {str(e)}"
            agent_state.quality_passed = False
            break
    
    # Prepare result payload
    result = {
        'task_id': agent_state.task_id,
        'status': 'success' if agent_state.quality_passed else 'error',
        'content': agent_state.final_response,
        'state_update': agent_state.state_update,
        'agent_trace': agent_state.agent_trace,
        'error_message': agent_state.error_message,
        'model': agent_state.model
    }
    
    if not agent_state.quality_passed:
        result['error_code'] = 'GENERATION_QUALITY_FAILED'
        result['quality_issues'] = agent_state.quality_issues
    
    return result
