import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    def _generate_judge_prompt(
        self,
        df: pd.DataFrame,
        topic: str,
        persona: Optional[str] = None
    ) -> Optional[str]:
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

        if persona:
            persona_instruction = f"""You are NOT a neutral academic judge. You are a real person with the following identity:
"{persona}"

You are watching this debate and forming a personal opinion based on WHO YOU ARE.
- Draw on your specific professional knowledge, life experience, and personal values.
- Some arguments will resonate with you more than others because of your background.
- You are allowed to be biased in ways that reflect your persona naturally.
- Your scoring should differ noticeably from a generic judge — your persona MUST influence which side you find more convincing and why.
- In your description, explicitly mention how your background as "{persona}" shaped your judgment.

"""
        else:
            persona_instruction = ""

        return f"""
        {persona_instruction}We had a debate and the topic was "{topic}". The two sides in the debate each provided arguments
        to prove their side and refute the points raised by the opponent. You are judging this debate.
        Give a score from 1 to 10 to each side. Take into account:
        clarity of arguments, factuality and use of evidence, rebuttal and counterarguments,
        logical consistency, persuasiveness and impact, conciseness, coherence.
        Also choose the overall winner. Your answer MUST follow this exact format:
        "{self.GPT_NAME}: [[score]], {self.GEMINI_NAME}: [[score]], winner: [[name]]. [[description]]".

        The script of the debate is as follows:
        {debate_script}

        평가 설명은 **한국어**로 작성해주세요. 당신의 페르소나가 평가에 어떤 영향을 미쳤는지 구체적으로 서술하세요.
        """

    def _get_gpt_judgement(self, prompt: str, persona: Optional[str] = None) -> str:
        """GPT-4o 모델을 호출하여 심판 평가를 받습니다."""
        if not prompt:
            return "Not enough valid debate turns to evaluate."

        system_content = "You are a debate judge."
        if persona:
            system_content = (
                f'You are fully embodying this persona: "{persona}". '
                f'You are NOT a neutral judge — you are this specific person, '
                f'with their career, knowledge, biases, and life experiences. '
                f'React to the debate arguments the way this person genuinely would. '
                f'Let your professional background drive your scoring. '
                f'Do not default to generic balanced evaluations — be authentically this persona.'
            )

        try:
            response = self.openai_client.responses.create(
                model=self.GPT_MODEL,
                input=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
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

    def evaluate(
        self,
        messages: List[Dict[str, Any]],
        topic: str = "NFT는 예술의 미래인가?",
        persona: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        토론 메시지 전체에 대한 평가를 수행합니다.

        Args:
            messages (List[Dict[str, Any]]): 평가할 토론 메시지 리스트.
            topic (str): 토론 주제.
            persona (Optional[str]): 평가 페르소나. None이면 중립 평가.

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

        prompt = self._generate_judge_prompt(df, topic, persona=persona)
        judge_result = self._get_gpt_judgement(prompt, persona=persona)

        coherence_gpt = self._calculate_coherence_score(gpt_turns)
        coherence_gemini = self._calculate_coherence_score(gemini_turns)

        diversity_gpt = self._calculate_diversity_index(gpt_turns)
        diversity_gemini = self._calculate_diversity_index(gemini_turns)

        return {
            "judge_result": judge_result,
            "coherence": {"gpt": round(coherence_gpt, 4), "gemini": round(coherence_gemini, 4)},
            "diversity": {"gpt": round(diversity_gpt, 4), "gemini": round(diversity_gemini, 4)}
        }


class PersonaDebateEvaluator:
    """
    filtered_persona.jsonl에서 무작위로 추출한 페르소나들을 이용해
    토론을 다각도로 평가하는 클래스.

    주요 기능:
    - JSONL 파일에서 N개의 페르소나를 랜덤 샘플링
    - 각 페르소나 관점에서 DebateEvaluator.evaluate() 호출
    - 전체 결과 및 종합 통계 반환
    """

    def __init__(self, persona_jsonl_path: str, num_agents: int = 10):
        """
        Args:
            persona_jsonl_path (str): filtered_persona.jsonl 파일 경로.
            num_agents (int): 사용할 페르소나 에이전트 수 (기본 10).
        """
        self.persona_jsonl_path = persona_jsonl_path
        self.num_agents = num_agents
        self.evaluator = DebateEvaluator()

    def _load_random_personas(self) -> List[str]:
        """JSONL 파일에서 num_agents개의 페르소나를 랜덤 샘플링합니다."""
        personas = []
        with open(self.persona_jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    persona_str = obj.get("persona", "")
                    if persona_str:
                        personas.append(persona_str)
                except json.JSONDecodeError:
                    continue

        if len(personas) < self.num_agents:
            raise ValueError(
                f"페르소나 수({len(personas)})가 요청한 에이전트 수({self.num_agents})보다 적습니다."
            )

        return random.sample(personas, self.num_agents)

    def _translate_personas(self, personas: List[str]) -> List[str]:
        """페르소나 목록을 한 번의 API 호출로 일괄 한국어 번역합니다."""
        numbered = "\n".join(f"{i+1}. {p}" for i, p in enumerate(personas))
        prompt = (
            f"아래 {len(personas)}개의 영어 페르소나 설명을 한국어로 번역해주세요.\n"
            f"반드시 번호와 함께 각 줄에 하나씩만 출력하고, 번호와 번역문 외에 다른 내용은 쓰지 마세요.\n\n"
            f"{numbered}"
        )
        try:
            response = self.evaluator.openai_client.chat.completions.create(
                model=DebateEvaluator.GPT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            lines = response.choices[0].message.content.strip().splitlines()
            translated = []
            for line in lines:
                # "1. 번역문" 형식에서 번역문만 추출
                line = line.strip()
                if line and line[0].isdigit():
                    parts = line.split(".", 1)
                    translated.append(parts[1].strip() if len(parts) > 1 else line)
                elif line:
                    translated.append(line)
            # 번역 결과 수가 맞지 않으면 원문 사용
            if len(translated) != len(personas):
                return personas
            return translated
        except Exception as e:
            print(f"번역 실패, 원문 사용: {e}")
            return personas

    def _compute_aggregate(self, agent_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        10개 에이전트 결과를 종합하여 평균/분포 통계를 계산합니다.

        Returns:
            Dict with keys: avg_coherence, avg_diversity, winner_tally,
                            avg_judge_score, score_distribution
        """
        header_re = (
            r'GPT\s*:\s*\[{0,2}(\d+(?:\.\d+)?)\]{0,2}\s*[,;]?\s*'
            r'GEMINI\s*:\s*\[{0,2}(\d+(?:\.\d+)?)\]{0,2}\s*[,;]?\s*'
            r'winner\s*:\s*\[{0,2}([\w가-힣]+)\]{0,2}'
        )
        import re

        gpt_scores, gemini_scores = [], []
        coh_gpt_list, coh_gem_list = [], []
        div_gpt_list, div_gem_list = [], []
        winner_tally = {"GPT": 0, "GEMINI": 0, "무승부": 0}

        for r in agent_results:
            # Judge 점수 파싱
            m = re.search(header_re, r["judge_result"], re.IGNORECASE)
            if m:
                gpt_scores.append(float(m.group(1)))
                gemini_scores.append(float(m.group(2)))
                winner = m.group(3).upper()
                if winner in winner_tally:
                    winner_tally[winner] += 1
                else:
                    winner_tally["무승부"] += 1

            coh_gpt_list.append(r["coherence"]["gpt"])
            coh_gem_list.append(r["coherence"]["gemini"])
            div_gpt_list.append(r["diversity"]["gpt"])
            div_gem_list.append(r["diversity"]["gemini"])

        def safe_mean(lst):
            return round(float(np.mean(lst)), 4) if lst else 0.0

        def safe_std(lst):
            return round(float(np.std(lst)), 4) if lst else 0.0

        return {
            "judge_score": {
                "gpt":    {"mean": safe_mean(gpt_scores),    "std": safe_std(gpt_scores)},
                "gemini": {"mean": safe_mean(gemini_scores), "std": safe_std(gemini_scores)},
            },
            "coherence": {
                "gpt":    {"mean": safe_mean(coh_gpt_list),  "std": safe_std(coh_gpt_list)},
                "gemini": {"mean": safe_mean(coh_gem_list),  "std": safe_std(coh_gem_list)},
            },
            "diversity": {
                "gpt":    {"mean": safe_mean(div_gpt_list),  "std": safe_std(div_gpt_list)},
                "gemini": {"mean": safe_mean(div_gem_list),  "std": safe_std(div_gem_list)},
            },
            "winner_tally": winner_tally,
            "total_agents": len(agent_results),
        }

    def evaluate_with_personas(
        self,
        messages: List[Dict[str, Any]],
        topic: str = "NFT는 예술의 미래인가?"
    ) -> Dict[str, Any]:
        """
        10개의 랜덤 페르소나 에이전트로 토론을 평가합니다.
 
        Args:
            messages: 평가할 토론 메시지 리스트.
            topic: 토론 주제.
 
        Returns:
            {
              "agents": [
                {
                  "agent_index": 1,
                  "persona": "...",
                  "result": { judge_result, coherence, diversity }
                },
                ...
              ],
              "aggregate": { judge_score, coherence, diversity, winner_tally, total_agents }
            }
        """
        personas = self._load_random_personas()
 
        # BERTScore/Diversity는 thread-safe하지 않으므로 메인 스레드에서 한 번만 계산
        df = self.evaluator._prepare_dataframe(messages)
        gpt_turns = df[df["role"] == self.evaluator.PROS_ROLE]["message"].tolist()
        gemini_turns = df[df["role"] == self.evaluator.CONS_ROLE]["message"].tolist()
 
        print("[공통 지표 계산 중] Coherence / Diversity...")
        coherence_gpt    = self.evaluator._calculate_coherence_score(gpt_turns)
        coherence_gemini = self.evaluator._calculate_coherence_score(gemini_turns)
        diversity_gpt    = self.evaluator._calculate_diversity_index(gpt_turns)
        diversity_gemini = self.evaluator._calculate_diversity_index(gemini_turns)
        shared_metrics = {
            "coherence": {"gpt": round(coherence_gpt, 4), "gemini": round(coherence_gemini, 4)},
            "diversity": {"gpt": round(diversity_gpt, 4), "gemini": round(diversity_gemini, 4)},
        }
 
        # LLM judge 호출만 병렬화 (API I/O bound → thread-safe)
        def _judge_one(args):
            idx, persona = args
            print(f"[{idx}/{self.num_agents}] 페르소나 평가 중: {persona[:60]}...")
            prompt = self.evaluator._generate_judge_prompt(df, topic, persona=persona)
            judge_result = self.evaluator._get_gpt_judgement(prompt, persona=persona)
            print(f"[{idx}/{self.num_agents}] 완료")
            return idx, persona, judge_result
 
        print("[병렬 실행 시작] 번역 + LLM Judge 평가...")
        with ThreadPoolExecutor(max_workers=self.num_agents + 1) as executor:
            translate_future = executor.submit(self._translate_personas, personas)
            judge_futures = {
                executor.submit(_judge_one, (idx, persona)): idx
                for idx, persona in enumerate(personas, start=1)
            }
 
            raw_results = {}
            for future in as_completed(judge_futures):
                idx, persona, judge_result = future.result()
                raw_results[idx] = (persona, judge_result)
 
            personas_ko = translate_future.result()
 
        # agent_index 순서로 정렬
        agent_results = [
            {
                "agent_index": idx,
                "persona": raw_results[idx][0],
                "persona_ko": personas_ko[idx - 1],
                "result": {
                    "judge_result": raw_results[idx][1],
                    **shared_metrics,
                },
            }
            for idx in sorted(raw_results)
        ]
 
        aggregate = self._compute_aggregate([a["result"] for a in agent_results])
 
        return {
            "agents": agent_results,
            "aggregate": aggregate,
        }
 


if __name__ == '__main__':
    # 페르소나 기반 평가 실행 예시
    try:
        with open("./debate-history-1754391739291.json", "r", encoding="utf-8") as f:
            debate_data = json.load(f)

        persona_evaluator = PersonaDebateEvaluator(
            persona_jsonl_path="./filtered_persona.jsonl",
            num_agents=10
        )

        full_result = persona_evaluator.evaluate_with_personas(
            debate_data,
            topic="AI는 인류에게 위협이 될 것인가?"
        )

        print(json.dumps(full_result, ensure_ascii=False, indent=2))

    except FileNotFoundError:
        print("Error: 필요한 파일을 찾을 수 없습니다.")
    except Exception as e:
        print(f"An error occurred: {e}")