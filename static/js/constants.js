// constants.js (별도의 파일로 분리하여 모듈화 가능)
export const DEBATE_ROLES = {
    PROS: 'pros',
    CONS: 'cons',
    USER: 'user',
    ADMIN: 'admin',
};

export const AVATARS = {
    GPT: './static/ChatGPT.png',
    GEMINI: './static/Gemini.png',
    USER: './static/User.png',
};

// 역할에 따른 표시 라벨
export const ROLE_LABELS = {
    [DEBATE_ROLES.PROS]: '찬성',
    [DEBATE_ROLES.CONS]: '반대',
    [DEBATE_ROLES.USER]: '사용자',
    [DEBATE_ROLES.ADMIN]: '관리자',
};
