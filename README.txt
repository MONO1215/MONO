MONO 배송지 주문 연동

파일: app.py, templates/register.html, templates/edit_profile.html, templates/checkout.html

기능: 회원 배송지 자동 입력, 비회원 배송지 직접 입력, 주문별 배송지 저장.
기존 bank_orders에는 새 배송지 컬럼이 자동 추가됩니다. 기존 주문 배송지 값은 NULL입니다.
관리자 주문 목록 템플릿(admin_orders.html)은 제공되지 않아 화면 출력은 수정하지 않았습니다.
주의: 실제 데이터베이스 연결 테스트 및 운영 배포는 수행하지 않았습니다.
