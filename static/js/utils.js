// utils.js - 토론 앱 유틸리티 함수들
import { DEBATE_ROLES, AVATARS, ROLE_LABELS } from './constants.js';

/**
 * 역할에 따른 표시 라벨을 반환
 * @param {string} role - 사용자 역할
 * @returns {string} 한글 라벨
 */
export const getRoleLabel = (role) => {
  return ROLE_LABELS[role] || role;
};

/**
 * 이름과 역할에 따라 아바타 경로를 결정
 * @param {string} name - 사용자/AI 이름
 * @param {string} role - 사용자 역할
 * @returns {string} 아바타 이미지 경로
 */
export const getAvatarPath = (name, role) => {
  // 관리자는 아바타 없음
  if (role === DEBATE_ROLES.ADMIN) return '';

  // AI 모델별 아바타
  const lowerName = name.toLowerCase();
  if (lowerName.includes('gpt') || lowerName === 'chatgpt') {
    return AVATARS.GPT;
  }
  if (lowerName.includes('gemini')) {
    return AVATARS.GEMINI;
  }

  // 기본 사용자 아바타
  return AVATARS.USER;
};

/**
 * 메시지 역할에 따라 CSS 클래스를 결정
 * @param {string} messageRole - 메시지 작성자 역할
 * @param {string} user1Role - 첫 번째 사용자(찬성측) 역할
 * @returns {string} CSS 클래스명
 */
export const getUserClass = (messageRole, user1Role) => {
  if (messageRole === DEBATE_ROLES.ADMIN) return 'admin';
  if (messageRole === DEBATE_ROLES.USER) return 'user';

  // 토론자의 경우 찬성/반대 구분
  return (messageRole === user1Role) ? 'user1' : 'user2';
};

/**
 * 메시지 헤더(프로필) HTML을 생성
 * @param {string} name - 사용자/AI 이름
 * @param {string} role - 사용자 역할
 * @returns {string} HTML 문자열
 */
export const createProfileBlock = (name, role) => {
  const avatar = getAvatarPath(name, role);
  const roleLabel = getRoleLabel(role);

  // 관리자 메시지의 경우 간단한 형태
  if (role === DEBATE_ROLES.ADMIN) {
    return `
            <div class="message-header admin-header">
                <div class="admin-badge">관리자</div>
            </div>
        `;
  }

  return `
        <div class="message-header">
            <img src="${avatar}" alt="${name}" class="speaker-avatar" loading="lazy">
            <div class="speaker-info">
                <h3 class="speaker-name">${name.toUpperCase()}</h3>
                <span class="speaker-role">${roleLabel}</span>
            </div>
        </div>
    `;
};

/**
 * 메시지 타임스탬프를 포맷팅
 * @param {Date|string} timestamp - 타임스탬프
 * @returns {string} 포맷된 시간 문자열
 */
export const formatTimestamp = (timestamp) => {
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);

  if (isNaN(date.getTime())) {
    return new Date().toLocaleString('ko-KR');
  }

  const now = new Date();
  const diff = now - date;

  // 1분 미만
  if (diff < 60000) {
    return '방금 전';
  }

  // 1시간 미만
  if (diff < 3600000) {
    const minutes = Math.floor(diff / 60000);
    return `${minutes}분 전`;
  }

  // 24시간 미만
  if (diff < 86400000) {
    const hours = Math.floor(diff / 3600000);
    return `${hours}시간 전`;
  }

  // 그 외는 전체 날짜
  return date.toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};

/**
 * 메시지 텍스트를 안전하게 HTML로 변환
 * @param {string} text - 원본 텍스트
 * @returns {string} HTML 안전 텍스트
 */
export const sanitizeMessage = (text) => {
  if (!text) return '';

  // HTML 특수문자 이스케이프
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');

  // 줄바꿈을 <br>로 변환
  return escaped.replace(/\n/g, '<br>');
};

/**
 * 역할에 따른 테마 색상을 반환
 * @param {string} role - 사용자 역할
 * @returns {object} 색상 객체
 */
export const getRoleColors = (role) => {
  const colors = {
    [DEBATE_ROLES.PROS]: {
      primary: 'var(--success-500)',
      light: 'var(--success-100)',
      gradient: 'var(--gradient-success)'
    },
    [DEBATE_ROLES.CONS]: {
      primary: 'var(--error-500)',
      light: 'var(--error-100)',
      gradient: 'var(--gradient-error)'
    },
    [DEBATE_ROLES.USER]: {
      primary: 'var(--primary-500)',
      light: 'var(--primary-100)',
      gradient: 'var(--gradient-primary)'
    },
    [DEBATE_ROLES.ADMIN]: {
      primary: 'var(--gray-500)',
      light: 'var(--gray-100)',
      gradient: 'linear-gradient(135deg, var(--gray-500), var(--gray-600))'
    }
  };

  return colors[role] || colors[DEBATE_ROLES.USER];
};

