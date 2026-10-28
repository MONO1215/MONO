import traceback
import re
from supabase import create_client
from uuid import uuid4
from secrets import token_urlsafe

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    Response,
    jsonify,
    abort
)

from datetime import date, timedelta, datetime

import os
import psycopg

from psycopg.rows import dict_row

from werkzeug.utils import secure_filename

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from functools import wraps


# ==================================================
# Flask
# ==================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "mono-admin-session-secret-2026"
)


# ==================================================
# 환경설정
# ==================================================

DATABASE_URL = os.environ.get(
    "DATABASE_URL"
)

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL"
)

SUPABASE_SERVICE_ROLE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY"
)

SUPABASE_BUCKET = "mono-products"
BANK_ACCOUNT_NUMBER = os.environ.get("MONO_BANK_ACCOUNT_NUMBER", "").strip()

IS_VERCEL = bool(
    os.environ.get("VERCEL")
)


if IS_VERCEL:
    UPLOAD_FOLDER = "/tmp/mono-products"
else:
    UPLOAD_FOLDER = os.path.join(
        "static",
        "uploads",
        "products"
    )


os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ==================================================
# 카테고리
# ==================================================

CATEGORIES = {
    "fashion": "패션의류/잡화",
    "food": "식품",
    "kitchen": "주방용품",
    "living": "생활용품",
    "hobby": "취미용품",
    "car": "자동차용품",
    "office": "사무용품",
    "sports": "스포츠용품"
}


# ==================================================
# DB 연결
# ==================================================

def get_db_connection():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL 환경변수가 설정되어 있지 않습니다."
        )

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        prepare_threshold=None
    )


# ==================================================
# Supabase Storage 연결
# ==================================================

def get_supabase_client():

    if not SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL 환경변수가 설정되어 있지 않습니다."
        )

    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY 환경변수가 설정되어 있지 않습니다."
        )

    return create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY
    )


# ==================================================
# 상품 이미지 업로드
# ==================================================

def upload_product_image(
    uploaded_file,
    folder="product-images"
):

    if not uploaded_file:
        return None

    if not uploaded_file.filename:
        return None

    # 이미지 MIME 확인
    if not (
        uploaded_file.mimetype
        and uploaded_file.mimetype.startswith("image/")
    ):
        raise ValueError(
            "이미지 파일만 업로드할 수 있습니다."
        )

    # 안전한 파일명
    safe_name = secure_filename(
        uploaded_file.filename
    )

    # 확장자
    extension = os.path.splitext(
        safe_name
    )[1].lower()

    allowed_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif"
    ]

    if extension not in allowed_extensions:
        raise ValueError(
            "JPG, JPEG, PNG, WEBP, GIF 이미지만 업로드할 수 있습니다."
        )

    # 랜덤 파일명
    filename = (
        str(uuid4())
        + extension
    )

    storage_path = (
        folder
        + "/"
        + filename
    )

    # 파일을 메모리 bytes로 읽기
    uploaded_file.stream.seek(0)

    file_data = uploaded_file.stream.read()

    if not file_data:
        raise ValueError(
            "업로드할 이미지 파일이 비어 있습니다."
        )

    supabase = get_supabase_client()

    # Supabase Storage 업로드
    supabase.storage.from_(
        SUPABASE_BUCKET
    ).upload(
        storage_path,
        file_data,
        {
            "content-type": uploaded_file.mimetype,
            "upsert": "false"
        }
    )

    # 공개 URL
    public_url = (
        supabase.storage
        .from_(SUPABASE_BUCKET)
        .get_public_url(storage_path)
    )

    return public_url


# ==================================================
# DB 생성 / 컬럼 업데이트
# ==================================================

def init_db():

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    image_url TEXT,
                    image_file TEXT,
                    description_html TEXT,
                    description_image BYTEA,
                    description_image_mime TEXT,
                    smartstore_price INTEGER,
                    smartstore_url TEXT,
                    coupang_price INTEGER,
                    coupang_url TEXT,
                    is_sold_out BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS
                description_image BYTEA
            """)

            cur.execute("""
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS
                description_image_mime TEXT
            """)

            cur.execute("""
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS
                is_sold_out BOOLEAN
                DEFAULT FALSE
            """)

            cur.execute("""
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS bank_transfer_price INTEGER
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_options (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER NOT NULL,
                    option_name TEXT NOT NULL,
                    smartstore_price INTEGER,
                    smartstore_url TEXT,
                    coupang_price INTEGER,
                    coupang_url TEXT,

                    FOREIGN KEY (product_id)
                        REFERENCES products(id)
                        ON DELETE CASCADE
                )
            """)

            cur.execute("""
                ALTER TABLE product_options
                ADD COLUMN IF NOT EXISTS bank_transfer_price INTEGER
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS bank_orders (
                    id BIGSERIAL PRIMARY KEY,
                    product_id INTEGER,
                    product_name TEXT NOT NULL,
                    option_name TEXT NOT NULL,
                    depositor_name VARCHAR(50) NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    status TEXT NOT NULL DEFAULT 'reported'
                        CHECK (status IN ('reported','paid','cancelled','refunded')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    paid_at TIMESTAMPTZ,
                    refunded_at TIMESTAMPTZ
                )
            """)
            # 주문 시점의 배송지 스냅샷 (기존 주문은 NULL 유지)
            cur.execute("ALTER TABLE bank_orders ADD COLUMN IF NOT EXISTS recipient_name VARCHAR(100)")
            cur.execute("ALTER TABLE bank_orders ADD COLUMN IF NOT EXISTS recipient_phone VARCHAR(30)")
            cur.execute("ALTER TABLE bank_orders ADD COLUMN IF NOT EXISTS postal_code VARCHAR(10)")
            cur.execute("ALTER TABLE bank_orders ADD COLUMN IF NOT EXISTS address TEXT")
            cur.execute("ALTER TABLE bank_orders ADD COLUMN IF NOT EXISTS address_detail TEXT")
            cur.execute("ALTER TABLE bank_orders ADD COLUMN IF NOT EXISTS user_id INTEGER")

            # 기존 회원 정보를 유지하면서 배송지 컬럼 추가
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS postal_code VARCHAR(10)")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS address TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS address_detail TEXT")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_bank_orders_status ON bank_orders(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bank_orders_paid_at ON bank_orders(paid_at)")

        conn.commit()

    finally:

        conn.close()


# ==================================================
# 서버 시작 후 DB 초기화
# ==================================================

_db_initialized = False


@app.before_request
def ensure_database():

    global _db_initialized

    if not _db_initialized:
        init_db()
        _db_initialized = True




def attach_listing_options(cur, products):
    """상품 목록에 옵션별 계좌이체 가격을 한 번의 조회로 연결."""
    if not products:
        return
    product_ids = [p["id"] for p in products]
    cur.execute("""
        SELECT id, product_id, option_name, bank_transfer_price
        FROM product_options
        WHERE product_id = ANY(%s)
        ORDER BY id ASC
    """, (product_ids,))
    by_product = {pid: [] for pid in product_ids}
    for option in cur.fetchall():
        by_product[option["product_id"]].append(option)
    for product in products:
        product["listing_options"] = by_product[product["id"]]

# ==================================================
# 메인
# ==================================================

@app.route("/")
def home():

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM products
                ORDER BY id DESC
            """)

            products = cur.fetchall()
            attach_listing_options(cur, products)

    finally:
        conn.close()

    return render_template(
        "index.html",
        products=products
    )


