"""Paper summarization module using Google Gemini API."""

import hashlib
import json
import logging
import time
from pathlib import Path

import google.generativeai as genai

logger = logging.getLogger(__name__)


class SummaryError(Exception):
    """Exception raised when summarization fails."""

    pass


# Prompt templates for different detail levels
PROMPTS = {
    "short": """당신은 생물학 논문 요약 전문가입니다. 아래 논문 내용을 한글로 간결하게 요약해주세요.

중요: Technical term (예: CRISPR-Cas9, phosphorylation, apoptosis, PCR, Western blot 등)은 반드시 영어 그대로 유지하세요.

다음 형식으로 요약해주세요:

:bar_chart: *논문 분석 결과*
*[논문 원제목 - 영어 그대로]*

:bulb: *한줄 핵심 (The Hook)*
[이 논문의 핵심을 한 문장으로 요약]

:dart: *추천 대상*
[이 논문을 읽으면 좋을 대상 - 쉼표로 구분]

*1. 연구 목적 (Problem & Goal)*
• [연구 배경과 목적을 2-3개 bullet point로]

*2. 주요 발견 (Key Results)*
• [핵심 발견사항 3개 이내]

`#Keyword1` `#Keyword2` `#Keyword3`

---
논문 내용:
{text}
""",
    "normal": """You are an expert biology paper summarizer. Summarize the paper below in Korean.

CRITICAL RULES:
1. Output MUST be in Korean, but keep ALL technical terms in English (e.g., CRISPR-Cas9, phosphorylation, apoptosis, PCR, Western blot, transfection, knockdown, RNA-seq)
2. Gene names, protein names, compound names, cell line names MUST remain in English
3. Statistics and p-values should be kept as-is
4. Use Slack emoji format (e.g., :bulb:, :dart:, :bar_chart:)
5. For bullet points with labels, make the label bold before colon (e.g., • *Method:* description here)
6. Follow the EXACT output format below - do not add or remove sections

OUTPUT FORMAT:

:bar_chart: *논문 분석 결과*
*[Original paper title in English]*

:bulb: *한줄 핵심 (The Hook)*
[One impactful sentence summarizing the key finding/contribution with specific numbers or achievements]

:dart: *추천 대상*
[Target audience - 3-5 researcher/expert types, comma-separated]

───────────────────────
*1. 연구 목적 (Problem & Goal)*
• *기존 한계:* [Previous limitations or problems]
• *연구 목표:* [Specific goals and approach of this study]

───────────────────────
*2. 핵심 방법론 (Method & Tech Stack)*
• *실험/분석 방법:* [Main experimental/analysis methods]
• *사용 기술:* [Technologies, models, tools used]
• *실험 설계:* [Key experimental design]

───────────────────────
*3. 주요 발견 (Key Results)*
• [Most important finding 1 - include specific numbers]
• [Important finding 2]
• [Important finding 3]
• [Experimental validation or statistical significance]

───────────────────────
*4. 한계 및 비판 (Critical View)*
• *한계점:* [Limitations of the study]
• *개선 방향:* [Potential improvements]
• *추가 연구:* [Areas needing further research]

───────────────────────
`#Keyword1` `#Keyword2` `#Keyword3` `#Keyword4` `#Keyword5`

---
Paper content:
{text}
""",
    "detailed": """당신은 생물학 논문 요약 전문가입니다. 아래 논문 내용을 한글로 상세하게 요약해주세요.

중요 규칙:
1. Technical term은 반드시 영어 그대로 유지 (예: CRISPR-Cas9, phosphorylation, apoptosis, PCR, Western blot, transfection, siRNA, shRNA, qRT-PCR, ChIP-seq, RNA-seq 등)
2. 유전자명, 단백질명, 화합물명, 세포주명은 영어로 유지
3. 통계 수치와 p-value는 그대로 표기
4. 일반적인 설명은 자연스러운 한글로 작성
5. 이모지는 Slack 형식 사용

다음 형식으로 상세히 요약해주세요:

:bar_chart: *논문 분석 결과*
*[논문 원제목 - 영어 그대로]*
_[저자 정보 및 소속기관]_

:bulb: *한줄 핵심 (The Hook)*
[이 논문의 핵심 발견/기여를 임팩트 있는 한 문장으로 요약]

:dart: *추천 대상*
[이 논문을 읽으면 좋을 연구자/전문가 유형]

*1. 연구 목적 (Problem & Goal)*
• [연구의 학문적 배경]
• [기존 연구의 한계점]
• [본 연구의 구체적인 목표와 가설]

*2. 핵심 방법론 (Method & Tech Stack)*
• [실험 모델 (세포주, 동물 모델 등)]
• [주요 분자생물학적 기법]
• [분석 방법 및 통계]
• [사용된 도구/소프트웨어]

*3. 주요 발견 (Key Results)*
• [Figure별 또는 실험별 주요 결과]
• [통계적 유의성과 함께 구체적 수치 포함]
• [대조군 대비 실험군의 차이]

*4. 한계 및 비판 (Critical View)*
• [연구 설계의 한계]
• [결과 해석의 주의점]
• [일반화의 제한]
• [향후 연구 방향]

*5. 의의 및 응용 (Implications)*
• [학문적 기여]
• [실용적 응용 가능성]
• [후속 연구 방향]

`#Keyword1` `#Keyword2` `#Keyword3` `#Keyword4` `#Keyword5` `#Keyword6`

---
논문 내용:
{text}
""",
}


