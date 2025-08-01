// utils.js (별도의 파일로 분리하여 모듈화 가능)
import { DEBATE_ROLES, AVATARS, ROLE_LABELS } from './constants.js';

export const getRoleLabel = (role) => {
    return ROLE_LABELS[role] || role;
};

// 역할과 이름에 따라 아바타 경로를 결정하는 함수
export const getAvatarPath = (name, role) => {
    if (role === DEBATE_ROLES.ADMIN) return '';
    if (name === 'gpt') return AVATARS.GPT;
    if (name === 'gemini') return AVATARS.GEMINI;
    return AVATARS.USER;
};

// 역할에 따라 메시지 클래스를 결정하는 함수
export const getUserClass = (messageRole, user1Role) => {
    if (messageRole === DEBATE_ROLES.ADMIN) return 'admin';
    return (messageRole === user1Role) ? 'user1' : 'user2';
};

// 메시지 헤더(프로필) HTML을 생성하는 함수
export const createProfileBlock = (name, role) => {
    const isLLM = [DEBATE_ROLES.PROS, DEBATE_ROLES.CONS].includes(role);
    const avatar = isLLM ? getAvatarPath(name, role) : AVATARS.USER;
    const roleLabel = ROLE_LABELS[role] || role;

    return `
    <div class="message-header">
      <img src="${avatar}" alt="${name}" class="speaker-avatar">
      <div class="speaker-info">
        <h3 class="speaker-name">${name.toUpperCase()}</h3>
        <span class="speaker-role">${roleLabel}</span>
      </div>
    </div>
  `;
};
