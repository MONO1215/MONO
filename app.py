import traceback
from supabase import create_client
from uuid import uuid4

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    Response
)

from datetime import date, timedelta

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

app.config[
    "UPLOAD_FOLDER"
] = UPLOAD_FOLDER


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
        and uploaded_file.mimetype.startswith(
            "image/"
        )
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


    # 랜덤 파일명 생성

    filename = (
        str(uuid4())
        + extension
    )


    storage_path = (
        folder
        + "/"
        + filename
    )


    # --------------------------------------------------
    # 중요:
    # Werkzeug FileStorage를 직접 전달하지 않고
    # 메모리 bytes로 읽어서 Supabase에 전달
    # --------------------------------------------------

    uploaded_file.stream.seek(0)

    file_data = (
        uploaded_file.stream.read()
    )


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
            "content-type":
                uploaded_file.mimetype,

            "upsert":
                "false"
        }
    )


    # Public bucket 공개 URL

    public_url = (
        supabase.storage
        .from_(SUPABASE_BUCKET)
        .get_public_url(
            storage_path
        )
    )


    return public_url


# ==================================================
# DB 생성 / 컬럼 업데이트
# ==================================================

def init_db():

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:


            # --------------------------------------
            # 상품
            # --------------------------------------

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

                    created_at TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # 기존 products 테이블에도
            # 설명 이미지 컬럼 자동 추가

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


            # --------------------------------------
            # 옵션
            # --------------------------------------

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

    finally:

        conn.close()


    return render_template(
        "index.html",
        products=products
    )


# ==================================================
# 카테고리
# ==================================================

@app.route(
    "/category/<category_slug>"
)
def category_page(
    category_slug
):

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

@app.route(
    "/product/<int:product_id>"
)
def product_detail(
    product_id
):

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
                    END
                    AS has_description_image,

                    smartstore_price,

                    smartstore_url,

                    coupang_price,

                    coupang_url,

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

        options=options
    )


# ==================================================
# 상품 설명 이미지 출력
# ==================================================

