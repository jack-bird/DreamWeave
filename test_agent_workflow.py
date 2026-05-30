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

def test_rag_lore_retrieval_node():
    """Test that RetrieveLoreNode prefers RAG results when available."""
    try:
        from dreamweave_worker import agent_nodes
        from dreamweave_worker.agent_nodes import RetrieveLoreNode
        from dreamweave_worker.agent_state import AgentState, StoryState

        class FakeRAGService:
            def search_lore(self, story_id, query, top_k=5):
                assert story_id == "story_test"
                assert "黑塔" in query
                return {
                    "success": True,
                    "results": [
                        {
                            "id": "lore_black_tower",
                            "title": "黑塔",
                            "category": "location",
                            "priority": 80,
                            "content": "黑塔位于北境荒原深处，是旧王朝留下的封印设施。",
                            "keywords": ["黑塔", "北境", "封印"],
                        }
                    ],
                }

        original_get_rag_service = agent_nodes.get_rag_service
        agent_nodes.get_rag_service = lambda: FakeRAGService()
        try:
            test_state = AgentState(
                task_id="test_rag",
                user_id="test_user",
                story_id="story_test",
                session_id="test_session",
                model="fake-model",
                user_input="我观察北境那座被封印的黑塔",
                story_state=StoryState(current_scene="北境荒原", story_stage="opening"),
            )

            result_state = RetrieveLoreNode()(test_state)
            joined_lore = "\n".join(result_state.retrieved_lore)
            assert result_state.agent_trace["lore_source"] == "chroma"
            assert result_state.agent_trace["rag_result_count"] == 1
            assert "=== RAG RELEVANT LORE ===" in joined_lore
            assert "黑塔位于北境荒原深处" in joined_lore
        finally:
            agent_nodes.get_rag_service = original_get_rag_service

        print("[OK] RAG lore retrieval node works correctly")
        return True
    except Exception as e:
        print(f"[FAIL] RAG lore retrieval node failed: {e}")
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

def test_output_cleanup_and_first_person_quality():
    """Test duplicate paragraph cleanup and first-person narration rejection."""
    try:
        from dreamweave_worker.agent_nodes import QualityCheckAndUpdateStateNode
        from dreamweave_worker.agent_state import AgentState, StoryState
        from dreamweave_worker.postprocess import clean_story_output

        repeated = (
            "风停了下来，月光照到塔基，隐藏的石门浮现。\n\n"
            "风停了下来，月光照到塔基，隐藏的石门浮现。\n\n"
            "风停了下来，月光照到塔基，隐藏的石门浮现。"
        )
        cleaned = clean_story_output(repeated)
        assert cleaned.count("隐藏的石门浮现") == 1

        inner_cleaned = clean_story_output(
            "风停了下来，月光照到塔基，隐藏的石门浮现。"
            "你心中燃起兴趣，也不知道它代表着什么。"
            "塔基附近的旧王朝纹路开始发亮，石缝里渗出细薄的银白光线。"
            "荒原上的碎石随低沉震动轻轻跳起，塔门内侧传来缓慢的锁链声。"
        )
        assert "心中" not in inner_cleaned
        assert "不知道" not in inner_cleaned
        assert "隐藏的石门浮现" in inner_cleaned
        assert "旧王朝纹路开始发亮" in inner_cleaned

        test_state = AgentState(
            task_id="test_first_person",
            user_id="test_user",
            story_id="test_story",
            session_id="test_session",
            model="fake-model",
            user_input="我查看黑塔入口",
            story_state=StoryState(current_scene="北境荒原"),
            final_response=(
                "我站在荒原边缘，看见黑塔在月光下显露轮廓。"
                "风停之后，塔基附近的石门浮现出细密的旧王朝纹路。"
            ),
        )

        checked = QualityCheckAndUpdateStateNode()(test_state)
        assert checked.quality_passed == False
        assert any("first-person" in issue for issue in checked.quality_issues)

        inner_state = AgentState(
            task_id="test_inner_state",
            user_id="test_user",
            story_id="test_story",
            session_id="test_session",
            model="fake-model",
            user_input="我查看黑塔入口",
            story_state=StoryState(current_scene="北境荒原"),
            final_response=inner_cleaned,
        )
        inner_checked = QualityCheckAndUpdateStateNode()(inner_state)
        assert inner_checked.quality_passed == True

        residual_feeling = AgentState(
            task_id="test_residual_feeling",
            user_id="test_user",
            story_id="test_story",
            session_id="test_session",
            model="fake-model",
            user_input="我查看黑塔入口",
            story_state=StoryState(current_scene="北境荒原"),
            final_response=(
                "风停了下来，月光照到塔基，隐藏的石门浮现。"
                "塔基附近的旧王朝纹路开始发亮，石缝里渗出细薄的银白光线。"
                "荒原上的碎石随低沉震动轻轻跳起，塔门内侧传来缓慢的锁链声。"
                "你感觉这座塔正在注视你。"
            ),
        )
        residual_checked = QualityCheckAndUpdateStateNode()(residual_feeling)
        assert residual_checked.quality_passed == True
        assert "你感觉" not in residual_checked.final_response

        print("[OK] Output cleanup and first-person quality checks work correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Output cleanup and first-person quality checks failed: {e}")
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

    print("\nTesting RAG Lore Retrieval Node...")
    results.append(test_rag_lore_retrieval_node())
    
    print("\nTesting Revision Node...")
    results.append(test_revision_node())

    print("\nTesting Output Cleanup and First-Person Quality Checks...")
    results.append(test_output_cleanup_and_first_person_quality())
    
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
