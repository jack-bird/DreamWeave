"""
Test script for the Agent Workflow implementation.
This simulates a complete flow to verify the integration works correctly.
"""

import json
import sys
import os

# Add the paths to import from different apps
sys.path.append(os.path.join(os.path.dirname(__file__), 'apps', 'local-ai-worker', 'src'))

def test_agent_data_structures():
    """Test that agent data structures can be imported and used."""
    try:
        from dreamweave_worker.agent_state import AgentState, StoryState
        
        # Test StoryState creation
        story_state = StoryState(
            current_world="default_world",
            current_scene="古堡大门",
            story_stage="opening",
            long_summary="玩家开始探索神秘古堡",
            characters={"mysterious_stranger": "第一次见面"},
            world_flags={"castle_gate_opened": True}
        )
        
        # Test serialization
        state_dict = story_state.to_dict()
        assert state_dict['current_world'] == "default_world"
        assert state_dict['current_scene'] == "古堡大门"
        
        # Test deserialization
        restored_state = StoryState.from_dict(state_dict)
        assert restored_state.current_world == story_state.current_world
        assert restored_state.current_scene == story_state.current_scene
        
        print("[OK] AgentState and StoryState data structures work correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Agent data structures failed: {e}")
        return False

def test_lore_system():
    """Test that the lore system can load and retrieve content."""
    try:
        from dreamweave_worker.lore import LoreSystem
        
        lore_system = LoreSystem()
        
        # Test loading lore
        lore = lore_system.load_lore("default_world")
        assert "魔法" in lore or "世界" in lore
        
        # Test loading characters
        characters = lore_system.load_characters("default_world")
        assert isinstance(characters, dict)
        
        # Test lore retrieval
        relevant_lore = lore_system.retrieve_relevant_lore(
            user_input="我推开了古堡的大门",
            current_scene="古堡大门",
            world_name="default_world"
        )
        assert isinstance(relevant_lore, list)
        
        print("[OK] Lore system works correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Lore system failed: {e}")
        return False

def test_agent_nodes():
    """Test that agent nodes can be created and executed."""
    try:
        from dreamweave_worker.agent_nodes import (
            LoadContextNode, 
            RetrieveLoreNode, 
            PlanNarrativeNode,
            QualityCheckAndUpdateStateNode
        )
        from dreamweave_worker.agent_state import AgentState, StoryState
        
        # Create a test agent state
        test_state = AgentState(
            task_id="test_task_123",
            user_id="test_user",
            story_id="test_story", 
            session_id="test_session",
            model="qwen2:7b",
            user_input="我仔细观察古堡大门上的符文",
            story_state=StoryState(
                current_world="default_world",
                current_scene="古堡大门",
                story_stage="opening"
            ),
            recent_history=[
                {"role": "user", "content": "我来到了古堡大门前"},
                {"role": "assistant", "content": "巨大的古堡大门在你面前耸立着..."}
            ]
        )
        
        # Test LoadContextNode
        context_node = LoadContextNode()
        updated_state = context_node(test_state)
        assert updated_state.agent_trace['context_prepared'] == True
        
        # Test PlanNarrativeNode
        plan_node = PlanNarrativeNode()
        planned_state = plan_node(updated_state)
        assert planned_state.narrative_plan != ""
        assert 'exploration_discovery' in planned_state.narrative_plan
        
        # Test QualityCheckNode
        quality_node = QualityCheckAndUpdateStateNode()
        # Set a mock response
        planned_state.final_response = (
            "你仔细观察大门上的符文，发现它们散发着微弱的魔法光芒。"
            "光线沿着石门缝隙缓慢游走，门后传来低沉的锁链摩擦声，像是某个沉睡已久的机关正在苏醒。"
        )
        quality_checked_state = quality_node(planned_state)
        assert quality_checked_state.quality_passed == True
        
        print("[OK] Agent nodes work correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Agent nodes failed: {e}")
        return False

