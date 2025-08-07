import json
import pandas as pd
import openai
from bert_score import score as bert_score
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np
from datetime import datetime
from .config import CONFIG as _CONFIG

# OpenAI API Key 설정
client = openai.OpenAI(
    api_key=_CONFIG["openai"]["GPT.API_KEY"]
)

# GPT Judge Prompt 생성
def get_judge_prompt(df, topic="NFT는 예술의 미래인가?"):
    # Ensure even number of debate points
    df2 = df.copy()
    if len(df2) % 2 != 0:
        df2 = df2.iloc[:-1]
    # If too few turns, return empty prompt
    if len(df2) < 2:
        return None

    script_lines = []
    for i in range(0, len(df2), 2):
        side1 = df2.iloc[i]
        side2 = df2.iloc[i + 1]
        script_lines.append(
            f'GPT: “{side1["message"]}”. GEMINI: “{side2["message"]}”'
        )
    print(script_lines)
    debate_script = " ".join(script_lines)

    return f"""We had a debate and the topic was “{topic}”. The two sides in the debate each provided arguments
    to prove their side and refute the points raised by the opponent. You are a judge for this debate.
    You should be impartial and as objective as possible. The debate script will be given. You should
    give a score from 1 to 10 to each side of the debate. In your judgement, you should take into
    account the following criteria: clarity of arguments, factuality and use of evidence, rebuttal and
    counterarguments, logical consistency, persuasiveness and impact, conciseness, coherence. Also,
    you should choose the side who you think is the overall winner. Your answer MUST follow the
    following format: "GPT: [[score of GPT]], GEMINI: [[score of GEMINI]], winner: [[name of winner]] (at next line) [[description]]".

    The script of the debate is as follows:
    {debate_script}

    평가는 **한국어**로 작성해주세요.
    """

# GPT-4o 평가 호출
def gpt_judge(prompt):
    if not prompt:
        return "Not enough valid debate turns to evaluate."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a debate judge."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content

# Coherence Flow Score (Leave-One-Out BERTScore)
def coherence_score(turns):
    if len(turns) < 2:
        return 0.0
    scores = []
    for i in range(len(turns)):
        target = turns[i]
        others = turns[:i] + turns[i+1:]
        _, _, F1 = bert_score([target]*len(others), others, lang="ko", verbose=False)
        scores.append(float(F1.mean()))
    return float(np.mean(scores))

# Argument Diversity (Leave-One-Out Distinct-n)
def diversity_index(turns, n=2):
    if len(turns) < 1:
        return 0.0
    analyzer = CountVectorizer(analyzer='word', ngram_range=(n, n)).build_analyzer()
    all_ngrams = [set(analyzer(t)) for t in turns]
    distinct_ratios = []
    for i, current in enumerate(all_ngrams):
        others_union = set().union(*[all_ngrams[j] for j in range(len(turns)) if j != i])
        if not current:
            distinct_ratios.append(0.0)
        else:
            distinct = current - others_union
            distinct_ratios.append(len(distinct) / len(current))
    return float(np.mean(distinct_ratios))

# 메시지 리스트로부터 전체 평가 수행
def evaluate_from_messages(messages, topic="NFT는 예술의 미래인가?"):
    df = pd.DataFrame(messages)
    df = df[df["role"].isin(["pros", "cons"])]
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
    df = df.sort_values("timestamp").reset_index(drop=True)
    # Keep even number of turns
    usable_df = df.iloc[:len(df) - len(df) % 2].copy()

    # Extract turns per side
    gpt_turns = usable_df[usable_df["role"] == "pros"]["message"].tolist()
    gemini_turns = usable_df[usable_df["role"] == "cons"]["message"].tolist()

    print(gpt_turns)
    print(gemini_turns)

    # Generate prompt and judge
    prompt = get_judge_prompt(usable_df, topic)
    judge_result = gpt_judge(prompt)

    # Compute metrics
    coherence_gpt = coherence_score(gpt_turns)
    coherence_gemini = coherence_score(gemini_turns)
    diversity_gpt = diversity_index(gpt_turns)
    diversity_gemini = diversity_index(gemini_turns)

    return {
        "judge_result": judge_result,
        "coherence": {"gpt": round(coherence_gpt, 4), "gemini": round(coherence_gemini, 4)},
        "diversity": {"gpt": round(diversity_gpt, 4), "gemini": round(diversity_gemini, 4)}
    }

if __name__ == "__main__":
    file_path = "./debate-history-1754391739291.json"
    with open(file_path, "r", encoding="utf-8") as f:
        debate_data = json.load(f)
    result = evaluate_from_messages(debate_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
