"""Agent nodes for the narrative generation workflow."""

import asyncio
import re
from typing import Dict, Any
from datetime import datetime

from .agent_state import AgentState
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
        state.agent_trace['history_context_chars'] = len("\n".join(history_context))
        
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
                    'num_predict': 420,
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
        prompt = f"""你是互动小说叙事引擎。玩家刚刚做出一个行动，你需要描写这个行动带来的直接结果。

{lore_text}

{history_text}

当前局面：
- 玩家行动：{state.user_input}
- 当前地点：{state.story_state.current_scene or '未知地点'}
- 剧情阶段：{state.story_state.story_stage}

{plan_text}

世界设定：
{state.world_setting}

角色设定：
{state.character_setting}

输出规则：
1. 只输出中文小说正文，不要标题、列表、选项或系统说明。
2. 使用第二人称“你”指代玩家。
3. 不要描写玩家的想法、感受或替玩家决定下一步行动。
4. 只描写玩家行动造成的直接后果、环境反馈和 NPC / 事件变化。
5. 保持世界观一致，不引入现代物品或无关设定。
6. 长度控制在 200 到 400 个中文字符。
7. 结尾停在开放局面，让玩家自己决定下一步。

请直接生成下一段正文："""

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
        
        # Update quality status. Soft issues are reported in trace, but only
        # critical generation failures should turn a usable story paragraph into
        # a task error.
        state.quality_issues = issues
        hard_issue_prefixes = (
            "Making decisions",
            "Describing player feelings",
            "Describing player thoughts",
            "Describing player desires",
            "Response too short",
        )
        state.quality_passed = not any(issue.startswith(hard_issue_prefixes) for issue in issues)
        
        # Generate state updates based on content
        self._generate_state_updates(state)
        
        state.agent_trace['quality_checked'] = True
        state.agent_trace['quality_issues'] = issues
        
        return state
    
    def _generate_state_updates(self, state: AgentState):
        """Generate state updates based on the generated content."""
        
        new_scene = self._extract_scene_change(state.final_response)
        if new_scene:
            state.state_update['current_scene'] = new_scene
        
        # Update world flags based on actions
        if any(word in state.user_input for word in ['打开', '启动', '激活']):
            # Extract what was opened/activated
            match = re.search(r'(打开|启动|激活)([^，。；;!?！？]+?)(?:[，。；;!?！？]|$)', state.user_input)
            if match:
                item = self._clean_state_text(match.group(2), max_length=24)
                flag_key = f"{item}_opened".lower().replace(" ", "_")
                state.state_update['world_flags'] = state.state_update.get('world_flags', {})
                state.state_update['world_flags'][flag_key] = True
        
        # Add pending events if interesting things happened
        interest_keywords = ['听到', '看到', '发现', '注意到']
        for keyword in interest_keywords:
            if keyword in state.final_response:
                match = re.search(f'{keyword}([^，。；;!?！？]+?)(?:[，。；;!?！？]|$)', state.final_response)
                if match:
                    event = self._clean_state_text(f"{keyword}{match.group(1)}", max_length=60)
                    if event:
                        pending_events = state.state_update.get('pending_events', [])
                        pending_events.append(event)
                        state.state_update['pending_events'] = pending_events[-3:]  # Keep last 3
                        break
        
        # Update long summary periodically
        if len(state.final_response) > 200:
            summary_snippet = self._clean_state_text(state.final_response[:220], max_length=220)
            current_summary = state.story_state.long_summary.strip()
            combined = f"{current_summary}\n{summary_snippet}" if current_summary else summary_snippet
            state.state_update['long_summary'] = combined[-1200:]

    def _extract_scene_change(self, text: str) -> str:
        """Extract only explicit location transitions."""
        patterns = [
            r'(?:进入|来到|到达|抵达|走进)([^，。；;!?！？]{2,24})',
            r'(?:走出|离开)([^，。；;!?！？]{2,24})',
            r'(?:穿越到)([^，。；;!?！？]{2,24})',
        ]
        location_suffixes = (
            '门', '厅', '室', '房', '廊', '庭', '院', '塔', '堡', '城',
            '桥', '路', '林', '谷', '村', '镇', '街', '广场', '祭坛', '大厅'
        )

        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue

            candidate = self._clean_state_text(match.group(1), max_length=24)
            if not candidate:
                continue
            if any(verb in candidate for verb in ('看到', '听到', '发现', '注意到', '传来', '伸手')):
                continue
            if candidate.endswith(location_suffixes) or any(suffix in candidate for suffix in location_suffixes):
                return candidate

        return ""

    def _clean_state_text(self, value: str, max_length: int) -> str:
        value = re.sub(r'\s+', '', value or '')
        value = value.strip(' ：:“”"\'，。；;!?！？、')
        if not value or len(value) > max_length:
            return ""
        return value


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
    error_message = agent_state.error_message
    if not error_message and agent_state.quality_issues:
        error_message = "Quality check failed: " + "; ".join(agent_state.quality_issues)

    result = {
        'task_id': agent_state.task_id,
        'status': 'success' if agent_state.quality_passed else 'error',
        'content': agent_state.final_response,
        'state_update': agent_state.state_update,
        'agent_trace': agent_state.agent_trace,
        'error_message': error_message,
        'model': agent_state.model
    }
    
    if not agent_state.quality_passed:
        result['error_code'] = 'GENERATION_QUALITY_FAILED'
        result['quality_issues'] = agent_state.quality_issues
    
    return result
