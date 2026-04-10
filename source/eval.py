import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

import numpy as np
import pandas as pd
from bert_score.scorer import BERTScorer
from googleapiclient import discovery
from sklearn.feature_extraction.text import CountVectorizer

from source.api.router import LLMRouter
from source.config import CONFIG as _CONFIG

logger = logging.getLogger(__name__)

Message = dict[str, Any]
EvalResult = dict[str, Any]


def loo_metric(
    turns: list[str],
    score_fn: Callable[[str, list[str]], float],
) -> float:
    if len(turns) < 2:
        return 0.0
    scores = [score_fn(turns[i], turns[:i] + turns[i + 1 :]) for i in range(len(turns))]

    return float(np.mean(scores))


def field_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0}

    return {
        "mean": round(float(np.mean(values)), 4),
        "std": round(float(np.std(values)), 4),
    }


def dual_stats(
    gpt_vals: list[float],
    gemini_vals: list[float],
) -> dict[str, dict[str, float]]:

    return {
        "gpt": field_stats(gpt_vals),
        "gemini": field_stats(gemini_vals),
    }


@dataclass
class AgentResult:
    agent_index: int
    persona: str
    persona_ko: str
    judge_result: str
    coherence: dict[str, float]
    diversity: dict[str, float]

    def to_dict(self) -> EvalResult:
        return {
            "agent_index": self.agent_index,
            "persona": self.persona,
            "persona_ko": self.persona_ko,
            "result": {
                "judge_result": self.judge_result,
                "coherence": self.coherence,
                "diversity": self.diversity,
            },
        }


class _C:
    GPT_NAME = "GPT"
    GEMINI_NAME = "GEMINI"
    DEFAULT_TOPIC = "NFT는 예술의 미래인가?"
    JUDGE_RULES = (
        "Evaluation rules:\n"
        "- Score each side from 1 to 10.\n"
        "- Consider:\n"
        "\t- clarity of arguments\n"
        "\t- factuality and use of evidence\n"
        "\t- rebuttal and counterarguments\n"
        "\t- logical consistency\n"
        "\t- persuasiveness and impact\n"
        "\t- conciseness\n"
        "\t- coherence\n\n"

        "Output format (STRICT):\n"
        f'"{GPT_NAME}: [[score]], {GEMINI_NAME}: [[score]], winner: [[name]]. [[description]]"\n\n'

        "Language rule:\n"
        "- The explanation MUST be written in Korean.\n"
    )
    PERSONA_RULES = (
        "Behavior rules:\n"
        "- Evaluate arguments based on quality, from the persona's perspective.\n"
        "- Let the persona's biases influence your judgment, but keep it reasonable.\n"
        "- Do not default to generic balanced evaluations.\n"
        "- Do not invent unsupported traits.\n"
        "- Explain how the persona influenced your judgment.\n"
    )

    JUDGE_SCORE_RE = re.compile(
        f"{GPT_NAME}"
        r"\s*:\s*\[{0,2}(\d+(?:\.\d+)?)\]{0,2}\s*[,;]?\s*"
        f"{GEMINI_NAME}"
        r"\s*:\s*\[{0,2}(\d+(?:\.\d+)?)\]{0,2}\s*[,;]?\s*"
        r"winner\s*:\s*\[{0,2}([\w가-힣]+)\]{0,2}",
        re.IGNORECASE,
    )