/**
 * 디바운스 함수
 * @param {Function} func - 실행할 함수
 * @param {number} wait - 대기 시간 (ms)
 * @returns {Function} 디바운스된 함수
 */
export const debounce = (func, wait) => {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
};

/**
 * 스로틀 함수
 * @param {Function} func - 실행할 함수
 * @param {number} limit - 제한 시간 (ms)
 * @returns {Function} 스로틀된 함수
 */
export const throttle = (func, limit) => {
  let inThrottle;
  return function (...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
};

/**
 * 로컬 스토리지 헬퍼 함수들
 */
export const storage = {
  /**
   * 데이터를 로컬 스토리지에 저장
   * @param {string} key - 키
   * @param {any} value - 저장할 값
   */
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.warn('로컬 스토리지 저장 실패:', error);
    }
  },

  /**
   * 로컬 스토리지에서 데이터 가져오기
   * @param {string} key - 키
   * @param {any} defaultValue - 기본값
   * @returns {any} 저장된 값 또는 기본값
   */
  get(key, defaultValue = null) {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : defaultValue;
    } catch (error) {
      console.warn('로컬 스토리지 읽기 실패:', error);
      return defaultValue;
    }
  },

  /**
   * 로컬 스토리지에서 데이터 제거
   * @param {string} key - 키
   */
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      console.warn('로컬 스토리지 삭제 실패:', error);
    }
  },

  /**
   * 로컬 스토리지 초기화
   */
  clear() {
    try {
      localStorage.clear();
    } catch (error) {
      console.warn('로컬 스토리지 초기화 실패:', error);
    }
  }
};

/**
 * 텍스트 복사 함수
 * @param {string} text - 복사할 텍스트
 * @returns {Promise<boolean>} 복사 성공 여부
 */
export const copyToClipboard = async (text) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    } else {
      // fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();

      const result = document.execCommand('copy');
      document.body.removeChild(textArea);
      return result;
    }
  } catch (error) {
    console.warn('클립보드 복사 실패:', error);
    return false;
  }
};

/**
 * 파일 다운로드 함수
 * @param {string} content - 파일 내용
 * @param {string} filename - 파일명
 * @param {string} mimeType - MIME 타입
 */
export const downloadFile = (content, filename, mimeType = 'text/plain') => {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  // 메모리 정리
  setTimeout(() => URL.revokeObjectURL(url), 100);
};

/**
 * 토론 히스토리를 JSON 형태로 내보내기
 * @param {Array} historyItems - 히스토리 아이템들
 * @param {string} topic - 토론 주제
 */
export const exportDebateHistory = (historyItems, topic) => {
  const exportData = {
    topic,
    exportDate: new Date().toISOString(),
    messages: historyItems.map(item => ({
      role: item.role,
      name: item.name,
      message: item.message,
      timestamp: item.timestamp
    }))
  };

  const content = JSON.stringify(exportData, null, 2);
  const filename = `debate-history-${topic.replace(/[^a-zA-Z0-9가-힣]/g, '-')}-${Date.now()}.json`;

  downloadFile(content, filename, 'application/json');
};

/**
 * 애니메이션 헬퍼 함수들
 */
export const animations = {
  /**
   * 요소를 페이드 인
   * @param {HTMLElement} element - 대상 요소
   * @param {number} duration - 애니메이션 시간 (ms)
   */
  fadeIn(element, duration = 300) {
    element.style.opacity = '0';
    element.style.display = 'block';

    const start = performance.now();

    const animate = (currentTime) => {
      const elapsed = currentTime - start;
      const progress = Math.min(elapsed / duration, 1);

      element.style.opacity = progress;

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    requestAnimationFrame(animate);
  },

  /**
   * 요소를 페이드 아웃
   * @param {HTMLElement} element - 대상 요소
   * @param {number} duration - 애니메이션 시간 (ms)
   */
  fadeOut(element, duration = 300) {
    const start = performance.now();
    const startOpacity = parseFloat(getComputedStyle(element).opacity);

    const animate = (currentTime) => {
      const elapsed = currentTime - start;
      const progress = Math.min(elapsed / duration, 1);

      element.style.opacity = startOpacity * (1 - progress);

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        element.style.display = 'none';
      }
    };

    requestAnimationFrame(animate);
  },

  /**
   * 요소를 슬라이드 업
   * @param {HTMLElement} element - 대상 요소
   * @param {number} duration - 애니메이션 시간 (ms)
   */
  slideUp(element, duration = 300) {
    const height = element.offsetHeight;
    element.style.height = height + 'px';
    element.style.overflow = 'hidden';

    const start = performance.now();

    const animate = (currentTime) => {
      const elapsed = currentTime - start;
      const progress = Math.min(elapsed / duration, 1);

      element.style.height = (height * (1 - progress)) + 'px';

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        element.style.display = 'none';
        element.style.height = '';
        element.style.overflow = '';
      }
    };

    requestAnimationFrame(animate);
  },

  /**
   * 요소를 슬라이드 다운
   * @param {HTMLElement} element - 대상 요소
   * @param {number} duration - 애니메이션 시간 (ms)
   */
  slideDown(element, duration = 300) {
    element.style.display = 'block';
    element.style.height = '0px';
    element.style.overflow = 'hidden';

    const targetHeight = element.scrollHeight;
    const start = performance.now();

    const animate = (currentTime) => {
      const elapsed = currentTime - start;
      const progress = Math.min(elapsed / duration, 1);

      element.style.height = (targetHeight * progress) + 'px';

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        element.style.height = '';
        element.style.overflow = '';
      }
    };

    requestAnimationFrame(animate);
  }
};

