# llms-discussions

## Install requirements

``` shell
uv venv .venv
source .venv/bin/activate
```

```shell
uv sync
```

## Config

```ini
[default]
TOPIC = [
        "AI가 인간 창의성을 완전히 재현할 수 있는가?",
        "양자컴퓨팅은 국가 안보에 위협이 될까?",
        "유전자 편집은 인류 진화를 가속화할까?",
        "우주 채굴은 지구 경제에 긍정적인가?",
        "메타버스가 현실 사회를 대체할 수 있을까?",
        "보편 기본소득은 경제 불평등을 줄일 수 있는가?",
        "표현의 자유는 어디까지 허용되어야 하는가?",
        "국경 없는 세상은 가능한가?",
        "감시 사회는 범죄 예방에 효과적인가?",
        "선거는 온라인으로만 진행해도 되는가?",
        "크립토화폐가 법정화폐를 대체할 수 있을까?",
        "대기업 해체는 시장 경쟁을 촉진하는가?",
        "재택근무는 장기적으로 생산성을 높일까?",
        "관광산업은 환경보다 우선되어야 하는가?",
        "인공지능 세금은 필요한가?",
        "예술은 창작자의 의도가 중요할까, 감상자의 해석이 중요할까?",
        "행복은 개인의 선택인가, 환경의 결과인가?",
        "박물관의 유물 반환은 의무인가 선택인가?",
        "고전 문학은 현대 교육에서 필수적인가?",
        "죽음의 권리는 개인이 선택할 수 있어야 하는가?",
        "기후 위기 대응, 원자력 발전은 필수적인가?",
        "탄소세 도입은 기업의 성장을 저해하는가?",
        "지속 가능한 삶을 위해 육식은 금지되어야 하는가?",
        "개인의 환경보호 노력은 실질적인 효과가 있는가, 아니면 정부와 기업의 책임이 우선인가?",
        "친환경 제품에 대한 추가 비용은 소비자가 감수해야 하는가?",
        "모든 학생에게 코딩 교육은 의무화되어야 하는가?",
        "대학은 취업을 위한 기관인가, 학문 탐구를 위한 공간인가?",
        "상대평가는 학생들의 건전한 경쟁을 유도하는가?",
        "역사 교육에서 '긍정적 서사'와 '비판적 서사' 중 무엇을 더 강조해야 하는가?",
        "조기 교육은 아동의 장기적인 발달에 긍정적인가?",
        "연인 간의 '선톡'(먼저 연락하는 것)은 관계의 호감도를 나타내는 척도인가?",
        "부모가 자녀의 사진을 SNS에 올리는 '셰어런팅(Sharenting)'은 정당한가?",
        "직장에서의 '사적인' 대화는 어디까지 허용될 수 있는가?",
        "연애를 끝낼 때, 잠수 이별(고스팅)은 최악의 방식인가?",
        "팁(Tip) 문화는 국내에도 도입되어야 하는가?",
        "사회 발전에 더 중요한 것은 '결과의 평등'인가, '기회의 평등'인가?",
        "개인의 성공에 더 중요한 것은 '타고난 재능'인가, '끊임없는 노력'인가?",
        "더 나은 사회를 위해 우선시해야 할 가치는 '개인의 자유'인가, '공동체의 안정'인가?",
        "도시 개발에서 '경제적 발전'과 '역사적 보존' 중 무엇이 우선되어야 하는가?",
        "위대한 예술가의 '작품'과 그의 '비도덕적인 사생활'은 분리해서 평가해야 하는가?",
        "특정 과학 기술(예: 인터넷)이 더 일찍 발명되었다면 인류는 더 행복해졌을까?",
        "역사 속의 논쟁적인 조약/결정은 당시로서 최선의 선택이었나?"
    ]
HISTORY.POSITIVE = You are a SKILLED DEBATER arguing FOR the given topic. Respond in Korean, using 2-4 sentences of plain text in a conversational debate style. Avoid simply repeating previous points. Each new turn should deepen, expand, or add specific details to earlier arguments. Support your argument with one of the following: a brief and compelling real-world example, a statistic from a credible source, or a logical analogy.
HISTORY.NEGATIVE = You are a SKILLED DEBATER arguing AGAINST the given topic. Respond in Korean, using 2-4 sentences of plain text in a conversational debate style. Avoid simply repeating previous points. Each new turn should deepen, expand, or add specific details to earlier arguments. Support your counterargument with one of the following: a brief and compelling real-world example, a statistic from a credible source, or a logical analogy.

[flask]
SECRET_KEY = @@@

[openai]
GPT.API_KEY = @@@
GPT.MODEL_NAME = gpt-5-nano

[google]
CREDENTIALS = @@@.json
GCP.API_KEY = @@@
GCP.PROJECT_ID = @@@
GCP.LOCATION = us-west1
GEMINI.MODEL_NAME = gemini-2.5-flash-lite
```

You need to generate "config.ini" file, and replace the `@@@` placeholder in the "config.ini" file with the appropriate value. Before that, you must create credential keys for both GCP and OpenAI.
- [GCP Service Accouunt credentials](https://cloud.google.com/iam/docs/keys-create-delete)
- [OpenAI API key](https://platform.openai.com/settings/organization/api-keys)

## Run flask app

```shell
flask run --debug
```
