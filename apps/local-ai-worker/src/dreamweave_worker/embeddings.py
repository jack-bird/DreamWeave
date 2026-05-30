"""
Embedding 生成模块
支持多种 embedding 模型，默认使用 sentence-transformers
"""

import logging
from typing import List, Optional
from sentence_transformers import SentenceTransformer
import numpy as np

logger = logging.getLogger(__name__)

class EmbeddingModel:
    """Embedding 模型封装"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        初始化 embedding 模型
        
        Args:
            model_name: 模型名称，默认使用支持中文的多语言模型
        """
        self.model_name = model_name
        self.model: Optional[SentenceTransformer] = None
        self.dimension = 384  # MiniLM-L12 的默认维度
        
    def load_model(self):
        """延迟加载模型"""
        if self.model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            try:
                self.model = SentenceTransformer(self.model_name)
                # 获取实际维度
                test_embedding = self.model.encode(["测试"])
                self.dimension = len(test_embedding[0])
                logger.info(f"Embedding model loaded, dimension: {self.dimension}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise
    
    def encode(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        生成文本的 embedding
        
        Args:
            texts: 文本列表
            batch_size: 批处理大小
            
        Returns:
            embedding 向量列表
        """
        if not texts:
            return []
        
        self.load_model()
        
        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            
            # 转换为列表格式
            return embeddings.tolist()
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    def encode_single(self, text: str) -> List[float]:
        """
        生成单个文本的 embedding
        
        Args:
            text: 单个文本
            
        Returns:
            embedding 向量
        """
        result = self.encode([text])
        return result[0] if result else []

# 全局模型实例
_global_model: Optional[EmbeddingModel] = None

def get_embedding_model(model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> EmbeddingModel:
    """
    获取全局 embedding 模型实例
    
    Args:
        model_name: 模型名称
        
    Returns:
        EmbeddingModel 实例
    """
    global _global_model
    
    if _global_model is None:
        _global_model = EmbeddingModel(model_name)
    
    return _global_model

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    便捷函数：生成 embeddings
    
    Args:
        texts: 文本列表
        
    Returns:
        embedding 向量列表
    """
    model = get_embedding_model()
    return model.encode(texts)

def generate_embedding(text: str) -> List[float]:
    """
    便捷函数：生成单个 embedding
    
    Args:
        text: 单个文本
        
    Returns:
        embedding 向量
    """
    model = get_embedding_model()
    return model.encode_single(text)