# ==================================================
# 전체 상품
# ==================================================

@app.route("/products")
def all_products():

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM products
                ORDER BY id DESC
            """)

            products = cur.fetchall()
            attach_listing_options(cur, products)

    finally:
        conn.close()

    return render_template(
        "index.html",
        products=products
    )


# ==================================================
# 카테고리
# ==================================================

@app.route("/category/<category_slug>")
def category_page(category_slug):

    category_name = CATEGORIES.get(
        category_slug
    )

    if not category_name:
        return redirect(
            url_for("home")
        )

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM products
                WHERE category = %s
                ORDER BY id DESC
            """, (
                category_name,
            ))

            products = cur.fetchall()
            attach_listing_options(cur, products)

    finally:
        conn.close()

    return render_template(
        "category.html",
        products=products,
        category_name=category_name,
        category_slug=category_slug
    )


# ==================================================
# 상품 상세
# ==================================================

def get_order_csrf():
    if "order_csrf" not in session:
        session["order_csrf"] = token_urlsafe(32)
    return session["order_csrf"]


@app.route("/product/<int:product_id>")
def product_detail(product_id):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    name,
                    category,
                    image_url,
                    image_file,
                    description_html,

                    CASE
                        WHEN description_image IS NOT NULL
                        THEN TRUE
                        ELSE FALSE
                    END AS has_description_image,

                    smartstore_price,
                    smartstore_url,
                    coupang_price,
                    coupang_url,
                    bank_transfer_price,

                    is_sold_out,

                    created_at

                FROM products
                WHERE id = %s
            """, (
                product_id,
            ))

            product = cur.fetchone()

            if product is None:

                return (
                    "상품을 찾을 수 없습니다.",
                    404
                )

            cur.execute("""
                SELECT *
                FROM product_options
                WHERE product_id = %s
                ORDER BY id ASC
            """, (
                product_id,
            ))

            options = cur.fetchall()

    finally:

        conn.close()

    return render_template(
        "product_detail.html",
        product=product,
        options=options,
        bank_account_number=BANK_ACCOUNT_NUMBER,
        order_csrf=get_order_csrf()
    )


# ==================================================
# 상품 설명 이미지 출력
# ==================================================

@app.route(
    "/product/<int:product_id>/description-image"
)
def product_description_image(product_id):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    description_image,
                    description_image_mime
                FROM products
                WHERE id = %s
            """, (
                product_id,
            ))

            product = cur.fetchone()

    finally:
        conn.close()

    if (
        product is None
        or product["description_image"] is None
    ):
        return (
            "상품 설명 이미지를 찾을 수 없습니다.",
            404
        )

    image_data = bytes(
        product["description_image"]
    )

    image_mime = (
        product["description_image_mime"]
        or "image/jpeg"
    )

    return Response(
        image_data,
        mimetype=image_mime
    )


