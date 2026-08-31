from pathlib import Path
import traceback
from typing import List, Optional

import paths

_instance: Optional["ChromaDBClient"] = None
_chroma_init_failed: bool = False


def _resolve_model_path(model_path: Optional[str]) -> str:
    """Explicit argument wins; otherwise read config.json `embedding.model_path`.
    Explicit relative paths are anchored to the project root; absolute paths
    stay as-is (config.json values are already anchored by get_embedding_model_path).

    config_loader is imported lazily because it (transitively) imports this
    module via RPA_langGraph.context_blocks — a top-level import would cycle.
    / 显式传参优先；否则读取 config.json 的 embedding.model_path。
      显式传入的相对路径锚定项目根，绝对路径原样保留（config.json 的值已由
      get_embedding_model_path 锚定）。
      config_loader 经 RPA_langGraph.context_blocks 传递依赖本模块，
      顶层导入会成环，故此处懒导入。
    """
    if model_path:
        p = Path(model_path)
        return str(p) if p.is_absolute() else str(paths.PROJECT_ROOT / p)
    from config_loader import get_embedding_model_path

    return get_embedding_model_path()


def get_chroma(persist_dir: Optional[str] = None, model_path: Optional[str] = None) -> "ChromaDBClient":
    global _instance
    if _instance is None:
        _instance = ChromaDBClient(persist_dir=persist_dir, model_path=_resolve_model_path(model_path))
    return _instance


def safe_get_chroma(persist_dir: Optional[str] = None, model_path: Optional[str] = None):
    """Return the Chroma client, or None when initialization fails (e.g. the
    embedding model cannot be loaded). Graph nodes use this so a broken
    vector store degrades to "no retrieval" instead of silently skipping
    actor turns or crashing the review chain. The failure is cached so the
    expensive model load is not retried on every call.
    / 返回 Chroma 客户端；初始化失败（如嵌入模型无法加载）时返回 None。
      图节点使用本函数，使向量库故障降级为"无检索"，而不是静默跳过
      角色扮演或让审看链崩溃。失败会被缓存，避免每次调用重复加载模型。
    """
    global _chroma_init_failed
    if _chroma_init_failed:
        return None
    try:
        return get_chroma(persist_dir=persist_dir, model_path=_resolve_model_path(model_path))
    except Exception:
        _chroma_init_failed = True
        traceback.print_exc()
        return None


class Qwen3EmbeddingFunction:
    """使用本地 Qwen3-Embedding-0.6B 模型的 ChromaDB 嵌入函数"""

    def __init__(self, model_path: str):
        """
        :param model_path: 本地模型目录路径
        """
        from sentence_transformers import SentenceTransformer
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(
            model_path,
            trust_remote_code=True,
            device=device,
            # transformers >= 4.51 defaults to initializing the model on the
            # meta device (low_cpu_mem_usage), and torch >= 2.13 refuses to
            # copy meta tensors to another device ("Cannot copy out of meta
            # tensor"). Force normal loading so the model can be moved to the
            # target device.
            # / transformers >= 4.51 默认以 low_cpu_mem_usage 在 meta 设备上
            #   初始化模型，torch >= 2.13 拒绝将 meta 张量复制到目标设备
            #   （Cannot copy out of meta tensor）。关闭该模式即可正常加载。
            model_kwargs={"low_cpu_mem_usage": False},
        )

    def __call__(self, texts) -> List[List[float]]:
        """将文本列表转换为向量列表"""
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=True)
        return embeddings.tolist()


class ChromaDBClient:
    """ChromaDB 向量数据库客户端"""

    def __init__(self, persist_dir: Optional[str] = None, model_path: str = "models/Qwen3-Embedding-0.6B"):
        """
        :param persist_dir: 向量数据库持久化目录；缺省锚定项目根 chroma_data/（显式传入原样生效）
        :param model_path: 本地嵌入模型路径
        """
        import chromadb

        if persist_dir is None:
            persist_dir = str(paths.CHROMA_DIR)
        self.embedding_func = Qwen3EmbeddingFunction(model_path)
        self.client = chromadb.PersistentClient(path=persist_dir)

    def get_collection(self, name: str):
        """获取已有集合"""
        return self.client.get_collection(name=name, embedding_function=self.embedding_func)

    def get_or_create_collection(self, name: str):
        """获取或创建集合"""
        return self.client.get_or_create_collection(name=name, embedding_function=self.embedding_func)

    def delete_collection(self, name: str):
        """删除集合"""
        self.client.delete_collection(name)

    def list_collections(self):
        """列出所有集合"""
        return self.client.list_collections()

    def query(self, collection_name: str, query_texts: List[str], n_results: int = 10):
        """
        语义搜索
        :param collection_name: 集合名称
        :param query_texts: 查询文本列表
        :param n_results: 返回结果数
        :return: 包含 ids, distances, documents, metadatas 的字典
        """
        collection = self.get_collection(collection_name)
        return collection.query(query_texts=query_texts, n_results=n_results)
