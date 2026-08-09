from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

if os.environ.get("VERCEL"):
    DATABASE = "/tmp/mono.db"
else:
    DATABASE = "mono.db"

UPLOAD_FOLDER = os.path.join("static", "uploads", "products")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =========================
# DB 연결
# =========================
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# =========================
# DB 생성
# =========================
def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,

            image_url TEXT,
            image_file TEXT,

            description_html TEXT,

            smartstore_price INTEGER,
            smartstore_url TEXT,

            coupang_price INTEGER,
            coupang_url TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.close()


# =========================
# 메인 쇼핑몰
# =========================
@app.route("/")
def home():
    conn = get_db_connection()

    products = conn.execute("""
        SELECT *
        FROM products
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        products=products
    )


# =========================
# 전체 상품
# =========================
@app.route("/products")
def all_products():
    conn = get_db_connection()

    products = conn.execute("""
        SELECT *
        FROM products
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        products=products
    )


# =========================
# 카테고리 페이지
# =========================
@app.route("/category/<category_slug>")
def category_page(category_slug):

    categories = {
        "fashion": "패션의류/잡화",
        "food": "식품",
        "kitchen": "주방용품",
        "living": "생활용품",
        "hobby": "취미용품",
        "car": "자동차용품",
        "office": "사무용품",
        "sports": "스포츠용품"
    }

    category_name = categories.get(category_slug)

    if not category_name:
        return redirect(url_for("home"))

    conn = get_db_connection()

    products = conn.execute("""
        SELECT *
        FROM products
        WHERE category = ?
        ORDER BY id DESC
    """, (category_name,)).fetchall()

    conn.close()

    return render_template(
        "category.html",
        products=products,
        category_name=category_name,
        category_slug=category_slug
    )


# =========================
# 관리자 상품 등록
# =========================
@app.route("/admin", methods=["GET", "POST"])
def admin():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()

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

        # -------------------------
        # 이미지 파일
        # -------------------------
        image_file_name = None
        image_file = request.files.get("image_file")

        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)

            image_file.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            image_file_name = filename

        # -------------------------
        # HTML 파일
        # -------------------------
        description_file = request.files.get(
            "description_file"
        )

        if description_file and description_file.filename:
            description_html = (
                description_file
                .read()
                .decode("utf-8")
            )

        # -------------------------
        # 상품 저장
        # -------------------------
        conn = get_db_connection()

        cursor = conn.execute("""
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

        product_id = cursor.lastrowid

        # -------------------------
        # 옵션 값
        # -------------------------
        option_names = request.form.getlist(
            "option_name[]"
        )

        option_smartstore_prices = request.form.getlist(
            "option_smartstore_price[]"
        )

        option_smartstore_urls = request.form.getlist(
            "option_smartstore_url[]"
        )

        option_coupang_prices = request.form.getlist(
            "option_coupang_price[]"
        )

        option_coupang_urls = request.form.getlist(
            "option_coupang_url[]"
        )

        # -------------------------
        # 옵션 저장
        # -------------------------
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

            option_name = option_name.strip()

            if not option_name:
                continue

            conn.execute("""
                INSERT INTO product_options (
                    product_id,
                    option_name,
                    smartstore_price,
                    smartstore_url,
                    coupang_price,
                    coupang_url
                )
                VALUES (?, ?, ?, ?, ?, ?)
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
        conn.close()

        return redirect(url_for("admin"))

    return render_template("admin.html")

# =========================
# DB 초기화
# =========================
init_db()


# =========================
# 로컬 실행
# =========================
if __name__ == "__main__":
    app.run(debug=True)