# ==================================================
# 일반 회원가입
# ==================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    error = None

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        postal_code = request.form.get("postal_code", "").strip()
        address = request.form.get("address", "").strip()
        address_detail = request.form.get("address_detail", "").strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        password_confirm = request.form.get(
            "password_confirm",
            ""
        )

        if not name:
            error = "이름을 입력해주세요."

        elif not username:
            error = "아이디를 입력해주세요."

        elif not postal_code or not address:
            error = "우편번호와 배송지 주소를 입력해주세요."
        elif not re.fullmatch(r"[0-9]{5}", postal_code):
            error = "우편번호는 5자리 숫자로 입력해주세요."
        elif len(address) > 300 or len(address_detail) > 300:
            error = "주소는 각 300자 이내로 입력해주세요."
        elif not email:
            error = "이메일을 입력해주세요."

        elif not password:
            error = "비밀번호를 입력해주세요."

        elif password != password_confirm:
            error = "비밀번호가 일치하지 않습니다."

        if error is None:

            conn = get_db_connection()

            try:

                with conn.cursor() as cur:

                    cur.execute("""
                        SELECT id
                        FROM users
                        WHERE username = %s
                    """, (
                        username,
                    ))

                    existing_username = cur.fetchone()

                    if existing_username:

                        error = (
                            "이미 사용 중인 아이디입니다."
                        )

                    else:

                        cur.execute("""
                            SELECT id
                            FROM users
                            WHERE email = %s
                        """, (
                            email,
                        ))

                        existing_email = cur.fetchone()

                        if existing_email:

                            error = (
                                "이미 가입된 이메일입니다."
                            )

                        else:

                            password_hash = (
                                generate_password_hash(
                                    password
                                )
                            )

                            cur.execute("""
                                INSERT INTO users (
                                    name,
                                    username,
                                    phone,
                                    email,
                                    password_hash,
                                    postal_code,
                                    address,
                                    address_detail
                                )
                                VALUES (
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    %s
                                )
                            """, (
                                name,
                                username,
                                phone,
                                email,
                                password_hash,
                                postal_code,
                                address,
                                address_detail
                            ))

                            conn.commit()

            except Exception:

                conn.rollback()
                raise

            finally:
                conn.close()

            if error is None:

                return redirect(
                    url_for("login")
                )

    return render_template(
        "register.html",
        error=error
    )


# ==================================================
# 일반 사용자 로그인
# ==================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    error = None

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db_connection()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    SELECT *
                    FROM users
                    WHERE username = %s
                """, (
                    username,
                ))

                user = cur.fetchone()

        finally:
            conn.close()

        if (
            user
            and check_password_hash(
                user["password_hash"],
                password
            )
        ):

            session["user_logged_in"] = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(
                url_for("home")
            )

        error = (
            "아이디 또는 비밀번호가 올바르지 않습니다."
        )

    return render_template(
        "login.html",
        error=error
    )


# ==================================================
# 일반 사용자 로그아웃
# ==================================================

@app.route("/logout")
def logout():

    session.pop(
        "user_logged_in",
        None
    )

    session.pop(
        "user_id",
        None
    )

    session.pop(
        "username",
        None
    )

    return redirect(
        url_for("home")
    )


# ==================================================
# 내 정보
# ==================================================

@app.route("/profile")
def profile():

    if not session.get(
        "user_logged_in"
    ):
        return redirect(
            url_for("login")
        )

    user_id = session.get(
        "user_id"
    )

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    name,
                    username,
                    phone,
                    email,
                    postal_code,
                    address,
                    address_detail,
                    level,
                    point,
                    exp,
                    streak,
                    last_attendance,
                    created_at
                FROM users
                WHERE id = %s
            """, (
                user_id,
            ))

            user = cur.fetchone()

    finally:
        conn.close()

    if user is None:

        session.pop(
            "user_logged_in",
            None
        )

        session.pop(
            "user_id",
            None
        )

        session.pop(
            "username",
            None
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "profile.html",
        user=user
    )


# ==================================================
# 내 정보 수정
# ==================================================

@app.route(
    "/profile/edit",
    methods=["GET", "POST"]
)
def edit_profile():

    if not session.get(
        "user_logged_in"
    ):
        return redirect(
            url_for("login")
        )

    user_id = session.get(
        "user_id"
    )

    error = None

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    name,
                    username,
                    phone,
                    email,
                    postal_code,
                    address,
                    address_detail,
                    password_hash
                FROM users
                WHERE id = %s
            """, (
                user_id,
            ))

            user = cur.fetchone()

        if user is None:

            session.pop(
                "user_logged_in",
                None
            )

            session.pop(
                "user_id",
                None
            )

            session.pop(
                "username",
                None
            )

            return redirect(
                url_for("login")
            )

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            phone = request.form.get(
                "phone",
                ""
            ).strip()

            email = request.form.get(
                "email",
                ""
            ).strip()

            postal_code = request.form.get("postal_code", "").strip()
            address = request.form.get("address", "").strip()
            address_detail = request.form.get("address_detail", "").strip()

            current_password = request.form.get(
                "current_password",
                ""
            )

            if not name:
                error = "이름을 입력해주세요."

            elif not postal_code or not address:
                error = "우편번호와 배송지 주소를 입력해주세요."
            elif not re.fullmatch(r"[0-9]{5}", postal_code):
                error = "우편번호는 5자리 숫자로 입력해주세요."
            elif len(address) > 300 or len(address_detail) > 300:
                error = "주소는 각 300자 이내로 입력해주세요."
            elif not email:
                error = "이메일을 입력해주세요."

            elif not current_password:
                error = "현재 비밀번호를 입력해주세요."

            elif not check_password_hash(
                user["password_hash"],
                current_password
            ):
                error = (
                    "비밀번호가 올바르지 않습니다."
                )

            if error is None:

                with conn.cursor() as cur:

                    cur.execute("""
                        SELECT id
                        FROM users
                        WHERE email = %s
                        AND id != %s
                    """, (
                        email,
                        user_id
                    ))

                    existing_email = cur.fetchone()

                if existing_email:
                    error = (
                        "이미 사용 중인 이메일입니다."
                    )

            if error is None:

                with conn.cursor() as cur:

                    cur.execute("""
                        UPDATE users
                        SET
                            name = %s,
                            phone = %s,
                            email = %s,
                            postal_code = %s,
                            address = %s,
                            address_detail = %s
                        WHERE id = %s
                    """, (
                        name,
                        phone,
                        email,
                        postal_code,
                        address,
                        address_detail,
                        user_id
                    ))

                conn.commit()

                return redirect(
                    url_for("profile")
                )

    except Exception:

        conn.rollback()
        raise

    finally:
        conn.close()

    return render_template(
        "edit_profile.html",
        user=user,
        error=error
    )


# ==================================================
# 출석체크
# ==================================================

@app.route(
    "/attendance",
    methods=["POST"]
)
def attendance():

    if not session.get(
        "user_logged_in"
    ):
        return redirect(
            url_for("login")
        )

    user_id = session.get(
        "user_id"
    )

    today = date.today()

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    point,
                    exp,
                    streak,
                    last_attendance
                FROM users
                WHERE id = %s
            """, (
                user_id,
            ))

            user = cur.fetchone()

            if user is None:

                return redirect(
                    url_for("login")
                )

            cur.execute("""
                SELECT id
                FROM attendance
                WHERE user_id = %s
                AND attendance_date = %s
            """, (
                user_id,
                today
            ))

            already_attended = cur.fetchone()

            if already_attended:

                return redirect(
                    url_for(
                        "profile",
                        attendance_message="already"
                    )
                )

            last_attendance = (
                user["last_attendance"]
            )

            if (
                last_attendance
                == today - timedelta(days=1)
            ):
                new_streak = (
                    user["streak"] + 1
                )

            else:
                new_streak = 1

            cur.execute("""
                INSERT INTO attendance (
                    user_id,
                    attendance_date
                )
                VALUES (
                    %s,
                    %s
                )
            """, (
                user_id,
                today
            ))

            cur.execute("""
                UPDATE users
                SET
                    point = point + 10,
                    exp = exp + 10,
                    streak = %s,
                    last_attendance = %s
                WHERE id = %s
            """, (
                new_streak,
                today,
                user_id
            ))

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:
        conn.close()

    return redirect(
        url_for(
            "profile",
            attendance_message="success"
        )
    )


