MONO 관리자 회원 관리 확장

수정/추가 파일:
- app.py (기존 포인트 결제 기능 포함)
- templates/admin_members.html (레벨/포인트 표시, 변경/삭제 버튼)
- templates/admin_member_edit.html (관리자 회원정보 수정)
- templates/profile.html, checkout.html, admin_orders.html (직전 버전 유지)

기존 프로젝트의 동일 경로에 덮어쓰기 후 배포하세요.
삭제 정책: 주문 기록이 있는 회원은 삭제할 수 없으며 HTTP 409 안내가 표시됩니다. 주문 기록이 없는 회원만 삭제됩니다.
수정 가능한 항목: 이름/전화번호/이메일/주소/레벨/포인트. 아이디/비밀번호는 변경하지 않습니다.
관리자 로그인과 CSRF 확인을 거칩니다.
실제 DB와 연동 테스트는 별도 필요합니다.