@app.route(
    "/product/<int:product_id>/description-image"
)
def product_description_image(
    product_id
):

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
        or product[
            "description_image"
        ] is None
    ):

        return (
            "상품 설명 이미지를 찾을 수 없습니다.",
            404
        )


    image_data = bytes(
        product[
            "description_image"
        ]
    )


    image_mime = (
        product[
            "description_image_mime"
        ]
        or
        "image/jpeg"
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
    methods=[
        "GET",
        "POST"
    ]
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

            error = (
                "이름을 입력해주세요."
            )


        elif not username:

            error = (
                "아이디를 입력해주세요."
            )


        elif not email:

            error = (
                "이메일을 입력해주세요."
            )


        elif not password:

            error = (
                "비밀번호를 입력해주세요."
            )


        elif (
            password
            !=
            password_confirm
        ):

            error = (
                "비밀번호가 일치하지 않습니다."
            )


        if error is None:


            conn = get_db_connection()


            try:

                with conn.cursor() as cur:


                    # 아이디 중복

                    cur.execute("""
                        SELECT id
                        FROM users
                        WHERE username = %s
                    """, (
                        username,
                    ))


                    existing_username = (
                        cur.fetchone()
                    )


                    if existing_username:

                        error = (
                            "이미 사용 중인 아이디입니다."
                        )


                    else:


                        # 이메일 중복

                        cur.execute("""
                            SELECT id
                            FROM users
                            WHERE email = %s
                        """, (
                            email,
                        ))


                        existing_email = (
                            cur.fetchone()
                        )


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

                                    password_hash

                                )

                                VALUES (

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

                                password_hash
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
    methods=[
        "GET",
        "POST"
    ]
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
            and
            check_password_hash(
                user[
                    "password_hash"
                ],
                password
            )
        ):

            session[
                "user_logged_in"
            ] = True


            session[
                "user_id"
            ] = user["id"]


            session[
                "username"
            ] = user[
                "username"
            ]


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
    methods=[
        "GET",
        "POST"
    ]
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


            current_password = (
                request.form.get(
                    "current_password",
                    ""
                )
            )


            if not name:

                error = (
                    "이름을 입력해주세요."
                )


            elif not email:

                error = (
                    "이메일을 입력해주세요."
                )


            elif not current_password:

                error = (
                    "현재 비밀번호를 입력해주세요."
                )


            elif not check_password_hash(

                user[
                    "password_hash"
                ],

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


                    existing_email = (
                        cur.fetchone()
                    )


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

                            email = %s

                        WHERE id = %s
                    """, (

                        name,

                        phone,

                        email,

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


            already_attended = (
                cur.fetchone()
            )


            if already_attended:

                return redirect(
                    url_for(
                        "profile",
                        attendance_message="already"
                    )
                )


            last_attendance = (
                user[
                    "last_attendance"
                ]
            )


            if (
                last_attendance
                ==
                today
                -
                timedelta(days=1)
            ):

                new_streak = (
                    user[
                        "streak"
                    ]
                    +
                    1
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
    methods=[
        "GET",
        "POST"
    ]
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


                admin_user = (
                    cur.fetchone()
                )


        finally:

            conn.close()


        if (
            admin_user
            and
            check_password_hash(

                admin_user[
                    "password_hash"
                ],

                password
            )
        ):

            session.clear()


            session[
                "admin_logged_in"
            ] = True


            session[
                "admin_username"
            ] = admin_user[
                "username"
            ]


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

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.clear()


    return redirect(
        url_for(
            "admin_login"
        )
    )


# ==================================================
# 관리자 상품 등록
# ==================================================

@app.route(
    "/admin",
    methods=[
        "GET",
        "POST"
    ]
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


        description_html = (
            request.form.get(
                "description_html",
                ""
            )
        )


        smartstore_price = (
            request.form.get(
                "smartstore_price",
                ""
            )
        )


        smartstore_url = (
            request.form.get(
                "smartstore_url",
                ""
            ).strip()
        )


        coupang_price = (
            request.form.get(
                "coupang_price",
                ""
            )
        )


        coupang_url = (
            request.form.get(
                "coupang_url",
                ""
            ).strip()
        )


        # ------------------------------------------
        # 대표 이미지
        # URL 또는 파일 업로드
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


                # 파일 선택 시 URL보다 우선

                image_url = (
                    uploaded_image_url
                )


            except ValueError as e:

                return str(e), 400


            except Exception as e:

    traceback.print_exc()

    return (
        "상품 이미지 업로드 중 오류가 발생했습니다: "
        + str(e),
        500
    )


        # 로컬 파일명은 사용하지 않음

        image_file_name = None


        # ------------------------------------------
        # 상품 설명 이미지
        # ------------------------------------------

        description_image_data = None

        description_image_mime = None


        description_image = (
            request.files.get(
                "description_image"
            )
        )


        if (
            description_image
            and
            description_image.filename
        ):


            if not (
                description_image.mimetype
                and
                description_image.mimetype.startswith(
                    "image/"
                )
            ):

                return (
                    "상품 설명 파일은 이미지 형식만 가능합니다.",
                    400
                )


            description_image_data = (
                description_image.read()
            )


            description_image_mime = (
                description_image.mimetype
            )


            # 이미지가 선택된 경우
            # HTML 설명은 사용하지 않음

            description_html = None


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

                        coupang_url

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

                    int(
                        smartstore_price
                    )
                    if smartstore_price
                    else None,

                    smartstore_url,

                    int(
                        coupang_price
                    )
                    if coupang_price
                    else None,

                    coupang_url
                ))


                product_id = (
                    cur.fetchone()[
                        "id"
                    ]
                )


            # --------------------------------------
            # 옵션
            # --------------------------------------

            option_names = (
                request.form.getlist(
                    "option_name[]"
                )
            )


            option_smartstore_prices = (
                request.form.getlist(
                    "option_smartstore_price[]"
                )
            )


            option_smartstore_urls = (
                request.form.getlist(
                    "option_smartstore_url[]"
                )
            )


            option_coupang_prices = (
                request.form.getlist(
                    "option_coupang_price[]"
                )
            )


            option_coupang_urls = (
                request.form.getlist(
                    "option_coupang_url[]"
                )
            )


            for (
                option_name,
                option_smart_price,
                option_smart_url,
                option_coupang_price,
                option_coupang_url
            ) in zip(

                option_names,

                option_smartstore_prices,

                option_smartstore_urls,

                option_coupang_prices,

                option_coupang_urls
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

                            coupang_url

                        )

                        VALUES (

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

                        int(
                            option_smart_price
                        )
                        if option_smart_price
                        else None,

                        option_smart_url.strip(),

                        int(
                            option_coupang_price
                        )
                        if option_coupang_price
                        else None,

                        option_coupang_url.strip()
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
    # 관리자 상품 목록
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
                    END
                    AS has_description_image,

                    smartstore_price,

                    smartstore_url,

                    coupang_price,

                    coupang_url,

                    created_at

                FROM products

                ORDER BY id DESC
            """)


            products = (
                cur.fetchall()
            )


    finally:

        conn.close()


    return render_template(

        "admin.html",

        products=products
    )


# ==================================================
# 관리자 상품 수정
# ==================================================