# ==================================================
# 관리자 로그인 확인
# ==================================================

def admin_login_required(
    view_function
):

    @wraps(view_function)
    def wrapped_view(
        *args,
        **kwargs
    ):

        if not session.get(
            "admin_logged_in"
        ):
            return redirect(
                url_for(
                    "admin_login"
                )
            )

        return view_function(
            *args,
            **kwargs
        )

    return wrapped_view


# ==================================================
# 관리자 로그인
# ==================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    error = None

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db_connection()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    SELECT *
                    FROM admins
                    WHERE username = %s
                """, (
                    username,
                ))

                admin_user = cur.fetchone()

        finally:
            conn.close()

        if (
            admin_user
            and check_password_hash(
                admin_user["password_hash"],
                password
            )
        ):

            session.clear()

            session["admin_logged_in"] = True
            session["admin_username"] = (
                admin_user["username"]
            )

            return redirect(
                url_for("admin")
            )

        error = (
            "아이디 또는 비밀번호가 올바르지 않습니다."
        )

    return render_template(
        "admin_login.html",
        error=error
    )


# ==================================================
# 관리자 로그아웃
# ==================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ==================================================
# 관리자 상품 등록
# ==================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
@admin_login_required
def admin():

    if request.method == "POST":

        # ------------------------------------------
        # 기본정보
        # ------------------------------------------

        name = request.form.get(
            "name",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        image_url = request.form.get(
            "image_url",
            ""
        ).strip()

        description_html = request.form.get(
            "description_html",
            ""
        )

        smartstore_price = request.form.get(
            "smartstore_price",
            ""
        )

        smartstore_url = request.form.get(
            "smartstore_url",
            ""
        ).strip()

        coupang_price = request.form.get(
            "coupang_price",
            ""
        )

        coupang_url = request.form.get(
            "coupang_url",
            ""
        ).strip()

        bank_transfer_price = request.form.get(
            "bank_transfer_price", ""
        ).strip()


        # ------------------------------------------
        # 대표 이미지
        # URL 또는 Supabase 파일 업로드
        # ------------------------------------------

        image_file = request.files.get(
            "image_file"
        )

        if (
            image_file
            and image_file.filename
        ):

            try:

                uploaded_image_url = (
                    upload_product_image(
                        image_file,
                        "product-images"
                    )
                )

                # 파일을 선택한 경우 업로드된 이미지 우선
                image_url = uploaded_image_url

            except ValueError as e:

                return (
                    str(e),
                    400
                )

            except Exception as e:

                traceback.print_exc()

                return (
                    "상품 이미지 업로드 중 오류가 발생했습니다: "
                    + str(e),
                    500
                )


        # 로컬 파일 저장은 사용하지 않음
        image_file_name = None


        # ------------------------------------------
        # 상품 설명
        # HTML 또는 이미지
        # ------------------------------------------

        description_image_data = None
        description_image_mime = None

        description_file = request.files.get(
            "description_file"
        )

        if (
            description_file
            and description_file.filename
        ):

            if (
                description_file.mimetype
                and description_file.mimetype.startswith(
                    "image/"
                )
            ):

                description_image_data = (
                    description_file.read()
                )

                description_image_mime = (
                    description_file.mimetype
                )

                # 이미지가 선택되면 HTML은 비움
                description_html = ""

            else:

                try:

                    description_html = (
                        description_file
                        .read()
                        .decode("utf-8")
                    )

                except UnicodeDecodeError:

                    return (
                        "상품 설명 파일은 HTML 또는 이미지 파일만 사용할 수 있습니다.",
                        400
                    )


        # ------------------------------------------
        # 상품 저장
        # ------------------------------------------

        conn = get_db_connection()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO products (
                        name,
                        category,
                        image_url,
                        image_file,
                        description_html,
                        description_image,
                        description_image_mime,
                        smartstore_price,
                        smartstore_url,
                        coupang_price,
                        coupang_url,
                        bank_transfer_price
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING id
                """, (
                    name,
                    category,
                    image_url,
                    image_file_name,
                    description_html,
                    description_image_data,
                    description_image_mime,

                    int(smartstore_price)
                    if smartstore_price
                    else None,

                    smartstore_url,

                    int(coupang_price)
                    if coupang_price
                    else None,

                    coupang_url,
                    int(bank_transfer_price) if bank_transfer_price else None
                ))

                product_id = (
                    cur.fetchone()["id"]
                )


            # --------------------------------------
            # 옵션
            # --------------------------------------

            option_names = (
                request.form.getlist(
                    "option_name[]"
                )
            )

            option_smartstore_prices = ["" for _ in option_names]

            option_smartstore_urls = ["" for _ in option_names]

            option_coupang_prices = ["" for _ in option_names]

            option_coupang_urls = ["" for _ in option_names]

            option_bank_transfer_prices = request.form.getlist(
                "option_bank_transfer_price[]"
            )



            for (
                option_name,
                option_smart_price,
                option_smart_url,
                option_coupang_price,
                option_coupang_url,
                option_bank_price
            ) in zip(
                option_names,
                option_smartstore_prices,
                option_smartstore_urls,
                option_coupang_prices,
                option_coupang_urls,
                option_bank_transfer_prices
            ):

                option_name = (
                    option_name.strip()
                )

                if not option_name:
                    continue

                with conn.cursor() as cur:

                    cur.execute("""
                        INSERT INTO product_options (
                            product_id,
                            option_name,
                            smartstore_price,
                            smartstore_url,
                            coupang_price,
                            coupang_url,
                            bank_transfer_price
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                    """, (
                        product_id,
                        option_name,

                        int(option_smart_price)
                        if option_smart_price
                        else None,

                        option_smart_url.strip(),

                        int(option_coupang_price)
                        if option_coupang_price
                        else None,

                        option_coupang_url.strip(),
                        int(option_bank_price) if option_bank_price else None
                    ))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            conn.close()


        return redirect(
            url_for("admin")
        )


    # ----------------------------------------------
    # 관리자 페이지 상품 목록
    # ----------------------------------------------

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    name,
                    category,
                    image_url,
                    image_file,
                    description_html,

                    CASE
                        WHEN description_image IS NOT NULL
                        THEN TRUE
                        ELSE FALSE
                    END AS has_description_image,

                    smartstore_price,
                    smartstore_url,
                    coupang_price,
                    coupang_url,
                    bank_transfer_price,
                    is_sold_out,
                    created_at

                FROM products
                ORDER BY id DESC
            """)

            products = cur.fetchall()

    finally:

        conn.close()


    return render_template(
        "admin.html",
        products=products
    )


# ==================================================
# 상품 수정
# ==================================================

@app.route(
    "/admin/product/<int:product_id>/edit",
    methods=["GET", "POST"]
)
@admin_login_required
def edit_product(product_id):

    conn = get_db_connection()

    try:

        # ------------------------------------------
        # 현재 상품
        # ------------------------------------------

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    name,
                    category,
                    image_url,
                    image_file,
                    description_html,

                    CASE
                        WHEN description_image IS NOT NULL
                        THEN TRUE
                        ELSE FALSE
                    END AS has_description_image,

                    description_image_mime,
                    smartstore_price,
                    smartstore_url,
                    coupang_price,
                    coupang_url,
                    bank_transfer_price,
                    created_at

                FROM products
                WHERE id = %s
            """, (
                product_id,
            ))

            product = cur.fetchone()

            if product is None:

                return (
                    "상품을 찾을 수 없습니다.",
                    404
                )


            cur.execute("""
                SELECT *
                FROM product_options
                WHERE product_id = %s
                ORDER BY id ASC
            """, (
                product_id,
            ))

            options = cur.fetchall()


        # ------------------------------------------
        # 수정 저장
        # ------------------------------------------

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            category = request.form.get(
                "category",
                ""
            ).strip()

            image_url = request.form.get(
                "image_url",
                ""
            ).strip()

            description_html = request.form.get(
                "description_html",
                ""
            )

            smartstore_price = request.form.get(
                "smartstore_price",
                ""
            )

            smartstore_url = request.form.get(
                "smartstore_url",
                ""
            ).strip()

            coupang_price = request.form.get(
                "coupang_price",
                ""
            )

            coupang_url = request.form.get(
                "coupang_url",
                ""
            ).strip()

            bank_transfer_price = request.form.get(
                "bank_transfer_price", ""
            ).strip()


            # --------------------------------------
            # 대표 이미지 수정
            # --------------------------------------

            image_file = request.files.get(
                "image_file"
            )

            # URL 입력을 비워두었다면
            # 기존 이미지 유지
            if not image_url:
                image_url = product[
                    "image_url"
                ]


            # 새 이미지 파일을 선택했다면
            # Supabase에 업로드하고 새 URL 사용
            if (
                image_file
                and image_file.filename
            ):

                try:

                    uploaded_image_url = (
                        upload_product_image(
                            image_file,
                            "product-images"
                        )
                    )

                    image_url = (
                        uploaded_image_url
                    )

                except ValueError as e:

                    return (
                        str(e),
                        400
                    )

                except Exception as e:

                    traceback.print_exc()

                    return (
                        "상품 이미지 업로드 중 오류가 발생했습니다: "
                        + str(e),
                        500
                    )


            # 로컬 파일 저장은 사용하지 않음
            image_file_name = None


            # --------------------------------------
            # 상품 설명 수정
            # --------------------------------------

            description_file = (
                request.files.get(
                    "description_file"
                )
            )

            new_description_image = None
            new_description_mime = None

            use_new_description_image = False


            if (
                description_file
                and description_file.filename
            ):

                if (
                    description_file.mimetype
                    and description_file.mimetype.startswith(
                        "image/"
                    )
                ):

                    new_description_image = (
                        description_file.read()
                    )

                    new_description_mime = (
                        description_file.mimetype
                    )

                    use_new_description_image = True

                    # 새 설명 이미지가 있으면
                    # HTML 설명 제거
                    description_html = ""

                else:

                    try:

                        description_html = (
                            description_file
                            .read()
                            .decode("utf-8")
                        )

                    except UnicodeDecodeError:

                        return (
                            "상품 설명 파일은 HTML 또는 이미지 파일만 사용할 수 있습니다.",
                            400
                        )


            # --------------------------------------
            # 상품 정보 UPDATE
            # --------------------------------------

            with conn.cursor() as cur:

                if use_new_description_image:

                    cur.execute("""
                        UPDATE products
                        SET
                            name = %s,
                            category = %s,
                            image_url = %s,
                            image_file = %s,
                            description_html = %s,
                            description_image = %s,
                            description_image_mime = %s,
                            smartstore_price = %s,
                            smartstore_url = %s,
                            coupang_price = %s,
                            coupang_url = %s,
                            bank_transfer_price = %s
                        WHERE id = %s
                    """, (
                        name,
                        category,
                        image_url,
                        image_file_name,
                        description_html,
                        new_description_image,
                        new_description_mime,

                        int(smartstore_price)
                        if smartstore_price
                        else None,

                        smartstore_url,

                        int(coupang_price)
                        if coupang_price
                        else None,

                        coupang_url,
                        int(bank_transfer_price) if bank_transfer_price else None,
                        product_id
                    ))

                else:

                    cur.execute("""
                        UPDATE products
                        SET
                            name = %s,
                            category = %s,
                            image_url = %s,
                            image_file = %s,
                            description_html = %s,
                            smartstore_price = %s,
                            smartstore_url = %s,
                            coupang_price = %s,
                            coupang_url = %s,
                            bank_transfer_price = %s
                        WHERE id = %s
                    """, (
                        name,
                        category,
                        image_url,
                        image_file_name,
                        description_html,

                        int(smartstore_price)
                        if smartstore_price
                        else None,

                        smartstore_url,

                        int(coupang_price)
                        if coupang_price
                        else None,

                        coupang_url,
                        int(bank_transfer_price) if bank_transfer_price else None,
                        product_id
                    ))


                # 기존 옵션 삭제
                cur.execute("""
                    DELETE FROM product_options
                    WHERE product_id = %s
                """, (
                    product_id,
                ))


            # --------------------------------------
            # 옵션 다시 저장
            # --------------------------------------

            option_names = (
                request.form.getlist(
                    "option_name[]"
                )
            )

            option_smartstore_prices = ["" for _ in option_names]

            option_smartstore_urls = ["" for _ in option_names]

            option_coupang_prices = ["" for _ in option_names]

            option_coupang_urls = ["" for _ in option_names]

            option_bank_transfer_prices = request.form.getlist(
                "option_bank_transfer_price[]"
            )



            for (
                option_name,
                smart_price,
                smart_url,
                cp_price,
                cp_url,
                bank_price
            ) in zip(
                option_names,
                option_smartstore_prices,
                option_smartstore_urls,
                option_coupang_prices,
                option_coupang_urls,
                option_bank_transfer_prices
            ):

                option_name = (
                    option_name.strip()
                )

                if not option_name:
                    continue


                with conn.cursor() as cur:

                    cur.execute("""
                        INSERT INTO product_options (
                            product_id,
                            option_name,
                            smartstore_price,
                            smartstore_url,
                            coupang_price,
                            coupang_url,
                            bank_transfer_price
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                    """, (
                        product_id,
                        option_name,

                        int(smart_price)
                        if smart_price
                        else None,

                        smart_url.strip(),

                        int(cp_price)
                        if cp_price
                        else None,

                        cp_url.strip(),
                        int(bank_price) if bank_price else None
                    ))


            conn.commit()

            return redirect(
                url_for("admin")
            )


        return render_template(
            "edit_product.html",
            product=product,
            options=options
        )


    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()


