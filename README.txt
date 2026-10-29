MONO 고객센터 1:1 문의 기능

기준: 직전 구매 인증 기능 추가 버전(app.py + index.html + event_page.html + purchase_reviews.html)

적용:
- app.py 기존 파일 교체
- templates/index.html, event_page.html, purchase_reviews.html 기존 파일 유지/교체
- templates/customer_support.html, admin_support.html 새 파일 추가

접속:
- 메인 > 고객센터: /events/support -> /support
- 관리자 문의/답변 관리: /admin/support (관리자 로그인 필요)

기능:
- 로그인 회원만 문의 등록, 자신의 문의/답변 열람
- 문의 유형, 제목, 내용 입력 및 접수
- 관리자 문의 조회 및 답변 등록/수정
- PostgreSQL support_tickets 테이블 서버 초기화 시 자동 생성
- CSRF 검사, 입력 길이 검사, 회원별 조회 제한

주의:
- 관리자 화면 링크는 /admin/support 주소로 직접 접속할 수 있습니다. 기존 관리자 메뉴 템플릿은 포함되지 않았습니다.
- 답변 알림 문자/메일, 첨부파일, 주문번호 연결은 아직 미구현입니다.
- 실제 DB와 Vercel 환경에서는 별도 테스트 필요합니다.
- 기존 운영 중인 app.py에 별도 수정이 있다면 덮어쓰기 전에 병합하세요.
