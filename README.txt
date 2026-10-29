MONO 구매 인증 기능

app.py는 최신 TOP20 이벤트 버전 기반입니다.
templates/purchase_reviews.html 신규 추가. 기존 index.html, event_page.html도 포함.

결제 완료(paid) 주문 항목당 후기 1개, 별점, 내용, 선택 사진 업로드(Supabase mono-products 버킷) 기능.
후기 보상 포인트 없음.

주의: Supabase mono-products 버킷에 이미지 업로드 권한이 필요합니다.
실제 PostgreSQL/Supabase 연결 테스트는 수행하지 않았습니다.