class PaperSummarizer:
    """Summarize biology papers using Google Gemini API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        detail_level: str = "normal",
        max_retries: int = 3,
        retry_delay: int = 2,
        cache_enabled: bool = True,
        cache_dir: str = "cache",
    ):
        """
        Initialize the summarizer.

        Args:
            api_key: Google Gemini API key
            model: Model name to use
            detail_level: Summary detail level (short, normal, detailed)
            max_retries: Number of retries on failure
            retry_delay: Seconds between retries
            cache_enabled: Whether to cache summaries
            cache_dir: Directory for cache files
        """
        self.model_name = model
        self.detail_level = detail_level
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cache_enabled = cache_enabled
        self.cache_dir = Path(cache_dir)

        # Configure Gemini
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

        # Create cache directory
        if cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized summarizer with model: {model}")

    def _get_cache_path(self, text_hash: str) -> Path:
        """Get cache file path for a text hash."""
        return self.cache_dir / f"{text_hash}_{self.detail_level}.json"

    def _load_from_cache(self, text_hash: str) -> str | None:
        """Load summary from cache if available."""
        if not self.cache_enabled:
            return None

        cache_path = self._get_cache_path(text_hash)
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"Loaded summary from cache: {text_hash[:8]}...")
                    return data.get("summary")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        return None

    def _save_to_cache(self, text_hash: str, summary: str) -> None:
        """Save summary to cache."""
        if not self.cache_enabled:
            return

        cache_path = self._get_cache_path(text_hash)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "hash": text_hash,
                        "detail_level": self.detail_level,
                        "model": self.model_name,
                        "summary": summary,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info(f"Saved summary to cache: {text_hash[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def summarize(self, text: str) -> str:
        """
        Generate a summary of the paper text.

        Args:
            text: Full text of the paper

        Returns:
            Formatted summary in Korean

        Raises:
            SummaryError: If summarization fails after all retries
        """
        # Check cache first
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        cached = self._load_from_cache(text_hash)
        if cached:
            return cached

        # Get appropriate prompt
        prompt_template = PROMPTS.get(self.detail_level, PROMPTS["normal"])
        prompt = prompt_template.format(text=text)

        # Truncate if too long (Gemini has token limits)
        max_chars = 900000  # Safe limit for most models
        if len(prompt) > max_chars:
            logger.warning(f"Text too long ({len(prompt)} chars), truncating")
            text_limit = max_chars - len(prompt_template)
            prompt = prompt_template.format(text=text[:text_limit])

        # Generate summary with retries
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Generating summary (attempt {attempt}/{self.max_retries})")

                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,  # Lower for more consistent output
                        top_p=0.8,
                        max_output_tokens=4096,
                    ),
                )

                if response.text:
                    summary = response.text.strip()
                    self._save_to_cache(text_hash, summary)
                    return summary
                else:
                    raise SummaryError("Empty response from Gemini")

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)  # Exponential backoff

        raise SummaryError(f"Failed to generate summary after {self.max_retries} attempts: {last_error}")

    def set_detail_level(self, level: str) -> None:
        """Change the summary detail level."""
        if level not in PROMPTS:
            raise ValueError(f"Invalid detail level: {level}. Must be one of: {list(PROMPTS.keys())}")
        self.detail_level = level
        logger.info(f"Detail level set to: {level}")
