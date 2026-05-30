"""
向量存储模块
基于 Chroma 实现向量的存储和检索
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import chromadb
from chromadb import Collection
from .embeddings import get_embedding_model, generate_embedding

logger = logging.getLogger(__name__)

class LoreVectorStore:
    """Lore 向量存储管理"""
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        """
        初始化向量存储
        
        Args:
            persist_directory: Chroma 数据持久化目录
        """
        self.persist_directory = persist_directory
        self.client: Optional[Any] = None
        self.collections: Dict[str, Collection] = {}
        
    def _get_client(self) -> Any:
        """获取或创建 Chroma 客户端"""
        if self.client is None:
            logger.info(f"Initializing Chroma client with persist directory: {self.persist_directory}")
            self.client = chromadb.PersistentClient(path=self.persist_directory)
        return self.client
    
    def _get_collection_name(self, story_id: str) -> str:
        """
        生成 collection 名称
        
        Args:
            story_id: 故事 ID
            
        Returns:
            collection 名称
        """
        return f"story_{story_id}"
    
    def _get_or_create_collection(self, story_id: str) -> Collection:
        """
        获取或创建 collection
        
        Args:
            story_id: 故事 ID
            
        Returns:
            Collection 实例
        """
        collection_name = self._get_collection_name(story_id)
        
        if collection_name not in self.collections:
            client = self._get_client()
            
            # 尝试获取已存在的 collection
            try:
                collection = client.get_collection(name=collection_name)
                logger.info(f"Using existing collection: {collection_name}")
            except:
                # 创建新 collection
                collection = client.create_collection(
                    name=collection_name,
                    metadata={"story_id": story_id}
                )
                logger.info(f"Created new collection: {collection_name}")
            
            self.collections[collection_name] = collection
        
        return self.collections[collection_name]
    
    def add_lore_entry(self, story_id: str, lore_entry: Dict[str, Any]) -> bool:
        """
        添加 Lore 条目到向量库
        
        Args:
            story_id: 故事 ID
            lore_entry: Lore 条目数据
            
        Returns:
            是否成功
        """
        try:
            collection = self._get_or_create_collection(story_id)
            
            lore_id = lore_entry.get("id")
            title = lore_entry.get("title", "")
            keywords = lore_entry.get("keywords", [])
            content = lore_entry.get("content", "")
            category = lore_entry.get("category", "lore")
            priority = lore_entry.get("priority", 50)
            enabled = lore_entry.get("enabled", True)
            
            # 组合文本用于生成 embedding
            combined_text = f"{title} {' '.join(keywords)} {content}"
            
            # 生成 embedding
            embedding = generate_embedding(combined_text)
            
            # 准备 metadata
            metadata = {
                "lore_id": lore_id,
                "title": title,
                "category": category,
                "priority": priority,
                "enabled": enabled,
                "keywords": ",".join(keywords) if keywords else ""
            }
            
            # 添加到 collection
            collection.add(
                ids=[lore_id],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[content]
            )
            
            logger.info(f"Added lore entry {lore_id} to collection {collection.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add lore entry to vector store: {e}")
            return False
    
    def update_lore_entry(self, story_id: str, lore_entry: Dict[str, Any]) -> bool:
        """
        更新 Lore 条目
        
        Args:
            story_id: 故事 ID
            lore_entry: Lore 条目数据
            
        Returns:
            是否成功
        """
        try:
            collection = self._get_or_create_collection(story_id)
            
            lore_id = lore_entry.get("id")
            
            # 先删除旧的
            try:
                collection.delete(ids=[lore_id])
            except:
                pass  # 如果不存在就忽略
            
            # 添加新的
            return self.add_lore_entry(story_id, lore_entry)
            
        except Exception as e:
            logger.error(f"Failed to update lore entry in vector store: {e}")
            return False
    
    def delete_lore_entry(self, story_id: str, lore_id: str) -> bool:
        """
        删除 Lore 条目
        
        Args:
            story_id: 故事 ID
            lore_id: Lore 条目 ID
            
        Returns:
            是否成功
        """
        try:
            collection = self._get_or_create_collection(story_id)
            collection.delete(ids=[lore_id])
            logger.info(f"Deleted lore entry {lore_id} from collection")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete lore entry from vector store: {e}")
            return False
    
    def search_similar_lore(
        self, 
        story_id: str, 
        query: str, 
        top_k: int = 5,
        enabled_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        搜索相似的 Lore 条目
        
        Args:
            story_id: 故事 ID
            query: 查询文本
            top_k: 返回结果数量
            enabled_only: 是否只返回启用的条目
            
        Returns:
            搜索结果列表
        """
        try:
            collection = self._get_or_create_collection(story_id)
            
            # 生成查询 embedding
            query_embedding = generate_embedding(query)
            
            # 搜索
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k * 2,  # 多取一些，因为可能需要过滤
                include=["metadatas", "documents", "distances"]
            )
            
            # 处理结果
            formatted_results = []
            if results and results.get("ids") and results["ids"][0]:
                for i, lore_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i]
                    document = results["documents"][0][i]
                    distance = results["distances"][0][i]
                    
                    # 转换距离为相似度分数 (Chroma 使用 L2 距离)
                    score = 1 / (1 + distance)
                    
                    # 过滤禁用的条目
                    if enabled_only and not metadata.get("enabled", True):
                        continue
                    
                    formatted_results.append({
                        "id": lore_id,
                        "title": metadata.get("title", ""),
                        "category": metadata.get("category", "lore"),
                        "priority": metadata.get("priority", 50),
                        "score": score,
                        "content": document,
                        "keywords": metadata.get("keywords", "").split(",") if metadata.get("keywords") else []
                    })
                    
                    if len(formatted_results) >= top_k:
                        break
            
            logger.info(f"Found {len(formatted_results)} similar lore entries for query: {query[:50]}...")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search similar lore: {e}")
            return []
    
    def rebuild_collection(self, story_id: str, lore_entries: List[Dict[str, Any]]) -> bool:
        """
        重建整个 collection
        
        Args:
            story_id: 故事 ID
            lore_entries: Lore 条目列表
            
        Returns:
            是否成功
        """
        try:
            collection_name = self._get_collection_name(story_id)
            client = self._get_client()
            
            # 删除旧 collection
            try:
                client.delete_collection(name=collection_name)
                logger.info(f"Deleted old collection: {collection_name}")
            except:
                pass
            
            # 清除缓存
            if collection_name in self.collections:
                del self.collections[collection_name]
            
            # 重新创建并添加所有条目
            for lore_entry in lore_entries:
                if lore_entry.get("enabled", True):  # 只添加启用的条目
                    self.add_lore_entry(story_id, lore_entry)
            
            logger.info(f"Rebuilt collection {collection_name} with {len(lore_entries)} entries")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rebuild collection: {e}")
            return False

# 全局向量存储实例
_global_vector_store: Optional[LoreVectorStore] = None

def get_vector_store(persist_directory: str = "./chroma_db") -> LoreVectorStore:
    """
    获取全局向量存储实例
    
    Args:
        persist_directory: 持久化目录
        
    Returns:
        LoreVectorStore 实例
    """
    global _global_vector_store
    
    if _global_vector_store is None:
        _global_vector_store = LoreVectorStore(persist_directory)
    
    return _global_vector_store
