MONO 회원정보 상단 카테고리 통일 + 포인트 결제 (1P=1원)

파일 위치:
 app.py -> 프로젝트 루트
 templates/profile.html, checkout.html, admin_orders.html -> templates 폴더

기능: 결제 화면에서 포인트 입력/전액 사용, 주문 저장과 포인트 차감 트랜잭션, 관리자 취소/환불 시 포인트 반환, 100% 포인트 결제, 관리자 주문 내역에서 포인트/입금액 구분.

주의: 기존 주문 테이블 bank_orders.amount 제약조건을 >=0으로 변경하며 point_used/gross_amount/order_group_id 컬럼을 자동 추가합니다. 배포 전에 DB 백업을 권장합니다. 관리자 매출 집계의 amount는 실제 입금액 기준입니다. 상품금액 합계와 다를 수 있습니다.

중요: 100% 포인트 결제는 자동 paid 처리합니다. 다른 경로(/api/bank-orders)에는 포인트 적용이 되지 않습니다. 실제 DB/배포 환경 테스트가 필요합니다.
