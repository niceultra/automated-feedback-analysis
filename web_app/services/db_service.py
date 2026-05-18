import streamlit as st
import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# --- ДАННЫЕ ПОДКЛЮЧЕНИЯ ---
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]


@st.cache_resource(show_spinner=False)
def get_db_engine():
    """Создаёт SQLAlchemy engine для чтения данных через pandas."""
    db_url = URL.create(
        "postgresql+psycopg2",
        username=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=6432,
        database=DB_NAME,
        query={"sslmode": "require"}
    )

    return create_engine(db_url, pool_pre_ping=True)


def get_db_connection():
    """Создаёт прямое подключение к PostgreSQL через psycopg2."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=6432,
        sslmode="require"
    )


def get_product_analytics(nm_id):
    """Получает текст резюме и HTML-код графика по товару."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT summary_text, chart_html FROM product_summary WHERE nm_id = %s",
            (str(nm_id),)
        )
        result = cursor.fetchone()
        conn.close()

        return result if result else (None, None)

    except Exception:
        return None, None


def get_reviews(nm_id):
    """Получает отзывы товара из базы данных."""
    try:
        query = text("""
            SELECT review_text, sentiment, confidence
            FROM reviews
            WHERE nm_id = :nm_id
        """)

        with get_db_engine().connect() as conn:
            df = pd.read_sql(query, conn, params={"nm_id": str(nm_id)})

        return df

    except Exception as e:
        st.error(f"Ошибка при загрузке отзывов: {e}")
        return None


def get_all_products():
    """Получает список всех товаров из базы данных."""
    try:
        query = text("""
            SELECT nm_id, category_name, product_name, product_url
            FROM products
        """)

        with get_db_engine().connect() as conn:
            df = pd.read_sql(query, conn)

        if not df.empty:
            df["nm_id"] = df["nm_id"].astype(str).str.strip()
            df["category_name"] = df["category_name"].fillna("Без категории").astype(str).str.strip()
            df["product_name"] = df["product_name"].fillna("").astype(str).str.strip()
            df["product_url"] = df["product_url"].fillna("").astype(str).str.strip()

            df.loc[df["product_name"] == "", "product_name"] = "Товар " + df["nm_id"]
            df.loc[df["category_name"] == "", "category_name"] = "Без категории"

        return df

    except Exception as e:
        st.error(f"Ошибка при загрузке списка товаров: {e}")
        return pd.DataFrame(columns=["nm_id", "category_name", "product_name", "product_url"])


def get_product_summary(nm_id):
    """Получает полную аналитику товара из базы данных."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT
            summary_text,
            chart_html
        FROM
            product_summary
        WHERE
            nm_id = %s
        """

        cursor.execute(query, (str(nm_id),))
        result = cursor.fetchone()

        conn.close()

        if result:
            return {
                "summary_text": result[0],
                "chart_html": result[1]
            }

        return None

    except Exception as e:
        st.error(f"Ошибка при получении аналитики: {str(e)}")
        return None


def save_uploaded_analysis_to_db(analyzed_df, product_summaries):
    """Сохраняет товары, отзывы и сводную аналитику в PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for item in product_summaries:
            nm_id = item["nm_id"]

            cursor.execute("SELECT 1 FROM products WHERE nm_id = %s", (nm_id,))

            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE products
                    SET category_name = %s,
                        product_name = %s,
                        product_url = %s
                    WHERE nm_id = %s
                    """,
                    (
                        item["category_name"],
                        item["product_name"],
                        item["product_url"],
                        nm_id
                    )
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO products (nm_id, category_name, product_name, product_url)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        nm_id,
                        item["category_name"],
                        item["product_name"],
                        item["product_url"]
                    )
                )

            cursor.execute("SELECT 1 FROM product_summary WHERE nm_id = %s", (nm_id,))

            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE product_summary
                    SET summary_text = %s,
                        chart_html = %s
                    WHERE nm_id = %s
                    """,
                    (
                        item["summary_text"],
                        item["chart_html"],
                        nm_id
                    )
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO product_summary (nm_id, summary_text, chart_html)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        nm_id,
                        item["summary_text"],
                        item["chart_html"]
                    )
                )

            # Для загруженного товара заменяем старые отзывы новыми,
            # чтобы аналитика не дублировалась.
            cursor.execute("DELETE FROM reviews WHERE nm_id = %s", (nm_id,))

        for _, row in analyzed_df.iterrows():
            cursor.execute(
                """
                INSERT INTO reviews (nm_id, review_text, sentiment, confidence)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    str(row["nm_id"]),
                    str(row["review_text"]),
                    int(row["sentiment"]),
                    float(row["confidence"])
                )
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()