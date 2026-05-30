#!/usr/bin/env python3
"""
测试 RAG 系统
测试 embedding 生成、向量存储和检索功能
"""

import sys
import os

# 添加 Worker 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apps', 'local-ai-worker', 'src'))

from dreamweave_worker.embeddings import generate_embedding, generate_embeddings
from dreamweave_worker.vector_store import get_vector_store
from dreamweave_worker.rag_service import get_rag_service

def test_embedding_generation():
    """测试 embedding 生成"""
    print("🔍 测试 Embedding 生成...")
    
    test_texts = [
        "玄阴谷是青云宗禁地，金丹以下弟子禁止进入。",
        "主角是一名失忆的贵族继承人，在古堡中醒来。",
        "这个世界的修炼体系分为练气、筑基、金丹、元婴等境界。"
    ]
    
    try:
        embeddings = generate_embeddings(test_texts)
        print(f"✅ 成功生成 {len(embeddings)} 个 embeddings")
        print(f"📊 第一个 embedding 维度: {len(embeddings[0])}")
        print(f"📝 第一个 embedding 前10个值: {embeddings[0][:10]}")
        return True
    except Exception as e:
        print(f"❌ Embedding 生成失败: {e}")
        return False

def test_vector_store():
    """测试向量存储"""
    print("\n🔍 测试向量存储...")
    
    try:
        vector_store = get_vector_store("./test_chroma_db")
        test_story_id = "test_story_123"
        
        # 创建测试 Lore 条目
        test_lore_entries = [
            {
                "id": "lore_1",
                "title": "玄阴谷",
                "category": "location",
                "keywords": ["玄阴谷", "禁地", "魔气"],
                "content": "玄阴谷是青云宗禁地，金丹以下弟子禁止进入，谷内有浓厚的魔气。",
                "priority": 80,
                "enabled": True
            },
            {
                "id": "lore_2", 
                "title": "青云宗",
                "category": "faction",
                "keywords": ["青云宗", "宗门", "修仙"],
                "content": "青云宗是修仙界著名的正道宗门，以剑修闻名于世。",
                "priority": 70,
                "enabled": True
            },
            {
                "id": "lore_3",
                "title": "主角",
                "category": "character",
                "keywords": ["主角", "失忆", "贵族"],
                "content": "主角是一名失忆的贵族继承人，在古堡中醒来后开始探索修仙世界。",
                "priority": 90,
                "enabled": True
            }
        ]
        
        # 添加 Lore 条目
        print(f"📝 添加 {len(test_lore_entries)} 个 Lore 条目...")
        for lore_entry in test_lore_entries:
            success = vector_store.add_lore_entry(test_story_id, lore_entry)
            if success:
                print(f"  ✅ 成功添加: {lore_entry['title']}")
            else:
                print(f"  ❌ 添加失败: {lore_entry['title']}")
        
        # 测试搜索
        print(f"\n🔍 测试向量搜索...")
        query = "我进入了玄阴谷"
        results = vector_store.search_similar_lore(test_story_id, query, top_k=2)
        
        print(f"📊 查询: '{query}'")
        print(f"🎯 找到 {len(results)} 个相关结果:")
        for i, result in enumerate(results):
            print(f"  {i+1}. {result['title']} (分数: {result['score']:.3f})")
            print(f"     分类: {result['category']}, 优先级: {result['priority']}")
        
        return True
    except Exception as e:
        print(f"❌ 向量存储测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_rag_service():
    """测试 RAG 服务"""
    print("\n🔍 测试 RAG 服务...")
    
    try:
        rag_service = get_rag_service()
        test_story_id = "test_story_456"
        
        # 测试单个 Lore 条目处理
        test_lore = {
            "id": "lore_test_1",
            "title": "测试地点",
            "category": "location",
            "keywords": ["测试", "地点"],
            "content": "这是一个测试用的地点描述。",
            "priority": 50,
            "enabled": True
        }
        
        print(f"📝 处理 Lore 条目: {test_lore['title']}")
        result = rag_service.process_lore_entry(test_story_id, test_lore, "add")
        print(f"✅ 处理结果: {result}")
        
        # 测试搜索
        print(f"\n🔍 测试 RAG 搜索...")
        search_result = rag_service.search_lore(test_story_id, "测试地点", top_k=1)
        print(f"📊 搜索结果: {search_result}")
        
        return True
    except Exception as e:
        print(f"❌ RAG 服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 开始测试 RAG 系统...")
    
    results = []
    
    # 测试 Embedding 生成
    results.append(("Embedding 生成", test_embedding_generation()))
    
    # 测试向量存储
    results.append(("向量存储", test_vector_store()))
    
    # 测试 RAG 服务
    results.append(("RAG 服务", test_rag_service()))
    
    # 输出总结
    print("\n" + "="*50)
    print("📊 测试结果总结:")
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("="*50)
    if all_passed:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())