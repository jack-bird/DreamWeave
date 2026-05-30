"""
RAG 服务模块
处理 Lore 条目的向量化和存储
"""

import logging
from typing import Dict, Any, List, Optional
from .embeddings import generate_embedding
from .vector_store import get_vector_store

logger = logging.getLogger(__name__)

class RAGService:
    """RAG 服务，处理 Lore 向量化"""
    
    def __init__(self):
        self.vector_store = get_vector_store()
    
    def process_lore_entry(self, story_id: str, lore_entry: Dict[str, Any], operation: str = "add") -> Dict[str, Any]:
        """
        处理 Lore 条目，生成 embedding 并写入向量库
        
        Args:
            story_id: 故事 ID
            lore_entry: Lore 条目数据
            operation: 操作类型 (add, update, delete)
            
        Returns:
            处理结果
        """
        try:
            lore_id = lore_entry.get("id")
            enabled = lore_entry.get("enabled", True)
            
            # 如果删除操作或条目被禁用，从向量库移除
            if operation == "delete" or not enabled:
                if operation == "delete":
                    success = self.vector_store.delete_lore_entry(story_id, lore_id)
                else:
                    # 禁用时也删除，启用时重新添加
                    success = self.vector_store.delete_lore_entry(story_id, lore_id)
                
                return {
                    "success": success,
                    "operation": operation,
                    "lore_id": lore_id,
                    "rag_index_status": "removed" if success else "failed"
                }
            
            # 添加或更新操作
            if operation == "add":
                success = self.vector_store.add_lore_entry(story_id, lore_entry)
            elif operation == "update":
                success = self.vector_store.update_lore_entry(story_id, lore_entry)
            else:
                success = False
            
            return {
                "success": success,
                "operation": operation,
                "lore_id": lore_id,
                "rag_index_status": "indexed" if success else "failed"
            }
            
        except Exception as e:
            logger.error(f"Failed to process lore entry {lore_entry.get('id')}: {e}")
            return {
                "success": False,
                "operation": operation,
                "lore_id": lore_entry.get("id"),
                "rag_index_status": "failed",
                "error": str(e)
            }
    
    def batch_reindex(self, story_id: str, lore_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量重建索引
        
        Args:
            story_id: 故事 ID
            lore_entries: Lore 条目列表
            
        Returns:
            处理结果
        """
        try:
            success = self.vector_store.rebuild_collection(story_id, lore_entries)
            
            return {
                "success": success,
                "operation": "reindex",
                "story_id": story_id,
                "total_entries": len(lore_entries),
                "rag_index_status": "indexed" if success else "failed"
            }
            
        except Exception as e:
            logger.error(f"Failed to batch reindex story {story_id}: {e}")
            return {
                "success": False,
                "operation": "reindex",
                "story_id": story_id,
                "rag_index_status": "failed",
                "error": str(e)
            }
    
    def search_lore(self, story_id: str, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        搜索 Lore 条目
        
        Args:
            story_id: 故事 ID
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果
        """
        try:
            results = self.vector_store.search_similar_lore(story_id, query, top_k)
            
            return {
                "success": True,
                "story_id": story_id,
                "query": query,
                "results": results,
                "count": len(results)
            }
            
        except Exception as e:
            logger.error(f"Failed to search lore for story {story_id}: {e}")
            return {
                "success": False,
                "story_id": story_id,
                "query": query,
                "results": [],
                "error": str(e)
            }

# 全局 RAG 服务实例
_global_rag_service: Optional[RAGService] = None

def get_rag_service() -> RAGService:
    """获取全局 RAG 服务实例"""
    global _global_rag_service
    
    if _global_rag_service is None:
        _global_rag_service = RAGService()
    
    return _global_rag_service