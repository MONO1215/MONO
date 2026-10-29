# MONO 보안 패치 적용

1. 기존 프로젝트 전체를 백업하고 ZIP 안의 app.py 및 templates 파일을 경로에 맞게 복사합니다.
2. Vercel 환경변수 SECRET_KEY에 32바이트 이상 난수 문자열을 지정합니다. 예: `python -c "import secrets; print(secrets.token_urlsafe(48))"` 출력값을 사용. 기존 세션은 로그아웃됩니다.
3. DATABASE_URL, SUPABASE_SERVICE_ROLE_KEY 등 비밀값을 Git에 올리지 마세요. 이미 유출됐다면 키를 교체하세요.
4. Vercel 배포 후 /login, /admin/login, /roulette, /support, /checkout, 이미지 업로드를 실제로 테스트하세요.
5. DB에 mono_login_failures 테이블이 자동 생성됩니다. 로그인 실패 8회/15분 제한(같은 IP와 아이디 조합)입니다.
6. CDN/WAF에서 IP 단위 속도 제한, 봇 방어 및 관리자 URL 보호를 별도 적용하세요.

## 적용한 방어
- 배포 환경의 SECRET_KEY 필수화, 개발용 비밀키 제거
- 보안 쿠키(HTTPS 배포 시 Secure, HttpOnly, SameSite=Lax), 세션 수명 12시간
- XSS/클릭재킹/콘텐츠 타입 스니핑 관련 HTTP 보안 헤더와 기본 CSP
- 민감 페이지 캐시 방지
- 전체 요청 업로드 크기 8MB 제한
- PostgreSQL 기반 로그인 실패 횟수 제한(회원/관리자)
- 로그인 성공 시 세션 초기화
- 운영 배포에서 Flask 디버그 비활성화

## 추가로 필요한 조치
- 기존 HTML 설명의 사용자 입력을 HTML로 렌더링하는 곳은 서버측 HTML 살균(allowlist) 검토 필요.
- CSP는 기존 외부 이미지·Daum 주소검색·인라인 스크립트 호환을 위해 일부 허용이 남아 있습니다. 완전한 XSS 방어가 아닙니다.
- 일부 기존 POST 라우트 및 GET 로그아웃에 대한 CSRF 보호 전수 감사가 필요합니다.
- 비밀번호 재설정, 관리자 MFA, 이메일 인증, 감사로그, 자동 백업 및 복구훈련은 미포함입니다.
- 8MB는 요청 전체 제한이므로 이미지+기타 폼이 큰 경우 크기를 조정하세요.
- 실제 운영 DB/서버 연동 검증은 수행하지 않았습니다.
