MONO 배송지 주소 기능
1. app.py를 프로젝트 루트에 덮어쓰기
2. templates/register.html, templates/edit_profile.html 덮어쓰기
3. 배포 시 기존 users 테이블에 postal_code, address, address_detail 컬럼이 자동 추가됩니다.
4. 기존 회원은 내 정보 수정에서 주소를 입력해 저장할 수 있습니다.
5. 현재 주문 checkout 및 bank_orders에는 배송지가 연동되지 않습니다. 별도 개발이 필요합니다.
