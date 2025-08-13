import json
import numpy as np
import pandas as pd
import openai

from typing import List, Dict, Any, Optional, Tuple
from sklearn.feature_extraction.text import CountVectorizer
from bert_score import score as bert_score
from googleapiclient import discovery

from .config import CONFIG as _CONFIG


class DebateEvaluator:
    """
    두 AI 모델 간의 토론 내용을 평가하는 클래스.

    주요 기능:
    1. GPT-4o를 이용한 심판 평가
    2. BERTScore를 이용한 일관성(Coherence) 점수 계산
    3. Distinct-n을 이용한 다양성(Diversity) 지수 계산
    4. Perspective API를 이용한 유해성 분석
    """
    GPT_MODEL = "gpt-4o"
    PROS_ROLE = "pros"
    CONS_ROLE = "cons"
    GPT_NAME = "GPT"
    GEMINI_NAME = "GEMINI"

    def __init__(self):
        """
        DebateEvaluator를 초기화합니다.

        Args:
            api_keys (Dict[str, str]): 'openai'와 'google' API 키를 포함하는 딕셔너리.
        """
        self.openai_client = openai.OpenAI(
            api_key=_CONFIG["openai"]["GPT.API_KEY"]
        )

        self.perspective_client = discovery.build(
            "commentanalyzer",
            "v1alpha1",
            discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",
            static_discovery=False,
            developerKey=_CONFIG["google"]["GCP.API_KEY"]
        )

    def _prepare_dataframe(self, messages: List[Dict[str, Any]]) -> pd.DataFrame:
        """메시지 리스트를 평가에 적합한 DataFrame으로 전처리합니다."""
        df = pd.DataFrame(messages)
        df = df[df["role"].isin([self.PROS_ROLE, self.CONS_ROLE])]
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
        df = df.sort_values("timestamp").reset_index(drop=True)

        # 짝수 개의 턴만 사용하도록 보장
        if len(df) % 2 != 0:
            df = df.iloc[:-1]
        return df

    def _generate_judge_prompt(self, df: pd.DataFrame, topic: str) -> Optional[str]:
        """GPT-4o 심판을 위한 프롬프트를 생성합니다."""
        if len(df) < 2:
            return None

        script_lines = []
        for i in range(0, len(df), 2):
            side1 = df.iloc[i]
            side2 = df.iloc[i + 1]
            script_lines.append(
                f'{self.GPT_NAME}: "{side1["message"]}". {self.GEMINI_NAME}: "{side2["message"]}"'
            )

        debate_script = " ".join(script_lines)

        return f"""
        We had a debate and the topic was "{topic}". The two sides in the debate each provided arguments
        to prove their side and refute the points raised by the opponent. You are a judge for this debate.
        You should be impartial and as objective as possible. The debate script will be given. You should
        give a score from 1 to 10 to each side of the debate. In your judgement, you should take into
        account the following criteria: clarity of arguments, factuality and use of evidence, rebuttal and
        counterarguments, logical consistency, persuasiveness and impact, conciseness, coherence. Also,
        you should choose the side who you think is the overall winner. Your answer MUST follow the
        following format: "{self.GPT_NAME}: [[score of {self.GPT_NAME}]], {self.GEMINI_NAME}: [[score of {self.GEMINI_NAME}]], winner: [[name of winner]]. [[description]]".

        The script of the debate is as follows:
        {debate_script}

        평가는 **한국어**로 작성해주세요.
        """

    def _get_gpt_judgement(self, prompt: str) -> str:
        """GPT-4o 모델을 호출하여 심판 평가를 받습니다."""
        if not prompt:
            return "Not enough valid debate turns to evaluate."

        try:
            response = self.openai_client.responses.create(
                model=self.GPT_MODEL,
                input=[
                    {"role": "system", "content": "You are a debate judge."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            return response.output_text
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return "Failed to get judgement from GPT-4o."

    def _calculate_coherence_score(self, turns: List[str]) -> float:
        """Leave-One-Out BERTScore를 사용하여 일관성 점수를 계산합니다."""
        if len(turns) < 2:
            return 0.0

        scores = []
        for i in range(len(turns)):
            target = turns[i]
            others = turns[:i] + turns[i+1:]
            _, _, f1_scores = bert_score(
                [target] * len(others), others, lang="ko", verbose=False)
            scores.append(float(f1_scores.mean()))

        return float(np.mean(scores))

    def _calculate_diversity_index(self, turns: List[str], n: int = 2) -> float:
        """Leave-One-Out Distinct-n을 사용하여 다양성 지수를 계산합니다."""
        if len(turns) < 1:
            return 0.0

        analyzer = CountVectorizer(
            analyzer='word', ngram_range=(n, n)).build_analyzer()
        all_ngrams = [set(analyzer(t)) for t in turns]

        distinct_ratios = []
        for i, current_ngrams in enumerate(all_ngrams):
            if not current_ngrams:
                distinct_ratios.append(0.0)
                continue

            other_ngrams_union = set().union(
                *[all_ngrams[j] for j in range(len(all_ngrams)) if i != j])
            distinct_ngrams = current_ngrams - other_ngrams_union
            distinct_ratios.append(len(distinct_ngrams) / len(current_ngrams))

        return float(np.mean(distinct_ratios))

    def get_perspective_analysis(self, text: str) -> Optional[Dict[str, Any]]:
        """Google Perspective API를 사용하여 텍스트의 유해성을 분석합니다."""

        try:
            analyze_request = {
                'comment': {'text': text},
                'requestedAttributes': {'TOXICITY': {}}
            }
            return self.perspective_client.comments().analyze(body=analyze_request).execute()
        except Exception as e:
            print(f"Error calling Perspective API: {e}")
            return None

    def evaluate(self, messages: List[Dict[str, Any]], topic: str = "NFT는 예술의 미래인가?") -> Dict[str, Any]:
        """
        토론 메시지 전체에 대한 평가를 수행합니다.

        Args:
            messages (List[Dict[str, Any]]): 평가할 토론 메시지 리스트.
            topic (str): 토론 주제.

        Returns:
            Dict[str, Any]: 심판 평가, 일관성, 다양성 점수를 포함하는 평가 결과.
        """
        df = self._prepare_dataframe(messages)

        if df.empty:
            return {
                "judge_result": "No valid turns to evaluate.",
                "coherence": {"gpt": 0.0, "gemini": 0.0},
                "diversity": {"gpt": 0.0, "gemini": 0.0}
            }

        gpt_turns = df[df["role"] == self.PROS_ROLE]["message"].tolist()
        gemini_turns = df[df["role"] == self.CONS_ROLE]["message"].tolist()

        prompt = self._generate_judge_prompt(df, topic)
        judge_result = self._get_gpt_judgement(prompt)

        coherence_gpt = self._calculate_coherence_score(gpt_turns)
        coherence_gemini = self._calculate_coherence_score(gemini_turns)

        diversity_gpt = self._calculate_diversity_index(gpt_turns)
        diversity_gemini = self._calculate_diversity_index(gemini_turns)

        return {
            "judge_result": judge_result,
            "coherence": {"gpt": round(coherence_gpt, 4), "gemini": round(coherence_gemini, 4)},
            "diversity": {"gpt": round(diversity_gpt, 4), "gemini": round(diversity_gemini, 4)}
        }


if __name__ == '__main__':
    evaluator = DebateEvaluator()

    # 토론 기록 파일 로드 (예시)
    try:
        with open("./debate-history-1754391739291.json", "r", encoding="utf-8") as f:
            debate_data = json.load(f)

        # 평가 실행
        evaluation_result = evaluator.evaluate(
            debate_data, topic="AI는 인류에게 위협이 될 것인가?")
        print(json.dumps(evaluation_result, ensure_ascii=False, indent=2))

        # 유해성 분석 예시
        sample_text = "이것은 유해성 분석을 위한 샘플 텍스트입니다."
        perspective_result = evaluator.get_perspective_analysis(sample_text)
        if perspective_result:
            print("\nPerspective API Analysis:")
            print(json.dumps(perspective_result, indent=2))

    except FileNotFoundError:
        print("Error: The debate history file was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