@app.route(
    "/admin/product/<int:product_id>/edit",
    methods=[
        "GET",
        "POST"
    ]
)
@admin_login_required
def edit_product(
    product_id
):

    conn = get_db_connection()


    try:


        # ------------------------------------------
        # 상품 조회
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
                    END
                    AS has_description_image,

                    smartstore_price,

                    smartstore_url,

                    coupang_price,

                    coupang_url,

                    created_at

                FROM products

                WHERE id = %s
            """, (
                product_id,
            ))


            product = (
                cur.fetchone()
            )


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


            options = (
                cur.fetchall()
            )


        # ------------------------------------------
        # 수정 저장
        # ------------------------------------------

        if request.method == "POST":


            name = (
                request.form.get(
                    "name",
                    ""
                ).strip()
            )


            category = (
                request.form.get(
                    "category",
                    ""
                ).strip()
            )


            image_url = (
                request.form.get(
                    "image_url",
                    ""
                ).strip()
            )


            description_html = (
                request.form.get(
                    "description_html",
                    ""
                )
            )


            smartstore_price = (
                request.form.get(
                    "smartstore_price",
                    ""
                )
            )


            smartstore_url = (
                request.form.get(
                    "smartstore_url",
                    ""
                ).strip()
            )


            coupang_price = (
                request.form.get(
                    "coupang_price",
                    ""
                )
            )


            coupang_url = (
                request.form.get(
                    "coupang_url",
                    ""
                ).strip()
            )


            # --------------------------------------
            # 대표 이미지 수정
            # URL 또는 파일 업로드
            # --------------------------------------

            image_file = request.files.get(
                "image_file"
            )


            # URL이 비어 있으면 기존 URL 유지

            if not image_url:

                image_url = (
                    product[
                        "image_url"
                    ]
                )


            # 새 파일 선택

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

                    return str(e), 400


                except Exception as e:

    traceback.print_exc()

    return (
        "상품 이미지 업로드 중 오류가 발생했습니다: "
        + str(e),
        500
    )


            # 로컬 이미지 파일명 미사용

            image_file_name = None


            # --------------------------------------
            # 기존 설명 이미지
            # --------------------------------------

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


                current_description = (
                    cur.fetchone()
                )


            description_image_data = (
                current_description[
                    "description_image"
                ]
            )


            description_image_mime = (
                current_description[
                    "description_image_mime"
                ]
            )


            # --------------------------------------
            # 새 설명 이미지
            # --------------------------------------

            new_description_image = (
                request.files.get(
                    "description_image"
                )
            )


            if (
                new_description_image
                and
                new_description_image.filename
            ):


                if not (
                    new_description_image.mimetype
                    and
                    new_description_image.mimetype.startswith(
                        "image/"
                    )
                ):

                    return (
                        "상품 설명 파일은 이미지 형식만 가능합니다.",
                        400
                    )


                description_image_data = (
                    new_description_image.read()
                )


                description_image_mime = (
                    new_description_image.mimetype
                )


                # 이미지 선택 시 HTML 제거

                description_html = None


            elif (
                description_html
                and
                description_html.strip()
            ):


                # HTML 입력 시 기존 상세 이미지 제거

                description_image_data = None

                description_image_mime = None


            # --------------------------------------
            # 상품 UPDATE
            # --------------------------------------

            with conn.cursor() as cur:

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

                        coupang_url = %s

                    WHERE id = %s
                """, (

                    name,

                    category,

                    image_url,

                    image_file_name,

                    description_html,

                    description_image_data,

                    description_image_mime,

                    int(
                        smartstore_price
                    )
                    if smartstore_price
                    else None,

                    smartstore_url,

                    int(
                        coupang_price
                    )
                    if coupang_price
                    else None,

                    coupang_url,

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


            option_smartstore_prices = (
                request.form.getlist(
                    "option_smartstore_price[]"
                )
            )


            option_smartstore_urls = (
                request.form.getlist(
                    "option_smartstore_url[]"
                )
            )


            option_coupang_prices = (
                request.form.getlist(
                    "option_coupang_price[]"
                )
            )


            option_coupang_urls = (
                request.form.getlist(
                    "option_coupang_url[]"
                )
            )


            for (
                option_name,
                smart_price,
                smart_url,
                cp_price,
                cp_url
            ) in zip(

                option_names,

                option_smartstore_prices,

                option_smartstore_urls,

                option_coupang_prices,

                option_coupang_urls
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

                            coupang_url

                        )

                        VALUES (

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

                        int(
                            smart_price
                        )
                        if smart_price
                        else None,

                        smart_url.strip(),

                        int(
                            cp_price
                        )
                        if cp_price
                        else None,

                        cp_url.strip()
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
# 상품 삭제
# ==================================================

@app.route(
    "/admin/product/<int:product_id>/delete",
    methods=["POST"]
)
@admin_login_required
def delete_product(
    product_id
):

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
# 로컬 실행
# ==================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