class DebateEvaluator:
    """
    두 AI 모델 간 토론 내용을 평가하는 클래스.

    평가 항목:
      - 심판 평가 (점수 1~10 + 승자 + 설명)
      - BERTScore 기반 일관성(Coherence)
      - Distinct-n 기반 다양성(Diversity)
      - Perspective API 기반 유해성(Toxicity)
    """

    def __init__(self) -> None:
        self._system_prompt = None

        self._llm = LLMRouter(
            model=_CONFIG["openrouter"]["OR.MODEL_NAME"],
            key=_CONFIG["openrouter"]["OR.API_KEY"]
        )
        # self._llm = LLMRouter(
        #     model="mlx-community/K-EXAONE-236B-A23B-8bit",
        #     base="vllm"
        # )
        self._bert = BERTScorer(lang="kr")
        self._perspective = discovery.build(
            serviceName="commentanalyzer",
            version="v1alpha1",
            discoveryServiceUrl=(
                "https://commentanalyzer.googleapis.com"
                "/$discovery/rest?version=v1alpha1"
            ),
            developerKey=_CONFIG["google"]["GCP.API_KEY"],
            static_discovery=False,
        )

    def _prepare_dataframe(self, messages: list[Message]) -> pd.DataFrame:
        df = pd.DataFrame(messages)
        df = df[df["role"].isin(["pros", "cons"])].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp").reset_index(drop=True)
        if len(df) % 2 != 0:
            df = df.iloc[:-1]

        return df

    def _build_system_prompt(self, persona: Optional[str]):
        prompt = (
            "You are a debate judge whose evaluations are influenced by a persona.\n\n"
            f"{_C.PERSONA_RULES}\n"
            f'Persona: \n"{persona}"\n\n'
            if persona
            else "You are a debate judge."
        )

        self._system_prompt = f"{prompt}\n\n{_C.JUDGE_RULES}"

    def _build_judge_prompt(
        self,
        df: pd.DataFrame,
        topic: str,
    ) -> str:
        if len(df) < 2:
            return ""

        script = " ".join(
            f'{_C.GPT_NAME}: "{df.iloc[i]["message"]}". '
            f'{_C.GEMINI_NAME}: "{df.iloc[i + 1]["message"]}"'
            for i in range(0, len(df), 2)
        )

        return (
            f'Topic: "{topic}"\n\n'
            f'Debate script: "{script}"\n\n'

            "Explicitly describe how your background influenced your judgment."
        )

    def _call_judge(self, prompt: Optional[str]) -> str:
        if not prompt:
            return "Not enough valid debate turns to evaluate."

        return self._llm.get_response(
            messages=[
                {
                    "role": "system",
                    "content": self._system_prompt,
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ],
        )

    def _coherence_score(self, turns: list[str]) -> float:
        def _score_fn(target: str, others: list[str]) -> float:
            _, _, f1 = self._bert.score([target] * len(others), others, verbose=False)
            return float(f1.mean())

        return loo_metric(turns, _score_fn)

    def _diversity_index(self, turns: list[str], n: int = 2) -> float:
        analyzer = CountVectorizer(analyzer="word", ngram_range=(n, n)).build_analyzer()

        def _score_fn(target: str, others: list[str]) -> float:
            current = set(analyzer(target))
            if not current:
                return 0.0
            other_union = set().union(*(set(analyzer(o)) for o in others))
            return len(current - other_union) / len(current)

        return loo_metric(turns, _score_fn)

    def _toxicity_score(self, text: str) -> Optional[float]:
        try:
            result = (
                self._perspective.comments()
                .analyze(
                    body={
                        "comment": {"text": text},
                        "requestedAttributes": {"TOXICITY": {}},
                    }
                )
                .execute()
            )
            return result["attributeScores"]["TOXICITY"]["summaryScore"]["value"]
        except Exception as exc:
            logger.warning("Perspective API 호출 실패: %s", exc)
            return None

    def _mean_toxicity(self, turns: list[str]) -> Optional[float]:
        scores = [s for t in turns if (s := self._toxicity_score(t)) is not None]
        return round(float(np.mean(scores)), 4) if scores else None

    def evaluate(
        self,
        messages: list[Message],
        topic: str = _C.DEFAULT_TOPIC,
        persona: Optional[str] = None,
        include_toxicity: bool = False,
    ) -> EvalResult:
        df = self._prepare_dataframe(messages)

        if df.empty:
            return {
                "judge_result": "No valid turns to evaluate.",
                "coherence": {"gpt": 0.0, "gemini": 0.0},
                "diversity": {"gpt": 0.0, "gemini": 0.0},
            }

        gpt_turns = df[df["role"] == "pros"]["message"].tolist()
        gemini_turns = df[df["role"] == "cons"]["message"].tolist()

        self._build_system_prompt(persona)
        prompt = self._build_judge_prompt(df, topic)
        result: EvalResult = {
            "judge_result": self._call_judge(prompt),
            "coherence": {
                "gpt": round(self._coherence_score(gpt_turns), 4),
                "gemini": round(self._coherence_score(gemini_turns), 4),
            },
            "diversity": {
                "gpt": round(self._diversity_index(gpt_turns), 4),
                "gemini": round(self._diversity_index(gemini_turns), 4),
            },
        }
        if include_toxicity:
            result["toxicity"] = {
                "gpt": self._mean_toxicity(gpt_turns),
                "gemini": self._mean_toxicity(gemini_turns),
            }

        return result


class PersonaDebateEvaluator:
    def __init__(self, persona_json_path: str, num_agents: int = 10) -> None:
        self._persona_path = persona_json_path
        self._num_agents = num_agents
        self._evaluator = DebateEvaluator()

    def _load_personas(self) -> list[dict]:
        with open(self._persona_path, "r", encoding="utf-8") as fh:
            all_personas: list[dict] = json.load(fh)

        if len(all_personas) < self._num_agents:
            raise ValueError(
                f"페르소나 수({len(all_personas)})가 "
                f"요청한 에이전트 수({self._num_agents})보다 적습니다."
            )

        return random.sample(all_personas, self._num_agents)

    def _judge_worker(
        self,
        idx: int,
        persona: str,
        *,
        df: pd.DataFrame,
        topic: str,
    ) -> tuple[int, str]:
        logger.info("[%d/%d] 평가 중: %.60s …", idx, self._num_agents, persona)
        self._evaluator._build_system_prompt(persona)
        prompt = self._evaluator._build_judge_prompt(df, topic)
        result = self._evaluator._call_judge(prompt)
        logger.info("[%d/%d] 완료", idx, self._num_agents)

        return idx, result

    def _compute_aggregate(self, results: list[EvalResult]) -> EvalResult:
        gpt_scores, gemini_scores = [], []
        coh_gpt, coh_gem, div_gpt, div_gem = [], [], [], []
        winner_tally: dict[str, int] = {_C.GPT_NAME: 0, _C.GEMINI_NAME: 0, "무승부": 0}

        for r in results:
            m = _C.JUDGE_SCORE_RE.search(r["judge_result"])
            if m:
                gpt_scores.append(float(m.group(1)))
                gemini_scores.append(float(m.group(2)))
                winner = m.group(3).upper()
                winner_tally[winner if winner in winner_tally else "무승부"] += 1
            else:
                logger.warning(
                    "점수 파싱 실패 — 해당 에이전트 결과가 집계에서 제외됩니다."
                )

            coh_gpt.append(r["coherence"]["gpt"])
            coh_gem.append(r["coherence"]["gemini"])
            div_gpt.append(r["diversity"]["gpt"])
            div_gem.append(r["diversity"]["gemini"])

        return {
            "judge_score": dual_stats(gpt_scores, gemini_scores),
            "coherence": dual_stats(coh_gpt, coh_gem),
            "diversity": dual_stats(div_gpt, div_gem),
            "winner_tally": winner_tally,
            "total_agents": len(results),
        }

    def evaluate_with_personas(
        self,
        messages: list[Message],
        topic: str = _C.DEFAULT_TOPIC,
    ) -> EvalResult:
        personas = self._load_personas()
        ev = self._evaluator
        df = ev._prepare_dataframe(messages)

        gpt_turns = df[df["role"] == "pros"]["message"].tolist()
        gemini_turns = df[df["role"] == "cons"]["message"].tolist()

        logger.info("[공통 지표 계산 중] Coherence / Diversity …")
        shared: EvalResult = {
            "coherence": {
                "gpt": round(ev._coherence_score(gpt_turns), 4),
                "gemini": round(ev._coherence_score(gemini_turns), 4),
            },
            "diversity": {
                "gpt": round(ev._diversity_index(gpt_turns), 4),
                "gemini": round(ev._diversity_index(gemini_turns), 4),
            },
        }

        logger.info("[병렬 실행] 번역 + LLM Judge 평가 시작 …")
        judge_results: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=self._num_agents + 1) as pool:
            judge_futures = {
                pool.submit(
                    self._judge_worker, idx, persona["en-US"], df=df, topic=topic
                ): idx
                for idx, persona in enumerate(personas, start=1)
            }
            for future in as_completed(judge_futures):
                idx, result = future.result()
                judge_results[idx] = result

        agents = [
            AgentResult(
                agent_index=idx,
                persona=personas[idx - 1]["en-US"],
                persona_ko=personas[idx - 1]["ko-KR"],
                judge_result=judge_results[idx],
                **shared,
            ).to_dict()
            for idx in sorted(judge_results)
        ]
        aggregate = self._compute_aggregate([a["result"] for a in agents])

        return {"agents": agents, "aggregate": aggregate}
