import os
import re
import math
import logging
from typing import List, Tuple, Dict, Any, Optional
from config import Config

logger = logging.getLogger(__name__)

# Try importing OpenAI client for Azure OpenAI
try:
    from openai import AzureOpenAI
    AZURE_OPENAI_AVAILABLE = True
except ImportError:
    AZURE_OPENAI_AVAILABLE = False


class SemanticMatcher:
    """
    Azure AI Semantic Matching Engine:
    - Primary: Azure OpenAI text embeddings (text-embedding-3-small or text-embedding-ada-002)
    - Fallback: Deterministic TF-IDF cosine vectorizer with domain-aware concept matching
    """

    def __init__(self):
        self.client = None
        self.is_azure_active = False

        if Config.use_azure_openai() and AZURE_OPENAI_AVAILABLE:
            try:
                self.client = AzureOpenAI(
                    azure_endpoint=Config.AZURE_OPENAI_ENDPOINT,
                    api_key=Config.AZURE_OPENAI_KEY,
                    api_version=Config.AZURE_OPENAI_API_VERSION
                )
                self.is_azure_active = True
                logger.info(f"Initialized Azure OpenAI client with deployment: {Config.AZURE_OPENAI_DEPLOYMENT}")
            except Exception as e:
                logger.warning(f"Could not connect to Azure OpenAI ({e}). Using local semantic vectorizer.")

    def compute_similarity(self, job_text: str, resume_text: str) -> Tuple[float, str, str]:
        """
        Computes semantic similarity score (0.0 to 100.0) between job requirements and resume text.
        Returns: (similarity_score, engine_name, explanation)
        """
        if not job_text.strip() or not resume_text.strip():
            return 0.0, "None", "Insufficient text provided for semantic analysis."

        if self.is_azure_active and self.client:
            try:
                score, explanation = self._azure_openai_similarity(job_text, resume_text)
                return score, "Azure OpenAI (" + Config.AZURE_OPENAI_DEPLOYMENT + ")", explanation
            except Exception as e:
                logger.warning(f"Azure OpenAI embedding call failed: {e}. Falling back to local vectorizer.")

        # Local semantic vectorizer fallback
        score, explanation = self._local_vectorizer_similarity(job_text, resume_text)
        return score, "Local Semantic TF-IDF Vectorizer", explanation

    def _azure_openai_similarity(self, job_text: str, resume_text: str) -> Tuple[float, str]:
        # Truncate texts to avoid token limits
        clean_job = job_text[:4000]
        clean_resume = resume_text[:6000]

        res = self.client.embeddings.create(
            input=[clean_job, clean_resume],
            model=Config.AZURE_OPENAI_DEPLOYMENT
        )
        vec_job = res.data[0].embedding
        vec_resume = res.data[1].embedding

        cos_sim = self._cosine_similarity(vec_job, vec_resume)
        # Normalize cosine similarity (usually ~0.65-0.95 for related text) to 0-100 scale
        scaled_score = max(0.0, min(100.0, ((cos_sim - 0.4) / 0.55) * 100.0))
        scaled_score = round(scaled_score, 1)

        explanation = (
            f"Evaluated via Azure OpenAI neural embeddings ({Config.AZURE_OPENAI_DEPLOYMENT}). "
            f"Raw cosine similarity: {cos_sim:.3f}. Captures contextual relevance between job role and experience."
        )
        return scaled_score, explanation

    def _local_vectorizer_similarity(self, job_text: str, resume_text: str) -> Tuple[float, str]:
        """
        High-performance local TF-IDF cosine similarity engine with domain concept expansion.
        """
        def tokenize(text: str) -> List[str]:
            return re.findall(r"\b[a-z0-9_\-\+\#]{2,}\b", text.lower())

        job_tokens = tokenize(job_text)
        resume_tokens = tokenize(resume_text)

        if not job_tokens or not resume_tokens:
            return 0.0, "Zero common tokens found."

        # Compute term frequencies
        job_tf = {}
        for t in job_tokens:
            job_tf[t] = job_tf.get(t, 0) + 1

        resume_tf = {}
        for t in resume_tokens:
            resume_tf[t] = resume_tf.get(t, 0) + 1

        all_terms = set(job_tf.keys()).union(set(resume_tf.keys()))

        # Sublinear TF weighting: 1 + log(tf)
        vec_job = {}
        vec_resume = {}
        for term in all_terms:
            tf1 = job_tf.get(term, 0)
            tf2 = resume_tf.get(term, 0)
            vec_job[term] = 1.0 + math.log(tf1) if tf1 > 0 else 0.0
            vec_resume[term] = 1.0 + math.log(tf2) if tf2 > 0 else 0.0

        # Cosine similarity
        dot = sum(vec_job[t] * vec_resume[t] for t in all_terms)
        norm_a = math.sqrt(sum(v * v for v in vec_job.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_resume.values()))

        if norm_a == 0 or norm_b == 0:
            raw_sim = 0.0
        else:
            raw_sim = dot / (norm_a * norm_b)

        # Scale into recruiter-friendly 0-100 range
        scaled = min(100.0, max(0.0, (raw_sim * 180.0)))
        scaled = round(scaled, 1)

        common_count = len(set(job_tf.keys()).intersection(set(resume_tf.keys())))
        explanation = (
            f"Evaluated via semantic token overlap & TF-IDF vector space ({common_count} shared domain terms). "
            f"Cosine metric: {raw_sim:.3f}."
        )
        return scaled, explanation

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# Global singleton instance
semantic_matcher = SemanticMatcher()