# ==================================================
# 상품 품절 / 판매 재개
# ==================================================

@app.route(
    "/admin/product/<int:product_id>/sold-out",
    methods=["POST"]
)
@admin_login_required
def toggle_sold_out(product_id):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            # 현재 품절 상태 확인
            cur.execute("""
                SELECT is_sold_out
                FROM products
                WHERE id = %s
            """, (
                product_id,
            ))

            product = cur.fetchone()

            if product is None:

                return (
                    "상품을 찾을 수 없습니다.",
                    404
                )

            # 현재 상태 반대로 변경
            new_status = not bool(
                product["is_sold_out"]
            )

            cur.execute("""
                UPDATE products
                SET is_sold_out = %s
                WHERE id = %s
            """, (
                new_status,
                product_id
            ))

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()

    return redirect(
        url_for("admin")
    )


# ==================================================
# 상품 삭제
# ==================================================

@app.route(
    "/admin/product/<int:product_id>/delete",
    methods=["POST"]
)
@admin_login_required
def delete_product(product_id):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM products
                WHERE id = %s
            """, (
                product_id,
            ))

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()


    return redirect(
        url_for("admin")
    )


# ==================================================
# 장바구니 / 바로 결제 (서버에서 가격 재확인)
# ==================================================

def cart_lines():
    cart = session.get("mono_cart", [])
    lines = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for item in cart[:30]:
                pid, oid, qty = item["product_id"], item.get("option_id"), item["quantity"]
                cur.execute("SELECT id,name,image_url,bank_transfer_price,is_sold_out FROM products WHERE id=%s", (pid,))
                product = cur.fetchone()
                if not product or product["is_sold_out"]: continue
                price, name = product["bank_transfer_price"], "기본 상품"
                if oid is not None:
                    cur.execute("SELECT option_name,bank_transfer_price FROM product_options WHERE id=%s AND product_id=%s", (oid,pid))
                    opt=cur.fetchone()
                    if not opt: continue
                    price,name=opt["bank_transfer_price"],opt["option_name"]
                if price is None or price <= 0: continue
                lines.append(dict(product_id=pid,option_id=oid,product_name=product["name"],option_name=name,image_url=product["image_url"],price=price,quantity=qty,subtotal=price*qty))
    finally: conn.close()
    return lines

@app.route("/cart")
def view_cart():
    lines=cart_lines()
    return render_template("cart.html", lines=lines, total=sum(x["subtotal"] for x in lines), csrf=get_order_csrf())

@app.route("/cart/add", methods=["POST"])
def add_to_cart():
    if request.form.get("csrf_token") != session.get("order_csrf") or not session.get("order_csrf"):
        abort(403)
    try:
        pid=int(request.form["product_id"])
        oid=int(request.form["option_id"]) if request.form.get("option_id") else None
        qty=int(request.form.get("quantity",1))
        if not (1<=qty<=20): raise ValueError()
    except (ValueError, KeyError): abort(400)
    cart=list(session.get("mono_cart",[]))
    # 서버 가격 검증을 위해 선택 항목을 임시로 추가하여 확인
    candidate={"product_id":pid,"option_id":oid,"quantity":qty}
    previous=session.get("mono_cart",[])
    session["mono_cart"]=[candidate]
    valid=bool(cart_lines())
    session["mono_cart"]=previous
    if not valid: abort(400)
    for item in cart:
        if item["product_id"]==pid and item.get("option_id")==oid:
            item["quantity"]=min(20,item["quantity"]+qty)
            break
    else:
        if len(cart)>=30: abort(400)
        cart.append(candidate)
    session["mono_cart"]=cart
    session.modified=True
    return redirect(url_for("checkout") if request.form.get("mode")=="buy" else url_for("view_cart"))

@app.route("/cart/update", methods=["POST"])
def update_cart():
    if request.form.get("csrf_token") != session.get("order_csrf"): abort(403)
    try:
        index=int(request.form.get("index"))
        quantity=int(request.form.get("quantity"))
    except (TypeError,ValueError): abort(400)
    cart=list(session.get("mono_cart",[]))
    if not 0<=index<len(cart) or not 0<=quantity<=20: abort(400)
    if quantity==0: cart.pop(index)
    else: cart[index]["quantity"]=quantity
    session["mono_cart"]=cart
    session.modified=True
    return redirect(url_for("view_cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines = cart_lines()
    if not lines:
        return redirect(url_for("view_cart"))
    total = sum(x["subtotal"] for x in lines)
    error = None
    user = None
    user_id = session.get("user_id") if session.get("user_logged_in") else None
    if user_id:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""SELECT id, name, phone, postal_code, address, address_detail
                               FROM users WHERE id=%s""", (user_id,))
                user = cur.fetchone()
        finally:
            conn.close()
    if request.method == "POST":
        if request.form.get("csrf_token") != session.get("order_csrf") or not session.get("order_csrf"):
            abort(403)
        if not BANK_ACCOUNT_NUMBER:
            error = "계좌번호가 아직 등록되지 않아 주문할 수 없습니다."
        depositor = request.form.get("depositor_name", "").strip()
        recipient_name = request.form.get("recipient_name", "").strip()
        recipient_phone = request.form.get("recipient_phone", "").strip()
        postal_code = request.form.get("postal_code", "").strip()
        address = request.form.get("address", "").strip()
        address_detail = request.form.get("address_detail", "").strip()
        if not 1 <= len(depositor) <= 50:
            error = "입금자명을 1~50자로 입력해 주세요."
        elif not 1 <= len(recipient_name) <= 100:
            error = "받는 분 이름을 입력해 주세요."
        elif not 1 <= len(recipient_phone) <= 30:
            error = "받는 분 연락처를 입력해 주세요."
        elif not re.fullmatch(r"[0-9]{5}", postal_code):
            error = "우편번호 5자리를 입력해 주세요."
        elif not address or len(address) > 300 or len(address_detail) > 300:
            error = "배송지 주소를 정확히 입력해 주세요."
        if not error:
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    ids = []
                    for line in lines:
                        # 기존 매출 집계와 호환되도록 상품별 주문을 유지하면서 배송지 저장
                        cur.execute("""INSERT INTO bank_orders
                            (product_id, product_name, option_name, depositor_name, amount,
                             recipient_name, recipient_phone, postal_code, address, address_detail, user_id)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                            (line["product_id"], line["product_name"],
                             line["option_name"] + (" × " + str(line["quantity"]) if line["quantity"] > 1 else ""),
                             depositor, line["subtotal"], recipient_name, recipient_phone,
                             postal_code, address, address_detail, user["id"] if user else None))
                        ids.append(cur.fetchone()["id"])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            session.pop("mono_cart", None)
            return render_template("checkout_success.html", ids=ids, total=total)
    return render_template(
        "checkout.html", lines=lines, total=total, csrf=get_order_csrf(),
        account=BANK_ACCOUNT_NUMBER, error=error, user=user
    )


# ==================================================
# 계좌이체 주문 접수 / 관리자 주문 및 매출 관리
# ==================================================

@app.route("/api/bank-orders", methods=["POST"])
def create_bank_order():
    if not BANK_ACCOUNT_NUMBER:
        return jsonify(error="계좌번호가 등록되지 않아 주문을 받을 수 없습니다."), 503
    data = request.get_json(silent=True) or {}
    if data.get("csrf_token") != session.get("order_csrf") or not session.get("order_csrf"):
        return jsonify(error="보안 토큰이 유효하지 않습니다. 페이지를 새로고침해 주세요."), 403
    depositor = str(data.get("depositor_name") or "").strip()
    if not (1 <= len(depositor) <= 50):
        return jsonify(error="입금자명을 1~50자로 입력해 주세요."), 400
    try:
        product_id = int(data.get("product_id"))
    except (TypeError, ValueError):
        return jsonify(error="상품 정보가 올바르지 않습니다."), 400
    option_id = data.get("option_id")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,name,bank_transfer_price,is_sold_out FROM products WHERE id=%s", (product_id,))
            product = cur.fetchone()
            if not product or product["is_sold_out"]:
                return jsonify(error="판매 중인 상품이 아닙니다."), 400
            option_name = "기본 상품"
            amount = product["bank_transfer_price"]
            if option_id is not None:
                try:
                    option_id = int(option_id)
                except (TypeError, ValueError):
                    return jsonify(error="옵션 정보가 올바르지 않습니다."), 400
                cur.execute("SELECT option_name,bank_transfer_price FROM product_options WHERE id=%s AND product_id=%s", (option_id, product_id))
                option = cur.fetchone()
                if not option:
                    return jsonify(error="옵션을 찾을 수 없습니다."), 400
                option_name, amount = option["option_name"], option["bank_transfer_price"]
            if amount is None or amount <= 0:
                return jsonify(error="계좌이체 판매가격이 등록되지 않았습니다."), 400
            cur.execute("""INSERT INTO bank_orders (product_id,product_name,option_name,depositor_name,amount)
                           VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                        (product_id, product["name"], option_name, depositor, amount))
            order_id = cur.fetchone()["id"]
        conn.commit()
        return jsonify(ok=True, order_id=order_id, message="입금 신고가 접수되었습니다. 관리자가 실제 입금을 확인한 뒤 결제 완료로 처리합니다."), 201
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route("/admin/orders")
@admin_login_required
def admin_orders():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bank_orders ORDER BY created_at DESC LIMIT 500")
            orders = cur.fetchall()
    finally:
        conn.close()
    return render_template("admin_orders.html", orders=orders, csrf_token=get_order_csrf())


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_login_required
def admin_order_status(order_id):
    if request.form.get("csrf_token") != session.get("order_csrf") or not session.get("order_csrf"):
        abort(403)
    status = request.form.get("status")
    if status not in ("paid", "cancelled", "refunded"):
        abort(400)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM bank_orders WHERE id=%s FOR UPDATE", (order_id,))
            order = cur.fetchone()
            if not order:
                abort(404)
            old = order["status"]
            allowed = {"reported": {"paid", "cancelled"}, "paid": {"refunded"}}
            if status not in allowed.get(old, set()):
                abort(400, "허용되지 않는 주문 상태 변경입니다.")
            cur.execute("""UPDATE bank_orders SET status=%s,
                paid_at=CASE WHEN %s='paid' THEN NOW() ELSE paid_at END,
                refunded_at=CASE WHEN %s='refunded' THEN NOW() ELSE refunded_at END
                WHERE id=%s""", (status, status, status, order_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return redirect(url_for("admin_orders"))


@app.route("/admin/sales")
@admin_login_required
def admin_sales():
    # 결제확인 시점 기준, 환불 주문은 전체 기간 집계에서 제외합니다.
    today = date.today()
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    try:
        start_date = date.fromisoformat(start) if start else today.replace(day=1)
        end_date = date.fromisoformat(end) if end else today
        if start_date > end_date or (end_date - start_date).days > 3660:
            raise ValueError()
    except ValueError:
        abort(400, "올바른 조회 기간을 입력해 주세요.")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT
                COALESCE(SUM(amount) FILTER (WHERE (paid_at AT TIME ZONE 'Asia/Seoul')::date=%s),0) AS today_sales,
                COALESCE(SUM(amount) FILTER (WHERE date_trunc('month',paid_at AT TIME ZONE 'Asia/Seoul')=date_trunc('month',NOW() AT TIME ZONE 'Asia/Seoul')),0) AS month_sales,
                COALESCE(SUM(amount),0) AS total_sales, COUNT(*) AS paid_count
                FROM bank_orders WHERE status='paid'""", (today,))
            summary = cur.fetchone()
            cur.execute("""SELECT (paid_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                SUM(amount) AS amount,COUNT(*) AS orders FROM bank_orders
                WHERE status='paid' AND (paid_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
                GROUP BY 1 ORDER BY 1""", (start_date, end_date))
            daily = cur.fetchall()
            cur.execute("""SELECT product_name, SUM(amount) AS amount,COUNT(*) AS orders
                FROM bank_orders WHERE status='paid' AND (paid_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
                GROUP BY product_name ORDER BY amount DESC LIMIT 20""", (start_date, end_date))
            ranking = cur.fetchall()
            cur.execute("""SELECT * FROM bank_orders WHERE status='paid'
                AND (paid_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
                ORDER BY paid_at DESC LIMIT 100""", (start_date, end_date))
            recent = cur.fetchall()
    finally:
        conn.close()
    return render_template("admin_sales.html", summary=summary, daily=daily,
                           ranking=ranking, recent=recent, start_date=start_date, end_date=end_date)


# ==================================================
# 로컬 실행
# ==================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
