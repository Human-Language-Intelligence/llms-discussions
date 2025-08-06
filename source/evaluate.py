import json
import pandas as pd
import openai
from bert_score import score as bert_score
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np
from .config import CONFIG as _CONFIG

# OpenAI API Key 설정
client = openai.OpenAI(
    api_key=_CONFIG["openai"]["GPT.API_KEY"]
)

# ⚖ GPT Judge Prompt 생성
def get_judge_prompt(df, topic="NFT는 예술의 미래인가?"):
    script_lines = []
    for i in range(0, len(df), 2):
        side1 = df.iloc[i]
        side2 = df.iloc[i + 1]
        script_lines.append(
            f'GPT: “{side1["message"]}”. GEMINI: “{side2["message"]}”'
        )
    debate_script = " ".join(script_lines)

    return f"""We had a debate and the topic was “{topic}”. The two sides in the debate each provided arguments
    to prove their side and refute the points raised by the opponent. You are a judge for this debate.
    You should be impartial and as objective as possible. The debate script will be given. You should
    give a score from 1 to 10 to each side of the debate. In your judgement, you should take into
    account the following criteria: clarity of arguments, factuality and use of evidence, rebuttal and
    counterarguments, logical consistency, persuasiveness and impact, conciseness, coherence. Also,
    you should choose the side who you think is the overall winner. Your answer MUST follow the
    following format: "GPT: [[score of GPT]], GEMINI: [[score of GEMINI]], winner: [[name of winner]]"

    The script of the debate is as follows: {debate_script}
    """

# 💬 GPT-4o 평가 호출
def gpt_judge(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a debate judge."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content

# Coherence Flow Score (BERTScore)
def coherence_score(turns):
    scores = []
    for i in range(len(turns)):
        target = turns[i]
        others = turns[:i] + turns[i+1:]
        # 다른 모든 발화와 각각 비교 후 평균
        _, _, F1 = bert_score([target]*len(others), others, lang="ko", verbose=False)
        scores.append(float(F1.mean()))
    return np.mean(scores)

# Argument Diversity (Distinct-n)
def diversity_index(turns, n=2):
    vectorizer = CountVectorizer(analyzer='word', ngram_range=(n, n))
    all_ngrams = [set(ngram for ngram in vectorizer.build_analyzer()(t)) for t in turns]
    
    distinct_ratios = []
    for i, current in enumerate(all_ngrams):
        other_ngrams = set().union(*[all_ngrams[j] for j in range(len(turns)) if j != i])
        # 얼마나 다른 n-gram으로 구성되었는지
        distinct = current - other_ngrams
        ratio = len(distinct) / len(current) if len(current) > 0 else 0
        distinct_ratios.append(ratio)

    return np.mean(distinct_ratios)

if __name__ == "__main__":
    # JSON 파일 경로
    file_path = "./debate-history-1754391739291.json"

    # 데이터 불러오기 및 정제
    with open(file_path, "r", encoding="utf-8") as f:
        debate_data = json.load(f)

    df = pd.DataFrame(debate_data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # 짝 맞는 발화만 사용 (짝수 개만)
    usable_df = df.iloc[:len(df) - len(df) % 2].copy()

    # GPT(GPT) / GEMINI 분리
    gpt_turns = usable_df[usable_df["role"] == "pros"]["message"].tolist()
    gemini_turns = usable_df[usable_df["role"] == "cons"]["message"].tolist()

    # 평가 실행
    prompt = get_judge_prompt(usable_df)
    judge_result = gpt_judge(prompt)

    coherence_gpt = coherence_score(gpt_turns)
    coherence_gemini = coherence_score(gemini_turns)

    diversity_gpt = diversity_index(gpt_turns)
    diversity_gemini = diversity_index(gemini_turns)

    # 결과 출력
    print("[LLM Judge] GPT Judge 평가 결과:")
    print(judge_result)
    print()
    print(f"[Coherence Flow Score] GPT: {coherence_gpt:.4f}, GEMINI: {coherence_gemini:.4f}")
    print(f"[Argument Diversity Index] GPT: {diversity_gpt:.4f}, GEMINI: {diversity_gemini:.4f}")