def test_revision_node():
    """Test that the revision node can rewrite a failed response."""
    try:
        from dreamweave_worker.agent_nodes import ReviseStoryNode
        from dreamweave_worker.agent_state import AgentState, StoryState

        class FakeOllama:
            async def generate(self, prompt, model=None, generation_options=None):
                return "你推开的石门在身后发出沉闷回响，走廊深处亮起一线冷白火光。墙上的符文依次苏醒，像无声的眼睛注视着门槛。远处传来锁链拖过石面的声音，某个看不见的机关正在缓慢转动。"

        test_state = AgentState(
            task_id="test_revision",
            user_id="test_user",
            story_id="test_story",
            session_id="test_session",
            model="fake-model",
            user_input="我推开石门",
            story_state=StoryState(current_scene="古堡大门"),
            final_response="你决定继续向前走。",
            quality_passed=False,
            quality_issues=["Making decisions for player"],
        )

        revised_state = ReviseStoryNode(FakeOllama())(test_state)
        assert revised_state.revision_count == 1
        assert revised_state.final_response != "你决定继续向前走。"
        assert revised_state.agent_trace["revision_attempted"] == True

        print("[OK] Revision node works correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Revision node failed: {e}")
        return False

def test_protocol_extensions():
    """Test that protocol extensions support new features."""
    try:
        from dreamweave_worker.protocol import (
            make_result_message,
            make_task_error_message
        )
        
        # Test result message with state_update
        result_msg = make_result_message(
            task_id="test_task",
            content="这是生成的内容",
            model="qwen2:7b",
            worker_id="test_worker",
            state_update={"current_scene": "古堡大厅", "world_flags": {"door_opened": True}},
            agent_trace={"quality_passed": True, "lore_retrieved": True}
        )
        
        assert result_msg['type'] == "ai.result"
        assert result_msg['payload']['state_update']['current_scene'] == "古堡大厅"
        assert result_msg['payload']['agent_trace']['quality_passed'] == True
        
        # Test error message
        error_msg = make_task_error_message(
            task_id="test_task",
            error_code="TEST_ERROR",
            message="Test error message",
            worker_id="test_worker"
        )
        
        assert error_msg['type'] == "ai.task_error"
        assert error_msg['payload']['error_code'] == "TEST_ERROR"
        
        print("[OK] Protocol extensions work correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Protocol extensions failed: {e}")
        return False

def test_database_schema():
    """Test that the database schema is correct."""
    try:
        # Check that the migration file exists and contains correct SQL
        migration_path = os.path.join(
            os.path.dirname(__file__), 
            'apps', 'database', 'migrations', '002_add_story_states.sql'
        )
        
        with open(migration_path, 'r', encoding='utf-8') as f:
            migration_content = f.read()
        
        # Check for key elements
        assert 'CREATE TABLE IF NOT EXISTS story_states' in migration_content
        assert 'session_id' in migration_content
        assert 'state jsonb' in migration_content
        assert 'version integer' in migration_content
        
        print("[OK] Database schema migration looks correct")
        return True
    except Exception as e:
        print(f"[FAIL] Database schema check failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=== DreamWeave Agent Workflow Integration Tests ===\n")
    
    results = []
    
    print("Testing Agent Data Structures...")
    results.append(test_agent_data_structures())
    
    print("\nTesting Lore System...")
    results.append(test_lore_system())
    
    print("\nTesting Agent Nodes...")
    results.append(test_agent_nodes())

    print("\nTesting Revision Node...")
    results.append(test_revision_node())
    
    print("\nTesting Protocol Extensions...")
    results.append(test_protocol_extensions())
    
    print("\nTesting Database Schema...")
    results.append(test_database_schema())
    
    print(f"\n=== Test Results: {sum(results)}/{len(results)} passed ===")
    
    if all(results):
        print("[OK] All tests passed! Agent workflow integration is ready.")
        return 0
    else:
        print("[FAIL] Some tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
