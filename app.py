from flask import Flask, render_template, request, redirect, url_for, session
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

DATABASE_URL = os.environ.get("DATABASE_URL")

IS_VERCEL = bool(os.environ.get("VERCEL"))

if IS_VERCEL:
    # Vercel은 로컬 파일 영구 저장용으로 사용할 수 없음
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
# DB 생성
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

                    smartstore_price INTEGER,
                    smartstore_url TEXT,

                    coupang_price INTEGER,
                    coupang_url TEXT,

                    created_at TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP
                )
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

@app.route("/product/<int:product_id>")
def product_detail(product_id):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            # 상품
            cur.execute("""
                SELECT *
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

            # 옵션
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

        # ------------------------------------------
        # 필수 입력 확인
        # ------------------------------------------

        if not name:
            error = "이름을 입력해주세요."

        elif not username:
            error = "아이디를 입력해주세요."

        elif not email:
            error = "이메일을 입력해주세요."

        elif not password:
            error = "비밀번호를 입력해주세요."

        elif password != password_confirm:
            error = "비밀번호가 일치하지 않습니다."


        # ------------------------------------------
        # DB 저장
        # ------------------------------------------

        if error is None:

            conn = get_db_connection()

            try:

                with conn.cursor() as cur:

                    # 아이디 중복 확인
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

                        # 이메일 중복 확인
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
                                    password_hash
                                )
                                VALUES (
                                    %s, %s, %s, %s, %s
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
# 관리자 로그인 확인
# ==================================================

def admin_login_required(view_function):

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(
                url_for("admin_login")
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
            session["admin_username"] = admin_user["username"]

            return redirect(
                url_for("admin")
            )

        error = "아이디 또는 비밀번호가 올바르지 않습니다."

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


        # ------------------------------------------
        # 이미지 파일
        # ------------------------------------------

        image_file_name = None

        image_file = request.files.get(
            "image_file"
        )

        if (
            image_file
            and image_file.filename
        ):

            # Vercel에서는 로컬 파일 영구 저장 불가
            if IS_VERCEL:

                return (
                    "현재 Vercel에서는 상품 이미지 "
                    "파일 업로드를 영구 저장할 수 없습니다. "
                    "이미지 URL을 사용해주세요.",
                    400
                )

            filename = secure_filename(
                image_file.filename
            )

            image_file.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            image_file_name = filename


        # ------------------------------------------
        # 상품 설명 HTML 파일
        # ------------------------------------------

        description_file = request.files.get(
            "description_file"
        )

        if (
            description_file
            and description_file.filename
        ):

            description_html = (
                description_file
                .read()
                .decode("utf-8")
            )


        # ------------------------------------------
        # 상품 DB 저장
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
                        smartstore_price,
                        smartstore_url,
                        coupang_price,
                        coupang_url
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    RETURNING id
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

                    coupang_url
                ))

                product_id = cur.fetchone()["id"]


            # --------------------------------------
            # 옵션
            # --------------------------------------

            option_names = request.form.getlist(
                "option_name[]"
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


            # --------------------------------------
            # 옵션 DB 저장
            # --------------------------------------

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
                            %s, %s, %s,
                            %s, %s, %s
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
        # 현재 상품 불러오기
        # ------------------------------------------

        with conn.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM products
                WHERE id = %s
            """, (product_id,))

            product = cur.fetchone()

            if product is None:
                return "상품을 찾을 수 없습니다.", 404


            cur.execute("""
                SELECT *
                FROM product_options
                WHERE product_id = %s
                ORDER BY id ASC
            """, (product_id,))

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


            # --------------------------------------
            # HTML 파일
            # --------------------------------------

            description_file = request.files.get(
                "description_file"
            )

            if (
                description_file
                and description_file.filename
            ):

                description_html = (
                    description_file
                    .read()
                    .decode("utf-8")
                )


            # --------------------------------------
            # 이미지 파일
            # --------------------------------------

            image_file_name = product["image_file"]

            image_file = request.files.get(
                "image_file"
            )

            if (
                image_file
                and image_file.filename
            ):

                if IS_VERCEL:

                    return (
                        "Vercel에서는 이미지 파일을 "
                        "영구 저장할 수 없습니다. "
                        "이미지 URL을 사용해주세요.",
                        400
                    )

                filename = secure_filename(
                    image_file.filename
                )

                image_file.save(
                    os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        filename
                    )
                )

                image_file_name = filename


            # --------------------------------------
            # 상품 수정
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

                    int(smartstore_price)
                    if smartstore_price
                    else None,

                    smartstore_url,

                    int(coupang_price)
                    if coupang_price
                    else None,

                    coupang_url,

                    product_id
                ))


                # 기존 옵션 전체 삭제
                cur.execute("""
                    DELETE FROM product_options
                    WHERE product_id = %s
                """, (product_id,))


            # --------------------------------------
            # 수정된 옵션 다시 저장
            # --------------------------------------

            option_names = request.form.getlist(
                "option_name[]"
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

                option_name = option_name.strip()

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
                            %s, %s, %s,
                            %s, %s, %s
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
def delete_product(product_id):

    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                DELETE FROM products
                WHERE id = %s
            """, (product_id,))

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
    app.run(debug=True)