/**
 * DOM 유틸리티 함수들
 */
export const dom = {
  /**
   * 요소가 뷰포트에 보이는지 확인
   * @param {HTMLElement} element - 확인할 요소
   * @returns {boolean} 보임 여부
   */
  isElementVisible(element) {
    const rect = element.getBoundingClientRect();
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
      rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
  },

  /**
   * 요소를 부드럽게 스크롤하여 보이게 함
   * @param {HTMLElement} element - 스크롤할 요소
   * @param {string} behavior - 스크롤 동작 ('smooth', 'auto')
   * @param {string} block - 세로 정렬 ('start', 'center', 'end', 'nearest')
   */
  scrollIntoView(element, behavior = 'smooth', block = 'nearest') {
    element.scrollIntoView({
      behavior,
      block,
      inline: 'nearest'
    });
  },

  /**
   * 요소에 클래스를 토글
   * @param {HTMLElement} element - 대상 요소
   * @param {string} className - 클래스명
   * @param {boolean} force - 강제 설정 (선택사항)
   */
  toggleClass(element, className, force) {
    if (force !== undefined) {
      element.classList.toggle(className, force);
    } else {
      element.classList.toggle(className);
    }
  },

  /**
   * 다수의 요소에 이벤트 리스너 추가
   * @param {NodeList|Array} elements - 요소들
   * @param {string} event - 이벤트 타입
   * @param {Function} handler - 이벤트 핸들러
   */
  addEventListeners(elements, event, handler) {
    elements.forEach(element => {
      element.addEventListener(event, handler);
    });
  }
};

/**
 * 유효성 검사 함수들
 */
export const validators = {
  /**
   * 이메일 형식 검사
   * @param {string} email - 이메일 주소
   * @returns {boolean} 유효성 여부
   */
  isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  },

  /**
   * 토론 주제 유효성 검사
   * @param {string} topic - 토론 주제
   * @returns {object} 검사 결과
   */
  validateTopic(topic) {
    const trimmed = topic.trim();

    if (!trimmed) {
      return { valid: false, message: '토론 주제를 입력해주세요.' };
    }

    if (trimmed.length < 3) {
      return { valid: false, message: '토론 주제는 3글자 이상 입력해주세요.' };
    }

    if (trimmed.length > 100) {
      return { valid: false, message: '토론 주제는 100글자 이하로 입력해주세요.' };
    }

    return { valid: true, message: '' };
  },

  /**
   * 메시지 유효성 검사
   * @param {string} message - 메시지 내용
   * @returns {object} 검사 결과
   */
  validateMessage(message) {
    const trimmed = message.trim();

    if (!trimmed) {
      return { valid: false, message: '메시지를 입력해주세요.' };
    }

    if (trimmed.length > 500) {
      return { valid: false, message: '메시지는 500글자 이하로 입력해주세요.' };
    }

    return { valid: true, message: '' };
  }
};

/**
 * 에러 핸들링 유틸리티
 */
export class ErrorHandler {
  static showToast(message, type = 'error', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `error-toast ${type}`;
    toast.textContent = message;
    toast.style.display = 'block';

    document.body.appendChild(toast);

    setTimeout(() => {
      animations.fadeOut(toast, 300);
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, duration);
  }

  static logError(error, context = '') {
    console.error(`[${context}] 에러 발생:`, error);

    // 개발 환경이 아닌 경우 에러 리포팅 서비스로 전송
    if (process.env.NODE_ENV === 'production') {
      // 에러 리포팅 로직
    }
  }
}
