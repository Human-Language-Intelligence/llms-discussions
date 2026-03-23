import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

import numpy as np
import openai
import pandas as pd
from bert_score.scorer import BERTScorer
from googleapiclient import discovery
from sklearn.feature_extraction.text import CountVectorizer

from source.config import CONFIG as _CONFIG

logger = logging.getLogger(__name__)

Message = dict[str, Any]
EvalResult = dict[str, Any]
T = TypeVar("T")


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
    GPT_MODEL = "gpt-5.4-mini"
    PROS_ROLE = "pros"
    CONS_ROLE = "cons"
    GPT_NAME = "GPT"
    GEMINI_NAME = "GEMINI"
    DEFAULT_TOPIC = "NFT는 예술의 미래인가?"

    JUDGE_SCORE_RE = re.compile(
        r"GPT\s*:\s*\[{0,2}(\d+(?:\.\d+)?)\]{0,2}\s*[,;]?\s*"
        r"GEMINI\s*:\s*\[{0,2}(\d+(?:\.\d+)?)\]{0,2}\s*[,;]?\s*"
        r"winner\s*:\s*\[{0,2}([\w가-힣]+)\]{0,2}",
        re.IGNORECASE,
    )


class LLMCaller:
    def __init__(self, client: openai.OpenAI, model: str = _C.GPT_MODEL) -> None:
        self._client = client
        self._model = model

    def call(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        res = self._client.responses.create(
            model=self._model, input=messages, reasoning={"effort": "none"}
        )

        return res.output_text


class DebateEvaluator:
    """
    두 AI 모델 간 토론 내용을 평가하는 클래스.

    평가 항목:
      - GPT-4o 심판 평가 (점수 1~10 + 승자 + 설명)
      - BERTScore 기반 일관성(Coherence)
      - Distinct-n 기반 다양성(Diversity)
      - Perspective API 기반 유해성(Toxicity)
    """

    def __init__(self) -> None:
        _openai_client = openai.OpenAI(api_key=_CONFIG["openai"]["GPT.API_KEY"])

        self._llm = LLMCaller(_openai_client)
        self._perspective = discovery.build(
            serviceName="commentanalyzer",
            version="v1alpha1",
            discoveryServiceUrl=(
                "https://commentanalyzer.googleapis.com"
                "/$discovery/rest?version=v1alpha1"
            ),
            static_discovery=False,
            developerKey=_CONFIG["google"]["GCP.API_KEY"],
        )
        self._bert = BERTScorer(lang="kr")

    def _prepare_dataframe(self, messages: list[Message]) -> pd.DataFrame:
        df = pd.DataFrame(messages)
        df = df[df["role"].isin([_C.PROS_ROLE, _C.CONS_ROLE])].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp").reset_index(drop=True)
        if len(df) % 2 != 0:
            df = df.iloc[:-1]

        return df

    def _build_judge_prompt(
        self,
        df: pd.DataFrame,
        topic: str,
        persona: Optional[str] = None,
    ) -> Optional[str]:
        if len(df) < 2:
            return None

        script = " ".join(
            f'{_C.GPT_NAME}: "{df.iloc[i]["message"]}". '
            f'{_C.GEMINI_NAME}: "{df.iloc[i + 1]["message"]}"'
            for i in range(0, len(df), 2)
        )
        persona_block = (
            "You are NOT a neutral academic judge. You are a real person with the following identity:\n"
            '"{persona}"\n\n'
            "You are watching this debate and forming a personal opinion based on WHO YOU ARE.\n"
            "- Draw on your specific professional knowledge, life experience, and personal values.\n"
            "- Some arguments will resonate with you more than others because of your background.\n"
            "- You are allowed to be biased in ways that reflect your persona naturally.\n"
            "- Your scoring should differ noticeably from a generic judge.\n"
            '- In your description, explicitly mention how your background as "{persona}" shaped your judgment.\n\n'
            if persona
            else ""
        )

        return (
            f"{persona_block}"
            f'We had a debate and the topic was "{topic}". '
            "The two sides each provided arguments to prove their side and refute the opponent. "
            "You are judging this debate. Give a score from 1 to 10 to each side. "
            "Take into account: clarity of arguments, factuality and use of evidence, "
            "rebuttal and counterarguments, logical consistency, persuasiveness and impact, "
            "conciseness, coherence. Also choose the overall winner.\n"
            "Your answer MUST follow this exact format: "
            f'"{_C.GPT_NAME}: [[score]], {_C.GEMINI_NAME}: [[score]], winner: [[name]]. [[description]]".\n\n'
            f"The script of the debate is as follows:\n{script}\n\n"
            "평가 설명은 **한국어**로 작성해주세요. "
            "당신의 페르소나가 평가에 어떤 영향을 미쳤는지 구체적으로 서술하세요."
        )

    def _build_system_prompt(self, persona: Optional[str]) -> str:
        if not persona:
            return "You are a debate judge."

        return (
            f'You are fully embodying this persona: "{persona}". '
            "You are NOT a neutral judge — you are this specific person, "
            "with their career, knowledge, biases, and life experiences. "
            "React to the debate arguments the way this person genuinely would. "
            "Let your professional background drive your scoring. "
            "Do not default to generic balanced evaluations — be authentically this persona."
        )

    def _call_judge(self, prompt: Optional[str], persona: Optional[str] = None) -> str:
        if not prompt:
            return "Not enough valid debate turns to evaluate."

        return self._llm.call(
            messages=[
                {"role": "system", "content": self._build_system_prompt(persona)},
                {"role": "user", "content": prompt},
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

        gpt_turns = df[df["role"] == _C.PROS_ROLE]["message"].tolist()
        gemini_turns = df[df["role"] == _C.CONS_ROLE]["message"].tolist()

        prompt = self._build_judge_prompt(df, topic, persona=persona)
        result: EvalResult = {
            "judge_result": self._call_judge(prompt, persona=persona),
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
        prompt = self._evaluator._build_judge_prompt(df, topic, persona=persona)
        result = self._evaluator._call_judge(prompt, persona=persona)
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

        gpt_turns = df[df["role"] == _C.PROS_ROLE]["message"].tolist()
        gemini_turns = df[df["role"] == _C.CONS_ROLE]["message"].tolist()

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
